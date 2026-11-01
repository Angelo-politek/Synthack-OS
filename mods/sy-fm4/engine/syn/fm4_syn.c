/* SY FM4 on the Syntakt's second CPU (section 7, OS 1.40A).
 *
 * SY FM4 replaces SY TONE (engine 4). The voice dispatcher (0x40004324)
 * calls, per voice and per block,
 *     prep(pitch, state, params)   params = track block + 0x1c
 *     render(out, state)           out = 32 x Q1.31 at 48 kHz
 * state is the voice's 0x708-byte slot at 0x80000000 + v * 0x708.
 *
 * Page 1/2 is SY TONE's own: TUNE RATIO PNCH DEC FDBK MOD MENV OVER, in its
 * frame slots. Page 2/2 (ALGO RAT3 LEV3 DEC3 RAT4 LEV4 DEC4 DET) comes from
 * the main CPU through the shared RAM, 16 bytes a voice at 0x700 (written by
 * the main OS patch, fm4m_dma_wait).
 *
 * ALGO 0 is SY TONE: its own prep and render, untouched, so a project made
 * with SY TONE sounds as it did. ALGO 1..11 are the four-operator
 * algorithms. They still run SY TONE's prep, which turns page 1 into the
 * voice state the firmware's shared blocks use (pitch with TUNE and PNCH,
 * RATIO, MOD, FDBK, the MENV envelope, DEC, the declick), then render four
 * operators from that state and page 2, and finish with the firmware's DEC
 * envelope, VCA and gate. OVER is applied to every voice after the engines
 * (FUN_4000112c), so not here.
 *
 * SY TONE's two operators are state slots 0 (modulator, with feedback) and
 * 1 (carrier), 0x80 bytes apart: +0x78 a 24-bit phase step at 96 kHz (its
 * render runs 64 samples a block, twice oversampled), +0x50 the slot's
 * frequency scale (0x4000000 = 1.0; the modulator's comes from RATIO
 * through table 0x40021604), +0x7c the slot's envelope (-2^31 = full,
 * rising to 0). Measured in digiemu: step0 = step1 * scale0 / 0x4000000.
 * Operators here: 1 = carrier, 2 = SY TONE's modulator (RATIO, MOD, MENV),
 * 3 and 4 from page 2/2 through the same tables as RATIO and MOD.
 */
#include <stdint.h>

#include "../fm4.h"

#define STATE_BASE 0x80000000u
#define STATE_SIZE 0x708u
#define VOICES 8
#define BLOCK 32

/* SY TONE (engine 4) and the shared blocks it calls, section 7 1.40A. */
#define TONE_PREP   ((void (*)(int32_t, uint8_t *, uint8_t *))0x4000709c)
#define TONE_RENDER ((void (*)(int32_t *, uint8_t *))0x40007214)
#define FW_ENVS     ((void (*)(uint8_t *, int32_t))0x40003c0e)
#define FW_DEC      ((void (*)(uint8_t *))0x40003d42)
#define FW_VCA      ((void (*)(int32_t *, uint8_t *))0x400045a0)
#define FW_GATE     ((void (*)(int32_t *, uint8_t *))0x400047ea)
#define FW_INTERP   ((int32_t (*)(const void *, int32_t))0x40004dc6)
#define RATIO_TABLE ((const void *)0x40021604)   /* RATIO -> slot scale */
#define LEVEL_TABLE ((const void *)0x40021804)   /* MOD -> modulation amount */

/* Page 2/2, from the main CPU (the DSP sees the shared RAM at 0). */
#define PAGE2(v) ((volatile const int16_t *)(0x700 + (v) * 16))
enum { P_ALGO, P_RAT3, P_LEV3, P_DEC3, P_RAT4, P_LEV4, P_DEC4, P_DET };

#define U32(st, off) (*(volatile uint32_t *)((st) + (off)))
#define S32(st, off) (*(volatile int32_t *)((st) + (off)))

typedef struct {
    fm4_voice_t v;
    fm4_params_t p;
    int algo;           /* latched at each new note: 0 = SY TONE */
    int32_t env3, env4; /* operators 3 and 4: Q1.31, decaying */
    int32_t k3, k4;     /* their per-block decay factors */
} voice_t;

static voice_t voices[VOICES];

extern const int32_t fm4_decay_k[128];
extern const uint32_t fm4_exp2_q16[257];

static inline int32_t mulq31(int32_t a, int32_t b) {
    /* Q1.31 x Q1.31 -> Q1.31 for a >= 0, in 32-bit multiplies. */
    uint32_t ah = (uint32_t)a >> 15;
    int32_t bh = b >> 16;
    uint32_t bl = (uint32_t)b & 0xFFFF;
    return (int32_t)(ah * bh) + (int32_t)((ah * bl) >> 16);
}

static inline int knob(int16_t raw) {
    int v = raw >> 8;
    return v < 0 ? 0 : v > 127 ? 127 : v;
}

static int voice_index(uint8_t *st) {
    uint32_t i = ((uint32_t)st - STATE_BASE) / STATE_SIZE;
    return i < VOICES ? (int)i : 0;
}

/* DET (SY DUAL VCO's: 0x4000 = 0, 1/256 semitone a unit, +-16 semitones)
 * -> a Q16.16 frequency factor 2^(semitones / 12). */
static uint32_t detune_q16(int16_t raw) {
    int32_t d = raw - 0x4000;               /* 1/256 semitone */
    if (d < -0x1000) d = -0x1000;
    if (d > 0x1000) d = 0x1000;
    int32_t oct256 = d * 256 / (12 * 256);  /* 1/256 octave */
    int32_t o = oct256 >> 8;                /* floor */
    uint32_t r = fm4_exp2_q16[oct256 & 255];
    return o >= 0 ? r << o : r >> -o;
}

/* A slot scale (0x4000000 = 1.0) -> a Q16.16 ratio. */
static inline uint32_t scale_q16(int32_t scale) {
    return scale > 0 ? (uint32_t)scale >> 10 : 0;
}

/* A modulation amount in SY TONE's units (state +0x10c: 24-bit phase per
 * full-scale modulator) -> fm4's Q4.12 index (4096 = one cycle). */
static inline int32_t amount_q12(int32_t amt) {
    return amt > 0 ? amt >> 12 : 0;
}

void syn_fm4_prep(int32_t pitch, uint8_t *st, uint8_t *params) {
    int vi = voice_index(st);
    voice_t *v = &voices[vi];
    volatile const int16_t *p2 = PAGE2(vi);
    int algo = p2[P_ALGO] >> 8;
    if (algo < 0) algo = 0;
    if (algo > FM4_ALGOS) algo = FM4_ALGOS;
    int new_note = U32(st, 0x38) != 0;
    if (new_note)
        v->algo = algo;

    TONE_PREP(pitch, st, params);
    if (v->algo == 0)
        return;

    /* Frequencies: the carrier as SY TONE plays it, operator 2 at RATIO,
     * 3 and 4 at RAT3/RAT4 through RATIO's table, 2..4 detuned by DET. */
    uint32_t car = U32(st, 0x78 + 0x80) << 9;     /* 96 kHz 24-bit -> 48 kHz 32-bit */
    uint32_t det = detune_q16(p2[P_DET]);
    uint32_t r2 = scale_q16(S32(st, 0x50));
    uint32_t r3 = scale_q16(FW_INTERP(RATIO_TABLE, p2[P_RAT3]));
    uint32_t r4 = scale_q16(FW_INTERP(RATIO_TABLE, p2[P_RAT4]));
    uint32_t dcar = fm4_inc_for(car, det);
    v->p.algo = (uint8_t)(v->algo - 1);
    v->p.inc[0] = car;
    v->p.inc[1] = fm4_inc_for(dcar, r2);
    v->p.inc[2] = fm4_inc_for(dcar, r3);
    v->p.inc[3] = fm4_inc_for(dcar, r4);

    /* Levels: MOD as SY TONE computed it; LEV3/LEV4 through MOD's table
     * the same way (table value x 2^25 as a fraction = value >> 6). */
    v->p.level[0] = 4096;
    v->p.level[1] = amount_q12(S32(st, 0x10c));
    v->p.level[2] = amount_q12(FW_INTERP(LEVEL_TABLE, p2[P_LEV3]) >> 6);
    v->p.level[3] = amount_q12(FW_INTERP(LEVEL_TABLE, p2[P_LEV4]) >> 6);
    /* FDBK: SY TONE's amount (state +0x2c) is phase per output at >> 17
     * in fm4's units; here it is the algorithm's feedback operator's. */
    int32_t fb = S32(st, 0x2c);
    v->p.feedback = fb > 0 ? fb >> 17 : 0;

    v->k3 = fm4_decay_k[knob(p2[P_DEC3])];
    v->k4 = fm4_decay_k[knob(p2[P_DEC4])];
    if (new_note) {
        fm4_init(&v->v);
        v->env3 = v->env4 = 0x7fffffff;
    }
}

void syn_fm4_render(int32_t *out, uint8_t *st) {
    voice_t *v = &voices[voice_index(st)];
    if (v->algo == 0) {
        TONE_RENDER(out, st);
        return;
    }
    /* SY TONE's envelopes (slot 0 is MENV), then operator 2 follows it. */
    FW_ENVS(st, 2);
    int32_t e2 = -S32(st, 0x7c);                   /* -2^31 = full */
    if (e2 < 0) e2 = 0x7fffffff;
    v->p.env[0] = 0x7fff;
    v->p.env[1] = (int16_t)(e2 >> 16);
    v->p.env[2] = (int16_t)(v->env3 >> 16);
    v->p.env[3] = (int16_t)(v->env4 >> 16);
    fm4_render(&v->v, &v->p, out, BLOCK);
    v->env3 = mulq31(v->env3, v->k3);
    v->env4 = mulq31(v->env4, v->k4);

    FW_DEC(st);
    FW_VCA(out, st);
    FW_GATE(out, st);
}
