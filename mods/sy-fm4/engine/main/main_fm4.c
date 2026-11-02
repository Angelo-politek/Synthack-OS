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
 * The SYN pages come from syn-pages (mods/syn-pages): fm4m_boot registers machine 4 (key: SY TONE's TUNE on
 * knob A) with two pages. Page 1/2 is SY TONE's parameters, renamed and ordered as page 2/2 (ratio, level,
 * decay per column); page 2/2 answers with its own descriptors; turning ALGO draws the algorithm.
 *
 * The descriptors are eight of the table's unused "Error" placeholders
 * (0x4022d83c, 0x34 bytes each), rewritten by patch/s3patch.py from
 * fm4m_records below. Their RAM-side info (0x41ba0a24, 0x54 bytes each:
 * knob scaling, formatter and icon callbacks, all stateless) is copied from
 * parameters of the same kind on first use (DET from SY DUAL VCO's DET:
 * the same range, centre and display).
 */
#include <stdint.h>
#include "synpages.h"

typedef uint32_t u32;

#define ORIG_SRC_BC    ((u32 (*)(void *, u32))0x40044c54)
#define REC_INFO(r)    ((u32 *)(0x41ba0a24 + (r) * 0x54))
#define INFO_LONGS     (0x54 / 4)

/* SY TONE's descriptors (machine 4): TUNE RATIO MOD FDBK MENV PNCH OVER DEC */
#define R_TUNE  190
#define R_RATIO 191
#define R_MOD   192
#define R_FDBK  193
#define R_MENV  194
#define R_PNCH  195
#define R_OVER  196
#define R_DEC   197
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

/* Page 1/2's names, written by the patcher into SY TONE's descriptors 190..197 (SY FM4 takes its machine
 * slot): operator 2 is SY TONE's modulator, operator 1 the carrier. */
__attribute__((used)) const char *const fm4m_names[8][2] = {
    {"Tune", "TUNE"}, {"Op2 Ratio", "RAT2"}, {"Op2 Level", "LEV2"}, {"Feedback", "FDBK"},
    {"Op2 Decay", "DEC2"}, {"Pitch Punch", "PNCH"}, {"Overdrive", "OVER"}, {"Op1 Decay", "DEC1"}};

/* Knobs A..H and LEVEL. Page 1/2: operator 2 on the top row; page 2/2: operator 3 on the top row, operator 4
 * under it; on both, a column is one kind (ratio, level, decay). */
static const u32 page1[9] = {R_TUNE, R_RATIO, R_MOD, R_MENV,
                             R_PNCH, R_FDBK, R_OVER, R_DEC, R_LEVEL};
static const u32 page2[9] = {R_ALGO, R_RAT3, R_LEV3, R_DEC3,
                             R_DET,  R_RAT4, R_LEV4, R_DEC4, R_LEVEL};
/* Where each new descriptor takes its knob/formatter/icon info from. */
static const u32 info_from[PAGE2_N] = {R_MOD, R_RATIO, R_MOD, R_MENV,
                                       R_RATIO, R_MOD, R_MENV, R_DUAL_DET};

/* ---- algorithms, drawn as SY FM4 routes them (engine/fm4.c): operators in boxes, modulation as lines into
 * the box modulated, carriers dotted up to the output, feedback as a hook under the box. */
typedef struct {
    uint8_t ops;            /* operators shown: 2 (SY TONE) or 4 */
    uint8_t at[4][2];       /* operator 1..4: column, row (row 0 at the top) */
    uint8_t edges;
    uint8_t edge[4][2];     /* modulator -> modulated */
    uint8_t carriers;       /* bit k = operator k + 1 */
    uint8_t fb;             /* operator with feedback, 0 none; 5 = ring (1 back to 4) */
} algo_t;

static const algo_t algos[12] = {
    {2, {{1, 0}, {1, 1}}, 1, {{2, 1}}, 1, 2},
    {4, {{1, 0}, {1, 1}, {1, 2}, {1, 3}}, 3, {{2, 1}, {3, 2}, {4, 3}}, 1, 4},
    {4, {{1, 0}, {1, 1}, {0, 2}, {2, 2}}, 3, {{2, 1}, {3, 2}, {4, 2}}, 1, 4},
    {4, {{1, 0}, {0, 1}, {0, 2}, {2, 1}}, 3, {{2, 1}, {3, 2}, {4, 1}}, 1, 4},
    {4, {{1, 0}, {0, 1}, {2, 1}, {2, 2}}, 3, {{2, 1}, {3, 1}, {4, 3}}, 1, 4},
    {4, {{0, 0}, {0, 1}, {2, 0}, {2, 1}}, 2, {{2, 1}, {4, 3}}, 5, 4},
    {4, {{0, 0}, {1, 0}, {2, 0}, {1, 1}}, 3, {{4, 1}, {4, 2}, {4, 3}}, 7, 4},
    {4, {{0, 0}, {1, 0}, {2, 0}, {2, 1}}, 1, {{4, 3}}, 7, 4},
    {4, {{0, 0}, {1, 0}, {2, 0}, {3, 0}}, 0, {{0, 0}}, 15, 4},
    {4, {{0, 0}, {2, 0}, {1, 1}, {1, 2}}, 3, {{3, 1}, {3, 2}, {4, 3}}, 3, 4},
    {4, {{1, 0}, {0, 1}, {2, 1}, {1, 2}}, 4, {{2, 1}, {3, 1}, {4, 2}, {4, 3}}, 1, 4},
    {4, {{1, 0}, {1, 1}, {1, 2}, {1, 3}}, 3, {{2, 1}, {3, 2}, {4, 3}}, 1, 5},
};

static const uint8_t digit[10][5] = {   /* 3x5, bit 2 = left */
    {7, 5, 5, 5, 7}, {2, 6, 2, 2, 7}, {6, 1, 2, 4, 7}, {6, 1, 2, 1, 6}, {5, 5, 7, 1, 1},
    {7, 4, 6, 1, 6}, {3, 4, 7, 5, 7}, {7, 1, 2, 2, 2}, {7, 5, 7, 5, 7}, {7, 5, 7, 1, 6}};

static void glyph(void *bm, int x, int y, int d, int scale) {
    for (int r = 0; r < 5; r++)
        for (int c = 0; c < 3; c++)
            if (digit[d][r] >> (2 - c) & 1)
                for (int i = 0; i < scale; i++)
                    for (int j = 0; j < scale; j++)
                        sp_px(bm, x + c * scale + i, y + r * scale + j, 1);
}

static void number(void *bm, int x, int y, u32 n, int scale) {
    if (n >= 10) {
        glyph(bm, x, y, 1, scale);
        x += 4 * scale;
        n -= 10;
    }
    glyph(bm, x, y, (int)n, scale);
}

#define BOX 9
#define COL(ox, i) ((ox) + 2 + (i) * 11)
#define ROW(oy, j) ((oy) + 8 + (j) * 12)

static void draw_algo(void *bm, int ox, int oy, u32 n) {
    const algo_t *a = &algos[n < 12 ? n : 0];
    int lo = 999, hi = -1;
    for (int k = 0; k < a->ops; k++) {
        int x = COL(ox, a->at[k][0]), y = ROW(oy, a->at[k][1]);
        sp_hline(bm, x + 1, x + BOX - 2, y, 1);
        sp_hline(bm, x + 1, x + BOX - 2, y + BOX - 1, 1);
        sp_vline(bm, x, y + 1, y + BOX - 2, 1);
        sp_vline(bm, x + BOX - 1, y + 1, y + BOX - 2, 1);
        glyph(bm, x + 3, y + 2, k + 1, 1);
        if (a->carriers >> k & 1) {
            sp_vline(bm, x + 4, oy + 4, y - 1, 2);
            lo = x + 4 < lo ? x + 4 : lo;
            hi = x + 4 > hi ? x + 4 : hi;
        }
    }
    for (int e = 0; e < a->edges; e++) {
        const uint8_t *m = a->at[a->edge[e][0] - 1], *t = a->at[a->edge[e][1] - 1];
        int xa = COL(ox, m[0]) + 4, xb = COL(ox, t[0]) + 4;
        if (m[1] > t[1]) {                      /* modulator below: up, across, into the bottom of the box */
            int ym = ROW(oy, m[1]) - 2;
            sp_vline(bm, xa, ym, ROW(oy, m[1]) - 1, 1);
            sp_hline(bm, xa, xb, ym, 1);
            sp_vline(bm, xb, ROW(oy, t[1]) + BOX, ym, 1);
        } else {                                /* same row: side to side */
            int l = m[0] < t[0] ? m[0] : t[0], r = m[0] < t[0] ? t[0] : m[0];
            sp_hline(bm, COL(ox, l) + BOX, COL(ox, r) - 1, ROW(oy, m[1]) + 4, 1);
        }
    }
    int mid = (lo + hi) / 2;                    /* output: an arrow up, over the carriers */
    if (hi > lo) {
        sp_hline(bm, lo, hi, oy + 4, 1);
        sp_vline(bm, mid, oy + 1, oy + 4, 1);
    }
    sp_px(bm, mid, oy, 1);
    sp_hline(bm, mid - 1, mid + 1, oy + 1, 1);
    sp_hline(bm, mid - 2, mid + 2, oy + 2, 1);
    if (a->fb == 5) {                           /* ring: operator 1 back to 4, on the left */
        int x = COL(ox, 1) - 2;
        sp_vline(bm, x, ROW(oy, 0) + 4, ROW(oy, 3) + 4, 1);
        sp_hline(bm, x, x + 1, ROW(oy, 0) + 4, 1);
        sp_hline(bm, x, x + 1, ROW(oy, 3) + 4, 1);
    } else if (a->fb) {                         /* feedback: a hook from under the box back into its left side */
        int x = COL(ox, a->at[a->fb - 1][0]), y = ROW(oy, a->at[a->fb - 1][1]);
        sp_vline(bm, x - 2, y + 4, y + 11, 1);
        sp_hline(bm, x - 2, x + 4, y + 11, 1);
        sp_vline(bm, x + 4, y + BOX, y + 11, 1);
        sp_hline(bm, x - 2, x - 1, y + 4, 1);
    }
}

/* the ALGO box: the algorithm's number, large (knob graphic: std::function(value, bitmap, x, y); the graphic
 * is 26 x 16 with its bottom left corner at x, y counted from the bottom of the screen) */
static void algo_gfx(const void *fn, int32_t value, void *bm, int32_t x, int32_t y) {
    (void)fn;
    u32 n = (u32)(value + 0x80) >> 8;
    n = n > 11 ? 11 : n;
    int top = *(int32_t *)((uint8_t *)bm + 8) - 16 - y;
    number(bm, x + (n >= 10 ? 6 : 10), top + 3, n, 2);
}

static int nothing(void *dst, const void *src, int op) {
    (void)dst;
    (void)src;
    (void)op;
    return 0;
}

static const void *const algo_gfx_proto[4] __attribute__((aligned(4))) = {0, 0, (const void *)nothing,
                                                                          (const void *)algo_gfx};

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
    for (int k = 0; k < 4; k++)                 /* +36: the knob graphic */
        REC_INFO(R_ALGO)[9 + k] = (u32)algo_gfx_proto[k];
    ready = 1;
}

static u32 fm4_record(void *view, u32 page, u32 knob) {
    init_once();
    if (knob < 9)
        return page == 1 ? page2[knob] : page1[knob];
    return ORIG_SRC_BC(view, knob);
}

static const char *fm4_title(void *view, u32 page) {
    (void)view;
    return page == 1 ? "SY FM4 2/2" : "SY FM4 1/2";
}

/* Turning ALGO (knob A on page 2/2): the algorithm at full size over columns A and B. */
#define SEQ_VALUES ((volatile uint16_t *)0x800021b0)
#define ACTIVE_TRACK ((int32_t (*)(void *))0x4001ff74)
static void fm4_draw(void *view, void *bm, u32 page) {
    if (page != 1 || SP_HIGHLIGHT(view, 0) == 0)
        return;
    int32_t t = ACTIVE_TRACK((void *)SP_V(view, 116));
    if (t < 0 || t > 7)
        return;
    u32 n = (u32)(SEQ_VALUES[0xe + t * 0x47 + PAGE2_FIRST] + 0x80) >> 8;
    sp_clear(bm, 16, 0, 72, 64);
    draw_algo(bm, 22, 3, n > 11 ? 11 : n);
    number(bm, 17, 2, n > 11 ? 11 : n, 1);
}

static const sp_machine_t fm4_pages = {R_TUNE, 2, fm4_record, fm4_title, fm4_draw};

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
    sp_register(&fm4_pages);
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

__attribute__((optimize("O2"))) void fm4m_dma_wait(void) {
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
const void *const fm4m_entries[2] = {(const void *)fm4m_records, (const void *)fm4m_names};
