/* 6-tap polyphase interpolation at twice the output rate (Digitakt 0x40075EA2, written in C).
 *
 * Position = *ipos (samples into win) + *frac (Q32), step = rate (Q4.28, negative backwards). Output n
 * uses phase frac >> 24 and taps win[ipos .. ipos + 5]: 2 * sum(c * s), the EMAC's 16 x 16 fractional
 * MAC without rounding. The coefficients sit as in the Digitakt's table: 3 rows of 256 pairs.
 */
#include "sampler.h"

const int16_t *sm_interp(const int16_t *win, uint32_t *frac, int32_t *ipos, int32_t rate, int32_t *out, int n,
                         const int16_t (*table)[256][2]) {
    uint32_t f = *frac, step_f = (uint32_t)rate << 4;
    int32_t i = *ipos, step_i = rate >> 28;
    while (n--) {
        unsigned p = f >> 24;
        const int16_t *s = win + i;
        const int16_t *c0 = table[0][p], *c1 = table[1][p], *c2 = table[2][p];
        int32_t acc = c0[0] * s[0] + c0[1] * s[1] + c1[0] * s[2] + c1[1] * s[3] + c2[0] * s[4] + c2[1] * s[5];
        *out++ = acc * 2;
        uint32_t nf = f + step_f;
        i += step_i + (nf < f);
        f = nf;
    }
    *frac = f;
    *ipos = i;
    return win + i;
}
