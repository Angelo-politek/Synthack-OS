/* fm4: a 4-operator FM voice with 11 routing algorithms.
 *
 * Fixed point throughout, 32-bit only inside the per-sample loop, so the same
 * source builds for the host and for the ColdFire voice CPU (no FPU, no
 * 64-bit multiply in the hot path).
 *
 * Operators are numbered 1..4 in the docs and 0..3 in code. They are evaluated
 * 4, 3, 2, 1 each sample. An edge from a later-evaluated operator (or an
 * operator to itself) therefore reads that operator's previous sample: those
 * are the feedback edges, and they are scaled by the feedback amount rather
 * than by the source's level. A self edge reads the mean of the last two
 * samples, as on the DX, which keeps high feedback from oscillating at Nyquist.
 */
#ifndef FM4_H
#define FM4_H

#include <stdint.h>

#define FM4_OPS 4
#define FM4_ALGOS 11
#define FM4_SINE_BITS 10            /* 1024-entry sine table */

/* One algorithm: which operators modulate each operator, and which are heard. */
typedef struct {
    uint8_t mod[FM4_OPS];   /* bit j: operator j modulates this operator */
    uint8_t carriers;       /* bit i: operator i goes to the output */
} fm4_algo_t;

extern const fm4_algo_t fm4_algos[FM4_ALGOS];
extern const int16_t fm4_sine[(1 << FM4_SINE_BITS) + 1];

/* What the voice is told, per block. Gains are Q4.12 (4096 = 1.0). */
typedef struct {
    uint8_t algo;                   /* 0..10 */
    uint32_t inc[FM4_OPS];          /* phase increment per sample, 2^32 = 1 cycle */
    int32_t level[FM4_OPS];         /* modulation index or output level, Q4.12 */
    int32_t feedback;               /* feedback / loop amount, Q4.12 */
    int32_t env[FM4_OPS];           /* envelope target at the block's end, Q1.15 */
} fm4_params_t;

typedef struct {
    uint32_t phase[FM4_OPS];
    int32_t out[FM4_OPS];           /* latest output, Q1.23, envelope applied */
    int32_t prev[FM4_OPS];          /* the sample before that */
    int32_t env[FM4_OPS];           /* envelope at the start of the block, Q1.15 */
} fm4_voice_t;

void fm4_init(fm4_voice_t *v);

/* Render n samples (n a power of two, at most 256), adding nothing: out[] is
 * overwritten, Q1.31. A carrier's envelope ramps linearly over the block from
 * the voice's current value to p->env; a modulator's envelope (p->env) scales
 * its modulation edges for the whole block. */
void fm4_render(fm4_voice_t *v, const fm4_params_t *p, int32_t *out, int n);

/* Parameter helpers for the UI's 0..127 values (not used in the hot path). */
uint32_t fm4_ratio_q16(int v);      /* 0..127 -> ratio, Q16.16 */
int32_t fm4_level_q12(int v);       /* 0..127 -> 0..4.0, squared curve */
int32_t fm4_feedback_q12(int v);    /* 0..127 -> 0..1.0, squared curve */
uint32_t fm4_inc_for(uint32_t base_inc, uint32_t ratio_q16);
int32_t fm4_carmix(const fm4_params_t *p, int i);  /* carrier gain x mix, Q16 */

#endif
