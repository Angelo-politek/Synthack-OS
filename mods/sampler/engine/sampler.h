/* SAMPLER: the Digitakt's sample machines (ONESHOT, WERP, REPITCH, SLICE) on the Syntakt's second CPU.
 *
 * Written from the Digitakt 1.54 code read in the emulator, not copied from it:
 * - sm_pos_*: the per-machine start/end functions (Digitakt 0x40074C9C ONESHOT, 0x40074D72 REPITCH,
 *   0x40074DF2 SLICE, 0x40074EBE WERP), same fixed-point steps (EMAC fractional, truncated);
 * - sm_grid_*: the 256-point grid of a sample, each point moved to the nearest zero crossing
 *   (Digitakt 0x400763B4 and 0x400762EE), used by SLICE and WERP;
 * - sm_interp: 6-tap polyphase interpolation at twice the output rate, 256 phases (Digitakt
 *   0x40075EA2); the table is ours (gen_table.py), fitted to the Digitakt's response;
 * - the 2:1 half-band decimator is the Syntakt's own (section 7, 0x400051C6), the same filter as the
 *   Digitakt's.
 * tests/test_sampler.py runs both sides in the emulator and compares them.
 */
#ifndef SAMPLER_H
#define SAMPLER_H

#include <stdint.h>

/* Parameters, words at params + 2 * logical index (the frame the main CPU sends, section 7 view). */
enum {
    LIX_TUNE = 0x12,    /* 8.8 semitones, 0x4000 = 0 */
    LIX_PLAY = 0x13,    /* 0 REV, 1 REV.L, 2 FWD.L, 3 FWD (Digitakt order) */
    LIX_BR = 0x14,      /* bit reduction 0..127 */
    LIX_SAMP = 0x15,    /* sample slot 0..63 */
    LIX_P5 = 0x16,      /* STRT | SEG | STRT | SLICE */
    LIX_P6 = 0x17,      /* LEN | MODE | LEN | LEN */
    LIX_P7 = 0x18,      /* LOOP | BARS | BARS | GRID */
    LIX_MODE = 0x19,    /* 0 ONESHOT, 1 WERP, 2 REPITCH, 3 SLICE (Digitakt machine numbers) */
    LIX_OVER = 0x1a,    /* the Syntakt's overdrive, applied after the engines: kept at 0 */
};

enum { M_ONESHOT, M_WERP, M_REPITCH, M_SLICE };

/* The Digitakt's parameter block for the position functions: words from lix 0x11 (TUNE) on. */
typedef struct {
    int16_t w[8];       /* TUNE PLAY BR SAMP P5 P6 P7 LEV, high byte = integer value */
} sm_par_t;

#define SM_BYTE(p, i) ((int8_t)((uint16_t)(p)->w[i] >> 8))

#define SM_GRID 256     /* points per sample */

/* One slot's grid: positions (samples) of grid points 0..255, valid for (data, len). */
typedef struct {
    const int16_t *data;
    int32_t len;
    int32_t pt[SM_GRID];
    uint8_t done[SM_GRID];
} sm_grid_t;

/* 32 x 32 -> 64 bit with 16-bit pieces (the ColdFire's multiply keeps the low 32 bits; the compiler's
 * 64-bit helpers are 68020 code). */
static inline void sm_umul64(uint32_t a, uint32_t b, uint32_t *hi, uint32_t *lo) {
    uint32_t a0 = a & 0xffff, a1 = a >> 16, b0 = b & 0xffff, b1 = b >> 16;
    uint32_t p00 = a0 * b0, p01 = a0 * b1, p10 = a1 * b0, p11 = a1 * b1;
    uint32_t mid = (p00 >> 16) + (p01 & 0xffff) + (p10 & 0xffff);
    *lo = (mid << 16) | (p00 & 0xffff);
    *hi = p11 + (p01 >> 16) + (p10 >> 16) + (mid >> 16);
}

/* (a * b) >> 31, rounded down: the EMAC's fractional multiply with truncation (saturated at -1 x -1) */
static inline int32_t sm_fmul(int32_t a, int32_t b) {
    uint32_t hi, lo;
    int neg = (a < 0) != (b < 0);
    sm_umul64(a < 0 ? 0u - (uint32_t)a : (uint32_t)a, b < 0 ? 0u - (uint32_t)b : (uint32_t)b, &hi, &lo);
    if (neg) {
        hi = ~hi + (lo == 0);
        lo = 0u - lo;
    }
    if (!neg && hi >= 0x40000000u)
        return 0x7fffffff;
    return (int32_t)((hi << 1) | (lo >> 31));
}

/* (a * b) >> s, unsigned, 0 < s < 32, result below 2^32 */
static inline uint32_t sm_umulshr(uint32_t a, uint32_t b, int s) {
    uint32_t hi, lo;
    sm_umul64(a, b, &hi, &lo);
    return (hi << (32 - s)) | (lo >> s);
}

/* (n << s) / d, unsigned, for a quotient below 2^32 (bit by bit) */
static inline uint32_t sm_udivshl(uint32_t n, uint32_t d, int s) {
    uint32_t q = n / d, r = n % d;
    while (s--) {
        q <<= 1;
        if (r >= d - r) {
            r -= d - r;
            q |= 1;
        } else {
            r <<= 1;
        }
    }
    return q;
}

void sm_pos_oneshot(const sm_par_t *p, int32_t len, int32_t first, int32_t *a, int32_t *b);
void sm_pos_repitch(const sm_par_t *p, int32_t len, int32_t *a, int32_t *b);
void sm_pos_slice(const sm_par_t *p, int32_t note16, int32_t len, const sm_grid_t *g, int32_t *a, int32_t *b);
void sm_pos_werp(const sm_par_t *p, uint32_t phase, int32_t len, const sm_grid_t *g, int32_t *a, int32_t *b);

int32_t sm_zero_cross(const int16_t *data, const int16_t *end, int32_t idx, int32_t dir, int32_t maxdist);
int32_t sm_grid_point(const int16_t *data, int32_t len, int k);
void sm_grid_need(sm_grid_t *g, int k);

extern const int16_t sm_interp_table[3][256][2];
const int16_t *sm_interp(const int16_t *win, uint32_t *frac, int32_t *ipos, int32_t rate, int32_t *out, int n,
                         const int16_t (*table)[256][2]);

#endif
