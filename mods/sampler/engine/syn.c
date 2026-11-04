/* SAMPLER on the Syntakt's second CPU: engine 11 (SP TWINSHOT) prep and render.
 *
 * The voice dispatcher calls, per voice and per block (see mods/sy-fm4/engine/syn/fm4_syn.c):
 *     prep(pitch, state, params)   pitch = note << 16; params = the voice's frame block
 *     render(out, state)           out = 32 x Q1.31 at 48 kHz
 * Parameters are the machine's words at params + 2 * logical index (sampler.h), sent by the main CPU
 * like every machine's: saved with the sound, p-lockable, nothing to add on the main CPU.
 *
 * Per block, like the Digitakt: the part to play from the machine's position function; a window of
 * samples (loop or silence past the end); 64 points at 96 kHz (sm_interp); the Syntakt's half-band
 * filter down to 32; LEV; then the Syntakt's DEC and VCA, as SP TWINSHOT ends.
 *
 * For the main CPU's SYN page 2/2 the engine also draws up the waveform of the slot the page shows (wave_step).
 *
 * Knob H of page 2/2, one parameter per machine (logical index 0x36, which sy-fm4 saves, locks and copies to shared
 * RAM 0x700, 16 bytes a voice): ONESHOT XFAD (loop crossfade), WERP RAND (segment jumps), REPITCH KEY (the note
 * transposes), SLICE ORDR (slice picked, next, random).
 */
#include "sampler.h"

#define STATE_BASE 0x80000000u
#define STATE_SIZE 0x708u
#define VOICES 8
#define BLOCK 32

/* Section 7 (the same in 1.40A, 1.41, 1.42). */
#define SAMPLES ((volatile const uint32_t *)0x4404f754)    /* 64 slots: {length in samples, pointer} */
#define SLOTS 128                                            /* 1..64 stock, 65..128 long samples (mods/long-samples) */
#define STOCK_SLOTS 64
#define MAX_LEN 0x7ffff                                      /* SP TWINSHOT's limit (stock slots) */
#define LONG_MAX 0x1000000                                   /* 16 M samples, 5.8 min: CPU #2 holds 64 MB */
#define POOL 0x4004f750u                                     /* the stock image on CPU #2 (64 MB to 0x4404f750) */
#define LONG_MAGIC 0x53484c53u                               /* 'SHLS' */
#define FW_HALFBAND ((void (*)(void *, int32_t *, int32_t *))0x400051c6)  /* state at voice + 1388 */
#define FW_DEC ((void (*)(uint8_t *))0x40003d42)
#define FW_VCA ((void (*)(int32_t *, uint8_t *))0x400045a0)
#define HB_STATE_AT 1388

/* From the main CPU (main/smp_main.c): BPM x 120, in shared RAM. */
#define TEMPO (*(volatile const uint32_t *)0x7f0)
#define TEMPO_DEFAULT (120 * 120)
#define BAR_120 1382400000u          /* samples of one bar at 48 kHz, times BPM x 120 */

#define S32(st, off) (*(volatile int32_t *)((st) + (off)))

#define UNITY (1 << 27)              /* rate Q4.28 per 96 kHz point: 0.5 sample */
#define RATE_MAX 0x23000000          /* 140 samples per block, the Digitakt's window */
#define WIN 160

/* output scale: one sample at the level of SP TWINSHOT playing one sample (MIX at one end), Q30
 * (tests/test_sampler.py), at LEV 100 */
#define OUT_GAIN 0x272fdfe2
#define LEV_UNITY 0x6400

/* Waveform for the main CPU (main/smp_main.c), in shared RAM: it asks for slot + 1 at 0x5B0 (0 = none); here the
 * slot + 1 being drawn (0x5B4), how many of WAVE_COLS columns are ready (0x5B6), the sample's length and address
 * (0x5B8, 0x5BC: a new sample in the slot starts again), the peak of each column 0..127 (0x5C0). */
#define WAVE_REQ (*(volatile const uint16_t *)0x5b0)
#define WAVE_SLOT (*(volatile uint16_t *)0x5b4)
#define WAVE_DONE (*(volatile uint16_t *)0x5b6)
#define WAVE_LEN (*(volatile uint32_t *)0x5b8)
#define WAVE_PTR (*(volatile uint32_t *)0x5bc)
#define WAVE ((volatile uint8_t *)0x5c0)
#define WAVE_COLS 112
#define WAVE_STEP 2                  /* columns per call */

/* Knob H of page 2/2 (logical index 0x36), from the main CPU (xparams copies it with this block's locks) */
#define XPAR(v) (*(volatile const int16_t *)(0x700 + (v) * 16))
/* The machine words as set (xparams, 20 bytes a voice from logical index 0x11): the frame carries them smoothed by
 * the main CPU (0x400979CA), a few percent a block towards a new value. Choices (PLAY, SAMP, the type's three, the
 * type) come from here; TUNE, BR and LEV stay smoothed. */
#define RAW(v, lix) (*(volatile const int16_t *)(0x640 + (v) * 20 + 2 * ((lix) - 0x11)))
enum { ORDR_SLICE, ORDR_NEXT, ORDR_RAND };
#define WAVE_READS 48                /* samples read per column at most */

typedef struct {
    const int16_t *data;
    int32_t len;
    int slot, mode, active;
    int32_t ipos;                    /* absolute sample index */
    int trig;                        /* this block started the note */
    uint32_t frac;
    int32_t a, b;                    /* the part being played, from a towards b */
    uint32_t elapsed;                /* samples since the trig (WERP) */
    int32_t seg;                     /* WERP: current segment number */
    uint32_t jump;                   /* WERP RAND: phase added to this segment's */
    int32_t sel;                     /* SLICE ORDR: the slice picked at the trig, 1..64, 0 = by the knob */
    int32_t step;                    /* SLICE ORDR NEXT: trigs so far */
    int32_t hb[12];                  /* half-band filter: 8 inputs + 4 outputs */
} voice_t;

static voice_t voices[VOICES];
static int32_t *hb_ptr[VOICES];
static sm_grid_t grids[STOCK_SLOTS];                     /* a cache: slot & 63, checked on (data, len) */

/* SAMP 0..127 -> length and pointer. One list of samples, as the main CPU shows it (main/smp_main.c): the stock
 * slots that hold a sample, in slot order, then the long samples mods/long-samples sends after the stock image (at
 * POOL + 2048 x ceil(stock bytes / 2048); stock bytes = 64 x 4 + 2 x the lengths). */
static int sample_at(int slot, uint32_t *len, uint32_t *ptr) {
    *len = *ptr = 0;
    if (slot < 0 || slot >= SLOTS)
        return 0;
    uint32_t bytes = 4 * STOCK_SLOTS;
    int k = 0;
    for (int s = 0; s < STOCK_SLOTS; s++) {
        uint32_t l = SAMPLES[2 * s], p = SAMPLES[2 * s + 1];
        bytes += 2 * l;
        if (l && p) {
            if (k == slot) {
                *len = l > MAX_LEN ? MAX_LEN : l;
                *ptr = p;
                return 1;
            }
            k++;
        }
    }
    volatile const uint32_t *t = (volatile const uint32_t *)(POOL + ((bytes + 2047) & ~2047u));
    uint32_t n = (uint32_t)(slot - k);
    if (bytes > 0x4000000u - 2048 || t[0] != LONG_MAGIC || n >= t[1] || n >= 64)
        return 0;
    *ptr = t[2 + 2 * n];
    *len = t[3 + 2 * n];
    if (*len > LONG_MAX || *ptr < POOL || *ptr + 2 * *len > POOL + 0x4000000u)
        *len = *ptr = 0;
    return *len && *ptr;
}
static int16_t win[WIN];
static int32_t hb_in[8 + 2 * BLOCK];
static int32_t hb_out[BLOCK];
static const sm_par_t *pars[VOICES];
static sm_par_t pv[VOICES];                      /* the voice's parameters: frame (smoothed) and raw words */
static int32_t pitches[VOICES];
static int types[VOICES];
static int xpars[VOICES];
static uint32_t seed = 0x2545f491;

static uint32_t rnd(void) {
    seed = seed * 1664525u + 1013904223u;
    return seed;
}

extern const uint32_t sm_exp2_q30[257];

static int voice_index(uint8_t *st) {
    uint32_t i = ((uint32_t)st - STATE_BASE) / STATE_SIZE;
    return i < VOICES ? (int)i : 0;
}

static inline int32_t clamp(int32_t v, int32_t lo, int32_t hi) {
    return v < lo ? lo : v > hi ? hi : v;
}

/* 2^(semis16 / 12 / 65536) x UNITY, semitones in 16.16 */
static int32_t pitch_rate(int32_t semis16) {
    int32_t oct = sm_fmul(semis16, 0x0aaaaaab);         /* / 12: Q16 octaves */
    int32_t o = oct >> 16;
    uint32_t f = (uint32_t)oct & 0xffff;
    uint32_t i = f >> 8, r = f & 0xff;
    uint32_t m = sm_exp2_q30[i] + (((sm_exp2_q30[i + 1] - sm_exp2_q30[i]) * r) >> 8);   /* Q30, 1..2 */
    int sh = 3 - o;                                     /* Q30 -> Q4.28 x UNITY: >> (3 - octaves) */
    if (sh <= 0)
        return RATE_MAX;
    if (sh >= 32)
        return 0;
    uint32_t v = m >> sh;
    return v > RATE_MAX ? RATE_MAX : (int32_t)v;
}

static uint32_t bar_samples(int bars_log2) {
    uint32_t t = TEMPO;
    if (t < 20 * 120 || t > 400 * 120)
        t = TEMPO_DEFAULT;
    return (BAR_120 / t) << bars_log2;
}

static sm_grid_t *grid_of(voice_t *v) {
    if (v->slot < 0 || v->slot >= SLOTS || v->data == 0)
        return 0;
    sm_grid_t *g = &grids[v->slot & (STOCK_SLOTS - 1)];
    if (g->data != v->data || g->len != v->len) {
        g->data = v->data;
        g->len = v->len;
        for (int k = 0; k < SM_GRID; k++)
            g->done[k] = 0;
        g->pt[0] = 0;
        g->done[0] = 1;
    }
    return g;
}

/* The grid points the position functions of SLICE and WERP read, computed on first use. */
static void need_slice(sm_grid_t *g, const sm_par_t *p, int32_t note16) {
    int32_t grid = SM_BYTE(p, 6), sel = SM_BYTE(p, 4), l = SM_BYTE(p, 5);
    grid = grid > 4 ? 4 : grid;
    int32_t n = 4 << grid, shift = 4 - grid;
    sel = sel < 0 ? 0 : sel;
    int32_t s = (sel < n ? sel : n) - 1;
    if (s < 0)
        s = (n - 1) & ((int32_t)(int16_t)(note16 >> 16) - 12);
    l = (l > 63 ? 63 : l) + 1;
    int32_t i0 = (s << shift) << 2, i1 = i0 + ((l << shift) << 2);
    sm_grid_need(g, i0);
    sm_grid_need(g, i1);
}

static void need_werp(sm_grid_t *g, const sm_par_t *p, uint32_t phase) {
    int32_t seg = clamp((int16_t)p->w[4] >> 8, 0, 2) + 3, bars = clamp((int16_t)p->w[6] >> 8, 0, 3);
    uint32_t i0 = (phase + 0x400000u) >> 23;
    sm_grid_need(g, (int)(i0 & 255));
    sm_grid_need(g, (int)(i0 + (1u << (seg - bars))));
}

/* WERP: phase of the BARS cycle and the segment number at the voice's time. */
static uint32_t werp_phase(voice_t *v, const sm_par_t *p, int32_t *segno) {
    int32_t bars = clamp((int16_t)p->w[6] >> 8, 0, 3);
    int32_t seg = clamp((int16_t)p->w[4] >> 8, 0, 2) + 3;
    uint32_t cycle = bar_samples(bars);
    uint32_t t = v->elapsed % cycle;
    int play = SM_BYTE(p, 1);
    if ((uint32_t)(play & 0xffff) <= 1)                 /* REV, REV.L: segments last to first */
        t = cycle - 1 - t;
    uint32_t seglen = cycle >> 8 << (seg - bars);       /* samples per segment */
    *segno = seglen ? (int32_t)(v->elapsed / seglen) : 0;
    return sm_udivshl(t, cycle, 31);                    /* t < cycle: below 2^31 */
}

static void part(voice_t *v, const sm_par_t *p, int32_t note16, uint32_t phase) {
    sm_grid_t *g;
    sm_par_t q;
    if (v->mode == M_SLICE && v->sel) {         /* ORDR NEXT, RAND: the slice picked at the trig */
        q = *p;
        q.w[4] = (int16_t)(v->sel << 8);
        p = &q;
    }
    switch (v->mode) {
    case M_WERP:
        g = grid_of(v);
        if (g)
            need_werp(g, p, phase);
        sm_pos_werp(p, phase, v->len, g, &v->a, &v->b);
        break;
    case M_REPITCH:
        sm_pos_repitch(p, v->len, &v->a, &v->b);
        break;
    case M_SLICE:
        g = grid_of(v);
        if (g)
            need_slice(g, p, note16);
        sm_pos_slice(p, note16, v->len, g, &v->a, &v->b);
        break;
    default:
        sm_pos_oneshot(p, v->len, v->trig, &v->a, &v->b);
        break;
    }
}

static int loops(const sm_par_t *p, int mode) {
    int play = SM_BYTE(p, mode == M_WERP ? 5 : 1);     /* WERP: the segment's MODE */
    return (uint32_t)((play - 1) & 0xffff) <= 1;
}

static void wave_step(void) {
    uint32_t req = WAVE_REQ;
    if (req == 0 || req > SLOTS)
        return;
    uint32_t len, ptr;
    sample_at((int)req - 1, &len, &ptr);
    if (WAVE_SLOT != req || WAVE_LEN != len || WAVE_PTR != ptr) {
        WAVE_DONE = 0;
        WAVE_LEN = len;
        WAVE_PTR = ptr;
        WAVE_SLOT = (uint16_t)req;
    }
    uint32_t c = WAVE_DONE;
    const int16_t *d = (const int16_t *)ptr;
    for (int n = 0; n < WAVE_STEP && c < WAVE_COLS; n++, c++) {
        uint32_t a = len * c / WAVE_COLS, b = len * (c + 1) / WAVE_COLS, step = (b - a) / WAVE_READS + 1;
        int32_t peak = 0;
        for (uint32_t i = a; d && i < b; i += step) {
            int32_t x = d[i] < 0 ? -d[i] : d[i];
            peak = x > peak ? x : peak;
        }
        WAVE[c] = (uint8_t)(peak >> 8 > 127 ? 127 : peak >> 8);
    }
    WAVE_DONE = (uint16_t)c;
}

static void start_part(voice_t *v) {
    v->ipos = v->a;
    v->frac = 0;
}

void syn_smp_prep(int32_t pitch, uint8_t *st, uint8_t *params) {
    int vi = voice_index(st);
    voice_t *v = &voices[vi];
    sm_par_t *p = &pv[vi];
    *p = *(const sm_par_t *)(params + 2 * LIX_TUNE);
    p->w[1] = RAW(vi, LIX_PLAY);
    p->w[3] = RAW(vi, LIX_SAMP);
    p->w[4] = RAW(vi, LIX_P5);
    p->w[5] = RAW(vi, LIX_P6);
    p->w[6] = RAW(vi, LIX_P7);
    pars[vi] = p;
    pitches[vi] = pitch;
    /* TYPE travels in the overdrive's word, which the overdrive after the engines (0x4000112C) reads: no
     * overdrive on this machine */
    types[vi] = clamp(RAW(vi, LIX_TYPE) >> 8, 0, 3);
    *(volatile int16_t *)(params + 2 * LIX_TYPE) = 0;
    xpars[vi] = clamp(XPAR(vi) >> 8, 0, 127);
    wave_step();

    /* SP TWINSHOT's DEC1 left at its end: no decay of the machine's own */
    S32(st, 1000) = (int32_t)0x80000000;
    S32(st, 1004) = 0;
    S32(st, 1008) = (int32_t)0x80000000;
    hb_ptr[vi] = v->hb;

    if (S32(st, 0x38)) {                                /* trig */
        int slot = SM_BYTE(p, 3);
        v->slot = slot;
        v->data = 0;
        v->len = 0;
        uint32_t len, ptr;
        if (sample_at(slot, &len, &ptr)) {
            v->data = (const int16_t *)ptr;
            v->len = (int32_t)len;
        }
        v->mode = types[vi];
        v->trig = 1;
        v->elapsed = 0;
        v->seg = 0;
        v->jump = 0;
        v->sel = 0;
        if (v->mode == M_SLICE && xpars[vi] != ORDR_SLICE) {
            int32_t n = 4 << clamp(SM_BYTE(p, 6), 0, 4), k = clamp(SM_BYTE(p, 4), 0, 64);
            int32_t s0 = k ? (k > n ? n : k) - 1 : (n - 1) & ((int32_t)(int16_t)(pitch >> 16) - 12);
            if (xpars[vi] == ORDR_NEXT)
                v->sel = (s0 + v->step++) % n + 1;
            else
                v->sel = (int32_t)((rnd() >> 16) % (uint32_t)n) + 1;
        } else {
            v->step = 0;
        }
        v->active = v->data != 0;
        for (int k = 0; k < 12; k++)
            v->hb[k] = 0;
        uint32_t phase = 0;
        if (v->mode == M_WERP)
            phase = werp_phase(v, p, &v->seg);
        part(v, p, pitch, phase);
        start_part(v);
        if (v->a == v->b && v->mode != M_WERP)
            v->active = 0;
    }
}

/* ONESHOT XFAD: the last xf samples before the loop's end fade into the samples before the loop's start (inv =
 * 32768 / xf), so the wrap joins them without a step */
static int32_t xf, xf_inv;

/* Sample at absolute index i of the part being played: the loop wraps past b, nothing else
 * plays past b; before a the sample's own data (taps reaching back). */
static inline int16_t fetch(const voice_t *v, int32_t i, int loop, int32_t la) {
    int fwd = v->b >= v->a;
    if (fwd ? i >= v->b : i < v->b) {
        if (!loop || la == v->b)
            return 0;
        int32_t span = fwd ? v->b - la : la - v->b;
        if (span <= 0)
            return 0;
        int32_t over = fwd ? i - v->b : v->b - 1 - i;
        over %= span;
        i = fwd ? la + over : la - 1 - over;
    }
    if (i < 0 || i >= v->len)
        return 0;
    int32_t s = v->data[i];
    if (xf) {
        int32_t d = fwd ? v->b - i : i - v->b + 1;             /* 1 at the loop's end */
        int32_t j = fwd ? la - d : la - 1 + d;
        if (d >= 1 && d <= xf && j >= 0 && j < v->len) {
            int32_t o = v->data[j];
            s = o + (((s - o) * (d * xf_inv)) >> 15);
        }
    }
    return (int16_t)s;
}

void syn_smp_render(int32_t *out, uint8_t *st) {
    int vi = voice_index(st);
    voice_t *v = &voices[vi];
    const sm_par_t *p = pars[vi];
    int32_t pitch = pitches[vi];

    if (!v->active || p == 0) {
        for (int k = 0; k < BLOCK; k++)
            out[k] = 0;
        FW_DEC(st);
        FW_VCA(out, st);
        return;
    }

    /* the part, with this block's parameters (the Digitakt recomputes it every block) */
    int32_t tune = p->w[0];
    int32_t note = pitch;
    int xp = xpars[vi];
    if (v->mode == M_SLICE && SM_BYTE(p, 4) <= 0)       /* SLIC KEY: the note picks the slice, no transposing */
        note = 60 << 16;
    int32_t semis = note - (60 << 16) + ((tune - 0x4000) << 8);
    int32_t rate = pitch_rate(semis);
    if (v->mode == M_WERP) {
        int32_t segno;
        uint32_t phase = werp_phase(v, p, &segno);
        if (segno != v->seg) {                          /* next segment: from its start; RAND: maybe elsewhere */
            v->seg = segno;
            v->jump = (int32_t)((rnd() >> 16) % 127u) < xp ? (rnd() - phase) & 0x7fffffffu : 0;
            part(v, p, pitch, (phase + v->jump) & 0x7fffffffu);
            start_part(v);
        } else {
            int32_t a = v->a;
            part(v, p, pitch, (phase + v->jump) & 0x7fffffffu);
            v->a = a;
        }
        int32_t bars = clamp((int16_t)p->w[6] >> 8, 0, 3);
        if (!loops(p, M_REPITCH) && v->elapsed >= bar_samples(bars))   /* PLAY without loop: one cycle */
            v->active = 0;
    } else {
        part(v, p, pitch, 0);
    }
    if (v->mode == M_REPITCH) {
        /* the part lasts BARS (1, 2, 4, 8 bars) at the tempo; TUNE and the note do not transpose it, as on the
         * Digitakt (0x400756C0: the rate from length and bars replaces the pitch); KEY ON: they do */
        int32_t bars = clamp((int16_t)p->w[6] >> 8, 0, 3);
        int32_t n = v->b - v->a;
        n = n < 0 ? -n : n;
        uint32_t d = bar_samples(bars);
        uint32_t r = (d && (uint32_t)n < 16 * d) ? sm_udivshl((uint32_t)n, d, 27) : RATE_MAX;  /* n/d x UNITY */
        if (xp)
            r = sm_umulshr(r, (uint32_t)pitch_rate(pitch - (60 << 16) + ((tune - 0x4000) << 8)), 27);
        rate = r > RATE_MAX ? RATE_MAX : (int32_t)r;
    }
    int fwd = v->b >= v->a;
    if (!fwd)
        rate = -rate;

    int loop = loops(p, v->mode);
    int32_t la = v->a;                                  /* where a loop starts again */
    xf = 0;
    if (loop && v->mode == M_ONESHOT) {
        int32_t a, b;
        sm_pos_oneshot(p, v->len, 0, &a, &b);
        la = a;
        int32_t span = b - a < 0 ? a - b : b - a;
        xf = span * xp >> 8;                            /* XFAD 127: about half the loop */
        if (xf)
            xf_inv = 32768 / xf;
    }

    /* window: every tap of the 64 points */
    int32_t span = (int32_t)((((uint32_t)(rate < 0 ? -rate : rate) >> 4) * 63) >> 24) + 2;
    int32_t base = (rate >= 0 ? v->ipos : v->ipos - span) - 2;
    int32_t n = span + 8;
    if (n > WIN)
        n = WIN;
    int br = clamp(SM_BYTE(p, 2), 0, 127);
    int16_t mask = (int16_t)~((1 << ((br * 15 + 63) / 127)) - 1);
    for (int k = 0; k < n; k++)
        win[k] = fetch(v, base + k, loop, la) & mask;

    int32_t rel = v->ipos - base - 2;
    sm_interp(win, &v->frac, &rel, rate, hb_in + 8, 2 * BLOCK, sm_interp_table);
    int32_t moved = rel - (v->ipos - base - 2);
    v->ipos += moved;
    v->elapsed += BLOCK;

    /* past the end of the part: wrap, or stop once the taps are past it too */
    if (fwd ? v->ipos >= v->b : v->ipos < v->b) {
        if (loop) {
            if (v->mode == M_ONESHOT) {
                sm_pos_oneshot(p, v->len, 0, &v->a, &v->b);
                la = v->a;
            }
            int32_t s = fwd ? v->b - la : la - v->b;
            if (s > 0) {
                int32_t over = fwd ? v->ipos - v->b : v->b - 1 - v->ipos;
                v->ipos = fwd ? la + over % s : la - 1 - over % s;
            } else if (v->mode != M_WERP) {
                v->active = 0;
            }
        } else if (fwd ? v->ipos >= v->b + 6 : v->ipos < v->b - 6) {
            if (v->mode != M_WERP)
                v->active = 0;
        }
    }

    FW_HALFBAND((uint8_t *)&hb_ptr[vi] - HB_STATE_AT, hb_in, hb_out);
    int32_t lev = clamp(p->w[7], 0, 0x7f00);
    int32_t gain = lev == LEV_UNITY ? OUT_GAIN : (OUT_GAIN / LEV_UNITY) * lev;
    for (int k = 0; k < BLOCK; k++)
        out[k] = sm_fmul(hb_out[k], gain) << 1;
    v->trig = 0;
    FW_DEC(st);
    FW_VCA(out, st);
}
