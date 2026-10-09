/* readable-values: testi con unita' reali per i parametri della Syntakt (OS 1.41).
 *
 * L'OS costruisce all'avvio un oggetto per parametro (0x41B9FA24 + 84*id) e copia nel campo +20
 * un formattatore (std::function) da un prototipo. make_patch.py fa puntare quella copia, per gli
 * id gestiti qui, a rv_proto: l'OS chiama allora rv_invoke(funzione, valore 0..0x7F00, buffer).
 * L'id si ricava dall'indirizzo della funzione; ogni testo e' calcolato dagli stessi dati che usa
 * il DSP (tabelle e blocchi di parametri dell'OS), con aritmetica intera (niente FPU).
 */

typedef unsigned int u32;
typedef int s32;

#define OBJS      0x41B9FA24u           /* oggetti per-parametro (84 B, indice = id logico) */
#define OBJ_SIZE  84u
#define N_IDS     505u
#define FLT_POLE  ((const s32 *)0x4029BFFCu)            /* polo dei filtri di delay/reverb, Q31 */
#define DLY       ((const volatile short *)0x80002896u) /* delay:  TIME X WID FDBK HPF LPF REV VOL */
#define REV       ((const volatile short *)0x800028AAu) /* reverb: PRE DEC FREQ GAIN HPF LPF VOL */
#define SHELF     ((const s32 *)0x4029B7FCu)            /* reverb: shelving bilineare, c = t/(1+t), Q31 */
#define ONE       (1u << 30)                            /* 1.0 in Q30 */
#define PI_2      1686629713u                           /* pi/2 in Q30 */
#define INV_SQRT2 759250125u                            /* 1/sqrt(2) in Q30 */
#define HZ100     1527887u                              /* 100 * 48000 / pi */
#define LN1000_Q27 927143219u                           /* ln(1000) in Q27: tempo a -60 dB */
#define LN2_Q27   93032640u
#define LOG2_7F00 982298                                /* log2(0x7F00) in Q16 */

/* inviluppi: tabelle dell'OS (128 voci, indice = valore >> 8). Il filtro lavora per blocco
 * (32 campioni, CPU #1); l'ampiezza delle tracce digitali per campione (CPU #2, copia identica qui) */
#define F_DEL     ((const s32 *)0x401DEAC0u)            /* ritardo in campioni */
#define F_ATK     ((const s32 *)0x401DEEC0u)            /* incremento per blocco (negativo) */
#define F_DEC     ((const s32 *)0x401DECC0u)            /* coefficiente per blocco (negativo, msac) */
#define A_ATK     ((const s32 *)0x401DADDCu)            /* incremento per campione */
#define A_HOLD    ((const s32 *)0x401DA9DCu)            /* durata in campioni */
#define A_DEC     ((const s32 *)0x401DABDCu)            /* coefficiente per campione */
#define ANALOG    8                                     /* tracce 9..12 (indici 8..11): voci analogiche */
#define TRACKS    ((const volatile short *)0x800021B0u) /* parametri per traccia (142 B) della CPU #1 */
#define T_BASE    51                                    /* BASE a +102 (parole) */
/* filtro multimodo delle tracce digitali (CPU #2): frequenza propria dei poli misurata nell'emulatore,
 * f0 = 4.918 Hz * e^(0.065542 * FREQ), errore < 0.1% (vedi tests/test_readable_values.py) */
#define K_Y       1586415u                              /* 0.065542 / ln2 / 256, in Q32 */
#define C_Q16     32230091u                             /* 491.79 (centesimi di Hz) in Q16 */
/* filtro analogico (tracce 9..12, FX track): misurato sulla macchina (tools/measure, rec/filtro9),
 * f = 14.645 Hz * e^(0.05741 * FREQ), errore entro 1.4% tra 0 e 112 */
#define KA_Y      1389575u
#define CA_Q16    95977472u

/* traccia attiva (0..11, 12 = FX track), chiesta all'OS come fanno le pagine dei parametri:
 * 0x4001FF74(selettore), con selettore = singleton 0x4016E804() (*0x444E13F4) + 48 (0x40018458) */
#define PROJECT   (*(void *const volatile *)0x444E13F4u)
#define GET_TRACK ((s32 (*)(void *))0x4001FF74u)

static s32 active_track(void)
{
    char *s = (char *)PROJECT;
    s32 t;
    if (!s)
        return -1;
    t = GET_TRACK(s + 48);
    return t >= 0 && t <= 12 ? t : -1;
}

/* ---------------------------------------------------------------- aritmetica a 32 bit */
static u32 mulq(u32 a, u32 b, int q)    /* (a * b) >> q, 0 < q < 32, senza moltiplicazioni a 64 bit */
{
    u32 al = a & 0xFFFF, ah = a >> 16, bl = b & 0xFFFF, bh = b >> 16;
    u32 ll = al * bl, lh = al * bh, hl = ah * bl, hh = ah * bh;
    u32 mid = (ll >> 16) + (lh & 0xFFFF) + (hl & 0xFFFF);
    u32 lo = (mid << 16) | (ll & 0xFFFF);
    u32 hi = hh + (lh >> 16) + (hl >> 16) + (mid >> 16);
    return (hi << (32 - q)) | (lo >> q);
}

static u32 isqrt(u32 n)
{
    u32 r = 0, bit = 1u << 30;
    while (bit > n)
        bit >>= 2;
    while (bit) {
        if (n >= r + bit) {
            n -= r + bit;
            r = (r >> 1) + bit;
        } else {
            r >>= 1;
        }
        bit >>= 2;
    }
    return r;
}

static u32 div_shl(u32 a, u32 d, int sh)  /* (a << sh) / d, con d < 2^(32-sh); satura a 2^31 */
{
    u32 q = a / d, r = a % d;
    if (q >= (1u << (31 - sh)))
        return 1u << 31;
    return (q << sh) + (r << sh) / d;
}

static u32 asin_small(u32 x)            /* x <= 0.5 (Q30) -> asin(x) (Q30), serie di Taylor */
{
    u32 x2 = mulq(x, x, 30), t = x, s = x;
    t = mulq(t, x2, 30); s += t / 6;
    t = mulq(t, x2, 30); s += t * 3 / 40;
    t = mulq(t, x2, 30); s += t * 5 / 112;
    t = mulq(t, x2, 30); s += t * 35 / 1152;
    return s;
}

static u32 asin_q30(u32 x)
{
    if (x >= ONE)
        return PI_2;
    if (x <= ONE / 2)
        return asin_small(x);
    /* asin(x) = pi/2 - 2 asin(sqrt((1 - x) / 2)) */
    return PI_2 - 2 * asin_small(isqrt((ONE - x) << 1) << 14);
}

static const u32 exp2_bits[16] = {      /* 2^(2^-i) in Q30, i = 1..16 */
    1518500250u, 1276901417u, 1170923762u, 1121280436u, 1097253708u, 1085434106u, 1079572136u, 1076653033u,
    1075196443u, 1074468888u, 1074105294u, 1073923544u, 1073832680u, 1073787251u, 1073764537u, 1073753181u,
};

static u32 exp_hz100(u32 v, u32 k_y, u32 c_q16)   /* c * 2^(v * k_y): centesimi di Hz */
{
    u32 y = mulq(v, k_y, 16), r = ONE;  /* log2(f / f(0)), Q16 */
    int i;
    for (i = 0; i < 16; i++)
        if (y & (0x8000u >> i))
            r = mulq(r, exp2_bits[i], 30);
    return mulq(c_q16, r, 30) >> (16 - (y >> 16));
}

static u32 freq_hz100(u32 v)            /* filtro digitale */
{
    return exp_hz100(v, K_Y, C_Q16);
}

static u32 analog_hz100(u32 v)          /* filtro analogico */
{
    return exp_hz100(v, KA_Y, CA_Q16);
}

/* inviluppo d'ampiezza analogico (generatore hardware, tracce 9..12 e FX track: stesse tabelle):
 * tempo digitale * k, k misurato sulla macchina (Q8) e interpolato; i testi portano "~" */
static const unsigned char k_atk_v[] = {64, 96, 120};
static const unsigned short k_atk_q8[] = {268, 309, 274};
static const unsigned char k_dec_v[] = {16, 32, 64, 96};
static const unsigned short k_dec_q8[] = {389, 363, 352, 341};

static u32 interp_q8(u32 i, const unsigned char *xs, const unsigned short *ks, int n)
{
    int j;
    if (i <= xs[0])
        return ks[0];
    for (j = 1; j < n; j++)
        if (i <= xs[j])
            return ks[j - 1] + ((s32)ks[j] - (s32)ks[j - 1]) * (s32)(i - xs[j - 1]) / (s32)(xs[j] - xs[j - 1]);
    return ks[n - 1];
}

static u32 log2_q16(u32 v)              /* v > 0 */
{
    u32 n = 31, m, r;
    int i;
    while (!(v >> n))
        n--;
    m = n <= 30 ? v << (30 - n) : v >> (n - 30);   /* mantissa [1, 2) in Q30 */
    r = n << 16;
    for (i = 15; i >= 0; i--) {
        m = mulq(m, m, 30);
        if (m >= 2 * ONE) {
            m >>= 1;
            r |= 1u << i;
        }
    }
    return r;
}

static u32 div64(u32 hi, u32 lo, u32 d)  /* (hi:lo) / d, risultato a 32 bit (hi < d) */
{
    int i;
    for (i = 0; i < 32; i++) {
        u32 top = hi >> 31;
        hi = (hi << 1) | (lo >> 31);
        lo <<= 1;
        if (top || hi >= d) {
            hi -= d;
            lo |= 1;
        }
    }
    return lo;
}

static u32 neg_ln_q27(u32 c)            /* -ln(c), c in (0, 1) Q31 -> Q27 (preciso anche vicino a 1) */
{
    u32 k = 0, q, t, s;
    u32 n;
    while (c < (1u << 30)) {            /* porta c in [0.5, 1) */
        c <<= 1;
        k++;
    }
    q = (1u << 31) - c;                 /* 1 - c, Q31, <= 0.5 */
    s = t = q;
    for (n = 2; n < 40 && t; n++) {     /* -ln(1-q) = q + q^2/2 + q^3/3 + ... */
        t = mulq(t, q, 31);
        s += t / n;
    }
    return (s >> 4) + k * LN2_Q27;
}

/* ---------------------------------------------------------------- testo */
static char *put_u(char *b, u32 n)
{
    char t[10];
    int i = 0;
    do {
        t[i++] = (char)('0' + n % 10);
        n /= 10;
    } while (n);
    while (i)
        *b++ = t[--i];
    return b;
}

static char *put_s(char *b, const char *s)
{
    while (*s)
        *b++ = *s++;
    return b;
}

static char *put_dec1(char *b, u32 v10)  /* v10 / 10 con una cifra decimale */
{
    b = put_u(b, v10 / 10);
    *b++ = '.';
    *b++ = (char)('0' + v10 % 10);
    return b;
}

static void hz(char *b, u32 f100)       /* centesimi di Hz: 5.0Hz 47Hz 172Hz 1.01k 12.0k */
{
    u32 t = (f100 + 5) / 10, u = (f100 + 50) / 100, c = (f100 + 500) / 1000;
    if (t < 100) {
        b = put_s(put_dec1(b, t), "Hz");
    } else if (u < 1000) {
        b = put_s(put_u(b, u), "Hz");
    } else if (c < 1000) {
        b = put_u(b, c / 100);
        *b++ = '.';
        *b++ = (char)('0' + c / 10 % 10);
        *b++ = (char)('0' + c % 10);
        *b++ = 'k';
    } else {
        b = put_s(put_dec1(b, (f100 + 5000) / 10000), "k");
    }
    *b = 0;
}

static void ms(char *b, u32 samples)    /* campioni a 48 kHz: 0.8ms 12ms 337ms */
{
    u32 t10 = (samples * 10 + 24) / 48;
    if (t10 < 100)
        b = put_dec1(b, t10);
    else
        b = put_u(b, (samples + 24) / 48);
    put_s(b, "ms")[0] = 0;
}

static void put_time(char *b, u32 samples)   /* campioni a 48 kHz: 0.7ms 40ms 1.25s 30.0s INF */
{
    u32 t10;
    if (samples != 0xFFFFFFFFu && (samples & 0x80000000u)) {   /* bit alto: stima, testo con "~" */
        *b++ = '~';
        samples &= 0x7FFFFFFFu;
    }
    if (samples >= 400000000u) {
        put_s(b, "INF")[0] = 0;
        return;
    }
    t10 = (samples / 48) * 10 + (samples % 48 * 10 + 24) / 48;  /* decimi di ms */
    if (t10 < 100) {
        b = put_s(put_dec1(b, t10), "ms");
    } else if (t10 < 9995) {
        b = put_s(put_u(b, (t10 + 5) / 10), "ms");
    } else if (t10 < 99950) {
        u32 c = (t10 + 50) / 100;       /* centesimi di secondo */
        b = put_u(b, c / 100);
        *b++ = '.';
        *b++ = (char)('0' + c / 10 % 10);
        *b++ = (char)('0' + c % 10);
        *b++ = 's';
    } else {
        b = put_s(put_dec1(b, (t10 + 500) / 1000), "s");
    }
    *b = 0;
}

static u32 mag(s32 v)                   /* |v| senza overflow con segno (anche per -2^31) */
{
    return v < 0 ? 0u - (u32)v : (u32)v;
}

static u32 ramp_samples(s32 inc, u32 step)   /* rampa sull'intera escursione (2^31), inc per passo */
{
    u32 a = mag(inc);
    if (!a)
        return 0xFFFFFFFFu;
    return div64(step >> 1, (step & 1) << 31, a);   /* 2^31 * step / a */
}

static u32 t60_samples(s32 coef, u32 step)   /* decadimento esponenziale fino a -60 dB */
{
    u32 c = mag(coef);
    if (c >= (1u << 31))
        return 0xFFFFFFFFu;              /* coefficiente 1: tiene per sempre */
    if (!c)
        return 0;
    return div64(mulq(LN1000_Q27, step, 32), LN1000_Q27 * step, neg_ln_q27(c));
}

static void percent(char *b, u32 v)     /* livello rispetto a 127 */
{
    put_s(put_u(b, (v * 100 + 0x3F80) / 0x7F00), "%")[0] = 0;
}

static void db_k(char *b, u32 v, s32 ref, u32 k)  /* k*log10(v / 2^(ref/65536)) dB: -inf -24dB -3.5dB */
{
    s32 l;
    u32 d100, t;
    if (!v) {
        put_s(b, "-inf")[0] = 0;
        return;
    }
    l = (s32)log2_q16(v) - ref;          /* log2(v / riferimento), Q16 */
    if (l < 0) {
        *b++ = '-';
        l = -l;
    }
    d100 = mulq((u32)l, k, 24);         /* centesimi di dB: k = 20 o 40 log10(2) * 100 / 65536 * 2^24 */
    t = (d100 + 5) / 10;                /* un solo arrotondamento per testo */
    if (t >= 100)
        b = put_u(b, (d100 + 50) / 100);
    else
        b = put_dec1(b, t);
    put_s(b, "dB")[0] = 0;
}

#define DB40 308256u
#define DB20 154128u

static void db_square(char *b, u32 v)   /* (v / 32768)^2: mandate, mix di delay e reverb */
{
    db_k(b, v, 15 << 16, DB40);
}

static void db_vol(char *b, u32 v)      /* (v / 127)^2: LEV, VOL, IN */
{
    db_k(b, v, LOG2_7F00, DB40);
}

static void db_lin(char *b, u32 v)      /* v / 32768: guadagno dello shelving */
{
    db_k(b, v, 15 << 16, DB20);
}

/* ---------------------------------------------------------------- filtri a un polo (delay, reverb) */
static u32 pole_q30(u32 idx)
{
    s32 p = FLT_POLE[idx];
    return p > 0 ? (u32)p >> 1 : 0;
}

static u32 hz100_of(u32 a)              /* asin (Q30) -> centesimi di Hz */
{
    return (mulq(a, HZ100, 29) + 1) >> 1;
}

static u32 lpf_hz100(u32 p)              /* y = (1-p) x + p y': -3 dB a sin(w/2) = (1-p) / (2 sqrt p) */
{
    u32 s = isqrt(p);                   /* sqrt(p) * 2^15 */
    u32 x = s ? div_shl(ONE - p, s, 14) : ONE;
    return hz100_of(asin_q30(x));
}

static u32 hpf_hz100(u32 p)              /* (1+p)/2 (x - x') + p y': sin(w/2) = (1-p) / sqrt(2 (1 + p^2)) */
{
    u32 r = isqrt(ONE + mulq(p, p, 30)); /* sqrt(1 + p^2) * 2^15 */
    u32 x = mulq(div_shl(ONE - p, r, 15), INV_SQRT2, 30);
    return hz100_of(asin_q30(x));
}

static u32 shelf_hz100(u32 i)           /* angolo dello shelving: fs/pi * atan(c / (1 - c)) */
{
    u32 c = (u32)SHELF[i] >> 1, d = ONE - c;          /* Q30 */
    u32 r = isqrt(mulq(c, c, 30) + mulq(d, d, 30));    /* sqrt(c^2 + (1-c)^2), Q15 */
    return hz100_of(asin_q30(div_shl(c, r, 15)));     /* atan(t) = asin(t / sqrt(1 + t^2)) */
}

static u32 clamp(s32 v)
{
    return v < 0 ? 0 : v > 0x7F00 ? 0x7F00 : (u32)v;
}

/* ---------------------------------------------------------------- formattatore */
static void amp_analog(char *b, u32 v, u32 id)   /* 73: ATK, 75/77: DEC/REL */
{
    u32 i = v >> 8, t, k;
    if (id == 73) {
        t = ramp_samples(A_ATK[i], 1);
        k = interp_q8(i, k_atk_v, k_atk_q8, 3);
    } else {
        t = t60_samples(A_DEC[i], 1);
        k = interp_q8(i, k_dec_v, k_dec_q8, 4);
    }
    if (t >= 400000000u) {
        put_time(b, t);
        return;
    }
    t = (t >> 8) * k + (((t & 0xFF) * k) >> 8);
    put_time(b, t | 0x80000000u);
}

static void plain(char *b, u32 v, int inf)   /* come l'OS: 0..127, "INF" a 127 per DEC/REL */
{
    if (inf && (v >> 8) == 127)
        put_s(b, "INF")[0] = 0;
    else
        put_u(b, v >> 8)[0] = 0;
}

void rv_invoke(const void *fn, s32 value, char *buf)
{
    u32 off = (u32)fn - (OBJS + 20), id = off / OBJ_SIZE, v = clamp(value);

    if (off % OBJ_SIZE || id >= N_IDS)
        id = 0;                         /* non e' un nostro oggetto: numero semplice */
    switch (id) {
    case 110:                           /* delay HPF */
        hz(buf, hpf_hz100(pole_q30(v >> 6)));
        break;
    case 111:                           /* delay LPF: parte dall'HPF (indice = HPF + LPF) */
        hz(buf, lpf_hz100(pole_q30((clamp(DLY[4]) + v) >> 6)));
        break;
    case 120:                           /* reverb HPF */
        hz(buf, hpf_hz100(pole_q30(v >> 6)));
        break;
    case 121:                           /* reverb LPF */
        hz(buf, lpf_hz100(pole_q30((clamp(REV[4]) + v) >> 6)));
        break;
    case 112:                           /* delay -> reverb */
    case 114:                           /* delay mix */
    case 122:                           /* reverb mix (alias) */
    case 123:                           /* reverb mix */
        db_square(buf, v);
        break;
    case 116: {                         /* reverb pre-delay: (v^2 >> 16) + 37 campioni, max 16384 */
        u32 n = ((v * v) >> 16) + 37;
        ms(buf, n > 16384 ? 16384 : n);
        break;
    }
    case 10:                            /* LEV di traccia (anche FX track) */
    case 81:                            /* VOL di traccia */
    case 154:                           /* VOL della FX track */
    case 125:                           /* IN (alias, IN R in dual mono) */
    case 126:                           /* IN LR */
        db_vol(buf, v);
        break;
    case 78:                            /* mandate DEL/REV: tracce, FX track, ingresso esterno */
    case 79:
    case 151:
    case 152:
    case 129:
    case 130:
        db_square(buf, v);
        break;
    case 58:                            /* FREQ del filtro multimodo, tracce digitali */
    case 70:                            /* BASE: passa-alto a un polo, stessa tabella di delay/reverb */
    case 71: {                          /* WDTH: passa-basso a un polo, indice BASE + WDTH */
        s32 t = active_track();
        if (id == 58 && t >= ANALOG) {
            hz(buf, analog_hz100(v));
            break;
        }
        if (t < 0 || t >= ANALOG) {
            plain(buf, v, 0);
            break;
        }
        if (id == 58)
            hz(buf, freq_hz100(v));
        else if (id == 70)
            hz(buf, hpf_hz100(pole_q30(v >> 6)));
        else
            hz(buf, lpf_hz100(pole_q30((clamp(TRACKS[71 * t + T_BASE]) + v) >> 6)));
        break;
    }
    case 118:                           /* reverb: angolo dello shelving (indice FREQ >> 8) */
        hz(buf, shelf_hz100(v >> 8));
        break;
    case 119:                           /* reverb: guadagno dello shelving sugli acuti */
        db_lin(buf, v);
        break;
    case 66:                            /* SUS del filtro e dell'ampiezza */
    case 76:
    case 140:                           /* FX track */
    case 148:
        percent(buf, v);
        break;
    case 146:                           /* FX track: stesse tabelle */
    case 74:                            /* HOLD: stessa durata per tracce digitali e analogiche */
        put_time(buf, (v >> 8) == 127 ? 0xFFFFFFFFu : (u32)A_HOLD[v >> 8]);
        break;
    case 145:                           /* FX track: ampiezza (generatore hardware) */
    case 147:
    case 149:
        amp_analog(buf, v, id == 145 ? 73 : 75);
        break;
    case 133:                           /* FX track: filtro analogico */
        hz(buf, analog_hz100(v));
        break;
    case 63: {                          /* inviluppo del filtro, tracce digitali */
    case 64:
    case 65:
    case 67:
    case 73:                            /* inviluppo d'ampiezza, tracce digitali */
    case 75:
    case 77:
        s32 t = active_track();
        if (t >= ANALOG && t < 12 && (id == 73 || id == 75 || id == 77)) {
            amp_analog(buf, v, id);
            break;
        }
        if (t < 0 || t >= ANALOG) {
            plain(buf, v, id != 63 && id != 64 && id != 73);
            break;
        }
        switch (id) {
        case 63: put_time(buf, (u32)F_DEL[v >> 8]); break;
        case 64: put_time(buf, ramp_samples(F_ATK[v >> 8], 32)); break;
        case 65:
        case 67: put_time(buf, t60_samples(F_DEC[v >> 8], 32)); break;
        case 73: put_time(buf, ramp_samples(A_ATK[v >> 8], 1)); break;
        default: put_time(buf, t60_samples(A_DEC[v >> 8], 1)); break;
        }
        break;
    }
    default:
        plain(buf, v, 0);
        break;
    }
}

/* gestore della std::function: nessuno stato da copiare o distruggere (l'OS vuole un gestore) */
int rv_mgr(void *dst, const void *src, int op)
{
    (void)dst;
    (void)src;
    (void)op;
    return 0;
}

/* prototipo copiato dall'OS nel campo +20 degli oggetti: dati (8 B), gestore, esecutore */
const void *const rv_proto[4] __attribute__((aligned(4))) = {0, 0, (const void *)rv_mgr, (const void *)rv_invoke};
