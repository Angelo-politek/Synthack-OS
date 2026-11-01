/* fm4: see fm4.h. */
#include "fm4.h"

#define B(op) (1u << ((op) - 1))   /* operator number 1..4 -> mask bit */

/* Routing. Numbers are operator numbers as in the docs; a self bit is the
 * operator's feedback. Operator 4 carries feedback in 1..10; 11 is a ring
 * whose 1 -> 4 edge takes the feedback amount instead. */
const fm4_algo_t fm4_algos[FM4_ALGOS] = {
    /*  1  4>3>2>1           */ {{B(2), B(3), B(4), B(4)}, B(1)},
    /*  2  (3+4)>2>1         */ {{B(2), B(3) | B(4), 0, B(4)}, B(1)},
    /*  3  3>2>1, 4>1        */ {{B(2) | B(4), B(3), 0, B(4)}, B(1)},
    /*  4  4>3>1, 2>1        */ {{B(2) | B(3), 0, B(4), B(4)}, B(1)},
    /*  5  4>3, 2>1          */ {{B(2), 0, B(4), B(4)}, B(1) | B(3)},
    /*  6  4>1, 4>2, 4>3     */ {{B(4), B(4), B(4), B(4)}, B(1) | B(2) | B(3)},
    /*  7  4>3, 2, 1         */ {{0, 0, B(4), B(4)}, B(1) | B(2) | B(3)},
    /*  8  1, 2, 3, 4        */ {{0, 0, 0, B(4)}, B(1) | B(2) | B(3) | B(4)},
    /*  9  4>3, 3>2, 3>1     */ {{B(3), B(3), B(4), B(4)}, B(1) | B(2)},
    /* 10  4>3, 4>2, 3+2>1   */ {{B(2) | B(3), B(4), B(4), B(4)}, B(1)},
    /* 11  4>3>2>1>4 (ring)  */ {{B(2), B(3), B(4), B(1)}, B(1)},
};

/* Output gain by carrier count, Q4.12, so that full-level carriers cannot
 * clip when summed. */
static const int32_t mix_gain[5] = {0, 4096, 2048, 1365, 1024};

/* Operator outputs are Q1.23: the Q1.15 table interpolated with 8 more bits.
 * The table's steepest step is about 201, so (b - a) * frac stays in 24 bits. */
static inline int32_t sine(uint32_t phase) {
    uint32_t i = phase >> (32 - FM4_SINE_BITS);
    int32_t frac = (int32_t)((phase >> (16 - FM4_SINE_BITS)) & 0xFFFF);
    int32_t a = fm4_sine[i], b = fm4_sine[i + 1];
    return a * 256 + (((b - a) * frac) >> 8);
}


void fm4_init(fm4_voice_t *v) {
    for (int i = 0; i < FM4_OPS; i++) {
        v->phase[i] = 0;
        v->out[i] = v->prev[i] = 0;
        v->env[i] = 0;
    }
}

/* Per block, each operator's modulation edges get one gain, its level (or
 * the feedback amount, for an edge from itself or from an operator evaluated
 * after it) times its source's envelope: a modulator's envelope moves its
 * index once a block. A carrier's envelope is ramped per sample into its
 * output gain. Sources are Q1.23 taken >> 3 (Q1.20), so a gain of
 * (Q4.12 x Q1.15) >> 15 makes 2^32 one cycle; the product and the sum wrap
 * modulo 2^32 on purpose, as the phase does. */
#define FM4_G(level, env) ((uint32_t)((level) * (env)) >> 15)

static inline uint32_t edge(int32_t src, uint32_t g) {
    return (uint32_t)(src >> 3) * g;
}

/* What a carrier's output gain is at envelope e (Q1.15): car (Q4.12) x mix
 * (Q4.12) x e, scaled so that a full Q1.23 output >> 8 times it is 2^31. */
static inline int32_t car_gain(int32_t carmix, int32_t e) {
    return (int32_t)(((uint32_t)carmix * (uint32_t)e) >> 15);
}

int32_t fm4_carmix(const fm4_params_t *p, int i) {
    const fm4_algo_t *a = &fm4_algos[p->algo < FM4_ALGOS ? p->algo : 0];
    if (!(a->carriers & (1u << i)))
        return 0;
    int ncar = 0;
    for (int k = 0; k < FM4_OPS; k++)
        ncar += (a->carriers >> k) & 1;
    int32_t g = i == 0 ? 4096 : p->level[i];
    if (g > 4096)
        g = 4096;
    return (g * mix_gain[ncar]) >> 8;          /* Q16: 65536 = 1.0 */
}

void fm4_render(fm4_voice_t *v, const fm4_params_t *p, int32_t *out, int n) {
    const fm4_algo_t *a = &fm4_algos[p->algo < FM4_ALGOS ? p->algo : 0];
    int shift = 0;
    while ((1 << shift) < n)
        shift++;

    /* Every algorithm is the same graph with some gains zero: the six
     * forward edges (a higher operator into a lower one, evaluated first),
     * operator 4's feedback on itself, and the ring's 1 -> 4 (operator 1's
     * previous sample). So one branch-free loop serves all eleven. Names are
     * gTS: into operator T from operator S, 1..4. */
    uint32_t g[FM4_OPS][FM4_OPS];
    for (int i = 0; i < FM4_OPS; i++)
        for (int j = 0; j < FM4_OPS; j++)
            g[i][j] = (a->mod[i] & (1u << j))
                ? FM4_G(j > i ? p->level[j] : p->feedback, p->env[j]) : 0;
    const uint32_t g44 = g[3][3], g41 = g[3][0], g34 = g[2][3];
    const uint32_t g23 = g[1][2], g24 = g[1][3];
    const uint32_t g12 = g[0][1], g13 = g[0][2], g14 = g[0][3];

    int32_t cg[FM4_OPS], cs[FM4_OPS];
    for (int i = 0; i < FM4_OPS; i++) {
        int32_t cm = fm4_carmix(p, i);
        cg[i] = car_gain(cm, v->env[i]);
        cs[i] = (car_gain(cm, p->env[i]) - cg[i]) >> shift;
    }
    int32_t c1 = cg[0], c2 = cg[1], c3 = cg[2], c4 = cg[3];
    const int32_t d1 = cs[0], d2 = cs[1], d3 = cs[2], d4 = cs[3];

    uint32_t ph1 = v->phase[0], ph2 = v->phase[1], ph3 = v->phase[2], ph4 = v->phase[3];
    const uint32_t i1 = p->inc[0], i2 = p->inc[1], i3 = p->inc[2], i4 = p->inc[3];
    int32_t o1 = v->out[0], o2 = v->out[1], o3 = v->out[2], o4 = v->out[3];
    int32_t p4 = v->prev[3];

    for (int s = 0; s < n; s++) {
        int32_t y4 = sine(ph4 + edge((o4 + p4) >> 1, g44) + edge(o1, g41));
        ph4 += i4;
        p4 = o4;
        o4 = y4;
        int32_t y3 = sine(ph3 + edge(o4, g34));
        ph3 += i3;
        o3 = y3;
        int32_t y2 = sine(ph2 + edge(o3, g23) + edge(o4, g24));
        ph2 += i2;
        o2 = y2;
        int32_t y1 = sine(ph1 + edge(o2, g12) + edge(o3, g13) + edge(o4, g14));
        ph1 += i1;
        o1 = y1;
        c1 += d1; c2 += d2; c3 += d3; c4 += d4;
        out[s] = (y1 >> 8) * c1 + (y2 >> 8) * c2 + (y3 >> 8) * c3 + (y4 >> 8) * c4;
    }

    v->phase[0] = ph1; v->phase[1] = ph2; v->phase[2] = ph3; v->phase[3] = ph4;
    v->prev[0] = v->out[0]; v->prev[1] = v->out[1]; v->prev[2] = v->out[2];
    v->out[0] = o1; v->out[1] = o2; v->out[2] = o3; v->out[3] = o4;
    v->prev[3] = p4;
    for (int i = 0; i < FM4_OPS; i++)
        v->env[i] = p->env[i];
}

/* Coarse ratios, as on a 4-op Yamaha, plus a fine step between: 0..127 spans
 * 22 coarse values, about six steps each, interpolated linearly. */
static const uint16_t ratios_q8[22] = {
    64, 128, 192, 256, 384, 512, 640, 768, 896, 1024, 1280,
    1536, 1792, 2048, 2304, 2560, 2816, 3072, 3328, 3584, 3840, 4096,
};

uint32_t fm4_ratio_q16(int v) {
    if (v < 0)
        v = 0;
    if (v > 127)
        v = 127;
    int pos = v * 21 * 256 / 127;          /* 0..21*256 */
    int k = pos >> 8, f = pos & 255;
    uint32_t a = ratios_q8[k], b = ratios_q8[k < 21 ? k + 1 : 21];
    /* snap to the coarse value when close, so the common ratios are exact */
    if (f < 24)
        return a << 8;
    if (f > 232)
        return b << 8;
    return (a << 8) + (((b - a) << 8) * (uint32_t)f >> 8);
}

int32_t fm4_level_q12(int v) {
    if (v < 0)
        v = 0;
    if (v > 127)
        v = 127;
    return (int32_t)(v * v * 16384 / (127 * 127));
}

int32_t fm4_feedback_q12(int v) {
    if (v < 0)
        v = 0;
    if (v > 127)
        v = 127;
    return (int32_t)(v * v * 4096 / (127 * 127));
}

uint32_t fm4_inc_for(uint32_t base_inc, uint32_t ratio_q16) {
    /* base * ratio >> 16 in three 32-bit multiplies (no 64-bit multiply on
     * the target): the ratio's integer part, then its fraction against the
     * increment's two halves. The first product wraps modulo 2^32, which
     * only matters above Nyquist, where the phase wraps anyway. */
    uint32_t ri = ratio_q16 >> 16, rf = ratio_q16 & 0xFFFF;
    return base_inc * ri + (base_inc >> 16) * rf + (((base_inc & 0xFFFF) * rf) >> 16);
}
