/* Start and end of the part of the sample a voice plays, per machine, and the zero-crossing grid.
 *
 * Each function returns (a, b) in samples: the voice plays from a towards b. Forward modes (PLAY FWD,
 * FWD.L) give a < b, reverse modes the other way round. Steps and clamps follow the Digitakt's
 * functions one by one (sampler.h); tests/test_sampler.py checks them against the originals.
 */
#include "sampler.h"

#define FULL 30720                  /* 120 << 8: STRT, LEN, LOOP at their maximum */
#define K_120 0x44444445            /* 64/120 in Q31: 0..FULL << 16 -> 0..2^30 */

static inline int32_t clamp(int32_t v, int32_t lo, int32_t hi) {
    return v < lo ? lo : v > hi ? hi : v;
}

/* Q30 fractions of the sample -> samples: (f * 2len) >> 31 */
static void to_samples(int32_t len, int32_t fa, int32_t fb, int32_t *a, int32_t *b) {
    int32_t l2 = (int32_t)((uint32_t)len << 1);
    *a = sm_fmul(l2, sm_fmul(K_120, fa));
    *b = sm_fmul(l2, sm_fmul(K_120, fb));
}

/* PLAY: 0 REV, 1 REV.L, 2 FWD.L, 3 FWD */
static inline int forward(int play) { return (uint32_t)(play & 0xffff) > 1; }
static inline int looping(int play) { return (uint32_t)((play - 1) & 0xffff) <= 1; }

/* ONESHOT: STRT, LEN (from STRT), LOOP (0 = at STRT, else LOOP - 1). In a loop mode, after the first
 * pass (first = 0), the voice plays between LOOP and the end. */
void sm_pos_oneshot(const sm_par_t *p, int32_t len, int32_t first, int32_t *a, int32_t *b) {
    int32_t start = clamp(p->w[4], 0, FULL);
    int32_t end = p->w[5] + start;
    end = end < 0 ? 0 : end > FULL ? FULL : end;
    int32_t loop = (uint16_t)p->w[6] ? clamp(p->w[6] - 1, 0, FULL) : start;
    int play = SM_BYTE(p, 1);
    int32_t x, y;                   /* x -> b, y -> a, swapped below for forward modes */
    if (!first && looping(play)) {
        if (end > loop) {
            x = loop << 16;
            y = end << 16;
        } else {
            x = end << 16;
            y = loop << 16;
        }
    } else {
        x = start << 16;
        y = end << 16;
    }
    if (forward(play)) {
        int32_t t = x;
        x = y;
        y = t;
    }
    to_samples(len, y, x, a, b);
}

/* REPITCH: STRT and LEN as ONESHOT, no loop point (loop modes repeat the whole part). */
void sm_pos_repitch(const sm_par_t *p, int32_t len, int32_t *a, int32_t *b) {
    int32_t start = clamp(p->w[4], 0, FULL);
    int32_t end = p->w[5] + start;
    end = end < 0 ? 0 : end > FULL ? FULL : end;
    int32_t x = end << 16, y = start << 16;
    if (forward(SM_BYTE(p, 1))) {
        int32_t t = x;
        x = y;
        y = t;
    }
    to_samples(len, x, y, a, b);
}

/* SLICE: GRID 0..4 = 4, 8, 16, 32, 64 slices; SLICE 1..n plays that slice, 0 picks it from the trig
 * note (note - 12, wrapped); LEN 0..63 = 1..64 slices long. Slices start on the zero-crossing grid. */
void sm_pos_slice(const sm_par_t *p, int32_t note16, int32_t len, const sm_grid_t *g, int32_t *a, int32_t *b) {
    if (g == 0) {
        *a = 0;
        *b = len;
        return;
    }
    int32_t grid = SM_BYTE(p, 6);
    if (grid > 4)
        grid = 4;
    int32_t sel = SM_BYTE(p, 4);
    int32_t n = 4 << grid;
    if (sel < 0)
        sel = 0;
    int32_t s = (sel < n ? sel : n) - 1;
    if (s < 0)
        s = (n - 1) & ((int32_t)(int16_t)(note16 >> 16) - 12);
    int32_t shift = 4 - grid;
    s <<= shift;
    int32_t l = SM_BYTE(p, 5);
    if (l > 63)
        l = 63;
    l = (l + 1) << shift;
    int32_t i0 = s << 2, i1 = i0 + (l << 2);
    int32_t from = g->pt[i0];
    int32_t to = i1 <= 255 ? g->pt[i1] : len;
    if (forward(SM_BYTE(p, 1))) {
        *a = from;
        *b = to;
    } else {
        *a = to;
        *b = from;
    }
}

/* WERP: the sample spans BARS (1, 2, 4, 8 bars); a segment of SEG (0..2) is 2^(SEG + 3 - BARS) grid
 * points long and starts at the grid point of the current phase (Q31, one turn = the whole sample).
 * Segment MODE 0, 1 play it backwards. */
void sm_pos_werp(const sm_par_t *p, uint32_t phase, int32_t len, const sm_grid_t *g, int32_t *a, int32_t *b) {
    int back = (uint32_t)(SM_BYTE(p, 5) & 0xffff) < 2;
    if (g == 0) {
        *a = back ? len : 0;
        *b = back ? 0 : len;
        return;
    }
    int32_t seg = clamp((int16_t)p->w[4] >> 8, 0, 2) + 3;
    int32_t bars = clamp((int16_t)p->w[6] >> 8, 0, 3);
    uint32_t i0 = (phase + 0x400000u) >> 23;
    uint32_t i1 = i0 + (1u << (seg - bars));
    int32_t from = g->pt[i0 & 255];
    int32_t to = i1 <= 255 ? g->pt[i1] : len;
    if (back) {
        *a = to;
        *b = from;
    } else {
        *a = from;
        *b = to;
    }
}

/* Nearest sign change from idx in one direction (dir -1 or +1), at most maxdist samples away: the
 * index i where data[i] and data[i + 1] differ in sign or data[i] is 0; idx if none. */
int32_t sm_zero_cross(const int16_t *data, const int16_t *end, int32_t idx, int32_t dir, int32_t maxdist) {
    if (data == 0 || end == 0 || dir == 0)
        return 0;
    int32_t len = (int32_t)(end - data);
    if (len <= 0 || len <= idx)
        return 0;
    int32_t i;
    if (dir < 0) {
        if (idx == 0)
            return 0;
        i = idx - 1;
        dir = -1;
    } else {
        if (len - 1 == idx)
            return idx;
        i = idx + 1;
        dir = 1;
    }
    for (;;) {
        if (len <= i || i < 0)
            return idx;
        int32_t s0 = data[i], s1 = data[i + 1];
        int32_t g0 = s0 ? (s0 < 0 ? -1 : 1) : 0;
        int32_t g1 = s1 ? (s1 < 0 ? -1 : 1) : 0;
        if (g0 != g1 || s0 == 0)
            return i;
        i += dir;
        int32_t d = i - idx;
        if ((d < 0 ? -d : d) > maxdist)
            return idx;
    }
}

/* Grid point k (1..255) of a sample: round(k * len / 256), moved to the nearest sign change within
 * len / 512 samples (the later one on a tie). Point 0 is 0. */
int32_t sm_grid_point(const int16_t *data, int32_t len, int k) {
    if (k <= 0)
        return 0;
    int32_t idx = (int32_t)(((uint32_t)len * (uint32_t)k + 128) >> 8);     /* len < 2^19 */
    int32_t maxdist = (int32_t)(((uint32_t)len << 1) >> 10);
    const int16_t *end = data + len;
    int32_t lo = sm_zero_cross(data, end, idx, -1, maxdist);
    int32_t hi = sm_zero_cross(data, end, idx, 1, maxdist);
    int32_t dl = idx - lo, dh = hi - idx;
    dl = dl < 0 ? -dl : dl;
    dh = dh < 0 ? -dh : dh;
    return dh <= dl ? hi : lo;
}

void sm_grid_need(sm_grid_t *g, int k) {
    if (k < 0 || k > 255 || g->done[k])
        return;
    g->pt[k] = sm_grid_point(g->data, g->len, k);
    g->done[k] = 1;
}
