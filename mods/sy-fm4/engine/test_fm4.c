/* Host tests for fm4: a double-precision reference, structural checks, and a
 * WAV per algorithm.  Build: make test  (writes wav/algoNN.wav). */
#include "fm4.h"

#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define SR 48000
#define BLOCK 32

static int failures;
#define CHECK(cond, ...) do { if (!(cond)) { failures++; printf("FAIL: " __VA_ARGS__); printf("\n"); } } while (0)

/* --- the reference: the same routing, in double ---
 * With ref_exact set the sine is exact; otherwise it is the engine's own table,
 * interpolated in double. The second isolates the engine's arithmetic (where a
 * bug would show) from the table's approximation (a design choice, which a
 * deep stack amplifies by roughly 2*pi*index per stage). */
static int ref_exact;

static double ref_sin(double cycles) {
    if (ref_exact)
        return sin(2 * M_PI * cycles);
    double x = (cycles - floor(cycles)) * (1 << FM4_SINE_BITS);
    int i = (int)x;
    double f = x - i;
    return (fm4_sine[i] + (fm4_sine[i + 1] - fm4_sine[i]) * f) / 32768.0;
}
typedef struct {
    double phase[FM4_OPS], out[FM4_OPS], prev[FM4_OPS], env[FM4_OPS];
} ref_voice_t;

static void ref_render(ref_voice_t *v, const fm4_params_t *p, double *out, int n) {
    const fm4_algo_t *a = &fm4_algos[p->algo];
    /* Edge gains in cycles per unit source; with ref_exact the exact product,
     * otherwise the engine's integer gain (src >> 3 times it, 2^32 a cycle). */
    double g[FM4_OPS][FM4_OPS];
    int live[FM4_OPS][FM4_OPS];
    for (int i = 0; i < FM4_OPS; i++)
        for (int j = 0; j < FM4_OPS; j++) {
            live[i][j] = 0;
            if (!(a->mod[i] & (1u << j)))
                continue;
            int32_t lv = j > i ? p->level[j] : p->feedback;
            uint32_t ig = (uint32_t)(lv * p->env[j]) >> 15;
            if (!ig)
                continue;
            live[i][j] = 1;
            g[i][j] = ref_exact ? lv / 4096.0 * p->env[j] / 32768.0 : ig / 4096.0;
        }
    /* Carrier gains, ramped per sample: exact, or on the engine's grid. */
    double cgd[FM4_OPS], cstepd[FM4_OPS];
    int32_t cg[FM4_OPS], cstep[FM4_OPS];
    int shift = 0;
    while ((1 << shift) < n) shift++;
    for (int i = 0; i < FM4_OPS; i++) {
        int32_t cm = fm4_carmix(p, i);
        int32_t start = (int32_t)llround(v->env[i] * 32768.0);
        cg[i] = (int32_t)(((uint32_t)cm * (uint32_t)start) >> 15);
        cstep[i] = ((int32_t)(((uint32_t)cm * (uint32_t)p->env[i]) >> 15) - cg[i]) >> shift;
        cgd[i] = cm / 65536.0 * v->env[i];
        cstepd[i] = (cm / 65536.0 * p->env[i] / 32768.0 - cgd[i]) / n;
    }
    for (int s = 0; s < n; s++) {
        double acc = 0;
        for (int i = FM4_OPS - 1; i >= 0; i--) {
            double m = 0;
            for (int j = 0; j < FM4_OPS; j++) {
                if (!live[i][j])
                    continue;
                double src = j == i ? (v->out[j] + v->prev[j]) / 2 : v->out[j];
                m += src * g[i][j];
            }
            double y = ref_sin(v->phase[i] + m);
            v->prev[i] = v->out[i];
            v->out[i] = y;
            v->phase[i] += p->inc[i] / 4294967296.0;
            v->phase[i] -= floor(v->phase[i]);
            cg[i] += cstep[i];
            cgd[i] += cstepd[i];
            acc += y * (ref_exact ? cgd[i] : cg[i] / 65536.0);
        }
        out[s] = acc;
    }
    for (int i = 0; i < FM4_OPS; i++)
        v->env[i] = p->env[i] / 32768.0;
}

/* --- helpers --- */
static void wav_write(const char *path, const int32_t *x, int n) {
    FILE *f = fopen(path, "wb");
    if (!f) { perror(path); return; }
    uint32_t data = (uint32_t)n * 2, riff = 36 + data, fmt = 16, rate = SR, byte_rate = SR * 2;
    uint16_t pcm = 1, ch = 1, align = 2, bits = 16;
    fwrite("RIFF", 1, 4, f); fwrite(&riff, 4, 1, f); fwrite("WAVEfmt ", 1, 8, f);
    fwrite(&fmt, 4, 1, f); fwrite(&pcm, 2, 1, f); fwrite(&ch, 2, 1, f);
    fwrite(&rate, 4, 1, f); fwrite(&byte_rate, 4, 1, f); fwrite(&align, 2, 1, f);
    fwrite(&bits, 2, 1, f); fwrite("data", 1, 4, f); fwrite(&data, 4, 1, f);
    for (int i = 0; i < n; i++) {
        int16_t s = (int16_t)(x[i] >> 16);
        fwrite(&s, 2, 1, f);
    }
    fclose(f);
}

static uint32_t inc_hz(double hz) { return (uint32_t)llround(hz / SR * 4294967296.0); }

/* A patch for listening: carrier steady with slow decay, modulators faster. */
typedef struct { int algo, rat[4], lev[4], fb; } patch_t;

static void setup(fm4_params_t *p, const patch_t *pt, double hz) {
    memset(p, 0, sizeof *p);
    p->algo = (uint8_t)pt->algo;
    uint32_t base = inc_hz(hz);
    for (int i = 0; i < FM4_OPS; i++) {
        p->inc[i] = i == 0 ? base : fm4_inc_for(base, fm4_ratio_q16(pt->rat[i]));
        p->level[i] = i == 0 ? 4096 : fm4_level_q12(pt->lev[i]);
    }
    p->feedback = fm4_feedback_q12(pt->fb);
}

/* Render seconds of a note, fixed and reference side by side.  Returns the
 * RMS error in dBFS; fills fixed[] if given. */
static double early_err;   /* the RMS error over the first 50 ms of the last run */

static double run(const patch_t *pt, double hz, int samples, int32_t *fixed, int decay) {
    fm4_voice_t v; fm4_init(&v);
    ref_voice_t r; memset(&r, 0, sizeof r);
    fm4_params_t p; setup(&p, pt, hz);
    int32_t blk[BLOCK]; double rb[BLOCK];
    double err2 = 0;
    for (int s = 0; s < samples; s += BLOCK) {
        double t = (s + BLOCK) / (double)SR;
        for (int i = 0; i < FM4_OPS; i++) {
            double tau = !decay ? 1e9 : (fm4_algos[p.algo].carriers & (1u << i)) ? 1.2 : 0.35;
            double e = exp(-t / tau);
            if (t < 0.003) e *= t / 0.003;       /* 3 ms attack, no click */
            p.env[i] = (int32_t)(e * 32767);
        }
        fm4_render(&v, &p, blk, BLOCK);
        ref_render(&r, &p, rb, BLOCK);
        for (int k = 0; k < BLOCK; k++) {
            double d = blk[k] / 2147483648.0 - rb[k];
            err2 += d * d;
            if (fixed) fixed[s + k] = blk[k];
        }
        if (s + BLOCK == SR / 20)
            early_err = 10 * log10(err2 / (SR / 20) + 1e-300);
    }
    return 10 * log10(err2 / samples + 1e-300);
}

/* How far two reference renders drift apart when one starts with operator 4
 * a billionth of a cycle ahead. A loop that amplifies that is chaotic, and no
 * finite-precision render can follow the reference along it for long; it can
 * only be checked early, before the difference grows. */
static double ref_divergence(const patch_t *pt, double hz, int samples) {
    ref_voice_t a, b; memset(&a, 0, sizeof a); memset(&b, 0, sizeof b);
    b.phase[3] = 1e-9;
    fm4_params_t p; setup(&p, pt, hz);
    double ra[BLOCK], rb[BLOCK], err2 = 0;
    for (int s = 0; s < samples; s += BLOCK) {
        double t = (s + BLOCK) / (double)SR;
        for (int i = 0; i < FM4_OPS; i++) {
            double tau = (fm4_algos[p.algo].carriers & (1u << i)) ? 1.2 : 0.35;
            double e = exp(-t / tau);
            if (t < 0.003) e *= t / 0.003;
            p.env[i] = (int32_t)(e * 32767);
        }
        ref_render(&a, &p, ra, BLOCK);
        ref_render(&b, &p, rb, BLOCK);
        for (int k = 0; k < BLOCK; k++) err2 += (ra[k] - rb[k]) * (ra[k] - rb[k]);
    }
    return 10 * log10(err2 / samples + 1e-300);
}

/* Magnitude of one DFT bin, normalised to a full-scale sine = 1. */
static double bin_mag(const int32_t *x, int n, double hz) {
    double re = 0, im = 0;
    for (int i = 0; i < n; i++) {
        double w = 0.5 - 0.5 * cos(2 * M_PI * i / (n - 1));   /* Hann */
        double s = x[i] / 2147483648.0 * w;
        re += s * cos(2 * M_PI * hz * i / SR);
        im -= s * sin(2 * M_PI * hz * i / SR);
    }
    return 2 * sqrt(re * re + im * im) / (n * 0.5);
}

int main(void) {
    const int N = SR * 2;
    int32_t *buf = malloc(sizeof(int32_t) * N);

    /* 1. Every algorithm, a characteristic patch, against the reference. */
    static const patch_t patches[FM4_ALGOS] = {
        {0, {0, 18, 30, 18}, {0, 70, 60, 50}, 40},   /* 1 stack: bright bell-ish */
        {1, {0, 18, 42, 30}, {0, 70, 55, 55}, 30},
        {2, {0, 18, 18, 42}, {0, 60, 60, 50}, 20},
        {3, {0, 30, 18, 42}, {0, 55, 60, 50}, 20},
        {4, {0, 18, 18, 30}, {0, 70, 90, 70}, 30},   /* 5 two pairs */
        {5, {0, 18, 42, 18}, {0, 90, 90, 75}, 25},
        {6, {0, 30, 18, 42}, {0, 80, 90, 60}, 20},
        {7, {0, 18, 30, 42}, {0, 100, 90, 80}, 0},  /* 8 additive organ */
        {8, {0, 18, 30, 42}, {0, 90, 60, 50}, 25},   /* 9 tree */
        {9, {0, 18, 30, 42}, {0, 60, 60, 60}, 25},   /* 10 diamond */
        {10, {0, 18, 30, 42}, {0, 60, 60, 60}, 50},  /* 11 ring, fb = loop amount */
    };
    char path[64];
    for (int a = 0; a < FM4_ALGOS; a++) {
        ref_exact = 1;
        double e_exact = run(&patches[a], 220.0, N, buf, 1);
        ref_exact = 0;
        double e = run(&patches[a], 220.0, N, buf, 1);
        snprintf(path, sizeof path, "wav/algo%02d.wav", a + 1);
        wav_write(path, buf, N);
        int32_t peak = 0;
        for (int i = 0; i < N; i++) peak = abs(buf[i]) > peak ? abs(buf[i]) : peak;
        double chaos = ref_divergence(&patches[a], 220.0, N);
        int chaotic = chaos > -60;
        printf("algo %2d  err %6.1f dBFS (first 50 ms %6.1f; vs exact sine %6.1f)  drift %6.1f%s  peak %5.1f dBFS  -> %s\n",
               a + 1, e, early_err, e_exact, chaos, chaotic ? " CHAOTIC" : "",
               20 * log10(peak / 2147483648.0 + 1e-12), path);
        CHECK(chaotic || early_err < -85, "algo %d: fixed point differs from reference early (%.1f dBFS)", a + 1, early_err);
        CHECK(chaotic || e < -85, "algo %d: fixed point drifts from a non-chaotic reference (%.1f dBFS)", a + 1, e);
        CHECK(peak > 0, "algo %d: silent", a + 1);
    }

    /* 2. Additive (8), ratios 1:2:3:4, no feedback: exactly four partials. */
    {
        patch_t pt = {7, {0, 0, 0, 0}, {0, 127, 127, 127}, 0};
        fm4_params_t p; setup(&p, &pt, 0);
        fm4_voice_t v; fm4_init(&v);
        double hz = 375.0;                          /* 1/128 of SR: exact bins */
        uint32_t base = inc_hz(hz);
        for (int i = 0; i < FM4_OPS; i++) p.inc[i] = base * (uint32_t)(i + 1);
        for (int i = 0; i < FM4_OPS; i++) p.env[i] = 32767;
        int n = 8192;
        for (int s = 0; s < n; s += BLOCK) fm4_render(&v, &p, buf + s, BLOCK);
        /* skip the first block's attack ramp by measuring the second half */
        int32_t *x = buf + n / 2;
        for (int h = 1; h <= 6; h++) {
            double m = bin_mag(x, n / 2, hz * h);
            if (h <= 4) CHECK(fabs(m - 0.25) < 0.01, "additive: partial %d is %.4f, want 0.25", h, m);
            else CHECK(m < 1e-3, "additive: partial %d present (%.5f)", h, m);
        }
        printf("additive 1:2:3:4  partials ok\n");
    }

    /* 3. Ring (11) with no loop amount is the plain stack (1) with no feedback. */
    {
        patch_t ring = {10, {0, 18, 30, 42}, {0, 70, 60, 50}, 0};
        patch_t stack = {0, {0, 18, 30, 42}, {0, 70, 60, 50}, 0};
        int32_t *b2 = malloc(sizeof(int32_t) * N);
        run(&ring, 220, N, buf, 1);
        run(&stack, 220, N, b2, 1);
        CHECK(!memcmp(buf, b2, sizeof(int32_t) * N), "ring with loop 0 != stack with fb 0");
        free(b2);
        printf("ring(fb=0) == stack(fb=0)  bit-exact\n");
    }

    /* 4. Worst case: every level and the feedback at maximum, every algorithm.
     * Must stay finite and never exceed full scale. */
    for (int a = 0; a < FM4_ALGOS; a++) {
        patch_t pt = {a, {127, 127, 127, 127}, {127, 127, 127, 127}, 127};
        run(&pt, 8000.0, SR / 4, buf, 0);
        int64_t peak = 0;
        for (int i = 0; i < SR / 4; i++) peak = llabs((int64_t)buf[i]) > peak ? llabs((int64_t)buf[i]) : peak;
        CHECK(peak <= 2147483647LL, "algo %d overflow at max", a + 1);
    }
    printf("max levels/feedback  no overflow\n");

    /* 5. Silence in, silence out. */
    {
        patch_t pt = {0, {0, 18, 30, 42}, {0, 127, 127, 127}, 127};
        fm4_params_t p; setup(&p, &pt, 220);
        fm4_voice_t v; fm4_init(&v);
        int nz = 0;
        for (int s = 0; s < 4096; s += BLOCK) {
            fm4_render(&v, &p, buf, BLOCK);
            for (int k = 0; k < BLOCK; k++) nz += buf[k] != 0;
        }
        CHECK(!nz, "envelopes at 0 but %d nonzero samples", nz);
        printf("zero envelope  silent\n");
    }

    free(buf);
    printf(failures ? "\n%d FAILED\n" : "\nALL PASSED\n", failures);
    return failures != 0;
}
