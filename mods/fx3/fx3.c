/* fx3: terza mandata effetti (Syntakt OS 1.41), primo effetto: chorus stereo.
 *
 * Audio (funzione di mix a blocchi 0x4008F1CA, 32 campioni a 48 kHz):
 * - nel ciclo per traccia (0x4008F3A0) fx3_trk_hook prende i guadagni sinistro/destro della traccia
 *   (livello e pan) e il valore di SND3 (parola +106 del motore = id 72, salvato per traccia) e ne
 *   ricava il bersaglio mono della mandata (a meta': si sommano coppie di campioni), come l'OS fa per
 *   DEL e REV, e segnala quando un bersaglio cambia (fx3_moving): a regime la rampa non gira;
 * - dopo le somme del master (0x4008FB04) fx3_run somma le tracce nel bus 3 a 24 kHz (coppie di campioni
 *   mediate, EMAC: un passaggio per traccia se mandano una o due tracce, se no uno solo per tutte), lo
 *   passa al chorus (a 24 kHz) e aggiunge il ritorno, scalato da VOL e riportato a 48 kHz per
 *   interpolazione lineare, al bus diretto (0x8000DAD0), con la convenzione di segno dell'OS;
 * - prima del delay del blocco seguente (0x4008F828) fx3_dsnd aggiunge l'uscita del chorus, scalata dalla
 *   mandata DEL, al bus d'ingresso del delay (0x8000DBD0): un blocco di ritardo (0,67 ms).
 * Il carico conta: l'OS usa gia' quasi tutta la CPU e l'interfaccia vive del resto. Senza mandate, con
 * VOL e DEL a zero o con gli ingressi muti (sequencer fermo) e la coda esaurita resta solo la somma o
 * nemmeno quella; i cicli caldi sono in assembly. Istruzioni per blocco in tests/test_fx3.py.
 *
 * Interfaccia: pagina 2 del tab REVERB (pagina 25 dell'OS, "OB8", inutilizzata) con TYPE SPD DEP TIME
 * FDBK WID DEL VOL: id nascosti delle tracce MIDI (246..253) tramite mods/vparams, non salvati. La classe
 * dei tab DELAY/REVERB disegna le caselle 5-6 come filtro: per la pagina 25 si usa il disegno generico
 * a 8 caselle (fx3_draw_hook). SND3 e la mandata DEL usano la grafica della mandata del delay.
 */

typedef unsigned int u32;
typedef int s32;
typedef short s16;

#include "fx3_tables.h"

#define DATA __attribute__((section(".data")))
#define H         16                                       /* campioni per blocco a 24 kHz */
#define DL        1024                                     /* linea a 24 kHz: 42 ms (TIME + DEP <= 38 ms) */
#define DL_M      ((s16 *)0x4600E000u)                     /* linea mono + copia a +DL (area mod azzerata) */
#define SRC_D     0x80003D50u                              /* tracce digitali, 32 campioni a passo 128 B */
#define SRC_A     0x80003950u                              /* tracce analogiche (canali 0..3) */
#define OUT_A     ((s32 *)0x8000DAD0u)                     /* bus d'uscita, L/R alternati */
#define DLY_IN    ((s32 *)0x8000DBD0u)                     /* bus d'ingresso del delay, L/R alternati */
#define LOUD      (10 << 16)                               /* ingresso udibile: oltre 10/32768 (-70 dB) */
#define UI_ROOT   (*(char *const volatile *)0x444E1334u)
#define DRAW_TEXT ((void (*)(void *, const void *, s32, s32, s32, s32, const char *, const char *, ...))                    0x400F8C18u)                            /* (ctx, font, x, y, centrato, 0, sagoma, fmt, ...) */
#define FONT      ((const void *)0x402A91C0u)              /* 4x6 */

enum { P_TYPE, P_SPD, P_DEP, P_TIME, P_FDBK, P_WID, P_DSND, P_VOL, NP };
static const unsigned short ids[NP] = {246, 247, 248, 250, 251, 252, 249, 253};
static const unsigned char maxv[NP] = {0, 127, 127, 127, 127, 127, 127, 127};
unsigned char fx3_p[NP] DATA = {0, 60, 64, 64, 0, 64, 0, 100};

s32 fx3_tgt[16] DATA = {0};                              /* bersagli mono (meta'): 0..7 digitali, 8..11 analogiche */
s32 fx3_cur[16] DATA = {0};                              /* guadagni del blocco (levigati verso i bersagli) */
s32 fx3_moving DATA = 0;                                  /* != 0: un bersaglio e' cambiato */
static u32 ramp DATA = 0;                                 /* != 0: un guadagno non ha ancora raggiunto il bersaglio */
static u32 live DATA = 0;                                 /* tracce con guadagno (bit 0..11) */
s32 fx3_bus[H] DATA = {0};                               /* bus 3 mono a 24 kHz */
s32 fx3_wet[2 * H] DATA = {0};                           /* uscita del chorus (scala 16 bit), L/R alternati */
s32 fx3_idle DATA = 1;                                    /* 1 = niente da fare (e fx3_wet non valido) */
static s32 ret_h[2] DATA = {0, 0}, dly_h[2] DATA = {0, 0}; /* ultimo mezzo campione L/R per l'interpolazione */
static u32 quiet DATA = 0;                                /* blocchi consecutivi senza ingresso ne' coda */
static u32 wpos DATA = 0, phase DATA = 0, dpos[2] DATA = {0, 0};


static s32 lfo(u32 ph)                                    /* seno unipolare 0..32767 */
{
    u32 i = ph >> 24, f = (ph >> 8) & 0xFFFF;
    s32 a = SIN_T[i], b = SIN_T[i + 1];
    return (a + (((b - a) * (s32)(f >> 1)) >> 15) + 32768) >> 1;
}


static const s32 zero[H] = {0};

/* ciclo del chorus in assembly (fx3_cho, sotto): 16 campioni, due prese interpolate dalla linea doppia
 * (le posizioni partono sotto DL e in un blocco avanzano al massimo di ~20 campioni: le letture restano
 * nella copia, senza ritorno a capo), retroazione mono saturata a 16 bit; due varianti (con/senza
 * retroazione). La retroazione sta subito prima della linea (muls.l non accetta indirizzi assoluti). */
struct cho { s16 *line; const s32 *in; s32 *wet; u32 pl, pr, il, ir, w; s32 yl, yr; };
#define CHO_FB    (*(volatile s32 *)((char *)DL_M - 4))
void fx3_cho(struct cho *c);
void fx3_sum(s32 *dst, const s32 *g, u32 which);         /* dst[n] = -sum g[k] (x_k[2n] + x_k[2n+1]) */
void fx3_sum1(s32 *dst, u32 src, s32 g, u32 add);         /* una traccia: dst[n] (+)= -g (x[2n] + x[2n+1]) */
void fx3_ret(const s32 *wet, s32 gain, s32 *a, s32 *h);  /* a -= 2 * wet * gain a 48 kHz (saturato) */

/* chorus: una linea mono, due prese (L/R) modulate da un LFO calcolato a inizio e fine blocco e
 * interpolato linearmente (le posizioni di lettura avanzano di 1 - pendenza a campione). Ritorna 1 se
 * la coda e' (quasi) muta. */
static u32 chorus(const s32 *in)
{
    struct cho c;
    u32 base = DEL_Q8[fx3_p[P_TIME]], dep = DEP_Q8[fx3_p[P_DEP]];
    u32 off = (u32)fx3_p[P_WID] * 0x01020408u;             /* 0..180 gradi */
    u32 end = phase + SPD_INC[fx3_p[P_SPD]] * H;
    u32 el = base + ((dep * (u32)lfo(end)) >> 15), er = base + ((dep * (u32)lfo(end + off)) >> 15);

    c.line = DL_M;
    c.in = in;
    c.wet = fx3_wet;
    c.pl = ((wpos << 8) - dpos[0] - 256) & ((DL << 8) - 1);
    c.pr = ((wpos << 8) - dpos[1] - 256) & ((DL << 8) - 1);
    c.il = 256 - (u32)(((s32)(el - dpos[0])) >> 4);
    c.ir = 256 - (u32)(((s32)(er - dpos[1])) >> 4);
    c.w = wpos;
    CHO_FB = FB_Q15[fx3_p[P_FDBK]];
    fx3_cho(&c);
    wpos = c.w & (DL - 1);                                 /* multiplo di H: nel blocco non torna a capo */
    phase = end;
    dpos[0] = el;
    dpos[1] = er;
    /* coda muta sotto 10/32768 (-70 dB): con la retroazione l'arrotondamento puo' lasciare un residuo
     * costante di qualche unita' che non si spegnerebbe mai */
    return (u32)(c.yl + 10) <= 20 && (u32)(c.yr + 10) <= 20;
}

static void rest(void)
{
    fx3_idle = 1;
    ret_h[0] = ret_h[1] = dly_h[0] = dly_h[1] = 0;
}

/* dopo le somme del master (MACSR impostato dal trampolino): bus 3, chorus e ritorno sul bus diretto
 * (come delay e riverbero con FX Routing spento; il bus 0x8000DFD0 passa dal blocco FX analogico).
 * I guadagni seguono i bersagli di 1/4 a blocco (~2.7 ms) e li raggiungono esatti quando sono vicini. */
void fx3_run(void)
{
    s32 *t = fx3_tgt, *c = fx3_cur;
    s32 vol = VOL_Q15[fx3_p[P_VOL]];
    u32 k, mask = 0, loud = 0, silent;

    if (!(vol | fx3_p[P_DSND])) {                          /* nessuno ascolta l'uscita */
        rest();
        return;
    }
    if (!(fx3_moving | ramp | live) && quiet > DL / H) {   /* nessuna mandata e coda esaurita */
        rest();
        return;
    }
    if (fx3_moving | ramp) {
        fx3_moving = 0;
        ramp = 0;
        for (k = 0; k < 12; k++) {
            s32 g = c[k];
            if (t[k] != g) {
                s32 d = t[k] - g;                          /* senza l'aggancio un piccolo resto non si */
                g = d > -64 && d < 64 ? t[k] : g + (d >> 2); /* annullerebbe mai: FX3 sempre acceso */
                c[k] = g;
                ramp |= (u32)(t[k] - g);
            }
            if (g)
                mask |= 1u << k;
        }
        live = mask;
    }
    mask = live;
    if (mask) {
        u32 two = mask & (mask - 1);
        if (!(two & (two - 1))) {                          /* una o due tracce: un passaggio ciascuna */
            u32 add = 0;
            do {
                k = 31 - (u32)__builtin_clz(mask);         /* ff1 */
                mask ^= 1u << k;
                fx3_sum1(fx3_bus, k < 8 ? SRC_D + 128 * k : SRC_A + 128 * (k - 8), c[k], add);
                add = 1;
            } while (mask);
            mask = live;
        } else
            fx3_sum(fx3_bus, c, (mask & 0xFF ? 1 : 0) | (mask >> 8 ? 2 : 0));
        for (k = 0; k < H; k++)                            /* ingresso udibile? (tracce ferme: no) */
            if ((u32)(fx3_bus[k] + LOUD) > 2 * LOUD) {
                loud = 1;
                break;
            }
    }
    if (!loud && quiet > DL / H) {                         /* ingresso muto e coda esaurita */
        rest();
        return;
    }
    fx3_idle = 0;
    silent = chorus(mask ? fx3_bus : zero);
    quiet = loud || !silent ? 0 : quiet + 1;
    if (vol)
        fx3_ret(fx3_wet, vol, OUT_A, ret_h);
    else
        ret_h[0] = ret_h[1] = 0;
}

/* prima del delay: l'uscita del chorus del blocco precedente nel suo bus d'ingresso (che ha la
 * convenzione del bus 3: si somma, quindi guadagno negativo) */
void fx3_dsnd(void)
{
    s32 ds = VOL_Q15[fx3_p[P_DSND]];

    if (ds)
        fx3_ret(fx3_wet, -ds, DLY_IN, dly_h);
    else
        dly_h[0] = dly_h[1] = 0;
}

/* parametri della pagina (vparams) */
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
    (void)obj;
    return (s32)fx3_p[slot(id)] << 8;
}

s32 fx3_set(void *obj, s32 id, s32 value)
{
    char *ui = UI_ROOT;
    s32 i = slot(id);
    (void)obj;
    value = (value + 0x80) >> 8;
    fx3_p[i] = (unsigned char)(value < 0 ? 0 : value > maxv[i] ? maxv[i] : value);
    if (ui)
        ui[96] = 1;
    return 0;
}

/* formattatori (std::function come in readable-values) */
static void put(char *buf, const char *s)
{
    while ((*buf++ = *s++))
        ;
}

static u32 pos(s32 value)
{
    value = (value + 0x80) >> 8;
    return (u32)(value < 0 ? 0 : value > 127 ? 127 : value);
}

void fx3_fmt_type(const void *fn, s32 value, char *buf) { (void)fn; (void)value; put(buf, "CHOR"); }
void fx3_fmt_spd(const void *fn, s32 value, char *buf) { (void)fn; put(buf, SPD_TXT[pos(value)]); }
void fx3_fmt_dep(const void *fn, s32 value, char *buf) { (void)fn; put(buf, DEP_TXT[pos(value)]); }
void fx3_fmt_del(const void *fn, s32 value, char *buf) { (void)fn; put(buf, DEL_TXT[pos(value)]); }

static void num(char *buf, u32 n, const char *unit)      /* intero 0..999 e unita' */
{
    char t[4];
    u32 k = 0;
    do
        t[k++] = (char)('0' + n % 10);
    while ((n /= 10) && k < 3);
    while (k)
        *buf++ = t[--k];
    put(buf, unit);
}

void fx3_fmt_fdbk(const void *fn, s32 value, char *buf) { (void)fn; num(buf, (90 * pos(value) + 63) / 127, "%"); }
void fx3_fmt_wid(const void *fn, s32 value, char *buf) { (void)fn; num(buf, (180 * pos(value) + 63) / 127, "deg"); }
void fx3_fmt_vol(const void *fn, s32 value, char *buf) { (void)fn; put(buf, VOL_TXT[pos(value)]); }

/* grafica di TYPE (+36): il tipo come testo, centrato come le destinazioni degli LFO */
void fx3_type_gfx(const void *fn, s32 value, void *ctx, s32 x, s32 y)
{
    (void)fn;
    (void)value;
    DRAW_TEXT(ctx, FONT, x + 8, y + 5, 1, 0, "XXXX", "%s", "CHOR");
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
const char fx3_page_l[] = "Chorus";
const char fx3_snd_s[] = "FX3";
const char fx3_snd_l[] = "FX3 Send";
#include "fx3_names.h"

/* cicli caldi in assembly */
__asm__(
    "        .globl  fx3_sum\n"
    "fx3_sum:\n"                                /* (dst, g[12], quali): 16 medie di coppie */
    "        lea     -44(%sp),%sp\n"
    "        movem.l %d2-%d7/%a2-%a6,(%sp)\n"
    "        movea.l 48(%sp),%a5\n"
    "        movea.l 52(%sp),%a6\n"
    "        movem.l (%a6),%d0-%d5/%d7/%a0-%a4\n" /* digitali d0-d5 d7 a0, analogiche a1-a4 */
    "        move.l  56(%sp),%d6\n"             /* 1 digitali, 2 analogiche, 3 tutte */
    "        movea.l #0x80003950,%a6\n"         /* analogiche a +128k, digitali a +1024+128k */
    "        subq.l  #2,%d6\n"
    "        beq.w   2f\n"
    "        bgt.w   3f\n"
    "1:      move.l  1024(%a6),%d6\n"           /* solo digitali */
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
    "1:      move.l  (%a6),%d6\n"               /* solo analogiche */
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
    "1:      move.l  1024(%a6),%d6\n"           /* tutte */
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
    "9:      movem.l (%sp),%d2-%d7/%a2-%a6\n"
    "        lea     44(%sp),%sp\n"
    "        rts\n"
    "        .globl  fx3_sum1\n"
    "fx3_sum1:\n"                               /* (dst, src, g, somma?): una traccia */
    "        lea     -8(%sp),%sp\n"
    "        movem.l %d2-%d3,(%sp)\n"
    "        movea.l 12(%sp),%a0\n"
    "        movea.l 16(%sp),%a1\n"
    "        move.l  20(%sp),%d0\n"
    "        move.l  (%a1)+,%d1\n"
    "        moveq   #16,%d3\n"
    "        tst.l   24(%sp)\n"
    "        bne.s   2f\n"
    "1:      msac.l  %d0,%d1,(%a1)+,%d1,%acc0\n"/* dst = -g (x0 + x1) */
    "        msac.l  %d0,%d1,(%a1)+,%d1,%acc0\n"
    "        movclr.l %acc0,%d2\n"
    "        move.l  %d2,(%a0)+\n"
    "        subq.l  #1,%d3\n"
    "        bne.s   1b\n"
    "        bra.s   9f\n"
    "2:      move.l  (%a0),%d2\n"               /* dst += -g (x0 + x1) */
    "        move.l  %d2,%acc0\n"
    "        msac.l  %d0,%d1,(%a1)+,%d1,%acc0\n"
    "        msac.l  %d0,%d1,(%a1)+,%d1,%acc0\n"
    "        movclr.l %acc0,%d2\n"
    "        move.l  %d2,(%a0)+\n"
    "        subq.l  #1,%d3\n"
    "        bne.s   2b\n"
    "9:      movem.l (%sp),%d2-%d3\n"
    "        lea     8(%sp),%sp\n"
    "        rts\n"
    "        .globl  fx3_sum_end\n"
    "fx3_sum_end:\n"
    "        .globl  fx3_cho\n"
    "fx3_cho:\n"
    "        lea     -44(%sp),%sp\n"
    "        movem.l %d2-%d7/%a2-%a6,(%sp)\n"
    "        movea.l 48(%sp),%a6\n"
    "        movea.l (%a6),%a0\n"               /* linea (-4: retroazione Q15) */
    "        movea.l 4(%a6),%a1\n"              /* ingresso mono (parola alta di ogni campione) */
    "        movea.l 8(%a6),%a2\n"              /* uscita */
    "        lea     2048(%a0),%a3\n"           /* copia della linea */
    "        move.l  12(%a6),%d0\n"             /* pl, pr: posizioni di lettura Q8 */
    "        move.l  16(%a6),%d1\n"
    "        movea.l 20(%a6),%a4\n"             /* il, ir: passi */
    "        movea.l 24(%a6),%a5\n"
    "        move.l  28(%a6),%d4\n"             /* w: scrittura */
    "        moveq   #16,%d5\n"
    "        tst.l   -4(%a0)\n"
    "        bne.w   2f\n"
    "1:      add.l   %a4,%d0\n"                 /* un campione per giro (letture nella copia) */
    "        add.l   %a5,%d1\n"
    "        move.l  %d0,%d6\n"                 /* presa sinistra */
    "        lsr.l   #8,%d6\n"
    "        mvs.w   (%a0,%d6.l*2),%d7\n"
    "        mvs.w   2(%a0,%d6.l*2),%d6\n"
    "        sub.l   %d7,%d6\n"
    "        asr.l   #1,%d6\n"                  /* la differenza sta in 16 bit */
    "        mvz.b   %d0,%d2\n"
    "        muls.w  %d2,%d6\n"
    "        asr.l   #7,%d6\n"
    "        add.l   %d7,%d6\n"
    "        move.l  %d1,%d3\n"                 /* presa destra */
    "        lsr.l   #8,%d3\n"
    "        mvs.w   (%a0,%d3.l*2),%d7\n"
    "        mvs.w   2(%a0,%d3.l*2),%d3\n"
    "        sub.l   %d7,%d3\n"
    "        asr.l   #1,%d3\n"                  /* la differenza sta in 16 bit */
    "        mvz.b   %d1,%d2\n"
    "        muls.w  %d2,%d3\n"
    "        asr.l   #7,%d3\n"
    "        add.l   %d3,%d7\n"
    "        move.l  %d6,(%a2)+\n"
    "        move.l  %d7,(%a2)+\n"
    "        move.w  (%a1),%d2\n"               /* ingresso (parola alta) */
    "        addq.l  #4,%a1\n"
    "        move.w  %d2,(%a0,%d4.l*2)\n"
    "        move.w  %d2,(%a3,%d4.l*2)\n"
    "        addq.l  #1,%d4\n"
    "        subq.l  #1,%d5\n"
    "        bne.w   1b\n"
    "        bra.w   9f\n"
    "2:\n"
    "1:      add.l   %a4,%d0\n"                 /* un campione per giro (letture nella copia) */
    "        add.l   %a5,%d1\n"
    "        move.l  %d0,%d6\n"                 /* presa sinistra */
    "        lsr.l   #8,%d6\n"
    "        mvs.w   (%a0,%d6.l*2),%d7\n"
    "        mvs.w   2(%a0,%d6.l*2),%d6\n"
    "        sub.l   %d7,%d6\n"
    "        asr.l   #1,%d6\n"                  /* la differenza sta in 16 bit */
    "        mvz.b   %d0,%d2\n"
    "        muls.w  %d2,%d6\n"
    "        asr.l   #7,%d6\n"
    "        add.l   %d7,%d6\n"
    "        move.l  %d1,%d3\n"                 /* presa destra */
    "        lsr.l   #8,%d3\n"
    "        mvs.w   (%a0,%d3.l*2),%d7\n"
    "        mvs.w   2(%a0,%d3.l*2),%d3\n"
    "        sub.l   %d7,%d3\n"
    "        asr.l   #1,%d3\n"                  /* la differenza sta in 16 bit */
    "        mvz.b   %d1,%d2\n"
    "        muls.w  %d2,%d3\n"
    "        asr.l   #7,%d3\n"
    "        add.l   %d3,%d7\n"
    "        move.l  %d6,(%a2)+\n"
    "        move.l  %d7,(%a2)+\n"
    "        move.l  %d6,%d2\n"                 /* retroazione mono e ingresso, saturati a 16 bit */
    "        add.l   %d7,%d2\n"
    "        asr.l   #1,%d2\n"
    "        muls.l  -4(%a0),%d2\n"
    "        moveq   #15,%d3\n"
    "        asr.l   %d3,%d2\n"
    "        mvs.w   (%a1),%d3\n"
    "        addq.l  #4,%a1\n"
    "        add.l   %d3,%d2\n"
    "        cmpi.l  #32767,%d2\n"
    "        ble.s   3f\n"
    "        move.l  #32767,%d2\n"
    "3:      cmpi.l  #-32768,%d2\n"
    "        bge.s   4f\n"
    "        move.l  #-32768,%d2\n"
    "4:\n"
    "        move.w  %d2,(%a0,%d4.l*2)\n"
    "        move.w  %d2,(%a3,%d4.l*2)\n"
    "        addq.l  #1,%d4\n"
    "        subq.l  #1,%d5\n"
    "        bne.w   1b\n"
    "9:      move.l  %d0,12(%a6)\n"
    "        move.l  %d1,16(%a6)\n"
    "        move.l  %d4,28(%a6)\n"
    "        move.l  %d6,32(%a6)\n"
    "        move.l  %d7,36(%a6)\n"
    "        movem.l (%sp),%d2-%d7/%a2-%a6\n"
    "        lea     44(%sp),%sp\n"
    "        rts\n"
    "        .globl  fx3_ret\n"
    "fx3_ret:\n"                                /* (wet, guadagno Q15, a, h[2]): a -= 2 * wet * guadagno a 48 kHz, */
    "        lea     -28(%sp),%sp\n"            /* saturato; i campioni dispari sono quelli del chorus, */
    "        movem.l %d2-%d7/%a2,(%sp)\n"       /* i pari la media con il precedente (h = mezzo campione) */
    "        movea.l 32(%sp),%a0\n"
    "        move.l  36(%sp),%d1\n"
    "        movea.l 44(%sp),%a1\n"
    "        move.l  (%a1),%d2\n"
    "        move.l  4(%a1),%d3\n"
    "        movea.l 40(%sp),%a1\n"
    "        lea     256(%a1),%a2\n"            /* fine: 32 coppie L/R */
    "1:      movem.l (%a1),%d4-%d7\n"           /* L R di un campione pari e del dispari seguente */
    "        move.l  (%a0)+,%d0\n"
    "        muls.w  %d1,%d0\n"
    "        add.l   %d0,%d2\n"
    "        sub.l   %d2,%d4\n"
    "        sats.l  %d4\n"
    "        move.l  %d0,%d2\n"
    "        add.l   %d0,%d0\n"
    "        sub.l   %d0,%d6\n"
    "        sats.l  %d6\n"
    "        move.l  (%a0)+,%d0\n"
    "        muls.w  %d1,%d0\n"
    "        add.l   %d0,%d3\n"
    "        sub.l   %d3,%d5\n"
    "        sats.l  %d5\n"
    "        move.l  %d0,%d3\n"
    "        add.l   %d0,%d0\n"
    "        sub.l   %d0,%d7\n"
    "        sats.l  %d7\n"
    "        movem.l %d4-%d7,(%a1)\n"
    "        lea     16(%a1),%a1\n"
    "        cmpa.l  %a2,%a1\n"
    "        bne.s   1b\n"
    "        movea.l 44(%sp),%a1\n"
    "        move.l  %d2,(%a1)\n"
    "        move.l  %d3,4(%a1)\n"
    "        movem.l (%sp),%d2-%d7/%a2\n"
    "        lea     28(%sp),%sp\n"
    "        rts\n");

/* trampolini */
__asm__(
    "        .globl  fx3_trk_hook\n"
    "fx3_trk_hook:\n"                           /* ciclo per traccia (0x4008F3A0): d0/d1 guadagni, */
    "        .word   0xae00, 0x0900\n"          /* d3 traccia, a3 struttura; istruzioni sostituite: */
    "        .word   0xae81, 0x0900\n"          /* msac.l d0,d7,acc0 ; msac.l d1,d7,acc1 */
    "        tst.w   106(%a3)\n"                /* SND3 (id 72) spenta e bersaglio gia' 0: niente */
    "        bgt.s   1f\n"                      /* da fare (il caso comune, 12 volte a blocco) */
    "        move.l  %a0,-(%sp)\n"
    "        lea     fx3_tgt,%a0\n"
    "        tst.l   (%a0,%d3.l*4)\n"
    "        bne.s   2f\n"
    "        movea.l (%sp)+,%a0\n"
    "        rts\n"
    "2:      movea.l (%sp)+,%a0\n"
    "1:      lea     -16(%sp),%sp\n"            /* bersaglio mono della traccia (meta', per le */
    "        movem.l %d0-%d2/%a0,(%sp)\n"       /* coppie): ((gl/2 + gr/2) >> 16) * (2 v^2 >> 16) */
    "        moveq   #12,%d2\n"                 /* 0..7 digitali, 8..11 analogiche */
    "        cmp.l   %d2,%d3\n"
    "        bcc.s   9f\n"
    "        move.l  -508(%fp),%d2\n"           /* maschera dei mute */
    "        btst    %d3,%d2\n"
    "        bne.s   8f\n"
    "        mvs.w   106(%a3),%d2\n"            /* SND3 (id 72) */
    "        tst.l   %d2\n"
    "        ble.s   8f\n"
    "        muls.w  %d2,%d2\n"                 /* (v/32768)^2 in Q31, come DEL e REV */
    "        add.l   %d2,%d2\n"
    "        swap    %d2\n"
    "        asr.l   #1,%d0\n"
    "        asr.l   #1,%d1\n"
    "        add.l   %d1,%d0\n"
    "        swap    %d0\n"
    "        muls.w  %d0,%d2\n"
    "        bra.s   7f\n"
    "8:      moveq   #0,%d2\n"
    "7:      lea     fx3_tgt,%a0\n"
    "        cmp.l   (%a0,%d3.l*4),%d2\n"
    "        beq.s   9f\n"
    "        move.l  %a0,fx3_moving\n"          /* bersaglio cambiato: la rampa riparte */
    "        move.l  %d2,(%a0,%d3.l*4)\n"
    "9:      movem.l (%sp),%d0-%d2/%a0\n"
    "        lea     16(%sp),%sp\n"
    "        rts\n"
    "        .globl  fx3_del_hook\n"
    "fx3_del_hook:\n"                           /* al posto di jsr 0x40096890 (delay), 0x4008F828 */
    "        tst.l   fx3_idle\n"
    "        bne.s   1f\n"
    "        lea     -16(%sp),%sp\n"
    "        movem.l %d0-%d1/%a0-%a1,(%sp)\n"
    "        jsr     fx3_dsnd\n"                /* chorus del blocco precedente nel bus del delay */
    "        movem.l (%sp),%d0-%d1/%a0-%a1\n"
    "        lea     16(%sp),%sp\n"
    "1:      jmp     0x40096890\n"              /* il delay, con gli argomenti al loro posto */
    "        .globl  fx3_mix_hook\n"
    "fx3_mix_hook:\n"                           /* 0x4008FB04: al posto di pea -296(fp) ; pea 0x8000E0F0 */
    "        lea     -16(%sp),%sp\n"
    "        movem.l %d0-%d1/%a0-%a1,(%sp)\n"
    "        .globl  fx3_macsr\n"
    "fx3_macsr:\n"
    "        move.l  #0xA0,%macsr\n"            /* come l'OS prima delle somme (lo e' gia') */
    "        jsr     fx3_run\n"
    "        movem.l (%sp),%d0-%d1/%a0-%a1\n"
    "        lea     16(%sp),%sp\n"
    "        move.l  (%sp)+,%a0\n"
    "        pea     -296(%fp)\n"               /* istruzioni sostituite */
    "        pea     0x8000E0F0\n"
    "        jmp     (%a0)\n"
    "        .globl  fx3_draw_hook\n"
    "fx3_draw_hook:\n"                          /* disegno dei tab DELAY/REVERB (0x40042CE0): la pagina 25 */
    "        movea.l 4(%sp),%a0\n"              /* usa il disegno generico a 8 caselle (0x4003A244) */
    "        move.l  144(%a0),%d0\n"            /* posizione della pagina corrente */
    "        movea.l 124(%a0),%a1\n"            /* vettore delle pagine */
    "        move.l  (%a1,%d0.l*4),%d0\n"
    "        moveq   #25,%d1\n"
    "        cmp.l   %d1,%d0\n"
    "        bne.s   1f\n"
    "        jmp     0x4003A244\n"
    "1:      lea     -96(%sp),%sp\n"            /* istruzioni sostituite */
    "        movem.l %d2-%d7/%a2-%a6,(%sp)\n"
    "        jmp     0x40042CE8\n"
    "        .globl  fx3_page_stub\n"
    "fx3_page_stub:\n"                          /* al posto di clr.l 0x41B9F83C: caselle della pagina 25 */
    "        move.l  %a0,-(%sp)\n"
    "        move.l  %d0,-(%sp)\n"
    "        lea     0x41B9F81C,%a0\n"
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
    "        clr.l   (%a0)\n"                   /* +40 (istruzione sostituita) */
    "        move.l  (%sp)+,%d0\n"
    "        move.l  (%sp)+,%a0\n"
    "        rts\n"
    "        .globl  fx3_amp_stub\n"
    "fx3_amp_stub:\n"                           /* al posto di clr.l 0x41B9F6A0: casella E di AMP 2 */
    "        move.l  %d0,-(%sp)\n"
    "        moveq   #72,%d0\n"
    "        move.l  %d0,0x41B9F674\n"
    "        move.l  %d0,0x41B9F6A0\n"
    "        move.l  (%sp)+,%d0\n"
    "        rts\n");
