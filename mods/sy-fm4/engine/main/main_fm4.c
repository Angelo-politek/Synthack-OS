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
 * knob A) with three pages. Page 1/3 is SY TONE's parameters, renamed (operator 2 on the bottom row); page 2/3
 * answers with its own descriptors (operator 3 on the top row, operator 4 under it); page 3/3 is ALGO and the
 * algorithm drawn.
 *
 * Page 2/3's values live in xparams' extra indices 0x36..0x3d (mods/xparams: saved, p-locked, copied to shared RAM
 * 0x700 for the voice engine every block).
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
#include "xparams.h"

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
 * room for logical indices 0x11..0x1a; midi 0xffffffff = no CC/NRPN; flags 0, as every stock descriptor
 * without an owner: not in the LFO and modulation destination lists (they would show on every track, under "ERR",
 * and the OS's modulation does not reach these indices). */
__attribute__((used)) const record_t fm4m_records[PAGE2_N] = {
    {0xffffffff, 0x36, 0, 0x0b00, 0,      0, 0xffffffff, 0xffffffff, R_ALGO, 0, "Algorithm", group, "ALGO"},
    {0xffffffff, 0x37, 0, 0x7f00, 0x0400, 0, 0xffffffff, 0xffffffff, R_RAT3, 0, "Op3 Ratio", group, "RAT3"},
    {0xffffffff, 0x38, 0, 0x7f00, 0,      0, 0xffffffff, 0xffffffff, R_LEV3, 0, "Op3 Level", group, "LEV3"},
    {0xffffffff, 0x39, 0, 0x7f00, 0x4c00, 0, 0xffffffff, 0xffffffff, R_DEC3, 0, "Op3 Decay", group, "DEC3"},
    {0xffffffff, 0x3a, 0, 0x7f00, 0x0400, 0, 0xffffffff, 0xffffffff, R_RAT4, 0, "Op4 Ratio", group, "RAT4"},
    {0xffffffff, 0x3b, 0, 0x7f00, 0,      0, 0xffffffff, 0xffffffff, R_LEV4, 0, "Op4 Level", group, "LEV4"},
    {0xffffffff, 0x3c, 0, 0x7f00, 0x4c00, 0, 0xffffffff, 0xffffffff, R_DEC4, 0, "Op4 Decay", group, "DEC4"},
    /* +-16 semitones around 0x4000, fine steps: SY DUAL VCO's DET */
    {0xffffffff, 0x3d, 0x3000, 0x5000, 0x4000, 1, 0xffffffff, 0xffffffff, R_DET, 0, "Detune", group, "DET"},
};
__attribute__((used)) const u32 fm4m_record_index[PAGE2_N] = {
    R_ALGO, R_RAT3, R_LEV3, R_DEC3, R_RAT4, R_LEV4, R_DEC4, R_DET};

/* Page 1/2's names, written by the patcher into SY TONE's descriptors 190..197 (SY FM4 takes its machine
 * slot): operator 2 is SY TONE's modulator, operator 1 the carrier. */
__attribute__((used)) const char *const fm4m_names[8][2] = {
    {"Tune", "TUNE"}, {"Op2 Ratio", "RAT2"}, {"Op2 Level", "LEV2"}, {"Feedback", "FDBK"},
    {"Op2 Decay", "DEC2"}, {"Pitch Punch", "PNCH"}, {"Overdrive", "OVER"}, {"Op1 Decay", "DEC1"}};

/* Knobs A..H and LEVEL. Page 1/3: TUNE PNCH DEC1 OVER / FDBK and operator 2 (ratio, level, decay); page 2/3:
 * operator 3 and DET / operator 4 and ALGO. Page 3/3: ALGO, its drawing over knobs B..H. */
static const u32 page1[9] = {R_TUNE, R_PNCH, R_DEC,  R_OVER,
                             R_FDBK, R_RATIO, R_MOD, R_MENV, R_LEVEL};
static const u32 page2[9] = {R_RAT3, R_LEV3, R_DEC3, R_DET,
                             R_RAT4, R_LEV4, R_DEC4, R_ALGO, R_LEVEL};
static const u32 page3[9] = {R_ALGO, 0, 0, 0, 0, 0, 0, 0, R_LEVEL};
/* Where each new descriptor takes its knob/formatter/icon info from. */
static const u32 info_from[PAGE2_N] = {R_MOD, R_RATIO, R_MOD, R_MENV,
                                       R_RATIO, R_MOD, R_MENV, R_DUAL_DET};

/* ---- algorithms, drawn as SY FM4 routes them (engine/fm4.c): operators in boxes, modulation as lines into
 * the box modulated, carriers dotted up to the output, feedback as a hook on the right of the box. */
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
#define ROW(oy, j) ((oy) + 5 + (j) * 12)

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
            sp_vline(bm, x + 4, oy + 3, y - 1, 2);
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
        sp_hline(bm, lo, hi, oy + 3, 1);
        sp_vline(bm, mid, oy + 1, oy + 3, 1);
    }
    sp_px(bm, mid, oy, 1);
    sp_hline(bm, mid - 1, mid + 1, oy + 1, 1);
    sp_hline(bm, mid - 2, mid + 2, oy + 2, 1);
    if (a->fb == 5) {                           /* ring: operator 1 back to 4, on the left */
        int x = COL(ox, 1) - 2;
        sp_vline(bm, x, ROW(oy, 0) + 4, ROW(oy, 3) + 4, 1);
        sp_hline(bm, x, x + 1, ROW(oy, 0) + 4, 1);
        sp_hline(bm, x, x + 1, ROW(oy, 3) + 4, 1);
    } else if (a->fb) {                         /* feedback: a loop out of the right side and back in */
        int x = COL(ox, a->at[a->fb - 1][0]) + BOX, y = ROW(oy, a->at[a->fb - 1][1]);
        sp_hline(bm, x, x + 1, y + 2, 1);
        sp_vline(bm, x + 1, y + 2, y + 6, 1);
        sp_hline(bm, x, x + 1, y + 6, 1);
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
    if (knob < 9) {
        u32 id = page == 2 ? page3[knob] : page == 1 ? page2[knob] : page1[knob];
        if (id == R_ALGO)                       /* its number is the icon, the name stays under it */
            SP_HIGHLIGHT(view, knob) = 0;
        return id;
    }
    return ORIG_SRC_BC(view, knob);
}

static const char *fm4_title(void *view, u32 page) {
    (void)view;
    return page == 2 ? "SY FM4 3/3" : page == 1 ? "SY FM4 2/3" : "SY FM4 1/3";
}

/* Page 3/3: the track's algorithm over knobs B..H (empty there), under the line the OS writes a turned value on;
 * knob E's empty box cleared. */
#define SEQ_VALUES ((volatile uint16_t *)0x800021b0)
#define ACTIVE_TRACK ((int32_t (*)(void *))0x4001ff74)
static void fm4_draw(void *view, void *bm, u32 page) {
    if (page != 2)
        return;
    int32_t t = ACTIVE_TRACK((void *)SP_V(view, 116));
    if (t < 0 || t > 7)
        return;
    u32 n = (u32)(SEQ_VALUES[0xe + t * 0x47 + PAGE2_FIRST] + 0x80) >> 8;
    sp_clear(bm, 44, 13, 128, 64);
    sp_clear(bm, 16, 38, 44, 64);               /* knob E's empty box */
    draw_algo(bm, 62, 13, n > 11 ? 11 : n);
}

static const sp_machine_t fm4_pages = {R_TUNE, 3, fm4_record, fm4_title, fm4_draw};

/* ---- sounds from a stock OS: page 2/3's defaults (xparams loads the extra indices, calls this when they are zero)
 *
 * A sound saved by a stock OS has zeros in the extra indices, which no SY FM4 sound has (DET is never below
 * 0x3000): those get page 2/3's defaults, so an old SY TONE sound opens as SY FM4 in its SY TONE algorithm with DET
 * centred. */
static void fm4m_empty(volatile uint16_t *lix) {
    for (int k = 0; k < PAGE2_N; k++)
        lix[PAGE2_FIRST + k] = (uint16_t)fm4m_records[k].def;
}

void fm4m_boot(void) {
    sp_register(&fm4_pages);
    xp_on_empty(fm4m_empty);
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

__attribute__((section(".entries"), used))
const void *const fm4m_entries[2] = {(const void *)fm4m_records, (const void *)fm4m_names};
