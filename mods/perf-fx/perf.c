/* perf-fx: effetti di performance sul sequencer, sui tasti 13-16 in modo Mod A (Syntakt OS 1.41).
 *
 * FUNC + 15 sceglie il modificatore Mod A dei tasti 13-16: con questa mod quei tasti suonano un effetto
 * sul sequencer invece del Mod A dell'OS. Ogni tasto ha il suo effetto, scelto nella pagina di
 * impostazione di Mod A (M1..M4) e salvato dall'OS con il kit, come gli altri modificatori.
 *
 * Il gestore del tick del sequencer (0x4008C924) fa avanzare per ogni traccia t (0..12) l'indice di step
 * 0x43BD73FC + t, con ritorno a capo sulla lunghezza. Alla fine dell'iterazione di ogni traccia
 * (0x4008D152) pf_step_hook chiama pf_step: con un effetto attivo lo step viene riportato nel segmento di
 * L step allineato alla griglia e si tiene la posizione "reale", ripresa al rilascio (in tempo).
 * Si suonano step (note e p-lock), quindi l'effetto vale su tutte le tracce, anche le analogiche.
 * - RPT: ripete il segmento che contiene lo step appena suonato (1/16 .. 1 battuta);
 * - REV: lo stesso segmento all'indietro;
 * - HALF: mezza velocita' dentro un segmento di 8 step (ogni step due volte).
 *
 * Tasti: aggancio nel ramo dei tasti 13-16 di KeyboardView::consumeKeyEvent (0x4002EA92), dopo i
 * controlli di modo dell'OS, solo se il modificatore attivo e' Mod A; i rilasci passano anche dal
 * dispatcher degli eventi (0x4000B420). Con piu' tasti premuti vale l'ultimo.
 */

typedef unsigned int u32;
typedef int s32;

#define N_TRACKS  13
#define PAT_MODE  136057                                    /* pattern: modo della lunghezza (0 = unica) */
#define PAT_LEN   136052                                    /* pattern: lunghezza (parola) */
#define TRK_LEN   969                                       /* traccia: lunghezza propria (parola) */
#define KEY_13    36                                        /* codici dei tasti di trig 1..16: 24..39 */
#define EV_DOWN   1u                                        /* evento: bit 0 premuto */
#define KIT       (*(const char *const volatile *)0x800030B8u)  /* kit attivo */
#define KIT_MODA  0x15B6                                    /* kit: Mod A M1..M4 (parole, 0..127) */
#define MOD_A     2                                         /* modificatori: 0 retrig, 1 velocity, 2 A, 3 B */
#define PROJ      ((void *(*)(void))0x40019000u)            /* impostazioni del progetto (+44: modificatori) */
#define MOD_MODE  ((s32 (*)(void *))0x40015AF6u)            /* modificatore attivo */
#define DRAW_TEXT ((void (*)(void *, const void *, s32, s32, s32, s32, const char *, const char *, ...)) \
                   0x400F8C18u)                             /* (ctx, font, x, y, centrato, 0, sagoma, fmt, ...) */
#define FONT      ((const void *)0x402A91C0u)               /* 4x6 */

#define DATA __attribute__((section(".data")))

enum { RPT, REV, HALF };
#define NFX 12
static const unsigned char fx_kind[NFX] = {0, RPT, RPT, RPT, RPT, RPT, RPT, REV, REV, REV, REV, HALF};
static const unsigned char fx_len[NFX] = {0, 1, 2, 3, 4, 8, 16, 2, 4, 8, 16, 8};
static const char fx_text[NFX][5] = {"--", "1/16", "1/8", "3/16", "1/4", "1/2", "1BAR",
                                     "R1/8", "R1/4", "R1/2", "RBAR", "HALF"};
static const unsigned char fx_def[4] = {1, 2, 8, 11};      /* kit senza valori validi: 1/16 1/8 R1/4 HALF */

unsigned char pf_held DATA = 0;                  /* bit k: tasto 13+k tenuto */
unsigned char pf_last DATA = 0;                  /* ultimo premuto */
static unsigned char key[4] DATA = {0xFF, 0xFF, 0xFF, 0xFF};
static unsigned char last[N_TRACKS] DATA = {0};  /* ultimo step visto */
static unsigned char real[N_TRACKS] DATA = {0};  /* step reale (senza effetto) */
static unsigned char anchor[N_TRACKS] DATA = {0};
static unsigned char cnt[N_TRACKS] DATA = {0};   /* tick dall'inizio del segmento */
static unsigned char act[N_TRACKS] DATA = {0};   /* effetto in corso sulla traccia, 0 = nessuno */

static s32 word(const unsigned char *p)          /* parola con segno, anche non allineata */
{
    return (short)((p[0] << 8) | p[1]);
}

/* effetto del tasto 13+k: valore M(k+1) di Mod A nel kit */
static u32 fx_of(u32 k)
{
    const char *kit = KIT;
    s32 v;

    if (!kit)
        return fx_def[k];
    v = *(const short *)(kit + KIT_MODA + 2 * k);
    return v >= 0 && v < NFX ? (u32)v : fx_def[k];
}

static u32 cur_fx(void)
{
    u32 h = pf_held, k = pf_last;

    if (!h)
        return 0;
    if (!((h >> k) & 1))
        for (k = 0; !((h >> k) & 1); k++)
            ;
    return fx_of(k);
}

void pf_step(u32 next_track, unsigned char *step, const unsigned char *pat, const unsigned char *trk)
{
    u32 t = next_track - 1, fx = cur_fx(), p, L, i;
    s32 len = pat[PAT_MODE] ? word(trk + TRK_LEN) : word(pat + PAT_LEN);
    unsigned char cur = *step;

    if (t >= N_TRACKS || len <= 0)
        return;
    if (!fx) {                                  /* rilascio: si riprende dove si sarebbe */
        if (act[t]) {
            act[t] = 0;
            *step = real[t];
        }
        last[t] = *step;
        return;
    }
    if (cur == last[t])                         /* nessun avanzamento in questo tick */
        return;
    L = fx_len[fx];
    if (act[t] == fx) {                         /* dentro il segmento */
        real[t] = (unsigned char)(real[t] + 1u >= (u32)len ? 0 : real[t] + 1);
        cnt[t]++;
    } else {                                    /* inizio o cambio: segmento che contiene */
        if (act[t]) {                           /* lo step reale appena suonato */
            p = real[t];
            real[t] = (unsigned char)(p + 1 >= (u32)len ? 0 : p + 1);
        } else {
            p = last[t];
            real[t] = cur;
        }
        act[t] = (unsigned char)fx;
        anchor[t] = (unsigned char)(p - p % L);
        cnt[t] = (unsigned char)(fx_kind[fx] == HALF ? 2 * (p - anchor[t]) + 1 : p - anchor[t] + 1);
    }
    switch (fx_kind[fx]) {
    case REV:
        i = L - 1 - cnt[t] % L;
        break;
    case HALF:
        i = (cnt[t] >> 1) % L;
        break;
    default:
        i = cnt[t] % L;
    }
    {
        s32 v = anchor[t] + (s32)i;
        *step = (unsigned char)(v >= len ? v % len : v);
    }
    last[t] = *step;
}

/* tasti 13-16 di KeyboardView: -1 = non nostro (prosegue l'originale), 1 = gestito */
s32 pf_kbd(const char *view, const unsigned char *ev, u32 code)
{
    u32 k = code - KEY_13;
    void *proj;

    (void)view;
    if (k > 3 || !(proj = PROJ()) || MOD_MODE((char *)proj + 44) != MOD_A)
        return -1;
    if (*(const u32 *)(ev + 16) & EV_DOWN) {
        key[k] = (unsigned char)code;
        pf_last = (unsigned char)k;
        pf_held |= (unsigned char)(1u << k);
    } else
        pf_held &= (unsigned char)~(1u << k);
    return 1;
}

void pf_ev(void *root, const unsigned char *ev)  /* ogni evento di tasto: rilascio ovunque */
{
    u32 code = *(const u32 *)(ev + 12), fl = *(const u32 *)(ev + 16), k;

    (void)root;
    if (fl & EV_DOWN)
        return;
    for (k = 0; k < 4; k++)
        if (key[k] == code)
            pf_held &= (unsigned char)~(1u << k);
}

/* testo del valore; fuori scala (kit da versioni precedenti) il default del tasto, come suona.
 * fn = std::function dentro l'oggetto del parametro (84 B, 0x41B9FA24 + 84 * id) */
static const char *text(const void *fn, u32 off, s32 value)
{
    u32 k = ((u32)fn - (0x41B9FA24u + 84u * 48u + off)) / 84u;

    value = (value + 0x80) >> 8;
    if (value < 0 || value >= NFX)
        return fx_text[k < 4 ? fx_def[k] : 0];
    return fx_text[value];
}

/* formattatore del testo (+20, std::function come in readable-values) */
void pf_invoke(const void *fn, s32 value, char *buf)
{
    const char *s = text(fn, 20, value);
    while ((*buf++ = *s++))
        ;
}

/* grafica della casella (+36): l'effetto come testo, centrato come le destinazioni degli LFO */
void pf_gfx(const void *fn, s32 value, void *ctx, s32 x, s32 y)
{
    DRAW_TEXT(ctx, FONT, x + 8, y + 5, 1, 0, "XXXX", "%s", text(fn, 36, value));
}

int pf_mgr(void *dst, const void *src, int op)
{
    (void)dst;
    (void)src;
    (void)op;
    return 0;
}

const void *const pf_proto[4] __attribute__((aligned(4))) = {0, 0, (const void *)pf_mgr, (const void *)pf_invoke};
const void *const pf_gfx_proto[4] __attribute__((aligned(4))) = {0, 0, (const void *)pf_mgr, (const void *)pf_gfx};

const char pf_page_s[] = "PERF";
const char pf_page_l[] = "Perf FX";
const char pf_on[] = "Perf FX ON";
const char pf_name1_l[] = "Perf FX 1";
const char pf_name2_l[] = "Perf FX 2";
const char pf_name3_l[] = "Perf FX 3";
const char pf_name4_l[] = "Perf FX 4";

/* trampolini */
__asm__(
    "        .globl  pf_step_hook\n"
    "pf_step_hook:\n"                           /* fine dell'iterazione di una traccia (0x4008D152) */
    "        lea     -16(%sp),%sp\n"
    "        movem.l %d0-%d1/%a0-%a1,(%sp)\n"
    "        move.l  %a3,-(%sp)\n"              /* dati della traccia */
    "        move.l  %a2,-(%sp)\n"              /* pattern */
    "        move.l  %a4,-(%sp)\n"              /* &step[traccia] */
    "        move.l  %d2,-(%sp)\n"              /* traccia + 1 */
    "        jsr     pf_step\n"
    "        lea     16(%sp),%sp\n"
    "        movem.l (%sp),%d0-%d1/%a0-%a1\n"
    "        lea     16(%sp),%sp\n"
    "        addq.l  #1,%d3\n"                  /* istruzioni sostituite */
    "        addq.l  #1,%a6\n"
    "        addq.l  #1,%a5\n"
    "        rts\n"
    "        .globl  pf_kbd_hook\n"
    "pf_kbd_hook:\n"                            /* tasti 13-16 (0x4002EA92): d0 = codice, d2 = evento, */
    "        lea     -12(%sp),%sp\n"            /* a2 = vista; d0/d1/a0/a1 liberi per le chiamate */
    "        movem.l %d0/%a0-%a1,(%sp)\n"
    "        move.l  %d0,-(%sp)\n"
    "        move.l  %d2,-(%sp)\n"
    "        move.l  %a2,-(%sp)\n"
    "        jsr     pf_kbd\n"
    "        lea     12(%sp),%sp\n"
    "        move.l  %d0,%d1\n"
    "        movem.l (%sp),%d0/%a0-%a1\n"
    "        lea     12(%sp),%sp\n"
    "        tst.l   %d1\n"
    "        bmi.s   1f\n"
    "        jmp     0x4002E954\n"              /* gestito: d3 = 1, uscita */
    "1:      moveq   #35,%d1\n"                 /* istruzioni sostituite */
    "        cmp.l   %d0,%d1\n"
    "        bge.s   2f\n"
    "        jmp     0x4002EA9A\n"
    "2:      jmp     0x4002EBA6\n"
    "        .globl  pf_ev_hook\n"
    "pf_ev_hook:\n"                             /* al posto di jsr 0x4000839e (dispatcher) */
    "        move.l  8(%sp),-(%sp)\n"
    "        move.l  8(%sp),-(%sp)\n"
    "        jsr     pf_ev\n"
    "        addq.l  #8,%sp\n"
    "        jmp     0x4000839E\n"
    "        .globl  pf_page_stub\n"
    "pf_page_stub:\n"                           /* al posto di clr.l 0x41B9F9DC (pagina Mod A, all'avvio): */
    "        clr.l   0x41B9F9DC\n"              /* casella D (DEST) vuota, restano M1..M4; oggetti 48..51 */
    "        clr.l   0x41B9F9E0\n"              /* con tipo 0 (valore discreto, come LFO MODE) */
    "        clr.l   0x41BA09E4\n"
    "        clr.l   0x41BA0A38\n"
    "        clr.l   0x41BA0A8C\n"
    "        clr.l   0x41BA0AE0\n"
    "        rts\n");
