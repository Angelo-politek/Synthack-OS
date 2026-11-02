/* SAMPLER on the Syntakt's main CPU (OS 1.42): SP TWINSHOT's page shown as the Digitakt's, and a waveform page.
 *
 * SP TWINSHOT's eight descriptors (497..504) are rewritten by make_patch.py: names, ranges and defaults of the
 * Digitakt's ONESHOT page, logical indices 0x12..0x19 (TUNE PLAY BR SAMP, the type's three, LEV). The machine
 * type travels in 0x1A, the overdrive's word (engine/syn.c reads it, then zeroes it). The values reach the voice
 * engine like any machine's; nothing here is saved.
 *
 * Here:
 * - two SYN pages through syn-pages (sm_boot registers machine 44): 1/2 the Digitakt's page; 2/2 the sample's
 *   waveform with the type's three knobs and TYPE under it. TYPE has no descriptor of its own (none is free):
 *   on page 2/2 knob H's descriptor (503) is LEV's rewritten as TYPE, on 1/2 back as LEV;
 * - sm_invoke: the text of each value (the OS calls it through the std::function copied from sm_proto, see
 *   readable-values), and the names and ranges of knobs E, F, G for the track's type;
 * - sm_gfx: the graphic in each knob's box (std::function copied from sm_gfx_proto);
 * - sm_block: once per audio block, the tempo to shared RAM for REPITCH and WERP, and a redraw when more of the
 *   waveform has arrived.
 * The waveform comes from the voice CPU, which has the samples: the slot asked for at 0x5B0 of shared RAM, peaks
 * at 0x5C0 (engine/syn.c, wave_step).
 */
#include <stdint.h>
#include "synpages.h"

typedef uint32_t u32;
typedef int32_t s32;

#define OBJS 0x41BA0A24u                    /* per-parameter objects, 84 B, index = id */
#define OBJ_SIZE 84u
#define DESC 0x4022D83Cu                    /* descriptors, 52 B per id */
#define TRACKS ((const volatile short *)0x800021B0u)    /* per-track values: 0x47 words from +0xE */
#define TRACK_WORDS 0x47
#define PROJECT (*(void *const volatile *)0x444E23F4u)
#define GET_TRACK ((s32 (*)(void *))0x4001FF74u)
#define TEMPO (*(const volatile u32 *)0x402D7360u)      /* BPM x 120 */
#define SHARED(off) (0x10000000u + (off))  /* shared RAM, the voice CPU's 0 */
#define SHARED_TEMPO (*(volatile u32 *)SHARED(0x7F0))
#define ORIG_BLOCK ((void (*)(u32))0x40095608u)
#define UI_ROOT (*(uint8_t *const volatile *)0x444E2334u)
#define UI_DIRTY 96                         /* +64 ViewController, +32 "to redraw" */

/* the waveform (engine/syn.c) */
#define WAVE_REQ (*(volatile uint16_t *)SHARED(0x5B0))
#define WAVE_SLOT (*(volatile const uint16_t *)SHARED(0x5B4))
#define WAVE_DONE (*(volatile const uint16_t *)SHARED(0x5B6))
#define WAVE ((volatile const uint8_t *)SHARED(0x5C0))
#define WAVE_COLS 112

enum { LIX_TUNE = 0x12, LIX_PLAY, LIX_BR, LIX_SAMP, LIX_P5, LIX_P6, LIX_P7, LIX_LEV, LIX_TYPE };
enum { M_ONESHOT, M_WERP, M_REPITCH, M_SLICE };

typedef struct {
    u32 owner, lix, min, max, def, r5, midi, cc, id, flags;
    const char *longname, *group, *shortname;
} desc_t;

#define ROW(id) ((volatile desc_t *)(DESC + 52u * (id)))

/* knobs E, F, G per machine type: name, short name, range, default */
typedef struct {
    const char *name, *shortname;
    u32 min, max, def;
} knob_t;

static const char group[] = "SMPL";

static const knob_t knobs[4][3] = {
    {{"Start", "STRT", 0, 0x7800, 0}, {"Length", "LEN", 0, 0x7800, 0x7800}, {"Loop Pos", "LOOP", 0, 0x7802, 0}},
    {{"Segment Size", "SEG", 0, 0x200, 0x100}, {"Segment Mode", "SMOD", 0, 0x300, 0x300},
     {"Bars", "BARS", 0, 0x300, 0x200}},
    {{"Start", "STRT", 0, 0x7800, 0}, {"Length", "LEN", 0, 0x7800, 0x7800}, {"Bars", "BARS", 0, 0x300, 0x200}},
    {{"Slice Select", "SLIC", 0, 0x4000, 0}, {"Slice Length", "LEN", 0, 0x3F00, 0},
     {"Slice Grid", "GRID", 0, 0x400, 0}},
};

/* knob H: LEV on page 1/2, TYPE on 2/2 (logical index, range, default, names) */
static const knob_t lev = {"Sample Level", "LEV", 0, 0x7F00, 0x6400};
static const knob_t type = {"Machine Type", "TYPE", 0, 0x300, 0};

/* make_patch.py copies these into descriptors 497..504 (52 B each, as the OS's), with SP TWINSHOT's MIDI
 * fields and parameter numbers. SP TWINSHOT's page puts them on knobs A B C G E F H D: logical indices
 * follow the knobs, 0x12 (A) to 0x19 (H), the Digitakt's order (engine/sampler.h). */
#define ID_TUNE 497
#define ID_PLAY 498
#define ID_BR 499
#define ID_P7 500
#define ID_P5 501
#define ID_P6 502
#define ID_H 503
#define ID_SAMP 504
__attribute__((used)) const desc_t sm_rows[8] = {
    {44, 0x12, 0x0400, 0x5800, 0x4000, 1, 0, 0, 0, 0xE00, "Tune", group, "TUNE"},           /* 497, A */
    {44, 0x13, 0, 0x300, 0x300, 1, 0, 0, 0, 0xE00, "Play Mode", group, "PLAY"},             /* 498, B */
    {44, 0x14, 0, 0x7F00, 0, 0, 0, 0, 0, 0xE00, "Bit Reduction", group, "BR"},              /* 499, C */
    {44, 0x18, 0, 0x7802, 0, 1, 0, 0, 0, 0xE00, "Loop Pos", group, "LOOP"},                 /* 500, G */
    {44, 0x16, 0, 0x7800, 0, 1, 0, 0, 0, 0xE00, "Start", group, "STRT"},                    /* 501, E */
    {44, 0x17, 0, 0x7800, 0x7800, 1, 0, 0, 0, 0xE00, "Length", group, "LEN"},               /* 502, F */
    {44, 0x19, 0, 0x7F00, 0x6400, 1, 0, 0, 0, 0xE00, "Sample Level", group, "LEV"},         /* 503, H */
    {44, 0x15, 0, 0x3F00, 0, 1, 0, 0, 0, 0xE00, "Sample Slot", group, "SAMP"},              /* 504, D */
};

/* knobs E, F, G: descriptors */
static const u32 knob_ids[3] = {ID_P5, ID_P6, ID_P7};

/* ---- the track shown */

static s32 active_track(void) {
    void *p = PROJECT;
    s32 t = p ? GET_TRACK((char *)p + 48) : -1;
    return t >= 0 && t < 8 ? t : -1;
}

static s32 value(s32 t, int lix) {
    return t < 0 ? 0 : TRACKS[0xE + TRACK_WORDS * t + lix];
}

static u32 clampi(s32 v, s32 hi) {
    return v < 0 ? 0 : v > hi ? (u32)hi : (u32)v;
}

static int track_type(void) {
    return (int)clampi(value(active_track(), LIX_TYPE) >> 8, 3);
}

static void set_row(u32 id, const knob_t *n, u32 lix) {
    volatile desc_t *r = ROW(id);
    if (r->longname != n->name) {
        r->longname = n->name;
        r->shortname = n->shortname;
        r->min = n->min;
        r->max = n->max;
        r->def = n->def;
        r->lix = lix;
    }
}

/* names and ranges of knobs E, F, G for the track's machine type */
static void fit_knobs(int t) {
    for (int k = 0; k < 3; k++)
        set_row(knob_ids[k], &knobs[t][k], LIX_P5 + k);
}

/* ---- value texts */

static char *put_s(char *b, const char *s) {
    while (*s)
        *b++ = *s++;
    return b;
}

static char *put_u(char *b, u32 n) {
    char t[10];
    int k = 0;
    do {
        t[k++] = (char)('0' + n % 10);
        n /= 10;
    } while (n);
    while (k)
        *b++ = t[--k];
    return b;
}

static const char *const play_names[4] = {"REV", "REV.L", "FWD.L", "FWD"};
static const char *const type_names[4] = {"ONE", "WERP", "PTCH", "SLIC"};
static const char *const seg_names[3] = {"1/32", "1/16", "1/8"};

static u32 id_of(const void *fn, u32 field) {
    u32 off = (u32)fn - (OBJS + field), id = off / OBJ_SIZE;
    return off % OBJ_SIZE ? 0 : id;
}

static void format(u32 id, s32 value, char *buf, int t) {
    u32 v = clampi(value, 0x7F00), i = v >> 8;
    char *b = buf;
    switch (id) {
    case ID_PLAY:
        b = put_s(b, play_names[clampi((s32)i, 3)]);
        break;
    case ID_SAMP:                               /* slot 1..64 */
        b = put_u(b, i + 1);
        break;
    case ID_P5:                                 /* STRT | SEG | STRT | SLICE */
        if (t == M_WERP)
            b = put_s(b, seg_names[clampi((s32)i, 2)]);
        else if (t == M_SLICE && i == 0)
            b = put_s(b, "KEY");
        else
            b = put_u(b, i);
        break;
    case ID_P6:                                 /* LEN | segment MODE | LEN | slice LEN */
        if (t == M_WERP)
            b = put_s(b, play_names[clampi((s32)i, 3)]);
        else
            b = put_u(b, t == M_SLICE ? i + 1 : i);
        break;
    case ID_P7:                                 /* LOOP | BARS | BARS | GRID */
        if (t == M_ONESHOT)
            b = v ? put_u(b, (v - 1) >> 8) : put_s(b, "STRT");
        else if (t == M_SLICE)
            b = put_u(b, 4u << clampi((s32)i, 4));
        else
            b = put_u(b, 1u << clampi((s32)i, 3));
        break;
    case ID_H:                                  /* LEV, or TYPE on page 2/2 */
        if (ROW(ID_H)->lix == LIX_TYPE)
            b = put_s(b, type_names[clampi((s32)i, 3)]);
        else
            b = put_u(b, i);
        break;
    default:                                    /* BR, and anything else: 0..127 */
        b = put_u(b, i);
        break;
    }
    *b = 0;
}

void sm_invoke(const void *fn, s32 value, char *buf) {
    int t = track_type();
    fit_knobs(t);
    format(id_of(fn, 20), value, buf, t);
}

/* std::function manager: nothing to copy or free */
int sm_mgr(void *dst, const void *src, int op) {
    (void)dst;
    (void)src;
    (void)op;
    return 0;
}

/* ---- the waveform */

/* ask the voice CPU for slot's waveform; 1 once all of it is there */
static int wave_ready(u32 slot) {
    WAVE_REQ = (uint16_t)(slot + 1);
    return WAVE_SLOT == slot + 1 && WAVE_DONE >= WAVE_COLS;
}

/* peak (0..127) over columns [c0, c1) of the WAVE_COLS */
static int peak(u32 c0, u32 c1) {
    int p = 0;
    for (u32 c = c0; c < c1 && c < WAVE_COLS; c++)
        p = WAVE[c] > p ? WAVE[c] : p;
    return p;
}

/* The part of the sample the knobs pick, in 1/0x7800 of the sample (0x7800 = all): played from a to b, loop
 * back to l (-1 none); for SLICE the grid's slices too. */
typedef struct {
    s32 a, b, l, slices;
} part_t;

static part_t part_of(s32 t) {
    part_t p = {0, 0x7800, -1, 0};
    int ty = (int)clampi(value(t, LIX_TYPE) >> 8, 3);
    s32 p5 = value(t, LIX_P5), p6 = value(t, LIX_P6), p7 = value(t, LIX_P7);
    if (ty == M_ONESHOT || ty == M_REPITCH) {
        p.a = (s32)clampi(p5, 0x7800);
        p.b = (s32)clampi(p.a + p6, 0x7800);
        if (ty == M_ONESHOT && (value(t, LIX_PLAY) >> 8) % 3 != 0)       /* REV.L, FWD.L */
            p.l = p7 ? (s32)clampi(p7 - 1, 0x7800) : p.a;
    } else if (ty == M_SLICE) {
        s32 n = 4 << clampi(p7 >> 8, 4), sel = (s32)clampi(p5 >> 8, n), len = (s32)clampi(p6 >> 8, 63) + 1;
        p.slices = n;
        if (sel > 0) {
            p.a = 0x7800 * (sel - 1) / n;
            p.b = (s32)clampi(0x7800 * (sel - 1 + len) / n, 0x7800);
        }
    }
    return p;
}

/* waveform over w columns from (x, top), h rows high (odd): the part played solid, the rest dotted, a line at
 * each end of the part, a dashed line at the loop point, ticks under the slices */
static void draw_wave(void *bm, int x, int top, int w, int h, const part_t *p, int marks) {
    int mid = top + h / 2, half = h / 2;
    for (int c = 0; c < w; c++) {
        int k = peak((u32)(c * WAVE_COLS / w), (u32)((c + 1) * WAVE_COLS / w)) * half / 127;
        s32 pos = 0x7800 * c / w;
        int in = pos >= p->a && pos < p->b;
        for (int y = mid - k; y <= mid + k; y++)
            if (in || (y + c) % 2 == 0)
                sp_px(bm, x + c, y, 1);
    }
    if (!marks)
        return;
    int xa = x + p->a * (w - 1) / 0x7800, xb = x + p->b * (w - 1) / 0x7800;
    sp_vline(bm, xa, top, top + h - 1, 1);
    sp_vline(bm, xb, top, top + h - 1, 1);
    sp_hline(bm, xa, xa + 2, top, 1);
    sp_hline(bm, xb - 2, xb, top, 1);
    if (p->l >= 0)
        sp_vline(bm, x + p->l * (w - 1) / 0x7800, top, top + h - 1, 2);
    for (s32 k = 1; k < p->slices; k++)
        sp_vline(bm, x + w * k / p->slices, top + h - 3, top + h - 1, 1);
}

/* ---- knob graphics: std::function(value, bitmap, x, y); 26 x 16 with the bottom left corner at x, y counted
 * from the bottom of the screen */

static void text(void *bm, s32 x, s32 y, const char *s) {
    SP_DRAW_TEXT(bm, SP_FONT, x + 8, y + 5, 1, 0, "XXXX", "%s", s);       /* as perf-fx's boxes */
}

static void gfx_play(void *bm, int x, int top, u32 i) {
    int fwd = i >= 2, loop = i == 1 || i == 2, y = top + 10;
    sp_hline(bm, x + 4, x + 21, y, 1);
    int tip = fwd ? x + 21 : x + 4, d = fwd ? -1 : 1;
    for (int k = 1; k <= 3; k++)
        sp_vline(bm, tip + d * k, y - k, y + k, 1);
    if (loop) {                                 /* back over the top: a loop */
        sp_vline(bm, x + 4, top + 3, y - 1, 1);
        sp_vline(bm, x + 21, top + 3, y - 1, 1);
        sp_hline(bm, x + 4, x + 21, top + 3, 1);
    }
}

static void gfx_br(void *bm, int x, int top, u32 i) {
    int steps = 8 - (int)(i * 7 / 127);         /* more reduction, fewer and coarser steps */
    for (int s = 0; s < steps; s++) {
        int x0 = x + 3 + s * 20 / steps, x1 = x + 3 + (s + 1) * 20 / steps, y = top + 14 - (s + 1) * 12 / steps;
        sp_hline(bm, x0, x1, y, 1);
        sp_vline(bm, x1, y, top + 14 - s * 12 / steps, 1);
    }
}

static void gfx_lev(void *bm, int x, int top, u32 i) {
    int h = (int)(i * 13 / 127);
    sp_hline(bm, x + 10, x + 15, top + 1, 1);
    sp_hline(bm, x + 10, x + 15, top + 15, 1);
    sp_vline(bm, x + 10, top + 1, top + 15, 1);
    sp_vline(bm, x + 15, top + 1, top + 15, 1);
    for (int y = top + 14 - h; y < top + 15; y++)
        sp_hline(bm, x + 11, x + 14, y, 1);
}

void sm_gfx(const void *fn, s32 val, void *bm, s32 x, s32 y) {
    u32 id = id_of(fn, 36), i = clampi(val, 0x7F00) >> 8;
    int top = *(int32_t *)((uint8_t *)bm + 8) - 16 - y;
    s32 t = active_track();
    int ty = track_type();
    char buf[8];
    switch (id) {
    case ID_PLAY:
        gfx_play(bm, x, top, clampi((s32)i, 3));
        return;
    case ID_BR:
        gfx_br(bm, x, top, i);
        return;
    case ID_SAMP:
        if (wave_ready(i)) {
            part_t all = {0, 0x7800, -1, 0};
            draw_wave(bm, x + 1, top + 1, 24, 15, &all, 0);
            return;
        }
        break;
    case ID_P5:
    case ID_P6:
    case ID_P7:
        if ((ty == M_ONESHOT || ty == M_REPITCH) && !(ty == M_REPITCH && id == ID_P7) &&
            wave_ready(clampi(value(t, LIX_SAMP) >> 8, 63))) {
            part_t p = part_of(t);
            if (id != ID_P7)
                p.l = -1;
            draw_wave(bm, x + 1, top + 1, 24, 15, &p, 1);
            return;
        }
        break;
    case ID_H:
        if (ROW(ID_H)->lix != LIX_TYPE) {
            gfx_lev(bm, x, top, i);
            return;
        }
        break;
    }
    format(id, val, buf, ty);
    text(bm, x, y, buf);
}

/* copied by the OS into each object's +20 and +36 (make_patch.py points the constructors here) */
const void *const sm_proto[4] __attribute__((aligned(4))) = {0, 0, (const void *)sm_mgr, (const void *)sm_invoke};
const void *const sm_gfx_proto[4] __attribute__((aligned(4))) = {0, 0, (const void *)sm_mgr, (const void *)sm_gfx};

/* ---- pages (syn-pages) */

/* page 2/2: knobs A..D under the waveform (none), the type's three, TYPE; LEVEL */
static const u32 page2[9] = {0, 0, 0, 0, ID_P5, ID_P6, ID_P7, ID_H, 10};

static u32 sm_record(void *view, u32 page, u32 knob) {
    fit_knobs(track_type());
    if (page == 1) {
        set_row(ID_H, &type, LIX_TYPE);
        return knob < 9 ? page2[knob] : 0;
    }
    set_row(ID_H, &lev, LIX_LEV);
    return SP_ORIG_RECORD(view, knob);
}

static const char *sm_title(void *view, u32 page) {
    (void)view;
    return page == 1 ? "SAMPLER 2/2" : "SAMPLER 1/2";
}

/* page 2/2: the waveform over the top row (x 16..127, rows 0..36) */
static void sm_draw(void *view, void *bm, u32 page) {
    (void)view;
    s32 t = active_track();
    if (page != 1 || t < 0)
        return;
    sp_clear(bm, 16, 0, 128, 37);
    if (wave_ready(clampi(value(t, LIX_SAMP) >> 8, 63))) {
        part_t p = part_of(t);
        draw_wave(bm, 16, 2, 112, 33, &p, 1);
    } else {
        sp_hline(bm, 16, 127, 18, 2);
    }
}

static const sp_machine_t sm_pages = {ID_TUNE, 2, sm_record, sm_title, sm_draw};

void sm_boot(void) {
    sp_register(&sm_pages);
}

/* ---- once per audio block, in place of the call to 0x40095608 */
static uint16_t seen;

void sm_block(u32 arg) {
    SHARED_TEMPO = TEMPO;
    uint16_t done = WAVE_DONE;
    if (done != seen) {                         /* more of the waveform: redraw */
        seen = done;
        uint8_t *ui = UI_ROOT;
        if (ui)
            ui[UI_DIRTY] = 1;
    }
    ORIG_BLOCK(arg);
}

__attribute__((section(".entries"), used)) const void *const sm_entries[5] = {
    (const void *)sm_proto, (const void *)sm_block, (const void *)sm_rows, (const void *)sm_gfx_proto,
    (const void *)sm_boot};
