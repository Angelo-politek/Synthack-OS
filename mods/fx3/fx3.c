/* fx3: terza mandata effetti (Syntakt OS 1.42): chorus, flanger, phaser, crusher.
 *
 * Audio (funzione di mix a blocchi 0x4008F242, 32 campioni a 48 kHz):
 * - nel ciclo per traccia (0x4008F418) fx3_trk_hook prende i guadagni sinistro/destro della traccia
 *   (livello e pan) e il valore di SND3 (parola +106 del motore = id 72, salvato per traccia) e ne
 *   ricava il bersaglio mono della mandata (a meta': si sommano coppie di campioni), come l'OS fa per
 *   DEL e REV, e segnala quando un bersaglio cambia (moving): a regime la rampa non gira;
 * - dopo le somme del master (0x4008FB7C) fx3_mix_hook somma le tracce nel bus 3 a 24 kHz (coppie di
 *   campioni mediate, EMAC: un passaggio per traccia se mandano una o due tracce, se no uno solo per tutte),
 *   lo passa all'effetto (a 24 kHz) e aggiunge il ritorno, riportato a 48 kHz per interpolazione lineare,
 *   al bus diretto (0x8000DAD0), con la convenzione di segno dell'OS;
 * - nel blocco seguente fx3_del_hook / fx3_rev_hook prendono il posto dei cicli dell'OS che completano i bus
 *   d'ingresso di delay e riverbero (0x4008F852, 0x4008F98A) e nello stesso passaggio aggiungono l'uscita
 *   dell'effetto, scalata dalle mandate DEL e REV (0x8000DBD0): un blocco di ritardo (0,67 ms).
 *
 * Il carico conta: l'OS usa gia' quasi tutta la CPU e l'interfaccia vive del resto. L'interrupt audio non sta
 * nella cache istruzioni da 8 KB: ogni riga di 16 byte di codice eseguita e ogni riga di dati in DDR toccata
 * costano una lettura dalla DDR a ogni blocco (tools/emu/cycles.py). Per questo il percorso di ogni blocco e'
 * in assembly compatto (sotto, "percorso caldo"), con lo stato in un blocco solo (fx3_s) e i valori che
 * dipendono dalle manopole calcolati quando cambiano (derive); in C solo i casi rari (parametri cambiati,
 * cambio di tipo, svuotamento della linea) e il crusher. Senza mandate, con gli ingressi muti (sequencer
 * fermo) e la coda esaurita resta solo la somma o nemmeno quella. Istruzioni per blocco in tests/test_fx3.py.
 *
 * Effetti (TYPE): CHOR e FLNG = una linea mono con due prese (L/R) modulate; PHSR = 4 celle allpass,
 * uscita destra complementare (WID); CRSH = tenuta del campione, bit ridotti e drive (mono).
 *
 * Interfaccia: pagina 2 del tab REVERB (pagina 25 dell'OS, "OB8", inutilizzata) con TYPE e 7 controlli:
 * id nascosti delle tracce MIDI (246..253) tramite mods/vparams. Nomi, testi e icone (prese da parametri
 * dell'OS simili) cambiano col tipo; il crusher lascia vuote le caselle che non usa. La
 * classe dei tab DELAY/REVERB disegna le caselle 5-6 come filtro: per la pagina 25 si usa il disegno
 * generico a 8 caselle (fx3_draw_hook). SND3 e la mandata DEL usano la grafica della mandata del delay.
 *
 * Salvataggio: nel kit del pattern (*0x800030BC = parametri della traccia FX, una parola per id interno),
 * 4 parole che l'OS non usa: id interni 0, 0x1A (tra delay e riverbero), 0x38 (id 144, "Delay Time"
 * dell'amp FX, nascosto) e 0x46 (dopo l'amp FX). Un byte per parametro, XOR il default: kit vecchi
 * (parole a zero) = valori di default.
 */

typedef unsigned int u32;
typedef int s32;
typedef short s16;
typedef unsigned short u16;

#include "fx3_tables.h"

#define DATA __attribute__((section(".data")))
#define S_(x)     #x
#define XS(x)     S_(x)                                    /* costante come testo, per l'assembly */
#define H         16                                       /* campioni per blocco a 24 kHz */
#define DL        1024                                     /* linea a 24 kHz: 42 ms (TIME + DEP <= 38 ms) */
#define DL_M      ((s16 *)(MODAREA_RAM + 0xE000))          /* linea mono + copia a +DL (area mod azzerata) */
#define KIT       (*(char *const volatile *)0x800030BCu)   /* kit del pattern attivo */
#define W_IN      110                                      /* parola 0x37 del kit: SND3 dell'ingresso (basso), routing (bit 8) */
#define UI_ROOT   (*(char *const volatile *)0x444E2334u)
#define DRAW_TEXT ((void (*)(void *, const void *, s32, s32, s32, s32, const char *, const char *, ...))                    0x400F8DDCu)                            /* (ctx, font, x, y, centrato, 0, sagoma, fmt, ...) */
#define FONT      ((const void *)0x402A9510u)              /* 4x6 */

enum { P_TYPE, P_SPD, P_DEP, P_TIME, P_FDBK, P_WID, P_DSND, P_RSND, NP };
enum { CHOR, FLNG, PHSR, CRSH, NT };
static const unsigned short ids[NP] = {246, 247, 248, 250, 251, 252, 249, 253};
static const unsigned char maxv[NP] = {NT - 1, 127, 127, 127, 127, 127, 127, 127};
static const unsigned char defv[NP] = {0, 60, 64, 64, 0, 64, 0, 0};
static const unsigned char woff[4] = {0, 2 * 0x1A, 2 * 0x38, 2 * 0x46}; /* parole nel kit */
u16 fx3_fallback[0x47] DATA = {0};                        /* nessun kit (ancora): valori in RAM */

/* ---- stato dell'interrupt audio: un blocco solo, allineato alle righe di cache da 16 B. Prima i guadagni
 * (indirizzabili con l'indice di traccia: (a5,dN*4) vuole uno spostamento sotto 128), poi i valori di ogni
 * blocco, poi quelli del phaser e del crusher (righe toccate solo con quel tipo), infine bus e uscita. Il
 * chorus tocca 23 righe. Gli offset servono all'assembly: O_* e i controlli sotto. */
#define O_CUR    0      /* s32[16]: guadagni del blocco (levigati verso i bersagli): 0..7 digitali, 8..11 analogiche, 12..13 ingresso, 14..15 FX track */
#define O_TGT    64     /* s32[16]: bersagli mono (meta') */
#define O_SEEN   128    /* u32[2]: ultime parole del kit lette, a coppie (1: rilettura) */
#define O_MOVING 136    /* != 0: un bersaglio e' cambiato */
#define O_RAMP   140    /* != 0: un guadagno non ha ancora raggiunto il bersaglio */
#define O_LIVE   144    /* canali con guadagno (bit 0..15; 14..15 FX track) */
#define O_QUIET  148    /* blocchi consecutivi senza ingresso ne' coda */
#define O_IDLE   152    /* 1 = niente da fare (e wet non valido) */
#define O_TYPE   156    /* tipo per cui e' preparato lo stato dell'effetto */
#define O_CLR    160    /* blocchi di svuotamento della linea che restano */
#define O_WPOS   164
#define O_PHASE  168
#define O_DPOS   172    /* u32[2]: ritardo L/R (campioni Q8) */
#define O_RET_H  180    /* s32[2]: ultimo mezzo campione L/R per l'interpolazione: ritorno, DEL, REV */
#define O_DLY_H  188
#define O_REV_H  196
#define O_DS     204    /* guadagni Q15 delle mandate DEL e REV di FX3 */
#define O_RS     208
#define O_P      212    /* u8[8]: parametri della pagina */
#define O_BASE   220    /* chorus / flanger */
#define O_DEP    224
#define O_OFF    228
#define O_INC    232
#define O_FB     236    /* retroazione Q15 */
#define O_PINC   240    /* phaser */
#define O_PX     244
#define O_PDEP   248
#define O_PFB    252
#define O_PW     256
#define O_PA     260    /* coefficiente del blocco */
#define O_PS     264    /* s32[5]: stato delle celle */
#define O_CN     284    /* crusher */
#define O_CMASK  288
#define O_CG     292
#define O_CCNT   296
#define O_CHOLD  300
#define O_BUS    304    /* s32[16]: bus 3 mono a 24 kHz */
#define O_WET    368    /* s16[32]: uscita dell'effetto (16 bit), L/R alternati */

struct fx3s {
    s32 cur[16], tgt[16];
    u32 seen[2];
    s32 moving;
    u32 ramp, live, quiet;
    s32 idle;
    u32 type, clr, wpos, phase, dpos[2];
    s32 ret_h[2], dly_h[2], rev_h[2], ds, rs;
    unsigned char p[NP];
    u32 base, dep, off, inc;
    s32 fb;
    u32 pinc, px, pdep;
    s32 pfb, pw, pa, ps[5];
    u32 cn;
    s32 cmask, cg;
    u32 ccnt;
    s32 chold;
    s32 bus[H];
    s16 wet[2 * H];
};
struct fx3s fx3_s DATA __attribute__((aligned(16))) = {.seen = {1, 1}, .idle = 1, .p = {0, 60, 64, 64, 0, 64, 0, 0}};
#define S         fx3_s
#define fx3_p     (fx3_s.p)
#define OFS(f, o) _Static_assert(__builtin_offsetof(struct fx3s, f) == (o), #f)
OFS(cur, O_CUR); OFS(tgt, O_TGT); OFS(seen, O_SEEN); OFS(moving, O_MOVING); OFS(ramp, O_RAMP); OFS(live, O_LIVE);
OFS(quiet, O_QUIET); OFS(idle, O_IDLE); OFS(type, O_TYPE); OFS(clr, O_CLR); OFS(wpos, O_WPOS); OFS(phase, O_PHASE);
OFS(dpos, O_DPOS); OFS(ret_h, O_RET_H); OFS(dly_h, O_DLY_H); OFS(rev_h, O_REV_H); OFS(ds, O_DS); OFS(rs, O_RS);
OFS(p, O_P); OFS(base, O_BASE); OFS(dep, O_DEP); OFS(off, O_OFF); OFS(inc, O_INC); OFS(fb, O_FB);
OFS(pinc, O_PINC); OFS(px, O_PX); OFS(pdep, O_PDEP); OFS(pfb, O_PFB); OFS(pw, O_PW); OFS(pa, O_PA); OFS(ps, O_PS);
OFS(cn, O_CN); OFS(cmask, O_CMASK); OFS(cg, O_CG); OFS(ccnt, O_CCNT); OFS(chold, O_CHOLD); OFS(bus, O_BUS);
OFS(wet, O_WET);
_Static_assert(sizeof(struct fx3s) == O_WET + 4 * H, "fx3_s");

/* nomi dello stato per i test e i descrittori */
__asm__(
    "        .globl  fx3_cur, fx3_tgt, fx3_moving, fx3_idle, fx3_clr, fx3_p, fx3_bus, fx3_wet\n"
    "        .set    fx3_cur, fx3_s + " XS(O_CUR) "\n"
    "        .set    fx3_tgt, fx3_s + " XS(O_TGT) "\n"
    "        .set    fx3_moving, fx3_s + " XS(O_MOVING) "\n"
    "        .set    fx3_idle, fx3_s + " XS(O_IDLE) "\n"
    "        .set    fx3_clr, fx3_s + " XS(O_CLR) "\n"
    "        .set    fx3_p, fx3_s + " XS(O_P) "\n"
    "        .set    fx3_bus, fx3_s + " XS(O_BUS) "\n"
    "        .set    fx3_wet, fx3_s + " XS(O_WET) "\n");

/* ---- salvataggio nel kit */
static char *kit(void)
{
    char *k = KIT;
    return k ? k : (char *)fx3_fallback;
}

static u32 word(const char *k, u32 j)
{
    return *(const volatile u16 *)(k + woff[j]);
}

static u32 decode(u32 w, u32 i)                          /* byte del parametro i dalla sua parola */
{
    u32 v = ((i & 1 ? w : w >> 8) & 0xFF) ^ defv[i];
    return v > maxv[i] ? maxv[i] : v;
}

/* nomi e testi della pagina secondo il tipo (stringhe in RAM: i descrittori puntano qui) */
#include "fx3_names.h"
static const char *const n_s[NT][5] = {{"SPD", "DEP", "TIME", "FDBK", "WID"},
                                       {"SPD", "DEP", "TIME", "FDBK", "WID"},
                                       {"SPD", "DEP", "FREQ", "FDBK", "WID"},
                                       {"SRR", "BITS", "DRV", "-", "-"}};
static const char *const n_l[NT][5] = {
    {"Chorus Speed", "Chorus Depth", "Chorus Delay", "Chorus Feedback", "Chorus Width"},
    {"Flanger Speed", "Flanger Depth", "Flanger Delay", "Flanger Feedback", "Flanger Width"},
    {"Phaser Speed", "Phaser Depth", "Phaser Frequency", "Phaser Feedback", "Phaser Width"},
    {"Crusher Rate", "Crusher Bits", "Crusher Drive", "-", "-"}};
static const char *const t_s[NT] = {"CHOR", "FLNG", "PHSR", "CRSH"};
static const char *const t_l[NT] = {"Chorus", "Flanger", "Phaser", "Crusher"};
static char *const name_s[5] = {fx3_n1_s, fx3_n2_s, fx3_n3_s, fx3_n4_s, fx3_n5_s};
static char *const name_l[5] = {fx3_n1_l, fx3_n2_l, fx3_n3_l, fx3_n4_l, fx3_n5_l};
static u32 named DATA = 0xFF;                             /* tipo di nomi, icone e caselle (0xFF: da fare) */

/* icone: per ogni casella la coppia (+36 grafica, +68 stile) di un parametro dell'OS dal significato
 * simile. Dei prototipi (std::function costruite all'avvio) si prende solo l'invoker (+12): nessuno di
 * quelli scelti usa i dati del functor; il gestore e' fx3_mgr (nessuna copia o distruzione sullo heap
 * condiviso col prototipo). 0 = vuoto. */
#define OBJ(id)   ((u32 *)(0x41BA0A24u + 84u * (id)))     /* oggetto del parametro */
#define SLOTS     ((u32 *)0x41BA081Cu)                     /* caselle della pagina 25 */
enum {
    G_DEF = 0x41B9ECD0, G_LFO = 0x41B9EC70, G_SPD = 0x41B9E6B0, G_MOD = 0x41B9E730, G_STIM = 0x41B9E7D0,
    G_SDEP = 0x41B9E7E0, G_BAL = 0x41B9E740, G_TONE = 0x41B9E760, G_NCOL = 0x41B9E780, G_TICK = 0x41B9E830,
    G_OVER = 0x41B9ECB0, S_KNOB = 0x41B9E670, S_660 = 0x41B9E660, S_FDBK = 0x41B9E5E0
};
static const u32 look[NT][5][2] = {
    {{G_SPD, 0}, {G_MOD, 0}, {G_STIM, 0}, {G_DEF, S_FDBK}, {G_BAL, S_660}},     /* SPD 467, MOD 176, STIM 274, FDBK 109, BAL 216 */
    {{G_SPD, 0}, {G_SDEP, 0}, {G_STIM, 0}, {G_LFO, S_660}, {G_BAL, S_660}},     /* SDEP 283, LFO DEP 94 (bipolare) */
    {{G_SPD, 0}, {G_SDEP, 0}, {G_TONE, S_660}, {G_LFO, S_660}, {G_BAL, S_660}}, /* TONE 394 */
    {{G_NCOL, S_660}, {G_TICK, 0}, {G_OVER, S_KNOB}, {0, 0}, {0, 0}}};          /* NCOL 385, TICK 277, OVER 164 */
static const unsigned short knob_id[5] = {247, 248, 250, 251, 252};

static void put(char *buf, const char *s)
{
    while ((*buf++ = *s++))
        ;
}

int fx3_mgr(void *dst, const void *src, int op);

static void graphic(u32 *dst, u32 proto)
{
    dst[0] = dst[1] = 0;
    dst[2] = proto ? (u32)fx3_mgr : 0;
    dst[3] = proto ? ((const u32 *)proto)[3] : 0;
}

/* nomi, icone e caselle secondo il tipo. Solo nel contesto dell'interfaccia (formattatori, grafica,
 * scrittura dei parametri): copiare una std::function mentre l'interfaccia la sta chiamando
 * porterebbe a saltare a un indirizzo sbagliato; l'interrupt audio aggiorna soltanto fx3_p. */
static void dress(void)
{
    char *ui = UI_ROOT;
    u32 t = fx3_p[P_TYPE], i;

    if (t == named)
        return;
    named = t;
    for (i = 0; i < 5; i++) {
        put(name_s[i], n_s[t][i]);
        put(name_l[i], n_l[t][i]);
        graphic(OBJ(knob_id[i]) + 9, look[t][i][0]);
        graphic(OBJ(knob_id[i]) + 17, look[t][i][1]);
    }
    SLOTS[4] = t == CRSH ? 0 : 251;                        /* il crusher non usa FDBK e WID: */
    SLOTS[5] = t == CRSH ? 0 : 252;                        /* caselle vuote */
    put(fx3_page_l, t_l[t]);
    if (ui)
        ui[96] = 1;
}

/* ---- valori che dipendono solo dalle manopole: calcolati quando cambiano (rilettura del kit, o DEL/REV
 * dall'interfaccia), non a ogni blocco */
static u32 inc(const u16 *rate)                           /* passo di fase per blocco da mHz */
{
    return ((u32)rate[fx3_p[P_SPD]] * 183252u >> 10) * H;  /* 2^32 / 24000 / 1000 = 178.96 */
}

static u32 q8(u32 us)                                     /* microsecondi -> campioni a 24 kHz, Q8 */
{
    return us * 6144u / 1000;                             /* 30 ms: 1.8e8, nessun traboccamento */
}

static s32 bip(u32 v, s32 max)                           /* 0..127, centro 64 -> -max..max */
{
    s32 x = ((s32)v - 64) * max / 63;
    return x > max ? max : x < -max ? -max : x;
}

static void sends(void)                                   /* DEL e REV di FX3 (0 dB = 32767) */
{
    S.ds = VOL_Q15[fx3_p[P_DSND]];
    S.rs = VOL_Q15[fx3_p[P_RSND]];
}

static void derive(void)
{
    u32 fl = fx3_p[P_TYPE] == FLNG;

    S.base = q8((fl ? TIME_F : TIME_C)[fx3_p[P_TIME]]);
    S.dep = q8((fl ? DEP_F : DEP_C)[fx3_p[P_DEP]]);
    S.off = (u32)fx3_p[P_WID] * 0x01020408u;               /* 0..180 gradi */
    S.inc = inc(fl ? RATE_F : RATE_C);
    S.fb = fl ? bip(fx3_p[P_FDBK], 31130) : 29490 * (s32)fx3_p[P_FDBK] / 127; /* 95 % / 90 % */
    S.pinc = inc(RATE_F);
    S.px = FIDX_P[fx3_p[P_TIME]];
    S.pdep = 49152u * fx3_p[P_DEP] / 127;                  /* 0..6 ottave */
    S.pfb = bip(fx3_p[P_FDBK], 29491);                     /* 90 % */
    S.pw = 16384 * (s32)fx3_p[P_WID] / 127;                /* Q14 */
    S.cn = 1 + (31 * fx3_p[P_SPD] + 63) / 127;
    S.cmask = -(1 << ((15 * fx3_p[P_DEP] + 63) / 127));    /* bit tolti */
    S.cg = DRV_G[fx3_p[P_TIME]];
    sends();
}

/* parole del kit cambiate (pattern, kit caricato, manopole): parametri e valori derivati */
void fx3_resync(void)
{
    const char *k = kit();
    u32 i;

    S.seen[0] = word(k, 0) << 16 | word(k, 1);
    S.seen[1] = word(k, 2) << 16 | word(k, 3);
    for (i = 0; i < NP; i++)
        fx3_p[i] = (unsigned char)decode(word(k, i >> 1), i);
    derive();
}

/* nuovo tipo: niente coda del precedente. La linea (4 KB) si svuota in CLR_N blocchi, 1/CLR_N per blocco,
 * con l'effetto muto: tutta in un blocco sono ~1 000 scritture e 256 righe di cache, l'interrupt sfora il blocco */
#define CLR_N 8

void fx3_retype(u32 t)
{
    u32 k;

    S.type = t;
    S.clr = CLR_N;
    for (k = 0; k < 5; k++)
        S.ps[k] = 0;
    S.chold = 0;
    S.ccnt = 0;
}

void fx3_clr_step(void)
{
    u32 *l = (u32 *)DL_M + (CLR_N - S.clr) * (DL / CLR_N), k;

    S.clr--;
    for (k = 0; k < DL / CLR_N; k++)                      /* linea e copia: 2 x DL campioni = DL parole */
        l[k] = 0;
    for (k = 0; k < 2 * H; k++)
        S.wet[k] = 0;
    S.ret_h[0] = S.ret_h[1] = 0;
}

/* CRSH: tenuta del campione (24 kHz / 1..32), bit 16..1, drive 0..24 dB con saturazione; mono.
 * Ritorna 1 se l'uscita e' (quasi) muta. */
u32 fx3_crusher(void)
{
    u32 n = S.cn, k;
    s32 g = S.cg, mask = S.cmask;

    for (k = 0; k < H; k++) {
        if (++S.ccnt >= n) {
            s32 x = ((S.bus[k] >> 16) * g) >> 8;
            S.ccnt = 0;
            x = x > 32767 ? 32767 : x < -32768 ? -32768 : x;
            S.chold = x & mask;
        }
        S.wet[2 * k] = S.wet[2 * k + 1] = (s16)S.chold;
    }
    return (u32)(S.chold + 10) <= 20;
}

/* ---- parametri della pagina (vparams): letti e scritti nel kit */
static s32 slot(s32 id)
{
    s32 i;
    for (i = 0; i < NP; i++)
        if (ids[i] == id)
            return i;
    return 0;
}

s32 fx3_get(void *obj, s32 id)
{
    s32 i = slot(id);
    (void)obj;
    return (s32)decode(word(kit(), (u32)i >> 1), (u32)i) << 8;
}

/* valori di partenza di SPD DEP TIME FDBK WID per tipo, scritti quando cambia il tipo: un tipo scelto
 * per sbaglio parte morbido (il crusher senza riduzione di frequenza e bit e senza drive) */
static const unsigned char tdef[NT][5] = {{60, 64, 64, 0, 64}, {60, 64, 64, 64, 64},
                                          {60, 64, 64, 64, 64}, {0, 0, 0, 0, 0}};

static void store(char *k, u32 i, u32 v)                   /* byte del parametro i nel kit, XOR default */
{
    volatile u16 *w = (volatile u16 *)(k + woff[i >> 1]);
    v ^= defv[i];
    *w = (u16)(i & 1 ? (*w & 0xFF00) | v : (*w & 0x00FF) | v << 8);
    fx3_p[i] = (unsigned char)decode(*w, i);
}

s32 fx3_set(void *obj, s32 id, s32 value)
{
    char *ui = UI_ROOT, *k = kit();
    u32 i = (u32)slot(id), v, old = decode(word(k, 0), P_TYPE);
    (void)obj;
    value = (value + 0x80) >> 8;
    v = (u32)(value < 0 ? 0 : value > maxv[i] ? maxv[i] : value);
    store(k, i, v);
    if (i == P_TYPE && v != old)
        for (i = 0; i < 5; i++)
            store(k, P_SPD + i, tdef[v][i]);
    sends();                                              /* DEL e REV di FX3 dal blocco dopo, come fx3_p */
    dress();
    if (ui)
        ui[96] = 1;
    return 0;
}

/* ---- SND3 dell'ingresso esterno: id 269 (vparams), byte basso della parola 0x37 del kit della FX track.
 * Bersagli come le mandate DEL/REV dell'ingresso (0x4008F4F8..): guadagni L/R da livello e bilanciamento,
 * per (v/32768)^2; ogni lato pesa meta' nel bus mono, come una traccia al centro (fx3_in_hook). */

/* Dual mono v2 (mods/dual-mono): intestazione a DM_HDR (tools/build/dualmono_layout.py). In mono il
 * blocco delle mandate dell'ingresso gira due volte: passata 1 = IN L (canale 12), passata 2 = IN R
 * (canale 13, mandata FX3 R nella parola KS_FX3_R del kit attivo, kitstore). La pagina IN R del tab
 * MIXER mostra 269 come la pagina IN L: con quella pagina aperta si legge e scrive FX3 R. */
#define DM_MAGIC  0x444D5632
#define UI_KIT    (*(char *const volatile *)0x800030B8u)    /* kit attivo (kitstore) */

static u32 dm_page_r(void)                                /* solo dal codice dell'interfaccia */
{
    u32 (*f)(void) = *(u32 (*const volatile *)(void))(DM_HDR + 8);
    return *(const volatile u32 *)DM_HDR == DM_MAGIC && f ? f() : 0;
}

static u32 in_snd(u32 r)
{
    const char *k = UI_KIT;
    u32 v = r ? (k ? *(const volatile u16 *)(k + KS_FX3_R) : 0) : *(const volatile u16 *)(kit() + W_IN) & 0xFF;
    return v > 127 ? 127 : v;
}

s32 fx3_in_get(void *obj, s32 id)
{
    (void)obj;
    (void)id;
    return (s32)in_snd(dm_page_r()) << 8;
}

s32 fx3_in_set(void *obj, s32 id, s32 value)
{
    char *ui = UI_ROOT, *k = UI_KIT;
    volatile u16 *w = (volatile u16 *)(kit() + W_IN);
    (void)obj;
    (void)id;
    value = (value + 0x80) >> 8;
    value = value < 0 ? 0 : value > 127 ? 127 : value;
    if (dm_page_r()) {
        if (k)
            *(volatile u16 *)(k + KS_FX3_R) = (u16)value;
    } else
        *w = (u16)((*w & 0xFF00) | (u32)value);
    if (ui)
        ui[96] = 1;
    return 0;
}

/* ---- SND3 della FX track: id 144 (vparams), parola KS_FX3_FX del kit attivo (kitstore), 0..127. Pagina AMP
 * della FX track, G, accanto a DEL e REV: manda il bus della FX track (ADC 6/7) a FX3 come l'OS lo manda a
 * delay e riverbero (canali 14/15, fx3_in_hook). */
s32 fx3_fx_get(void *obj, s32 id)
{
    const char *k = UI_KIT;
    u32 v = k ? *(const volatile u16 *)(k + KS_FX3_FX) : 0;
    (void)obj;
    (void)id;
    return (s32)(v > 127 ? 127 : v) << 8;
}

s32 fx3_fx_set(void *obj, s32 id, s32 value)
{
    char *ui = UI_ROOT, *k = UI_KIT;
    (void)obj;
    (void)id;
    value = (value + 0x80) >> 8;
    value = value < 0 ? 0 : value > 127 ? 127 : value;
    if (k)
        *(volatile u16 *)(k + KS_FX3_FX) = (u16)value;
    if (ui)
        ui[96] = 1;
    return 0;
}

/* ---- ROUTING (FUNC+FX), tasto 13: il ritorno di FX3 nella FX track (bit 8 della parola 0x37 del kit), come
 * il routing di delay e riverbero sui tasti 14 e 15 */
#define DRAW_BOX  ((void (*)(void *, s32, s32, s32, s32, s32))0x400F7D9Au)
#define DRAW_STR  ((void (*)(void *, const void *, s32, s32, s32, const char *, ...))0x400F8BD0u)
#define FONT_RT   ((const void *)0x443DB218u)

u32 fx3_route(void)
{
    return (*(const volatile u16 *)(kit() + W_IN) >> 8) & 1;
}

void fx3_route_toggle(void)
{
    volatile u16 *w = (volatile u16 *)(kit() + W_IN);
    char *ui = UI_ROOT;
    *w = (u16)(*w ^ 0x100);
    if (ui)
        ui[96] = 1;
}

void fx3_route_draw(void *ctx, s32 x, s32 base, s32 ty)  /* al posto del segnaposto della voce 13: */
{                                                          /* casella e testo come le tracce (0x4004C1F4) */
    DRAW_BOX(ctx, x - 4, base - 12, x + 8, base, 1);
    DRAW_STR(ctx, FONT_RT, x + 2, ty, 2, "FX3");
}

/* ---- testi (std::function come in readable-values) */
static u32 pos(s32 value)
{
    value = (value + 0x80) >> 8;
    return (u32)(value < 0 ? 0 : value > 127 ? 127 : value);
}

static char *dec(char *buf, u32 n)                        /* intero senza segno */
{
    char t[10];
    u32 k = 0;
    do
        t[k++] = (char)('0' + n % 10);
    while ((n /= 10) && k < 10);
    while (k)
        *buf++ = t[--k];
    return buf;
}

static void fixed(char *buf, u32 n, u32 d, const char *unit) /* n / 10^d con d decimali (0..2) */
{
    u32 p = d == 2 ? 100 : d == 1 ? 10 : 1;
    buf = dec(buf, n / p);
    if (d) {
        *buf++ = '.';
        if (d == 2)
            *buf++ = (char)('0' + n / 10 % 10);
        *buf++ = (char)('0' + n % 10);
    }
    put(buf, unit);
}

static void hz_m(char *buf, u32 mhz)                      /* velocita': 0.05Hz .. 9.99Hz, 10.0 */
{
    if (mhz < 9995)
        fixed(buf, (mhz + 5) / 10, 2, "Hz");
    else
        fixed(buf, (mhz + 50) / 100, 1, "");
}

static void ms_u(char *buf, u32 us)                       /* tempi: 0.00ms, 1.0ms, 30ms */
{
    if (us < 995)
        fixed(buf, (us + 5) / 10, 2, "ms");
    else if (us < 9950)
        fixed(buf, (us + 50) / 100, 1, "ms");
    else
        fixed(buf, (us + 500) / 1000, 0, "ms");
}

static void hz(char *buf, u32 f)                          /* frequenze: 750Hz, 1.2kHz, 24kHz */
{
    if (f < 995)
        fixed(buf, f, 0, "Hz");
    else if (f < 9950)
        fixed(buf, (f + 50) / 100, 1, "kHz");
    else
        fixed(buf, (f + 500) / 1000, 0, "kHz");
}

static void sgn(char *buf, s32 x, const char *unit)       /* -95% 0% +95% */
{
    if (x)
        *buf++ = x < 0 ? '-' : '+';
    fixed(buf, (u32)(x < 0 ? -x : x), 0, unit);
}

static u32 type(void)
{
    return fx3_p[P_TYPE];
}

void fx3_fmt_type(const void *fn, s32 value, char *buf)
{
    u32 t = pos(value);
    (void)fn;
    put(buf, t_s[t < NT ? t : 0]);
}

void fx3_fmt_spd(const void *fn, s32 value, char *buf)
{
    u32 v = pos(value), t = type();
    (void)fn;
    dress();
    if (t == CRSH)
        hz(buf, 24000 / (1 + (31 * v + 63) / 127));
    else
        hz_m(buf, (t == CHOR ? RATE_C : RATE_F)[v]);
}

void fx3_fmt_dep(const void *fn, s32 value, char *buf)
{
    u32 v = pos(value), t = type();
    (void)fn;
    dress();
    if (t == CRSH)
        put(dec(buf, 16 - (15 * v + 63) / 127), "bit");
    else if (t == PHSR)
        fixed(buf, (60 * v + 63) / 127, 1, "oct");
    else
        ms_u(buf, (t == CHOR ? DEP_C : DEP_F)[v]);
}

void fx3_fmt_del(const void *fn, s32 value, char *buf)
{
    u32 v = pos(value), t = type();
    (void)fn;
    dress();
    if (t == CRSH)
        fixed(buf, (240 * v + 63) / 127, 1, "dB");
    else if (t == PHSR)
        hz(buf, FREQ_P[v]);
    else
        ms_u(buf, (t == CHOR ? TIME_C : TIME_F)[v]);
}

void fx3_fmt_fdbk(const void *fn, s32 value, char *buf)
{
    u32 v = pos(value), t = type();
    (void)fn;
    dress();
    if (t == CRSH)
        put(buf, "-");
    else if (t == CHOR)
        fixed(buf, (90 * v + 63) / 127, 0, "%");
    else {
        s32 m = t == FLNG ? 95 : 90, x = ((s32)v - 64) * m, r = (x < 0 ? -x + 31 : x + 31) / 63;
        sgn(buf, x < 0 ? -(r > m ? m : r) : r > m ? m : r, "%");
    }
}

void fx3_fmt_wid(const void *fn, s32 value, char *buf)
{
    u32 v = pos(value), t = type();
    (void)fn;
    dress();
    if (t == CRSH)
        put(buf, "-");
    else if (t == PHSR)
        fixed(buf, (100 * v + 63) / 127, 0, "%");
    else
        fixed(buf, (180 * v + 63) / 127, 0, "deg");
}

void fx3_fmt_vol(const void *fn, s32 value, char *buf) { (void)fn; put(buf, VOL_TXT[pos(value)]); }

/* grafica di TYPE (+36): il tipo come testo, centrato come le destinazioni degli LFO */
void fx3_type_gfx(const void *fn, s32 value, void *ctx, s32 x, s32 y)
{
    u32 t = pos(value);
    (void)fn;
    dress();
    DRAW_TEXT(ctx, FONT, x + 8, y + 5, 1, 0, "XXXX", "%s", t_s[t < NT ? t : 0]);
}

int fx3_mgr(void *dst, const void *src, int op)
{
    (void)dst;
    (void)src;
    (void)op;
    return 0;
}

#define PROTO(name, inv) \
    const void *const name[4] __attribute__((aligned(4))) = {0, 0, (const void *)fx3_mgr, (const void *)inv}
PROTO(fx3_proto_type, fx3_fmt_type);
PROTO(fx3_proto_spd, fx3_fmt_spd);
PROTO(fx3_proto_dep, fx3_fmt_dep);
PROTO(fx3_proto_del, fx3_fmt_del);
PROTO(fx3_proto_fdbk, fx3_fmt_fdbk);
PROTO(fx3_proto_wid, fx3_fmt_wid);
PROTO(fx3_proto_vol, fx3_fmt_vol);
PROTO(fx3_proto_type_gfx, fx3_type_gfx);

const u32 fx3_reverb_pages[2] = {21, 25};                  /* tab REVERB: pagina dell'OS + la nostra */
const char fx3_page_s[] = "FX3";
const char fx3_snd_s[] = "FX3";
const char fx3_in_l[] = "Input FX3 Send";
const char fx3_fx_l[] = "FX Track FX3 Send";
const char fx3_snd_l[] = "FX3 Send";

/* ===== percorso caldo: tutto il codice che gira a ogni blocco, di seguito (righe di cache contigue).
 * Registri: a5 = fx3_s nel trampolino delle somme del master; le routine interne prendono gli argomenti nei
 * registri e non salvano nulla (lo fa chi entra dall'OS). */
#define ST(o)     XS(o) "(%a5)"
__asm__(
    "        .equ    MAXD, 2048\n"                       /* variazione massima del ritardo per blocco (Q8) */
    "        .equ    LOUD, 655360\n"                     /* ingresso udibile: oltre 10/32768 (-70 dB), 10 << 16 */
    "        .macro  f3_add768\n"                        /* bus += parte analogica a +0x300, saturato (l'OS) */
    "        add.l   768(%a0),%d4\n"
    "        sats.l  %d4\n"
    "        add.l   772(%a0),%d5\n"
    "        sats.l  %d5\n"
    "        add.l   776(%a0),%d6\n"
    "        sats.l  %d6\n"
    "        add.l   780(%a0),%d7\n"
    "        sats.l  %d7\n"
    "        .endm\n"
    "        .macro  f3_wet\n"                           /* d4-d7 = L R del campione pari e del dispari a 48 kHz; */
    "        move.w  (%a1)+,%d3\n"                       /* dispari -= 2 x, pari -= h + x (media col precedente), */
    "        muls.w  %d0,%d3\n"                          /* x = wet * guadagno, saturati; h in d1/d2 */
    "        add.l   %d3,%d1\n"
    "        sub.l   %d1,%d4\n"
    "        sats.l  %d4\n"
    "        move.l  %d3,%d1\n"
    "        add.l   %d3,%d3\n"
    "        sub.l   %d3,%d6\n"
    "        sats.l  %d6\n"
    "        move.w  (%a1)+,%d3\n"
    "        muls.w  %d0,%d3\n"
    "        add.l   %d3,%d2\n"
    "        sub.l   %d2,%d5\n"
    "        sats.l  %d5\n"
    "        move.l  %d3,%d2\n"
    "        add.l   %d3,%d3\n"
    "        sub.l   %d3,%d7\n"
    "        sats.l  %d7\n"
    "        .endm\n"
    "        .macro  f3_tap p, q\n"                      /* presa interpolata: \\p = posizione Q8 -> \\q (usa d2, e d7 */
    "        move.l  \\p,\\q\n"                          /* per la sinistra) */
    "        lsr.l   #8,\\q\n"
    "        mvs.w   (%a0,\\q\\().l*2),%d7\n"
    "        mvs.w   2(%a0,\\q\\().l*2),\\q\n"
    "        sub.l   %d7,\\q\n"
    "        asr.l   #1,\\q\n"                            /* la differenza sta in 16 bit */
    "        mvz.b   \\p,%d2\n"
    "        muls.w  %d2,\\q\n"
    "        asr.l   #7,\\q\n"
    "        .endm\n"
    "        .text\n"
    /* ---- dopo le somme del master: bus 3, effetto e ritorno sul bus diretto (come delay e riverbero con FX
     * Routing spento; il bus 0x8000DFD0 passa dal blocco FX analogico). I guadagni seguono i bersagli di 1/4 a
     * blocco (~2.7 ms) e li raggiungono esatti quando sono vicini. */
    "        .globl  fx3_mix_hook\n"
    "fx3_mix_hook:\n"                                    /* 0x4008FB7C: al posto di pea -296(fp) ; pea 0x8000E0F0 */
    "        lea     -60(%sp),%sp\n"
    "        movem.l %d0-%d7/%a0-%a6,(%sp)\n"
    "        .globl  fx3_macsr\n"
    "fx3_macsr:\n"
    "        move.l  #0xA0,%macsr\n"                     /* come l'OS prima delle somme (lo e' gia') */
    "        lea     fx3_s,%a5\n"
    "        bsr.w   f3_kit\n"                           /* parametri dal kit (cambia col pattern): solo se le */
    "        move.w  (%a4),%d0\n"                        /* parole sono cambiate */
    "        swap    %d0\n"
    "        move.w  52(%a4),%d0\n"
    "        move.w  112(%a4),%d1\n"
    "        swap    %d1\n"
    "        move.w  140(%a4),%d1\n"
    "        cmp.l   " ST(O_SEEN) ",%d0\n"
    "        bne.s   1f\n"
    "        cmp.l   " ST(O_SEEN + 4) ",%d1\n"
    "        beq.s   2f\n"
    "1:      jsr     fx3_resync\n"
    "2:      move.l  " ST(O_MOVING) ",%d0\n"
    "        or.l    " ST(O_RAMP) ",%d0\n"
    "        beq.s   3f\n"
    "        bsr.w   f3_ramp\n"
    "3:      move.l  " ST(O_LIVE) ",%d6\n"
    "        beq.w   .Lmute\n"
    "        move.l  %d6,%d0\n"                          /* una o due tracce: un passaggio ciascuna */
    "        subq.l  #1,%d0\n"
    "        and.l   %d6,%d0\n"
    "        move.l  %d0,%d1\n"
    "        subq.l  #1,%d1\n"
    "        and.l   %d0,%d1\n"
    "        bne.s   .Lmany\n"
    "        moveq   #0,%d5\n"                           /* d5: 0 scrive il bus, 1 somma */
    "        move.l  %d6,%d4\n"
    "1:      move.l  %d4,%d1\n"
    "        ff1     %d1\n"
    "        moveq   #31,%d0\n"
    "        sub.l   %d1,%d0\n"                          /* k: il bit piu' alto */
    "        bclr    %d0,%d4\n"
    "        move.l  %d0,%d1\n"
    "        lsl.l   #7,%d1\n"
    "        movea.l #0x80003D50,%a1\n"                  /* digitali, 32 campioni a passo 128 B */
    "        moveq   #8,%d2\n"
    "        cmp.l   %d2,%d0\n"
    "        bcs.s   2f\n"
    "        movea.l #0x80003550,%a1\n"                  /* analogiche e ingresso: 0x80003950 + 128 (k - 8) */
    "2:      adda.l  %d1,%a1\n"
    "        move.l  (%a5,%d0.l*4),%d0\n"
    "        lea     " ST(O_BUS) ",%a0\n"
    "        bsr.w   f3_sum1\n"
    "        moveq   #1,%d5\n"
    "        tst.l   %d4\n"
    "        bne.s   1b\n"
    "        bra.w   .Lloud\n"
    ".Lmany: moveq   #0,%d5\n"                           /* tracce insieme, poi l'ingresso (ADC 4/5) */
    "        move.l  %d6,%d0\n"
    "        andi.l  #0xFFF,%d0\n"
    "        beq.s   2f\n"
    "        moveq   #0,%d6\n"                           /* 1 digitali, 2 analogiche, 3 tutte */
    "        tst.b   %d0\n"
    "        beq.s   1f\n"
    "        moveq   #1,%d6\n"
    "1:      lsr.l   #8,%d0\n"
    "        beq.s   1f\n"
    "        addq.l  #2,%d6\n"
    "1:      bsr.w   fx3_sum\n"
    "        moveq   #1,%d5\n"
    "2:      move.l  " ST(O_LIVE) ",%d6\n"
    "        moveq   #12,%d0\n"
    "        lsr.l   %d0,%d6\n"                          /* ingresso: bit 0 L, bit 1 R */
    "        moveq   #3,%d0\n"
    "        and.l   %d0,%d6\n"
    "        lea     " ST(O_BUS) ",%a0\n"
    "        lea     0x80003B50,%a1\n"
    "        move.l  " ST(O_CUR + 48) ",%d0\n"
    "        moveq   #3,%d1\n"
    "        cmp.l   %d1,%d6\n"
    "        bne.s   3f\n"
    "        lea     0x80003BD0,%a2\n"                   /* L e R: un passaggio solo */
    "        move.l  " ST(O_CUR + 52) ",%d4\n"
    "        bsr.w   f3_sum2\n"
    "        moveq   #1,%d5\n"
    "        bra.s   .Lfxtrk\n"
    "3:      btst    #0,%d6\n"
    "        beq.s   4f\n"
    "        bsr.w   f3_sum1\n"
    "        moveq   #1,%d5\n"
    "4:      btst    #1,%d6\n"
    "        beq.s   .Lfxtrk\n"
    "        lea     " ST(O_BUS) ",%a0\n"
    "        lea     0x80003BD0,%a1\n"
    "        move.l  " ST(O_CUR + 52) ",%d0\n"
    "        bsr.w   f3_sum1\n"
    "        moveq   #1,%d5\n"
    ".Lfxtrk: move.l  " ST(O_LIVE) ",%d6\n"               /* FX track (ADC 6/7, canali 14/15): stesso guadagno */
    "        andi.l  #0xC000,%d6\n"
    "        beq.s   .Lloud\n"
    "        lea     " ST(O_BUS) ",%a0\n"
    "        lea     0x80003C50,%a1\n"
    "        move.l  " ST(O_CUR + 56) ",%d0\n"
    "        lea     0x80003CD0,%a2\n"
    "        move.l  " ST(O_CUR + 60) ",%d4\n"
    "        bsr.w   f3_sum2\n"
    ".Lloud: lea     " ST(O_BUS) ",%a0\n"               /* ingresso udibile? (tracce ferme: no) */
    "        moveq   #16,%d1\n"
    "        move.l  #LOUD,%d2\n"
    "1:      move.l  (%a0)+,%d0\n"
    "        add.l   %d2,%d0\n"
    "        cmpi.l  #2 * LOUD,%d0\n"
    "        bhi.s   2f\n"
    "        subq.l  #1,%d1\n"
    "        bne.s   1b\n"
    ".Lmute: moveq   #0,%d7\n"
    "        bra.s   3f\n"
    "2:      moveq   #1,%d7\n"
    "3:      bne.s   4f\n"                               /* ingresso muto e coda esaurita: a riposo */
    "        moveq   #64,%d0\n"
    "        cmp.l   " ST(O_QUIET) ",%d0\n"
    "        bcs.w   .Lrest\n"
    "4:      clr.l   " ST(O_IDLE) "\n"
    "        moveq   #0,%d0\n"
    "        move.b  " ST(O_P) ",%d0\n"
    "        cmp.l   " ST(O_TYPE) ",%d0\n"
    "        beq.s   5f\n"
    "        move.l  %d0,-(%sp)\n"
    "        jsr     fx3_retype\n"
    "        addq.l  #4,%sp\n"
    "5:      tst.l   " ST(O_CLR) "\n"
    "        beq.s   6f\n"
    "        jsr     fx3_clr_step\n"                     /* svuotamento della linea: effetto muto */
    "        bra.w   .Lout\n"
    "6:      tst.l   " ST(O_LIVE) "\n"
    "        bne.s   7f\n"
    "        lea     " ST(O_BUS) ",%a0\n"                /* nessuna mandata (coda): ingresso a zero */
    "        moveq   #16,%d0\n"
    "1:      clr.l   (%a0)+\n"
    "        subq.l  #1,%d0\n"
    "        bne.s   1b\n"
    "7:      move.l  %d7,-(%sp)\n"
    "        move.l  " ST(O_TYPE) ",%d0\n"
    "        subq.l  #2,%d0\n"
    "        beq.w   .Lphs\n"
    "        subq.l  #1,%d0\n"
    "        beq.w   .Lcrsh\n"
    /* CHOR / FLNG: una linea mono, due prese (L/R) modulate da un LFO calcolato a inizio e fine blocco e
     * interpolato linearmente (le posizioni di lettura avanzano di 1 - pendenza a campione); 16 campioni,
     * prese interpolate dalla linea doppia, retroazione mono saturata a 16 bit. Le posizioni partono sotto DL
     * e in un blocco avanzano di 16 +- MAXD campioni: le letture restano nella copia, senza ritorno a capo. */
    "        move.l  " ST(O_PHASE) ",%d3\n"
    "        add.l   " ST(O_INC) ",%d3\n"                /* fase a fine blocco */
    "        move.l  %d3," ST(O_PHASE) "\n"
    "        move.l  %d3,%d0\n"
    "        bsr.w   f3_lfo\n"
    "        move.l  " ST(O_DPOS) ",%d4\n"
    "        bsr.w   f3_aim\n"
    "        move.l  %d0,%d5\n"                          /* ritardo L a fine blocco */
    "        move.l  %d3,%d0\n"
    "        add.l   " ST(O_OFF) ",%d0\n"
    "        bsr.w   f3_lfo\n"
    "        move.l  %d4,%d6\n"
    "        move.l  " ST(O_DPOS + 4) ",%d4\n"
    "        bsr.w   f3_aim\n"
    "        move.l  %d0,%d7\n"                          /* ritardo R */
    "        movem.l %d5/%d7," ST(O_DPOS) "\n"
    "        move.l  " ST(O_WPOS) ",%d2\n"
    "        lsl.l   #8,%d2\n"
    "        subi.l  #256,%d2\n"
    "        move.l  %d2,%d0\n"
    "        sub.l   %d6,%d0\n"
    "        move.l  %d2,%d1\n"
    "        sub.l   %d4,%d1\n"
    "        move.l  #(" XS(DL) " << 8) - 1,%d2\n"
    "        and.l   %d2,%d0\n"                          /* presa L, Q8 */
    "        and.l   %d2,%d1\n"                          /* presa R */
    "        sub.l   %d6,%d5\n"
    "        asr.l   #4,%d5\n"
    "        movea.w #256,%a4\n"
    "        suba.l  %d5,%a4\n"                          /* passi */
    "        sub.l   %d4,%d7\n"
    "        asr.l   #4,%d7\n"
    "        movea.w #256,%a6\n"
    "        suba.l  %d7,%a6\n"
    "        lea     " XS(MODAREA_RAM) " + 0xE000,%a0\n" /* linea */
    "        lea     2048(%a0),%a3\n"                    /* copia */
    "        lea     " ST(O_BUS) ",%a1\n"
    "        lea     " ST(O_WET) ",%a2\n"
    "        move.l  " ST(O_WPOS) ",%d4\n"
    "        moveq   #16,%d5\n"
    "        tst.l   " ST(O_FB) "\n"
    "        bne.s   2f\n"
    "1:      add.l   %a4,%d0\n"                          /* senza retroazione */
    "        add.l   %a6,%d1\n"
    "        f3_tap  %d0,%d6\n"
    "        add.l   %d7,%d6\n"
    "        f3_tap  %d1,%d3\n"
    "        add.l   %d3,%d7\n"
    "        move.w  %d6,(%a2)+\n"
    "        move.w  %d7,(%a2)+\n"
    "        move.l  (%a1)+,%d2\n"                       /* ingresso (parola alta) */
    "        swap    %d2\n"
    "        move.w  %d2,(%a0,%d4.l*2)\n"
    "        move.w  %d2,(%a3,%d4.l*2)\n"
    "        addq.l  #1,%d4\n"
    "        subq.l  #1,%d5\n"
    "        bne.s   1b\n"
    "        bra.s   3f\n"
    "2:      add.l   %a4,%d0\n"                          /* con retroazione */
    "        add.l   %a6,%d1\n"
    "        f3_tap  %d0,%d6\n"
    "        add.l   %d7,%d6\n"
    "        f3_tap  %d1,%d3\n"
    "        add.l   %d3,%d7\n"
    "        move.w  %d6,(%a2)+\n"
    "        move.w  %d7,(%a2)+\n"
    "        move.l  %d6,%d2\n"                          /* retroazione mono: |r| < 32768, in Q16 */
    "        add.l   %d7,%d2\n"
    "        asr.l   #1,%d2\n"
    "        muls.l  " ST(O_FB) ",%d2\n"
    "        moveq   #15,%d3\n"
    "        asr.l   %d3,%d2\n"
    "        swap    %d2\n"
    "        clr.w   %d2\n"
    "        move.l  (%a1)+,%d3\n"                       /* + ingresso (parola alta), saturato a 16 bit */
    "        clr.w   %d3\n"
    "        add.l   %d3,%d2\n"
    "        sats.l  %d2\n"
    "        swap    %d2\n"
    "        move.w  %d2,(%a0,%d4.l*2)\n"
    "        move.w  %d2,(%a3,%d4.l*2)\n"
    "        addq.l  #1,%d4\n"
    "        subq.l  #1,%d5\n"
    "        bne.s   2b\n"
    "3:      andi.l  #" XS(DL) " - 1,%d4\n"              /* multiplo di H: nel blocco non torna a capo */
    "        move.l  %d4," ST(O_WPOS) "\n"
    "        moveq   #10,%d1\n"                          /* coda muta sotto 10/32768 (-70 dB): con la retroazione */
    "        add.l   %d1,%d6\n"                          /* l'arrotondamento puo' lasciare un residuo costante */
    "        add.l   %d1,%d7\n"
    "        moveq   #20,%d1\n"
    "        moveq   #0,%d0\n"
    "        cmp.l   %d1,%d6\n"
    "        bhi.s   .Lfx\n"
    "        cmp.l   %d1,%d7\n"
    "        bhi.s   .Lfx\n"
    "        moveq   #1,%d0\n"
    ".Lfx:   move.l  (%sp)+,%d7\n"                       /* d0 = coda muta, d7 = ingresso udibile */
    "        tst.l   %d7\n"
    "        bne.s   1f\n"
    "        tst.l   %d0\n"
    "        beq.s   1f\n"
    "        addq.l  #1," ST(O_QUIET) "\n"
    "        bra.s   2f\n"
    "1:      clr.l   " ST(O_QUIET) "\n"
    "2:      bsr.w   f3_kit\n"                           /* ROUTING (FUNC+FX), tasto 13: nella FX track */
    "        lea     0x8000DAD0,%a0\n"
    "        btst    #0," XS(W_IN) "(%a4)\n"
    "        beq.s   3f\n"
    "        lea     0x8000DFD0,%a0\n"
    "3:      lea     " ST(O_WET) ",%a1\n"
    "        lea     " ST(O_RET_H) ",%a3\n"
    "        move.l  #32767,%d0\n"                       /* ritorno sul master: pieno (0 dB) */
    "        bsr.w   f3_ret\n"
    ".Lout:  movem.l (%sp),%d0-%d7/%a0-%a6\n"
    "        lea     60(%sp),%sp\n"
    "        move.l  (%sp)+,%a0\n"
    "        pea     -296(%fp)\n"                        /* istruzioni sostituite */
    "        pea     0x8000E0F0\n"
    "        jmp     (%a0)\n"
    ".Lrest: moveq   #1,%d0\n"                           /* a riposo: wet non valido, interpolazioni da zero */
    "        move.l  %d0," ST(O_IDLE) "\n"
    "        lea     " ST(O_RET_H) ",%a0\n"
    "        moveq   #6,%d0\n"
    "1:      clr.l   (%a0)+\n"
    "        subq.l  #1,%d0\n"
    "        bne.s   1b\n"
    "        bra.s   .Lout\n"
    ".Lcrsh: jsr     fx3_crusher\n"
    "        bra.s   .Lfx\n"
    /* PHSR: 4 celle allpass del primo ordine in cascata (coefficiente per blocco, Q12, dalla frequenza
     * spazzata dall'LFO in ottave), retroazione dall'uscita; sinistra = (x + y) / 2, destra = sinistra -
     * WID * y (a WID massimo (x - y) / 2: notch e picchi scambiati). */
    ".Lphs:  move.l  " ST(O_PHASE) ",%d0\n"
    "        add.l   " ST(O_PINC) ",%d0\n"
    "        move.l  %d0," ST(O_PHASE) "\n"
    "        bsr.w   f3_lfo\n"
    "        mulu.l  " ST(O_PDEP) ",%d0\n"
    "        moveq   #15,%d1\n"
    "        lsr.l   %d1,%d0\n"
    "        add.l   " ST(O_PX) ",%d0\n"                 /* 0..6 ottave */
    "        cmpi.l  #(" XS(PH_N) " - 2) << 8,%d0\n"
    "        bls.s   1f\n"
    "        move.l  #(" XS(PH_N) " - 2) << 8,%d0\n"
    "1:      mvz.b   %d0,%d1\n"
    "        lsr.l   #8,%d0\n"
    "        lea     PH_A,%a0\n"
    "        adda.l  %d0,%a0\n"
    "        adda.l  %d0,%a0\n"
    "        mvs.w   (%a0)+,%d0\n"
    "        mvs.w   (%a0),%d2\n"
    "        sub.l   %d0,%d2\n"
    "        muls.w  %d1,%d2\n"
    "        asr.l   #8,%d2\n"
    "        add.l   %d2,%d0\n"
    "        move.l  %d0," ST(O_PA) "\n"
    "        bsr.w   f3_phs\n"
    "        moveq   #10,%d1\n"
    "        moveq   #20,%d2\n"
    "        moveq   #0,%d0\n"
    "        move.l  " ST(O_PS + 16) ",%d3\n"
    "        add.l   %d1,%d3\n"
    "        cmp.l   %d2,%d3\n"
    "        bhi.w   .Lfx\n"
    "        mvs.w   " ST(O_WET + 60) ",%d3\n"
    "        add.l   %d1,%d3\n"
    "        cmp.l   %d2,%d3\n"
    "        bhi.w   .Lfx\n"
    "        mvs.w   " ST(O_WET + 62) ",%d3\n"
    "        add.l   %d1,%d3\n"
    "        cmp.l   %d2,%d3\n"
    "        bhi.w   .Lfx\n"
    "        moveq   #1,%d0\n"
    "        bra.w   .Lfx\n"
    /* ---- routine interne */
    "f3_kit:                                         \n" /* -> a4 = kit del pattern (o i valori in RAM) */
    "        move.l  0x800030BC,%d0\n"
    "        bne.s   1f\n"
    "        move.l  #fx3_fallback,%d0\n"
    "1:      movea.l %d0,%a4\n"
    "        rts\n"
    "f3_lfo:                                         \n" /* d0 = fase -> seno unipolare 0..32767; usa d1-d2/a0 */
    "        lea     SIN_T,%a0\n"
    "        move.l  %d0,%d1\n"
    "        lsr.l   #8,%d1\n"
    "        mvz.w   %d1,%d1\n"
    "        lsr.l   #1,%d1\n"
    "        moveq   #24,%d2\n"
    "        lsr.l   %d2,%d0\n"
    "        add.l   %d0,%d0\n"
    "        adda.l  %d0,%a0\n"
    "        mvs.w   (%a0)+,%d0\n"
    "        mvs.w   (%a0),%d2\n"
    "        sub.l   %d0,%d2\n"
    "        muls.w  %d1,%d2\n"
    "        moveq   #15,%d1\n"
    "        asr.l   %d1,%d2\n"
    "        add.l   %d2,%d0\n"
    "        addi.l  #32768,%d0\n"
    "        asr.l   #1,%d0\n"
    "        rts\n"
    "f3_aim:                                         \n" /* d0 = LFO, d4 = ritardo di prima -> d0 = base + dep * */
    "        mulu.l  " ST(O_DEP) ",%d0\n"                /* LFO / 2^15; TIME girato di colpo: scivola di MAXD */
    "        moveq   #15,%d1\n"                          /* al piu'. Usa d1 */
    "        lsr.l   %d1,%d0\n"
    "        add.l   " ST(O_BASE) ",%d0\n"
    "        move.l  %d0,%d1\n"
    "        sub.l   %d4,%d1\n"
    "        cmpi.l  #MAXD,%d1\n"
    "        bgt.s   1f\n"
    "        cmpi.l  #-MAXD,%d1\n"
    "        bge.s   2f\n"
    "        move.l  %d4,%d0\n"
    "        subi.l  #MAXD,%d0\n"
    "        rts\n"
    "1:      move.l  %d4,%d0\n"
    "        addi.l  #MAXD,%d0\n"
    "2:      rts\n"
    "f3_ramp:                                        \n" /* bersagli cambiati o rampa in corso: 1/4 a blocco, */
    "        clr.l   " ST(O_MOVING) "\n"                 /* esatti a meno di 64 (senza l'aggancio un piccolo */
    "        moveq   #0,%d4\n"                           /* resto non si annullerebbe mai: FX3 sempre acceso). */
    "        moveq   #0,%d5\n"                           /* d4 = rampa, d5 = canali con guadagno */
    "        moveq   #0,%d1\n"
    "        movea.l %a5,%a0\n"
    "1:      move.l  (%a0),%d0\n"                        /* 0..11 tracce, 12..13 ingresso L/R */
    "        move.l  " XS(O_TGT) "(%a0),%d2\n"
    "        cmp.l   %d0,%d2\n"
    "        beq.s   4f\n"
    "        move.l  %d2,%d3\n"
    "        sub.l   %d0,%d3\n"
    "        moveq   #-64,%d6\n"
    "        cmp.l   %d6,%d3\n"
    "        ble.s   2f\n"
    "        moveq   #64,%d6\n"
    "        cmp.l   %d6,%d3\n"
    "        bge.s   2f\n"
    "        move.l  %d2,%d0\n"
    "        bra.s   3f\n"
    "2:      asr.l   #2,%d3\n"
    "        add.l   %d3,%d0\n"
    "3:      move.l  %d0,(%a0)\n"
    "        sub.l   %d0,%d2\n"
    "        or.l    %d2,%d4\n"
    "4:      tst.l   %d0\n"
    "        beq.s   5f\n"
    "        bset    %d1,%d5\n"
    "5:      addq.l  #4,%a0\n"
    "        addq.l  #1,%d1\n"
    "        moveq   #16,%d2\n"                          /* 14..15: FX track (ADC 6/7) */
    "        cmp.l   %d2,%d1\n"
    "        bne.s   1b\n"
    "        move.l  %d4," ST(O_RAMP) "\n"
    "        move.l  %d5," ST(O_LIVE) "\n"
    "        rts\n"
    /* ritorno: a0 = bus a 48 kHz (64 L/R), a1 = uscita a 24 kHz (s16 L/R), a3 = h[2], d0 = guadagno Q15:
     * bus -= 2 * wet * guadagno, saturato; i campioni dispari sono quelli dell'effetto, i pari la media con il
     * precedente (h = mezzo campione). Usa d1-d7/a0/a2 */
    "f3_ret:                                         \n"
    "        lea     256(%a0),%a2\n"
    "        move.l  (%a3),%d1\n"
    "        move.l  4(%a3),%d2\n"
    "1:      movem.l (%a0),%d4-%d7\n"
    "        f3_wet\n"
    "        movem.l %d4-%d7,(%a0)\n"
    "        lea     16(%a0),%a0\n"
    "        cmpa.l  %a2,%a0\n"
    "        bne.s   1b\n"
    "        move.l  %d1,(%a3)\n"
    "        move.l  %d2,4(%a3)\n"
    "        rts\n"
    /* Mandate DEL e REV dentro i cicli dell'OS che preparano i bus d'ingresso di delay e riverbero
     * (0x4008F852 e 0x4008F98A: bus += parte analogica a +0x300, saturato): lo stesso lavoro in meno
     * istruzioni e, con la mandata alzata, l'uscita dell'effetto del blocco precedente nello stesso passaggio
     * (convenzione del bus 3: si somma, quindi guadagno negativo), come il ritorno. d0-d1/a0-a1 liberi: il
     * ciclo dell'OS li sporca. */
    "        .globl  fx3_del_hook\n"
    "fx3_del_hook:\n"                                    /* 0x4008F852: jsr fx3_del_hook ; jmp 0x4008F882 */
    "        lea     fx3_s + " XS(O_DLY_H) ",%a1\n"
    "        move.l  fx3_s + " XS(O_DS) ",%d0\n"
    "        bra.s   1f\n"
    "        .globl  fx3_rev_hook\n"
    "fx3_rev_hook:\n"                                    /* 0x4008F98A: jsr fx3_rev_hook ; jmp 0x4008F9BA */
    "        lea     fx3_s + " XS(O_REV_H) ",%a1\n"
    "        move.l  fx3_s + " XS(O_RS) ",%d0\n"
    "1:      tst.l   fx3_s + " XS(O_IDLE) "\n"
    "        beq.s   2f\n"
    "        moveq   #0,%d0\n"
    "2:      tst.l   %d0\n"
    "        bne.s   3f\n"
    "        clr.l   (%a1)\n"
    "        clr.l   4(%a1)\n"
    "3:      neg.l   %d0\n"
    "        lea     0x8000DBD0,%a0\n"
    "f3_send:                                        \n" /* a0 = bus, d0 = guadagno Q15, a1 = h[2] */
    "        lea     -32(%sp),%sp\n"
    "        movem.l %d2-%d7/%a2-%a3,(%sp)\n"
    "        movea.l %a1,%a3\n"
    "        lea     fx3_s + " XS(O_WET) ",%a1\n"
    "        lea     256(%a0),%a2\n"
    "        move.l  (%a3),%d1\n"
    "        move.l  4(%a3),%d2\n"
    "        tst.l   %d0\n"
    "        bne.s   2f\n"
    "1:      movem.l (%a0),%d4-%d7\n"                    /* solo il ciclo dell'OS */
    "        f3_add768\n"
    "        movem.l %d4-%d7,(%a0)\n"
    "        lea     16(%a0),%a0\n"
    "        cmpa.l  %a2,%a0\n"
    "        bne.s   1b\n"
    "        bra.s   3f\n"
    "2:      movem.l (%a0),%d4-%d7\n"                    /* il ciclo dell'OS e la mandata */
    "        f3_add768\n"
    "        f3_wet\n"
    "        movem.l %d4-%d7,(%a0)\n"
    "        lea     16(%a0),%a0\n"
    "        cmpa.l  %a2,%a0\n"
    "        bne.s   2b\n"
    "        move.l  %d1,(%a3)\n"
    "        move.l  %d2,4(%a3)\n"
    "3:      movem.l (%sp),%d2-%d7/%a2-%a3\n"
    "        lea     32(%sp),%sp\n"
    "        rts\n"
    /* SND3 dell'ingresso: bersagli dei canali 12/13 dal ciclo delle mandate dell'ingresso */
    "        .globl  fx3_in_hook\n"
    "fx3_in_hook:\n"                                     /* 0x4008F53C: d1/a0 = guadagni L/R; istruzioni sostituite: */
    "        move.l  (%sp),4(%sp)\n"                     /* addq.l #4,sp (argomento della legge di bilanciamento), */
    "        addq.l  #4,%sp\n"                           /* move.w 1812(a2),d2 (REV) */
    "        move.w  1812(%a2),%d2\n"
    "        lea     -24(%sp),%sp\n"
    "        movem.l %d0-%d1/%d3-%d5/%a1,(%sp)\n"
    "        moveq   #0,%d3\n"                           /* lato del dual mono: 1 = passata IN L, 2 = IN R */
    "        move.l  " XS(DM_HDR) ",%d0\n"
    "        cmpi.l  #" XS(DM_MAGIC) ",%d0\n"
    "        bne.s   1f\n"
    "        mvz.b   " XS(DM_HDR) " + 4,%d3\n"
    "1:      moveq   #2,%d0\n"
    "        cmp.l   %d0,%d3\n"
    "        bne.s   2f\n"
    "        moveq   #0,%d0\n"                           /* IN R: parola KS_FX3_R del kit attivo */
    "        move.l  0x800030B8,%d4\n"
    "        beq.s   3f\n"
    "        movea.l %d4,%a1\n"
    "        mvz.w   " XS(KS_FX3_R) "(%a1),%d0\n"
    "        bra.s   3f\n"
    "2:      bsr.w   f3_kit2\n"                          /* byte basso della parola 0x37 */
    "        mvz.b   " XS(W_IN) " + 1(%a1),%d0\n"
    "3:      moveq   #127,%d4\n"
    "        cmp.l   %d4,%d0\n"
    "        bls.s   4f\n"
    "        move.l  %d4,%d0\n"
    "4:      moveq   #0,%d4\n"                           /* tl */
    "        moveq   #0,%d5\n"                           /* tr */
    "        tst.l   %d0\n"
    "        beq.s   5f\n"
    "        lsl.l   #8,%d0\n"
    "        mulu.w  %d0,%d0\n"
    "        add.l   %d0,%d0\n"
    "        swap    %d0\n"                              /* (2 v^2) >> 16: (v/32768)^2 come DEL e REV */
    "        move.l  %d1,%d4\n"
    "        asr.l   #1,%d4\n"
    "        swap    %d4\n"
    "        muls.w  %d0,%d4\n"
    "        move.l  %a0,%d5\n"
    "        asr.l   #1,%d5\n"
    "        swap    %d5\n"
    "        muls.w  %d0,%d5\n"
    "5:      lea     fx3_s + " XS(O_TGT) " + 48,%a1\n"
    "        subq.l  #1,%d3\n"
    "        bne.s   6f\n"
    "        move.l  4(%a1),%d5\n"                       /* passata IN L: solo il canale 12 */
    "6:      subq.l  #1,%d3\n"
    "        bne.s   7f\n"
    "        move.l  (%a1),%d4\n"                        /* passata IN R: solo il canale 13 */
    "7:      cmp.l   (%a1),%d4\n"
    "        bne.s   8f\n"
    "        cmp.l   4(%a1),%d5\n"
    "        beq.s   9f\n"
    "8:      move.l  %d4,(%a1)\n"
    "        move.l  %d5,4(%a1)\n"
    "        move.l  %a1,fx3_s + " XS(O_MOVING) "\n"
    "9:      moveq   #0,%d0\n"                           /* SND3 della FX track (parola KS_FX3_FX): canali 14/15 */
    "        move.l  0x800030B8,%d4\n"                   /* = ADC 6/7, ognuno meta' come l'ingresso a guadagno */
    "        beq.s   1f\n"                               /* pieno; 0 se il ritorno di FX3 va nella FX track */
    "        movea.l %d4,%a1\n"                          /* (anello, come l'OS per DEL e REV) */
    "        mvz.w   " XS(KS_FX3_FX) "(%a1),%d0\n"
    "        bsr.w   f3_kit2\n"
    "        btst    #0," XS(W_IN) "(%a1)\n"
    "        beq.s   1f\n"
    "        moveq   #0,%d0\n"
    "1:      moveq   #0,%d4\n"
    "        tst.l   %d0\n"
    "        beq.s   2f\n"
    "        moveq   #127,%d4\n"
    "        cmp.l   %d4,%d0\n"
    "        bls.s   3f\n"
    "        move.l  %d4,%d0\n"
    "3:      lsl.l   #8,%d0\n"
    "        mulu.w  %d0,%d0\n"
    "        add.l   %d0,%d0\n"
    "        swap    %d0\n"                              /* (v/32768)^2 Q15 */
    "        andi.l  #0xFFFF,%d0\n"
    "        moveq   #14,%d4\n"                          /* -0x4000 x: segno degli ADC come l'ingresso */
    "        lsl.l   %d4,%d0\n"                          /* (guadagno pieno dall'OS = -1) */
    "        move.l  %d0,%d4\n"
    "        neg.l   %d4\n"
    "2:      lea     fx3_s + " XS(O_TGT) " + 56,%a1\n"
    "        cmp.l   (%a1),%d4\n"
    "        beq.s   4f\n"
    "        move.l  %d4,(%a1)\n"
    "        move.l  %d4,4(%a1)\n"
    "        move.l  %a1,fx3_s + " XS(O_MOVING) "\n"
    "4:      movem.l (%sp),%d0-%d1/%d3-%d5/%a1\n"
    "        lea     24(%sp),%sp\n"
    "        rts\n"
    "f3_kit2:                                        \n" /* -> a1 = kit (usa d4) */
    "        move.l  0x800030BC,%d4\n"
    "        bne.s   1f\n"
    "        move.l  #fx3_fallback,%d4\n"
    "1:      movea.l %d4,%a1\n"
    "        rts\n"
    /* ciclo per traccia (0x4008F418): d0/d1 guadagni, d3 traccia, a3 struttura; istruzioni sostituite:
     * msac.l d0,d7,acc0 ; msac.l d1,d7,acc1 */
    "        .globl  fx3_trk_hook\n"
    "fx3_trk_hook:\n"
    "        .word   0xae00, 0x0900\n"
    "        .word   0xae81, 0x0900\n"
    "        tst.w   106(%a3)\n"                         /* SND3 (id 72) spenta e bersaglio gia' 0: niente */
    "        bgt.s   1f\n"                               /* da fare (il caso comune, 12 volte a blocco) */
    "        move.l  %a0,-(%sp)\n"
    "        lea     fx3_tgt,%a0\n"
    "        tst.l   (%a0,%d3.l*4)\n"
    "        movea.l (%sp)+,%a0\n"
    "        bne.s   2f\n"
    "        rts\n"
    "1:      cmpi.l  #12,%d3\n"                          /* 0..7 digitali, 8..11 analogiche: FX track no */
    "        bcc.s   0f\n"
    "        lea     -16(%sp),%sp\n"                     /* bersaglio mono della traccia (meta', per le */
    "        movem.l %d0-%d2/%a0,(%sp)\n"                /* coppie): ((gl/2 + gr/2) >> 16) * (2 v^2 >> 16) */
    "        move.l  -508(%fp),%d2\n"                    /* maschera dei mute */
    "        btst    %d3,%d2\n"
    "        bne.s   8f\n"
    "        mvs.w   106(%a3),%d2\n"                     /* SND3 (id 72), qui > 0 */
    "        muls.w  %d2,%d2\n"                          /* (v/32768)^2 in Q31, come DEL e REV */
    "        add.l   %d2,%d2\n"
    "        swap    %d2\n"
    "        asr.l   #1,%d0\n"
    "        asr.l   #1,%d1\n"
    "        add.l   %d1,%d0\n"
    "        swap    %d0\n"
    "        muls.w  %d0,%d2\n"
    "        bra.s   7f\n"
    "2:      cmpi.l  #12,%d3\n"                          /* SND3 a 0 ma bersaglio no: va a 0 */
    "        bcc.s   0f\n"
    "        lea     -16(%sp),%sp\n"
    "        movem.l %d0-%d2/%a0,(%sp)\n"
    "8:      moveq   #0,%d2\n"
    "7:      lea     fx3_tgt,%a0\n"
    "        cmp.l   (%a0,%d3.l*4),%d2\n"
    "        beq.s   9f\n"
    "        move.l  %a0,fx3_moving\n"                   /* bersaglio cambiato: la rampa riparte */
    "        move.l  %d2,(%a0,%d3.l*4)\n"
    "9:      movem.l (%sp),%d0-%d2/%a0\n"
    "        lea     16(%sp),%sp\n"
    "0:      rts\n"
    /* ---- somme del bus 3 (EMAC): 16 medie di coppie, bus[n] = -somma g (x[2n] + x[2n+1]) */
    "        .globl  fx3_sum\n"
    "fx3_sum:\n"                                         /* a5 = fx3_s (guadagni in testa), d6 = 1 digitali, 2 */
    "        movem.l (%a5),%d0-%d5/%d7/%a0-%a4\n"        /* analogiche, 3 tutte. Sporca tutto; a5 rimesso */
    "        lea     " XS(O_BUS) "(%a5),%a5\n"           /* digitali d0-d5 d7 a0, analogiche a1-a4 */
    "        movea.l #0x80003950,%a6\n"                  /* analogiche a +128k, digitali a +1024+128k */
    "        subq.l  #2,%d6\n"
    "        beq.w   2f\n"
    "        bgt.w   3f\n"
    "1:      move.l  1024(%a6),%d6\n"                    /* solo digitali */
    "        msac.l  %d0,%d6,1028(%a6),%d6,%acc0\n"
    "        msac.l  %d0,%d6,1152(%a6),%d6,%acc0\n"
    "        msac.l  %d1,%d6,1156(%a6),%d6,%acc0\n"
    "        msac.l  %d1,%d6,1280(%a6),%d6,%acc0\n"
    "        msac.l  %d2,%d6,1284(%a6),%d6,%acc0\n"
    "        msac.l  %d2,%d6,1408(%a6),%d6,%acc0\n"
    "        msac.l  %d3,%d6,1412(%a6),%d6,%acc0\n"
    "        msac.l  %d3,%d6,1536(%a6),%d6,%acc0\n"
    "        msac.l  %d4,%d6,1540(%a6),%d6,%acc0\n"
    "        msac.l  %d4,%d6,1664(%a6),%d6,%acc0\n"
    "        msac.l  %d5,%d6,1668(%a6),%d6,%acc0\n"
    "        msac.l  %d5,%d6,1792(%a6),%d6,%acc0\n"
    "        msac.l  %d7,%d6,1796(%a6),%d6,%acc0\n"
    "        msac.l  %d7,%d6,1920(%a6),%d6,%acc0\n"
    "        msac.l  %a0,%d6,1924(%a6),%d6,%acc0\n"
    "        msac.l  %a0,%d6,%acc0\n"
    "        addq.l  #8,%a6\n"
    "        movclr.l %acc0,%d6\n"
    "        move.l  %d6,(%a5)+\n"
    "        cmpa.l  #0x800039d0,%a6\n"
    "        bne.w   1b\n"
    "        bra.w   9f\n"
    "2:\n"
    "1:      move.l  (%a6),%d6\n"                        /* solo analogiche */
    "        msac.l  %a1,%d6,4(%a6),%d6,%acc0\n"
    "        msac.l  %a1,%d6,128(%a6),%d6,%acc0\n"
    "        msac.l  %a2,%d6,132(%a6),%d6,%acc0\n"
    "        msac.l  %a2,%d6,256(%a6),%d6,%acc0\n"
    "        msac.l  %a3,%d6,260(%a6),%d6,%acc0\n"
    "        msac.l  %a3,%d6,384(%a6),%d6,%acc0\n"
    "        msac.l  %a4,%d6,388(%a6),%d6,%acc0\n"
    "        msac.l  %a4,%d6,%acc0\n"
    "        addq.l  #8,%a6\n"
    "        movclr.l %acc0,%d6\n"
    "        move.l  %d6,(%a5)+\n"
    "        cmpa.l  #0x800039d0,%a6\n"
    "        bne.w   1b\n"
    "        bra.w   9f\n"
    "3:\n"
    "1:      move.l  1024(%a6),%d6\n"                    /* tutte */
    "        msac.l  %d0,%d6,1028(%a6),%d6,%acc0\n"
    "        msac.l  %d0,%d6,1152(%a6),%d6,%acc0\n"
    "        msac.l  %d1,%d6,1156(%a6),%d6,%acc0\n"
    "        msac.l  %d1,%d6,1280(%a6),%d6,%acc0\n"
    "        msac.l  %d2,%d6,1284(%a6),%d6,%acc0\n"
    "        msac.l  %d2,%d6,1408(%a6),%d6,%acc0\n"
    "        msac.l  %d3,%d6,1412(%a6),%d6,%acc0\n"
    "        msac.l  %d3,%d6,1536(%a6),%d6,%acc0\n"
    "        msac.l  %d4,%d6,1540(%a6),%d6,%acc0\n"
    "        msac.l  %d4,%d6,1664(%a6),%d6,%acc0\n"
    "        msac.l  %d5,%d6,1668(%a6),%d6,%acc0\n"
    "        msac.l  %d5,%d6,1792(%a6),%d6,%acc0\n"
    "        msac.l  %d7,%d6,1796(%a6),%d6,%acc0\n"
    "        msac.l  %d7,%d6,1920(%a6),%d6,%acc0\n"
    "        msac.l  %a0,%d6,1924(%a6),%d6,%acc0\n"
    "        msac.l  %a0,%d6,(%a6),%d6,%acc0\n"
    "        msac.l  %a1,%d6,4(%a6),%d6,%acc0\n"
    "        msac.l  %a1,%d6,128(%a6),%d6,%acc0\n"
    "        msac.l  %a2,%d6,132(%a6),%d6,%acc0\n"
    "        msac.l  %a2,%d6,256(%a6),%d6,%acc0\n"
    "        msac.l  %a3,%d6,260(%a6),%d6,%acc0\n"
    "        msac.l  %a3,%d6,384(%a6),%d6,%acc0\n"
    "        msac.l  %a4,%d6,388(%a6),%d6,%acc0\n"
    "        msac.l  %a4,%d6,%acc0\n"
    "        addq.l  #8,%a6\n"
    "        movclr.l %acc0,%d6\n"
    "        move.l  %d6,(%a5)+\n"
    "        cmpa.l  #0x800039d0,%a6\n"
    "        bne.w   1b\n"
    "9:      lea     fx3_s,%a5\n"
    "        rts\n"
    "f3_sum1:                                        \n" /* a0 = bus, a1 = canale, d0 = g, d5 = 0 scrive / 1 somma: */
    "        move.l  (%a1)+,%d1\n"                       /* una traccia, dst[n] (+)= -g (x0 + x1). Usa d1-d3 */
    "        moveq   #16,%d3\n"
    "        tst.l   %d5\n"
    "        bne.s   2f\n"
    "1:      msac.l  %d0,%d1,(%a1)+,%d1,%acc0\n"
    "        msac.l  %d0,%d1,(%a1)+,%d1,%acc0\n"
    "        movclr.l %acc0,%d2\n"
    "        move.l  %d2,(%a0)+\n"
    "        subq.l  #1,%d3\n"
    "        bne.s   1b\n"
    "        rts\n"
    "2:      move.l  (%a0),%d2\n"
    "        move.l  %d2,%acc0\n"
    "        msac.l  %d0,%d1,(%a1)+,%d1,%acc0\n"
    "        msac.l  %d0,%d1,(%a1)+,%d1,%acc0\n"
    "        movclr.l %acc0,%d2\n"
    "        move.l  %d2,(%a0)+\n"
    "        subq.l  #1,%d3\n"
    "        bne.s   2b\n"
    "        rts\n"
    "f3_sum2:                                        \n" /* a0 = bus, a1/a2 = canali, d0/d4 = g, d5 come sopra: */
    "        move.l  (%a1)+,%d1\n"                       /* due canali in un passaggio. Usa d1-d3/a3 */
    "        move.l  (%a2)+,%d2\n"
    "        moveq   #16,%d3\n"
    "        tst.l   %d5\n"
    "        bne.s   2f\n"
    "1:      msac.l  %d0,%d1,(%a1)+,%d1,%acc0\n"
    "        msac.l  %d0,%d1,(%a1)+,%d1,%acc0\n"
    "        msac.l  %d4,%d2,(%a2)+,%d2,%acc0\n"
    "        msac.l  %d4,%d2,(%a2)+,%d2,%acc0\n"
    "        movclr.l %acc0,%a3\n"
    "        move.l  %a3,(%a0)+\n"
    "        subq.l  #1,%d3\n"
    "        bne.s   1b\n"
    "        rts\n"
    "2:      movea.l (%a0),%a3\n"
    "        move.l  %a3,%acc0\n"
    "        msac.l  %d0,%d1,(%a1)+,%d1,%acc0\n"
    "        msac.l  %d0,%d1,(%a1)+,%d1,%acc0\n"
    "        msac.l  %d4,%d2,(%a2)+,%d2,%acc0\n"
    "        msac.l  %d4,%d2,(%a2)+,%d2,%acc0\n"
    "        movclr.l %acc0,%a3\n"
    "        move.l  %a3,(%a0)+\n"
    "        subq.l  #1,%d3\n"
    "        bne.s   2b\n"
    "        rts\n"
    "        .globl  fx3_sum_end\n"
    "fx3_sum_end:\n"
    /* ---- phaser, 16 campioni: y = a (x - s_k) + s_k-1 per 4 celle (s0 d1, s1..s3 a4..a6, s4 d5), coefficiente
     * a in d6 (Q12), retroazione dall'uscita; a2 = fx3_s. Sporca tutto; a5 rimesso */
    "        .globl  fx3_phs\n"
    "fx3_phs:\n"
    "f3_phs:\n"
    "        movea.l %a5,%a2\n"
    "        lea     " XS(O_BUS) "(%a2),%a0\n"           /* ingresso */
    "        lea     " XS(O_WET) "(%a2),%a1\n"           /* uscita */
    "        lea     64(%a0),%a3\n"                      /* fine dell'ingresso */
    "        move.l  " XS(O_PA) "(%a2),%d6\n"            /* coefficiente Q12 */
    "        movem.l " XS(O_PS) "(%a2),%d1-%d5\n"        /* stato */
    "        movea.l %d2,%a4\n"
    "        movea.l %d3,%a5\n"
    "        movea.l %d4,%a6\n"
    "        moveq   #12,%d2\n"                          /* spostamento delle celle */
    "        tst.l   " XS(O_PFB) "(%a2)\n"
    "        bne.w   2f\n"
    "1:      mvs.w   (%a0),%d0\n"                        /* x (parola alta del bus) */
    "        addq.l  #4,%a0\n"
    "        move.l  %d0,%d7\n"                          /* y = a (x - s_k) + s_k-1: s0 d1, s1..s3 a4..a6, s4 d5 */
    "        sub.l   %a4,%d7\n"
    "        muls.l  %d6,%d7\n"
    "        asr.l   %d2,%d7\n"
    "        add.l   %d1,%d7\n"
    "        move.l  %d0,%d1\n"
    "        move.l  %d7,%d0\n"
    "        sub.l   %a5,%d0\n"
    "        muls.l  %d6,%d0\n"
    "        asr.l   %d2,%d0\n"
    "        add.l   %a4,%d0\n"
    "        movea.l %d7,%a4\n"
    "        move.l  %d0,%d7\n"
    "        sub.l   %a6,%d7\n"
    "        muls.l  %d6,%d7\n"
    "        asr.l   %d2,%d7\n"
    "        add.l   %a5,%d7\n"
    "        movea.l %d0,%a5\n"
    "        move.l  %d7,%d0\n"
    "        sub.l   %d5,%d0\n"
    "        muls.l  %d6,%d0\n"
    "        asr.l   %d2,%d0\n"
    "        add.l   %a6,%d0\n"
    "        movea.l %d7,%a6\n"
    "        move.l  %d0,%d5\n"
    "        move.l  %d0,%d7\n"                          /* sinistra (x + y) / 2 */
    "        add.l   %d1,%d7\n"
    "        asr.l   #1,%d7\n"
    "        mvs.w   %d7,%d3\n"
    "        cmp.l   %d7,%d3\n"
    "        beq.s   4f\n"
    "        move.l  #32767,%d3\n"
    "        tst.l   %d7\n"
    "        bpl.s   3f\n"
    "        move.l  #-32768,%d3\n"
    "3:      move.l  %d3,%d7\n"
    "4:      move.w  %d7,(%a1)+\n"
    "        muls.l  " XS(O_PW) "(%a2),%d0\n"            /* destra: sinistra - WID * y */
    "        asr.l   #8,%d0\n"
    "        asr.l   #6,%d0\n"
    "        sub.l   %d0,%d7\n"
    "        mvs.w   %d7,%d3\n"
    "        cmp.l   %d7,%d3\n"
    "        beq.s   4f\n"
    "        move.l  #32767,%d3\n"
    "        tst.l   %d7\n"
    "        bpl.s   3f\n"
    "        move.l  #-32768,%d3\n"
    "3:      move.l  %d3,%d7\n"
    "4:      move.w  %d7,(%a1)+\n"
    "        cmpa.l  %a3,%a0\n"
    "        bne.w   1b\n"
    "        bra.w   9f\n"
    "2:      mvs.w   (%a0),%d0\n"                        /* x (parola alta del bus) */
    "        addq.l  #4,%a0\n"
    "        move.l  %d5,%d7\n"                          /* + retroazione dall'uscita, saturato a 16 bit */
    "        muls.l  " XS(O_PFB) "(%a2),%d7\n"
    "        asr.l   #8,%d7\n"
    "        asr.l   #7,%d7\n"
    "        add.l   %d7,%d0\n"
    "        mvs.w   %d0,%d3\n"
    "        cmp.l   %d0,%d3\n"
    "        beq.s   4f\n"
    "        move.l  #32767,%d3\n"
    "        tst.l   %d0\n"
    "        bpl.s   3f\n"
    "        move.l  #-32768,%d3\n"
    "3:      move.l  %d3,%d0\n"
    "4:      move.l  %d0,%d7\n"                          /* y = a (x - s_k) + s_k-1 */
    "        sub.l   %a4,%d7\n"
    "        muls.l  %d6,%d7\n"
    "        asr.l   %d2,%d7\n"
    "        add.l   %d1,%d7\n"
    "        move.l  %d0,%d1\n"
    "        move.l  %d7,%d0\n"
    "        sub.l   %a5,%d0\n"
    "        muls.l  %d6,%d0\n"
    "        asr.l   %d2,%d0\n"
    "        add.l   %a4,%d0\n"
    "        movea.l %d7,%a4\n"
    "        move.l  %d0,%d7\n"
    "        sub.l   %a6,%d7\n"
    "        muls.l  %d6,%d7\n"
    "        asr.l   %d2,%d7\n"
    "        add.l   %a5,%d7\n"
    "        movea.l %d0,%a5\n"
    "        move.l  %d7,%d0\n"
    "        sub.l   %d5,%d0\n"
    "        muls.l  %d6,%d0\n"
    "        asr.l   %d2,%d0\n"
    "        add.l   %a6,%d0\n"
    "        movea.l %d7,%a6\n"
    "        move.l  %d0,%d5\n"
    "        move.l  %d0,%d7\n"                          /* sinistra (x + y) / 2 */
    "        add.l   %d1,%d7\n"
    "        asr.l   #1,%d7\n"
    "        mvs.w   %d7,%d3\n"
    "        cmp.l   %d7,%d3\n"
    "        beq.s   4f\n"
    "        move.l  #32767,%d3\n"
    "        tst.l   %d7\n"
    "        bpl.s   3f\n"
    "        move.l  #-32768,%d3\n"
    "3:      move.l  %d3,%d7\n"
    "4:      move.w  %d7,(%a1)+\n"
    "        muls.l  " XS(O_PW) "(%a2),%d0\n"            /* destra: sinistra - WID * y */
    "        asr.l   #8,%d0\n"
    "        asr.l   #6,%d0\n"
    "        sub.l   %d0,%d7\n"
    "        mvs.w   %d7,%d3\n"
    "        cmp.l   %d7,%d3\n"
    "        beq.s   4f\n"
    "        move.l  #32767,%d3\n"
    "        tst.l   %d7\n"
    "        bpl.s   3f\n"
    "        move.l  #-32768,%d3\n"
    "3:      move.l  %d3,%d7\n"
    "4:      move.w  %d7,(%a1)+\n"
    "        cmpa.l  %a3,%a0\n"
    "        bne.w   2b\n"
    "9:      move.l  %a4,%d2\n"
    "        move.l  %a5,%d3\n"
    "        move.l  %a6,%d4\n"
    "        movem.l %d1-%d5," XS(O_PS) "(%a2)\n"
    "        movea.l %a2,%a5\n"
    "        rts\n");

/* fuori dal percorso di ogni blocco: chiamate C per i test e agganci dell'interfaccia */
__asm__(
    "        .globl  fx3_ret\n"
    "fx3_ret:\n"                                         /* (wet, guadagno Q15, a, h[2]): il ritorno (f3_ret) */
    "        lea     -32(%sp),%sp\n"
    "        movem.l %d2-%d7/%a2-%a3,(%sp)\n"
    "        movea.l 36(%sp),%a1\n"
    "        move.l  40(%sp),%d0\n"
    "        movea.l 44(%sp),%a0\n"
    "        movea.l 48(%sp),%a3\n"
    "        bsr.w   f3_ret\n"
    "        movem.l (%sp),%d2-%d7/%a2-%a3\n"
    "        lea     32(%sp),%sp\n"
    "        rts\n"
    "        .globl  fx3_addsat\n"
    "fx3_addsat:\n"                                      /* (bus, guadagno Q15, h[2]): il ciclo dell'OS e la */
    "        movea.l 4(%sp),%a0\n"                       /* mandata (f3_send) */
    "        move.l  8(%sp),%d0\n"
    "        movea.l 12(%sp),%a1\n"
    "        bra.w   f3_send\n"
    "        .globl  fx3_rt_key\n"
    "fx3_rt_key:\n"                                      /* 0x4004C5E2 (ROUTING, tasti): d0 = codice, d2 = evento, */
    "        moveq   #36,%d1\n"                          /* a2 = vista. Tasto 13: commuta FX3 */
    "        cmp.l   %d0,%d1\n"
    "        bne.s   1f\n"
    "        move.l  %d2,-(%sp)\n"
    "        jsr     0x400F9830\n"                       /* pressione? */
    "        addq.l  #4,%sp\n"
    "        tst.b   %d0\n"
    "        beq.s   2f\n"
    "        jsr     fx3_route_toggle\n"
    "        move.l  %a2,-(%sp)\n"
    "        jsr     0x400FFE22\n"                       /* aggiorna la vista (come i tasti 14-16) */
    "        addq.l  #4,%sp\n"
    "2:      jmp     0x4004C80A\n"                       /* gestito */
    "1:      bgt.s   3f\n"                               /* istruzioni sostituite: tracce sotto, 14-16 sopra */
    "        jmp     0x4004C5EC\n"
    "3:      jmp     0x4004C5FA\n"
    "        .globl  fx3_rt_get\n"
    "fx3_rt_get:\n"                                      /* 0x4004BF86: stato della voce (vista, indice) */
    "        moveq   #12,%d0\n"
    "        cmp.l   8(%sp),%d0\n"
    "        bne.s   1f\n"
    "        jmp     fx3_route\n"                        /* voce 13: FX3 nella FX track */
    "1:      lea     -16(%sp),%sp\n"                     /* istruzioni sostituite */
    "        movem.l %d2-%d4/%a2,(%sp)\n"
    "        jmp     0x4004BF8E\n"
    "        .globl  fx3_rt_draw\n"
    "fx3_rt_draw:\n"                                     /* 0x4004C242: d2 = contesto, a2 = x, d3 = base della riga, */
    "        move.l  %d7,-(%sp)\n"                       /* d7 = riga del testo (registri del ciclo dell'OS) */
    "        move.l  %d3,-(%sp)\n"
    "        move.l  %a2,-(%sp)\n"
    "        move.l  %d2,-(%sp)\n"
    "        jsr     fx3_route_draw\n"
    "        lea     16(%sp),%sp\n"
    "        rts\n"
    "        .globl  fx3_draw_hook\n"
    "fx3_draw_hook:\n"                                   /* disegno dei tab DELAY/REVERB (0x40042CE0): la pagina 25 */
    "        movea.l 4(%sp),%a0\n"                       /* usa il disegno generico a 8 caselle (0x4003A244) */
    "        move.l  144(%a0),%d0\n"                     /* posizione della pagina corrente */
    "        movea.l 124(%a0),%a1\n"                     /* vettore delle pagine */
    "        move.l  (%a1,%d0.l*4),%d0\n"
    "        moveq   #25,%d1\n"
    "        cmp.l   %d1,%d0\n"
    "        bne.s   1f\n"
    "        jmp     0x4003A244\n"
    "1:      lea     -96(%sp),%sp\n"                     /* istruzioni sostituite */
    "        movem.l %d2-%d7/%a2-%a6,(%sp)\n"
    "        jmp     0x40042CE8\n"
    /* Kit nel file (salvataggio, FUNC+YES/NO, progetto): il blocco della FX track passa da 0x400A6E0E
     * (scrittura) e 0x400A6DA6 (lettura) con una tabella di posizioni che perde le parole degli id
     * interni 0x1A e 0x46 e rilegge nella 0 il valore della 0x1A. Le tre parole di fx3 vanno nei byte
     * +148..+155 del blocco nel file, che l'OS azzera e non legge: marcatore "SH" e le tre parole. */
    "        .globl  fx3_in_page\n"
    "fx3_in_page:\n"                                     /* al posto di clr.l 0x41BA07F8 (External Mixer, casella C) */
    "        move.l  %d0,-(%sp)\n"
    "        move.l  #269,%d0\n"
    "        move.l  %d0,0x41BA07F8\n"
    "        move.l  (%sp)+,%d0\n"
    "        rts\n"
    "        .globl  fx3_kser_hook\n"
    "fx3_kser_hook:\n"                                   /* al posto di 0x400A6E0E (file, kit) */
    "        move.l  8(%sp),-(%sp)\n"
    "        move.l  8(%sp),-(%sp)\n"
    "        bsr.s   1f\n"
    "        addq.l  #8,%sp\n"
    "        tst.b   %d0\n"
    "        beq.s   2f\n"
    "        movea.l 4(%sp),%a0\n"                       /* blocco nel file */
    "        movea.l 8(%sp),%a1\n"                       /* blocco nel kit: una parola per id interno */
    "        move.w  #0x5349,%d1\n"                      /* "SI": v0.9 (byte basso di 0x46 = REV) */
    "        move.w  %d1,148(%a0)\n"
    "        move.w  (%a1),150(%a0)\n"
    "        move.w  52(%a1),152(%a0)\n"
    "        move.w  140(%a1),154(%a0)\n"
    "2:      rts\n"
    "1:      move.l  %a3,-(%sp)\n"                       /* istruzioni sostituite */
    "        move.l  %a2,-(%sp)\n"
    "        movea.l 12(%sp),%a2\n"
    "        jmp     0x400A6E16\n"
    "        .globl  fx3_kdes_hook\n"
    "fx3_kdes_hook:\n"                                   /* al posto di 0x400A6DA6 (kit, file) */
    "        move.l  8(%sp),-(%sp)\n"
    "        move.l  8(%sp),-(%sp)\n"
    "        bsr.s   1f\n"
    "        addq.l  #8,%sp\n"
    "        tst.b   %d0\n"
    "        beq.s   3f\n"
    "        movea.l 4(%sp),%a0\n"                       /* blocco nel kit */
    "        movea.l 8(%sp),%a1\n"                       /* blocco nel file */
    "        move.w  148(%a1),%d1\n"
    "        move.w  150(%a1),(%a0)\n"
    "        move.w  152(%a1),52(%a0)\n"
    "        cmpi.w  #0x5349,%d1\n"
    "        bne.s   4f\n"
    "        move.w  154(%a1),140(%a0)\n"
    "        rts\n"
    "4:      cmpi.w  #0x5348,%d1\n"                      /* "SH" (v0.8.1): il byte basso di 0x46 era VOL, */
    "        bne.s   2f\n"                               /* REV riparte da 0 */
    "        move.w  154(%a1),%d1\n"
    "        andi.l  #0xFF00,%d1\n"
    "        move.w  %d1,140(%a0)\n"
    "        rts\n"
    "2:      clr.w   (%a0)\n"                            /* file senza marcatore: valori di default */
    "        clr.w   52(%a0)\n"
    "        clr.w   140(%a0)\n"
    "3:      rts\n"
    "1:      lea     -12(%sp),%sp\n"                     /* istruzioni sostituite */
    "        movem.l %a2-%a4,(%sp)\n"
    "        jmp     0x400A6DAE\n"
    "        .globl  fx3_page_stub\n"
    "fx3_page_stub:\n"                                   /* al posto di clr.l 0x41BA083C: caselle della pagina 25 */
    "        move.l  %a0,-(%sp)\n"
    "        move.l  %d0,-(%sp)\n"
    "        lea     0x41BA081C,%a0\n"
    "        move.l  #246,%d0\n"
    "        move.l  %d0,(%a0)+\n"
    "        move.l  #247,%d0\n"
    "        move.l  %d0,(%a0)+\n"
    "        move.l  #248,%d0\n"
    "        move.l  %d0,(%a0)+\n"
    "        move.l  #250,%d0\n"
    "        move.l  %d0,(%a0)+\n"
    "        move.l  #251,%d0\n"
    "        move.l  %d0,(%a0)+\n"
    "        move.l  #252,%d0\n"
    "        move.l  %d0,(%a0)+\n"
    "        move.l  #249,%d0\n"
    "        move.l  %d0,(%a0)+\n"
    "        move.l  #253,%d0\n"
    "        move.l  %d0,(%a0)+\n"
    "        clr.l   (%a0)\n"                            /* +40 (istruzione sostituita) */
    "        move.l  (%sp)+,%d0\n"
    "        move.l  (%sp)+,%a0\n"
    "        rts\n"
    "        .globl  fx3_amp_stub\n"
    "fx3_amp_stub:\n"                                    /* al posto di clr.l 0x41BA06A0 (fine delle pagine AMP): */
    "        move.l  %d0,-(%sp)\n"                       /* SND3 (72) in G della pagina 1, accanto a DEL e REV, */
    "        moveq   #72,%d0\n"                          /* PAN (80) in E della pagina 2; due varianti per pagina */
    "        move.l  %d0,0x41BA0624\n"                   /* (inviluppo AHD / ADSR) */
    "        move.l  %d0,0x41BA0650\n"
    "        moveq   #80,%d0\n"
    "        move.l  %d0,0x41BA0674\n"
    "        move.l  %d0,0x41BA06A0\n"
    "        move.l  (%sp)+,%d0\n"
    "        rts\n"
    "        .globl  fx3_fxamp_stub\n"
    "fx3_fxamp_stub:\n"                                  /* al posto di clr.l 0x41BA0724 (pagina AMP 2 della FX */
    "        move.l  %d0,-(%sp)\n"                       /* track, E): SND3 della FX track (144) in G della */
    "        move.l  #144,%d0\n"                         /* pagina 1 (AHD / ADSR), accanto a DEL e REV; */
    "        move.l  %d0,0x41BA06D4\n"                   /* PAN (153) in E della pagina 2 */
    "        move.l  %d0,0x41BA0700\n"
    "        move.l  #153,%d0\n"
    "        move.l  %d0,0x41BA0724\n"
    "        move.l  (%sp)+,%d0\n"
    "        rts\n");
