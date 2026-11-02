/* SY FM4 on the Syntakt's main CPU.
 *
 * Ported to MAIN OS 1.42 for SyntHack (mods/sy-fm4/README.md): addresses moved with tools/build/osmap.py and
 * checked against the 1.40A hashes of the original patcher; page 2/2 on descriptors 254..261 (Digitakt
 * MIDI-track "CC1..CC8 Value", no page on the Syntakt) instead of the MIDI CC placeholders 1-5, 12-14;
 * code in the SyntHack mod area, tables filled from its boot list. Original: Rxuting/sy-fm4 (MIT).
 * FUN_xxxxxxxx names below are the 1.40A functions of the original notes.
 *
 * SY FM4 takes SY TONE's machine slot (id 4) and keeps its SYN page as page
 * 1/2. Page 2/2 adds eight parameters on track logical indices 0x36..0x3d,
 * which every track has room for (the sound, the pattern's lock table and
 * the sequencer's per-track values are 0x47 wide; tracks use 0..0x35).
 *
 * The SYN page is a SourcePageView: its knob -> descriptor lookup (vtable
 * slot 47, FUN_40043f9c) reads the machine's page object, one per machine.
 * The page view base already cycles through its page list on a second press
 * of its key (FUN_4003b8a4: index +0x90 = (index + 1) % pages). So for
 * SY FM4 the view gets a two-entry page list, and on page index 1 the lookup
 * answers with page 2/2's descriptors.
 *
 * The descriptors are eight of the table's unused "Error" placeholders
 * (0x4022d83c, 0x34 bytes each), rewritten by patch/s3patch.py from
 * fm4m_records below. Their RAM-side info (0x41ba0a24, 0x54 bytes each:
 * knob scaling, formatter and icon callbacks, all stateless) is copied from
 * parameters of the same kind on first use (DET from SY DUAL VCO's DET:
 * the same range, centre and display).
 */
#include <stdint.h>

typedef uint32_t u32;

#define ORIG_SRC_BC    ((u32 (*)(void *, u32))0x40044c54)
/* The OS returns pointers in d0; this compiler (m68k-linux ABI) reads a pointer result from a0. */
#define FW_MALLOC      ((u32 (*)(u32))0x4010394c)
#define FW_FREE        ((void (*)(void *))0x40103958)
#define REC_INFO(r)    ((u32 *)(0x41ba0a24 + (r) * 0x54))
#define INFO_LONGS     (0x54 / 4)

/* SY TONE's descriptors (machine 4): TUNE RATIO MOD FDBK MENV PNCH OVER DEC */
#define R_TUNE  190
#define R_RATIO 191
#define R_MOD   192
#define R_MENV  194
#define R_OVER  196
#define R_LEVEL 10
#define R_DUAL_DET 369     /* SY DUAL VCO "Osc 2 Detune" */

/* The placeholders page 2/2 takes over, in knob order A..H. */
#define R_ALGO 254
#define R_RAT3 255
#define R_LEV3 256
#define R_DEC3 257
#define R_RAT4 258
#define R_LEV4 259
#define R_DEC4 260
#define R_DET  261

#define PAGE2_FIRST 0x36
#define PAGE2_N 8

#define V(view, off) (*(volatile u32 *)((uint8_t *)(view) + (off)))
#define PAGES_BEGIN 0x7c
#define PAGES_END   0x80
#define PAGES_CAP   0x84
#define PAGE_INDEX  0x90

typedef struct {
    u32 owner, lix, min, max, def, r5, midi, cc, id, flags;
    const char *longname, *group, *shortname;
} record_t;

static const char group[] = "SYF4";

/* Copied into the descriptor table by the patcher. owner 0xffffffff keeps
 * them out of the per-machine index tables (FUN_400a4ef0), which only have
 * room for logical indices 0x11..0x1a; midi 0xffffffff = no CC/NRPN. */
__attribute__((used)) const record_t fm4m_records[PAGE2_N] = {
    {0xffffffff, 0x36, 0, 0x0b00, 0,      0, 0xffffffff, 0xffffffff, R_ALGO, 0xe00, "Algorithm", group, "ALGO"},
    {0xffffffff, 0x37, 0, 0x7f00, 0x0400, 0, 0xffffffff, 0xffffffff, R_RAT3, 0xe00, "Op3 Ratio", group, "RAT3"},
    {0xffffffff, 0x38, 0, 0x7f00, 0,      0, 0xffffffff, 0xffffffff, R_LEV3, 0xe00, "Op3 Level", group, "LEV3"},
    {0xffffffff, 0x39, 0, 0x7f00, 0x4c00, 0, 0xffffffff, 0xffffffff, R_DEC3, 0xe00, "Op3 Decay", group, "DEC3"},
    {0xffffffff, 0x3a, 0, 0x7f00, 0x0400, 0, 0xffffffff, 0xffffffff, R_RAT4, 0xe00, "Op4 Ratio", group, "RAT4"},
    {0xffffffff, 0x3b, 0, 0x7f00, 0,      0, 0xffffffff, 0xffffffff, R_LEV4, 0xe00, "Op4 Level", group, "LEV4"},
    {0xffffffff, 0x3c, 0, 0x7f00, 0x4c00, 0, 0xffffffff, 0xffffffff, R_DEC4, 0xe00, "Op4 Decay", group, "DEC4"},
    /* +-16 semitones around 0x4000, fine steps: SY DUAL VCO's DET */
    {0xffffffff, 0x3d, 0x3000, 0x5000, 0x4000, 1, 0xffffffff, 0xffffffff, R_DET, 0xe00, "Detune", group, "DET"},
};
__attribute__((used)) const u32 fm4m_record_index[PAGE2_N] = {
    R_ALGO, R_RAT3, R_LEV3, R_DEC3, R_RAT4, R_LEV4, R_DEC4, R_DET};

/* Page 2/2, knobs A..H and LEVEL: operator 3 on the top row, operator 4
 * under it on the bottom row, each column one kind (ratio, level, decay). */
static const u32 page2[9] = {R_ALGO, R_RAT3, R_LEV3, R_DEC3,
                             R_DET,  R_RAT4, R_LEV4, R_DEC4, R_LEVEL};
/* Where each new descriptor takes its knob/formatter/icon info from. */
static const u32 info_from[PAGE2_N] = {R_MOD, R_RATIO, R_MOD, R_MENV,
                                       R_RATIO, R_MOD, R_MENV, R_DUAL_DET};

static int ready;

static void init_once(void) {
    if (ready)
        return;
    for (int i = 0; i < PAGE2_N; i++) {
        const u32 *src = REC_INFO(info_from[i]);
        u32 *dst = REC_INFO(fm4m_record_index[i]);
        for (int k = 0; k < INFO_LONGS; k++)
            dst[k] = src[k];
    }
    ready = 1;
}

/* SY FM4's page (machine 4's page object) answers SY TONE's TUNE on knob A,
 * whichever sound the view shows (the track's, or a held trig's). */
static int is_fm4(void *view) {
    return ORIG_SRC_BC(view, 0) == R_TUNE;
}

/* Give the view two pages while it shows SY FM4, one otherwise. */
static void fit_pages(void *view, int fm4) {
    u32 *begin = (u32 *)V(view, PAGES_BEGIN);
    u32 n = (V(view, PAGES_END) - (u32)begin) / 4;
    if (begin == 0 || n == 0)
        return;
    if (fm4 && n == 1) {
        if (V(view, PAGES_CAP) - (u32)begin < 8) {
            u32 *b = (u32 *)FW_MALLOC(8);
            if (b == 0)
                return;
            b[0] = begin[0];
            FW_FREE(begin);
            begin = b;
            V(view, PAGES_BEGIN) = (u32)b;
            V(view, PAGES_CAP) = (u32)(b + 2);
        }
        begin[1] = begin[0];
        V(view, PAGES_END) = (u32)(begin + 2);
    } else if (!fm4 && n == 2) {
        V(view, PAGES_END) = (u32)(begin + 1);
        V(view, PAGE_INDEX) = 0;
    }
}

/* SourcePageView vtable slot 47: knob (0..8) -> descriptor. */
u32 fm4m_src_record(void *view, u32 knob) {
    init_once();
    int fm4 = is_fm4(view);
    fit_pages(view, fm4);
    if (fm4 && V(view, PAGE_INDEX) == 1 && knob < 9)
        return page2[knob];
    return ORIG_SRC_BC(view, knob);
}

/* SourcePageView vtable slot 19: the page's name (the toast on a page key), returned as a std::string by
 * value: the caller passes the string to construct in a0 and gets it back in d0 (0x40044894 builds it with
 * the constructor 0x401bf31e(string, text, allocator)). fm4m_src_title wraps fm4m_title_text: SY FM4's name,
 * or 0 for the stock function. */
const char *fm4m_title_text(void *view) {
    if (is_fm4(view))
        return V(view, PAGE_INDEX) == 1 ? "SY FM4 2/2" : "SY FM4 1/2";
    return 0;
}

void fm4m_src_title(void);
__asm__(
    "    .text\n"
    "    .globl fm4m_src_title\n"
    "fm4m_src_title:\n"
    "    move.l %a0,-(%sp)\n"           /* string to construct */
    "    move.l 8(%sp),-(%sp)\n"        /* view */
    "    jsr fm4m_title_text\n"
    "    addq.l #4,%sp\n"
    "    movea.l (%sp)+,%a0\n"
    "    tst.l %d0\n"
    "    bne.s 1f\n"
    "    jmp 0x40044894\n"              /* stock title: a0 and the stack as on entry */
    "1:  move.l %a0,-(%sp)\n"
    "    pea (%sp)\n"                   /* allocator (empty) */
    "    move.l %d0,-(%sp)\n"
    "    move.l %a0,-(%sp)\n"
    "    jsr 0x401bf31e\n"
    "    lea 12(%sp),%sp\n"
    "    move.l (%sp)+,%d0\n"
    "    rts\n");

/* ---- storage: logical index <-> storage slot ------------------------------
 *
 * MAIN OS maps a track's logical indices 0..0x35 to storage slots through
 * 0x40234344 (54 entries) and back through 0x4023441c, which follows it, so
 * neither can grow in place. These copies run to 0x46: page 2/2's indices
 * map to themselves for sounds (soundStorage has 72 slots, 54 used, so slots
 * 0x36..0x3d are spare and a stock OS skips them), and to lock lane ids
 * 0x50..0x57 for pattern locks: a stock OS drops lanes above 0x46, where an
 * id of 0x36 would have loaded as a lock on logical index 0 (trig note).
 * Filled at boot, before MAIN OS reads anything (fm4m_boot, from the mod area's boot list).
 */
#define LIX2PHYS ((const u32 *)0x40234344)
#define PHYS2LIX ((const u32 *)0x4023441c)
#define FX_PHYS2LIX ((const u32 *)0x40234230)
#define STOCK_LIX 0x36
#define ALL_LIX 0x47
#define LANE_FIRST 0x50

u32 fm4m_sound_l2p[ALL_LIX];
u32 fm4m_sound_p2l[ALL_LIX];
u32 fm4m_lane_of_lix[ALL_LIX];

void fm4m_boot(void) {
    for (int i = 0; i < ALL_LIX; i++) {
        int stock = i < STOCK_LIX;
        fm4m_sound_l2p[i] = stock ? LIX2PHYS[i] : (u32)i;
        fm4m_sound_p2l[i] = stock ? PHYS2LIX[i] : (u32)i;
        if (stock)
            fm4m_lane_of_lix[i] = LIX2PHYS[i];
        else if (i < PAGE2_FIRST + PAGE2_N)
            fm4m_lane_of_lix[i] = LANE_FIRST + (i - PAGE2_FIRST);
        else
            fm4m_lane_of_lix[i] = 0xff;
    }
}

/* Replaces FUN_400a5d5e (storage slot / lock lane id -> logical index, per
 * track; 12 is the FX track). Same answers for every id it took before. */
u32 fm4m_phys_to_lix(u32 track, u32 phys) {
    if (track > 12)
        return 0;
    if (track == 12)
        return phys < 0x45 ? FX_PHYS2LIX[phys] : 0;
    if (phys < STOCK_LIX)
        return PHYS2LIX[phys];
    if (phys >= LANE_FIRST && phys < LANE_FIRST + PAGE2_N)
        return PAGE2_FIRST + (phys - LANE_FIRST);
    return 0;
}

/* Replaces the deserialiser's slot loop (0x400a706a..0x400a708c in
 * FUN_400a6022, called through fm4m_load_shim with its a2/a3): storage
 * slots 0..0x3d to the sound's logical indices. A sound saved by a stock OS
 * has zeros in page 2/2's slots, which no SY FM4 sound has (DET is never
 * below 0x3000): those get page 2/2's defaults, so an old SY TONE sound
 * opens as SY FM4 in its SY TONE algorithm with DET centred. */
void fm4m_load_params(uint8_t *sound, const uint8_t *storage) {
    volatile uint16_t *lix = (volatile uint16_t *)(sound + 10 * 2);
    const uint16_t *slot = (const uint16_t *)(storage + 0x1c);
    for (int p = 0; p < PAGE2_FIRST + PAGE2_N; p++)
        lix[fm4m_sound_p2l[p]] = slot[p];
    int empty = 1;
    for (int k = 0; k < PAGE2_N; k++)
        if (lix[PAGE2_FIRST + k])
            empty = 0;
    if (empty)
        for (int k = 0; k < PAGE2_N; k++)
            lix[PAGE2_FIRST + k] = (uint16_t)fm4m_records[k].def;
}

/* Runs where FUN_400a4ef0 (the descriptor index tables) finishes, in place
 * of its `move.l d0,0x43bdf44c`: enter page 2/2's descriptors in the
 * per-logical-index tables a sound's defaults come from (FUN_400a5490 for
 * logical indices outside 0x11..0x1a; 0x43bdf7fc and 0x43bdf6e0 by machine
 * kind), so a new sound starts with them (FUN_400b23f8). */
#define LIX_TABLE_A ((volatile u32 *)0x43bdf7fc)
#define LIX_TABLE_B ((volatile u32 *)0x43bdf6e0)
u32 fm4m_index_done(void) {
    for (int k = 0; k < PAGE2_N; k++) {
        LIX_TABLE_A[PAGE2_FIRST + k] = fm4m_record_index[k];
        LIX_TABLE_B[PAGE2_FIRST + k] = fm4m_record_index[k];
    }
    *(volatile u32 *)0x43bdf44c = 1;
    return 1;
}

__asm__(
    "    .text\n"
    "    .globl fm4m_load_shim\n"
    "fm4m_load_shim:\n"
    "    move.l %a3,-(%sp)\n"
    "    move.l %a2,-(%sp)\n"
    "    jsr fm4m_load_params\n"
    "    addq.l #8,%sp\n"
    "    rts\n");

/* ---- page 2/2 to the second CPU ---------------------------------------------
 *
 * Replaces FUN_400a10da, the render's wait for eDMA 47 before it starts the
 * frame transfer (and the voice transfer). After the wait it copies each
 * synth track's page 2/2 values, with this block's locks applied, from the
 * sequencer's per-track values (0x800021b0 + (0xe + track * 0x47 + lix) * 2,
 * where FUN_40096958 writes locks and FUN_40096804 restores them) to the
 * shared RAM at FM4_SHARED: 16 bytes a voice, which the voice engine reads.
 * 0x5b0..0x800 is past the frame (0x1b0) and the voice output (0x400) and
 * below the boot-time upload window (0x800..0x1000).
 */
#define FM4_SHARED 0x700
#define SEQ_VALUES ((volatile uint16_t *)0x800021b0)
#define SHARED_MAIN ((volatile uint16_t *)(0x10000000 + FM4_SHARED))
#define DMA_PENDING (*(volatile uint8_t *)0x43bde73c)
#define TCD47_CSR (*(volatile uint16_t *)0xfc0455fe)

void fm4m_dma_wait(void) {
    if (DMA_PENDING) {
        while (!(TCD47_CSR & 0x80))     /* DONE */
            ;
        DMA_PENDING = 0;
    }
    for (int t = 0; t < 8; t++)
        for (int k = 0; k < PAGE2_N; k++)
            SHARED_MAIN[t * 8 + k] = SEQ_VALUES[0xe + t * 0x47 + PAGE2_FIRST + k];
}

__attribute__((section(".entries"), used))
void *const fm4m_entries[2] = {(void *)fm4m_src_record, (void *)fm4m_src_title};
