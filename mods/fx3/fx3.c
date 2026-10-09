/* fx3: terza mandata effetti (Syntakt OS 1.41), primo effetto: chorus stereo.
 *
 * Audio (funzione di mix a blocchi 0x4008F1CA, 32 campioni a 48 kHz):
 * - nel ciclo per traccia (0x4008F3A0) fx3_trk_hook prende i guadagni sinistro/destro della traccia
 *   (livello e pan) e il valore di SND3 (parola +106 del motore = id 72, salvato per traccia) e ne
 *   ricava il bersaglio mono della mandata, come l'OS fa per DEL e REV;
 * - prima del delay (0x4008F828) fx3_block somma le tracce nel bus 3 con la stessa routine dell'OS
 *   delle altre mandate (0x4008F03E: guadagni in rampa), digitali e analogiche, lo passa al chorus e
 *   aggiunge l'uscita, scalata dalla mandata DEL, al bus d'ingresso del delay (0x8000DBD0);
 * - dopo le somme del master (0x4008FB04) fx3_out aggiunge il ritorno, scalato da VOL, al bus diretto
 *   (0x8000DAD0), con la convenzione di segno dell'OS.
 * Costo per blocco misurato in emulazione (tests/test_fx3.py): ~0 a riposo, poche migliaia di istruzioni
 * con tutte le mandate attive; i cicli caldi sono in assembly.
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
#define N         32                                       /* campioni per blocco */
#define DL        2048                                     /* linea di ritardo: 42 ms (TIME + DEP <= 38 ms) */
#define DL_M      ((s16 *)0x4600E000u)                     /* linea mono + copia a +DL (area mod azzerata) */
#define SRC_DIG   0x80003D50u                              /* 8 tracce digitali x 32 campioni */
#define SRC_ANA   0x80003950u                              /* tracce analogiche (canali 0..3) */
#define OUT_A     ((s32 *)0x8000DAD0u)                     /* bus d'uscita, L/R alternati */
#define OUT_B     ((s32 *)0x8000DFD0u)
#define DLY_IN    ((s32 *)0x8000DBD0u)                     /* bus d'ingresso del delay, L/R alternati */
#define UI_ROOT   (*(char *const volatile *)0x444E1334u)
#define DRAW_TEXT ((void (*)(void *, const void *, s32, s32, s32, s32, const char *, const char *, ...))                    0x400F8C18u)                            /* (ctx, font, x, y, centrato, 0, sagoma, fmt, ...) */
#define FONT      ((const void *)0x402A91C0u)              /* 4x6 */

enum { P_TYPE, P_SPD, P_DEP, P_TIME, P_FDBK, P_WID, P_DSND, P_VOL, NP };
static const unsigned short ids[NP] = {246, 247, 248, 250, 251, 252, 249, 253};
static const unsigned char maxv[NP] = {0, 127, 127, 127, 127, 127, 127, 127};
unsigned char fx3_p[NP] DATA = {0, 60, 64, 64, 0, 64, 0, 100};

s32 fx3_tgt[16] DATA = {0};                              /* bersagli mono: 0..7 digitali, 8..11 analogiche */
s32 fx3_cur[16] DATA = {0};                              /* guadagni del blocco (levigati verso i bersagli) */
s32 fx3_bus[N] DATA = {0};                               /* bus 3 mono */
s32 fx3_wet[2 * N] DATA = {0};                            /* uscita del chorus (scala 16 bit), L/R alternati */
s32 fx3_idle DATA = 1;                                    /* 1 = nessuna mandata e coda esaurita: niente da fare */
static u32 quiet DATA = 0;                                /* blocchi consecutivi senza ingresso ne' coda */
static u32 wpos DATA = 0, phase DATA = 0, dpos[2] DATA = {0, 0};


static s32 lfo(u32 ph)                                    /* seno unipolare 0..32767 */
{
    u32 i = ph >> 24, f = (ph >> 8) & 0xFFFF;
    s32 a = SIN_T[i], b = SIN_T[i + 1];
    return (a + (((b - a) * (s32)(f >> 1)) >> 15) + 32768) >> 1;
}


static const s32 zero[N] = {0};

/* ciclo del chorus in assembly (fx3_cho, sotto): 32 campioni, due prese interpolate dalla linea doppia
 * (nessun ritorno a capo in lettura), retroazione mono saturata a 16 bit, mandata al delay nello stesso
 * giro; quattro varianti (con/senza retroazione, con/senza mandata). Retroazione e mandata stanno subito
 * prima della linea (letture relative al suo indirizzo: muls.l non accetta indirizzi assoluti). */
struct cho { s16 *line; const s32 *in; s32 *wet; s32 *dly; u32 pl, pr, il, ir, w; s32 yl, yr; };
#define CHO_FB    (*(volatile s32 *)((char *)DL_M - 4))
#define CHO_DS    (*(volatile s16 *)((char *)DL_M - 6))
void fx3_cho(struct cho *c);
void fx3_mix(const s32 *wet, s32 gain, s32 *a);         /* a -= 2 * wet * gain (saturato) */

/* chorus: una linea mono, due prese (L/R) modulate da un LFO calcolato a inizio e fine blocco e
 * interpolato linearmente (le posizioni di lettura avanzano di 1 - pendenza a campione). VOL si applica
 * al ritorno; la mandata DEL va al bus del delay, solo se accesa. Ritorna 1 se la coda e' (quasi) muta. */
static u32 chorus(u32 live)
{
    struct cho c;
    u32 base = DEL_Q8[fx3_p[P_TIME]], dep = DEP_Q8[fx3_p[P_DEP]];
    u32 off = (u32)fx3_p[P_WID] * 0x01020408u;             /* 0..180 gradi */
    u32 end = phase + SPD_INC[fx3_p[P_SPD]] * N;
    u32 el = base + ((dep * (u32)lfo(end)) >> 15), er = base + ((dep * (u32)lfo(end + off)) >> 15);
    s32 ds = VOL_Q15[fx3_p[P_DSND]];

    c.line = DL_M;
    c.in = live ? fx3_bus : zero;
    c.wet = fx3_wet;
    c.pl = ((wpos << 8) - dpos[0] - 256) & ((DL << 8) - 1);
    c.pr = ((wpos << 8) - dpos[1] - 256) & ((DL << 8) - 1);
    c.il = 256 - (u32)(((s32)(el - dpos[0])) >> 5);
    c.ir = 256 - (u32)(((s32)(er - dpos[1])) >> 5);
    c.w = wpos;
    c.dly = ds ? DLY_IN : 0;                               /* il bus del delay ha la convenzione del bus 3 */
    CHO_FB = FB_Q15[fx3_p[P_FDBK]];
    CHO_DS = (s16)ds;
    fx3_cho(&c);
    wpos = c.w;
    phase = end;
    dpos[0] = el;
    dpos[1] = er;
    /* coda muta sotto 10/32768 (-70 dB): con la retroazione l'arrotondamento puo' lasciare un residuo
     * costante di qualche unita' che non si spegnerebbe mai */
    return (u32)(c.yl + 10) <= 20 && (u32)(c.yr + 10) <= 20;
}

/* somme del bus in assembly (fx3_sum8, fx3_add4, sotto): EMAC con caricamento, come le routine delle
 * mandate dell'OS ma con il guadagno costante nel blocco (niente rampa per campione); stesso segno (msac) */
void fx3_sum8(s32 *dst, u32 src, const s32 *g);           /* dst[n] = -sum g[k] x_k[n], 8 canali */
void fx3_add4(s32 *dst, u32 src, const s32 *g);           /* dst[n] += -sum g[k] x_k[n], 4 canali */

/* prima del delay (MACSR gia' impostato): bus 3 dalle tracce, chorus e mandata verso il delay (stessa
 * convenzione di segno del suo bus d'ingresso). Senza mandate attive e a coda esaurita non fa nulla.
 * I guadagni seguono i bersagli di 1/4 a blocco (~2.7 ms) e li raggiungono esatti quando sono vicini. */
void fx3_block(void)
{
    u32 k, n, dig = 0, ana = 0, silent;

    if (!(fx3_p[P_VOL] | fx3_p[P_DSND])) {                 /* nessuno ascolta l'uscita */
        fx3_idle = 1;
        return;
    }
    for (k = 0; k < 12; k++)                               /* a riposo: uscita rapida */
        dig |= (u32)(fx3_tgt[k] | fx3_cur[k]);
    if (!dig && quiet > DL / N) {
        fx3_idle = 1;
        return;
    }
    dig = 0;
    for (k = 0; k < 12; k++) {
        s32 t = fx3_tgt[k], c = fx3_cur[k], d = t - c;
        c = d > -64 && d < 64 ? t : c + (d >> 2);          /* senza l'aggancio un piccolo resto non si */
        fx3_cur[k] = c;                                    /* annullerebbe mai e FX3 non tornerebbe a riposo */
        if (k < 8)
            dig |= (u32)c;
        else
            ana |= (u32)c;
    }
    if (!(dig | ana) && quiet > DL / N) {
        fx3_idle = 1;
        return;
    }
    fx3_idle = 0;
    if (dig)
        fx3_sum8(fx3_bus, SRC_DIG, fx3_cur);
    else if (ana)
        for (n = 0; n < N; n++)
            fx3_bus[n] = 0;
    if (ana)
        fx3_add4(fx3_bus, SRC_ANA, fx3_cur + 8);
    silent = chorus(dig | ana);
    quiet = (dig | ana) || !silent ? 0 : quiet + 1;
}

/* dopo le somme del master: ritorno sul bus diretto (come delay e riverbero con FX Routing spento; il
 * bus 0x8000DFD0 passa dal blocco FX analogico). L'OS sottrae (msac). */
void fx3_out(void)
{
    s32 vol = VOL_Q15[fx3_p[P_VOL]];

    if (!fx3_idle && vol)
        fx3_mix(fx3_wet, vol, OUT_A);
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

#ifdef METER
/* misuratore di carico (solo build di prova): tempo passato nell'interrupt audio 0x400A3856, letto dal
 * contatore libero DTIM0 all'ingresso e all'uscita; ogni 1500 interrupt media e picco in percentuale */
u32 fx3_m_t0 DATA = 0, fx3_m_busy DATA = 0, fx3_m_peak DATA = 0, fx3_m_n DATA = 0, fx3_m_start DATA = 0;
u32 fx3_m_avg DATA = 0, fx3_m_max DATA = 0;

void fx3_meter(u32 now)
{
    u32 busy = now - fx3_m_t0, el;
    char *ui = UI_ROOT;

    fx3_m_busy += busy;
    if (busy > fx3_m_peak)
        fx3_m_peak = busy;
    if (++fx3_m_n < 1500)
        return;
    el = (now - fx3_m_start) / 100;
    if (el) {
        fx3_m_avg = fx3_m_busy / el;
        fx3_m_max = fx3_m_peak * fx3_m_n / el;
    }
    fx3_m_busy = fx3_m_peak = fx3_m_n = 0;
    fx3_m_start = now;
    if (ui)
        ui[96] = 1;
}
#endif

/* grafica di TYPE (+36): il tipo come testo, centrato come le destinazioni degli LFO; nella build di
 * prova col misuratore, carico medio/picco dell'interrupt audio in % */
void fx3_type_gfx(const void *fn, s32 value, void *ctx, s32 x, s32 y)
{
    (void)fn;
    (void)value;
#ifdef METER
    DRAW_TEXT(ctx, FONT, x + 8, y + 5, 1, 0, "XXXXX", "%d/%d", (s32)fx3_m_avg, (s32)fx3_m_max);
#else
    DRAW_TEXT(ctx, FONT, x + 8, y + 5, 1, 0, "XXXX", "%s", "CHOR");
#endif
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
    "        .globl  fx3_sum8\n"
    "fx3_sum8:\n"                               /* (dst, src, g[8]): 8 canali da 32 campioni a passo 128 B */
    "        lea     -44(%sp),%sp\n"
    "        movem.l %d2-%d7/%a2-%a6,(%sp)\n"
    "        movea.l 48(%sp),%a5\n"
    "        movea.l 52(%sp),%a4\n"
    "        movea.l 56(%sp),%a6\n"
    "        movem.l (%a6),%d0-%d4/%a0-%a2\n"
    "        moveq   #32,%d5\n"
    "        move.l  (%a4)+,%d6\n"
    "1:      msac.l  %d0,%d6,124(%a4),%d6,%acc0\n"
    "        msac.l  %d1,%d6,252(%a4),%d6,%acc0\n"
    "        msac.l  %d2,%d6,380(%a4),%d6,%acc0\n"
    "        msac.l  %d3,%d6,508(%a4),%d6,%acc0\n"
    "        msac.l  %d4,%d6,636(%a4),%d6,%acc0\n"
    "        msac.l  %a0,%d6,764(%a4),%d6,%acc0\n"
    "        msac.l  %a1,%d6,892(%a4),%d6,%acc0\n"
    "        msac.l  %a2,%d6,(%a4)+,%d6,%acc0\n"
    "        movclr.l %acc0,%d7\n"
    "        move.l  %d7,(%a5)+\n"
    "        subq.l  #1,%d5\n"
    "        bgt.s   1b\n"
    "        movem.l (%sp),%d2-%d7/%a2-%a6\n"
    "        lea     44(%sp),%sp\n"
    "        rts\n"
    "        .globl  fx3_add4\n"
    "fx3_add4:\n"                               /* (dst, src, g[4]): somma (saturata) di 4 canali */
    "        lea     -32(%sp),%sp\n"
    "        movem.l %d2-%d7/%a4-%a5,(%sp)\n"
    "        movea.l 36(%sp),%a5\n"
    "        movea.l 40(%sp),%a4\n"
    "        movea.l 44(%sp),%a0\n"
    "        movem.l (%a0),%d0-%d3\n"
    "        moveq   #32,%d5\n"
    "        move.l  (%a4)+,%d6\n"
    "1:      msac.l  %d0,%d6,124(%a4),%d6,%acc0\n"
    "        msac.l  %d1,%d6,252(%a4),%d6,%acc0\n"
    "        msac.l  %d2,%d6,380(%a4),%d6,%acc0\n"
    "        msac.l  %d3,%d6,(%a4)+,%d6,%acc0\n"
    "        movclr.l %acc0,%d7\n"
    "        add.l   (%a5),%d7\n"
    "        sats.l  %d7\n"
    "        move.l  %d7,(%a5)+\n"
    "        subq.l  #1,%d5\n"
    "        bgt.s   1b\n"
    "        movem.l (%sp),%d2-%d7/%a4-%a5\n"
    "        lea     32(%sp),%sp\n"
    "        rts\n"
    "        .globl  fx3_sum_end\n"
    "fx3_sum_end:\n"
    "        .macro  CHO fb, ds\n"  /* un campione per giro; fb, ds = 0/1 */
    ".Lc\\@:  add.l   %a4,%d0\n"
    "        andi.l  #0x7FFFF,%d0\n"
    "        add.l   %a5,%d1\n"
    "        andi.l  #0x7FFFF,%d1\n"
    "        move.l  %d0,%d6\n"  /* presa sinistra */
    "        lsr.l   #8,%d6\n"
    "        mvs.w   (%a0,%d6.l*2),%d7\n"
    "        mvs.w   2(%a0,%d6.l*2),%d6\n"
    "        sub.l   %d7,%d6\n"
    "        mvz.b   %d0,%d2\n"
    "        muls.w  %d2,%d6\n"
    "        asr.l   #8,%d6\n"
    "        add.l   %d7,%d6\n"
    "        move.l  %d1,%d3\n"  /* presa destra */
    "        lsr.l   #8,%d3\n"
    "        mvs.w   (%a0,%d3.l*2),%d7\n"
    "        mvs.w   2(%a0,%d3.l*2),%d3\n"
    "        sub.l   %d7,%d3\n"
    "        mvz.b   %d1,%d2\n"
    "        muls.w  %d2,%d3\n"
    "        asr.l   #8,%d3\n"
    "        add.l   %d3,%d7\n"
    "        move.l  %d6,(%a2)+\n"
    "        move.l  %d7,(%a2)+\n"
    "        .if     \\ds\n"  /* mandata al delay (convenzione del bus 3) */
    "        move.l  %d6,%d2\n"
    "        muls.w  -6(%a0),%d2\n"
    "        add.l   %d2,%d2\n"
    "        add.l   (%a6),%d2\n"
    "        sats.l  %d2\n"
    "        move.l  %d2,(%a6)+\n"
    "        move.l  %d7,%d2\n"
    "        muls.w  -6(%a0),%d2\n"
    "        add.l   %d2,%d2\n"
    "        add.l   (%a6),%d2\n"
    "        sats.l  %d2\n"
    "        move.l  %d2,(%a6)+\n"
    "        .endif\n"
    "        .if     \\fb\n"  /* retroazione mono e ingresso, saturati a 16 bit */
    "        move.l  %d6,%d2\n"
    "        add.l   %d7,%d2\n"
    "        asr.l   #1,%d2\n"
    "        muls.l  -4(%a0),%d2\n"
    "        moveq   #15,%d3\n"
    "        asr.l   %d3,%d2\n"
    "        mvs.w   (%a1),%d3\n"
    "        addq.l  #4,%a1\n"
    "        add.l   %d3,%d2\n"
    "        cmpi.l  #32767,%d2\n"
    "        ble.s   .La\\@\n"
    "        move.l  #32767,%d2\n"
    ".La\\@:  cmpi.l  #-32768,%d2\n"
    "        bge.s   .Lb\\@\n"
    "        move.l  #-32768,%d2\n"
    ".Lb\\@:\n"
    "        .else\n"
    "        move.w  (%a1),%d2\n"  /* ingresso gia' a 16 bit */
    "        addq.l  #4,%a1\n"
    "        .endif\n"
    "        move.w  %d2,(%a0,%d4.l*2)\n"
    "        move.w  %d2,(%a3,%d4.l*2)\n"
    "        addq.l  #1,%d4\n"
    "        andi.l  #2047,%d4\n"
    "        subq.l  #1,%d5\n"
    "        bne.w   .Lc\\@\n"
    "        .endm\n"
    "        .globl  fx3_cho\n"
    "fx3_cho:\n"
    "        lea     -48(%sp),%sp\n"
    "        movem.l %d2-%d7/%a2-%a6,(%sp)\n"
    "        movea.l 52(%sp),%a6\n"
    "        move.l  %a6,44(%sp)\n"
    "        movea.l (%a6),%a0\n"  /* linea (-4: retroazione Q15, -6: mandata DEL Q15) */
    "        movea.l 4(%a6),%a1\n"  /* ingresso mono (parola alta di ogni campione) */
    "        movea.l 8(%a6),%a2\n"  /* uscita */
    "        lea     4096(%a0),%a3\n"  /* copia della linea */
    "        move.l  16(%a6),%d0\n"  /* pl, pr: posizioni di lettura Q8 */
    "        move.l  20(%a6),%d1\n"
    "        movea.l 24(%a6),%a4\n"  /* il, ir: passi */
    "        movea.l 28(%a6),%a5\n"
    "        move.l  32(%a6),%d4\n"  /* w: scrittura */
    "        movea.l 12(%a6),%a6\n"  /* bus del delay, o 0 se DEL e' spento */
    "        moveq   #32,%d5\n"
    "        move.l  %a6,%d2\n"
    "        tst.l   -4(%a0)\n"
    "        bne.w   2f\n"
    "        tst.l   %d2\n"
    "        bne.w   1f\n"
    "        CHO     0, 0\n"
    "        bra.w   9f\n"
    "1:      CHO     0, 1\n"
    "        bra.w   9f\n"
    "2:      tst.l   %d2\n"
    "        bne.w   3f\n"
    "        CHO     1, 0\n"
    "        bra.w   9f\n"
    "3:      CHO     1, 1\n"
    "9:      movea.l 44(%sp),%a6\n"
    "        move.l  %d0,16(%a6)\n"
    "        move.l  %d1,20(%a6)\n"
    "        move.l  %d4,32(%a6)\n"
    "        move.l  %d6,36(%a6)\n"
    "        move.l  %d7,40(%a6)\n"
    "        movem.l (%sp),%d2-%d7/%a2-%a6\n"
    "        lea     48(%sp),%sp\n"
    "        rts\n"
    "        .globl  fx3_mix\n"
    "fx3_mix:\n"                                /* (wet, guadagno Q15, a): a -= 2 * wet * guadagno, saturato */
    "        movea.l 4(%sp),%a0\n"
    "        move.l  8(%sp),%d1\n"
    "        movea.l 12(%sp),%a1\n"
    "        moveq   #32,%d0\n"                  /* 32 coppie L/R */
    "        move.l  %d2,-(%sp)\n"
    "        move.l  %d3,-(%sp)\n"
    "1:      move.l  (%a0)+,%d2\n"
    "        muls.w  %d1,%d2\n"
    "        add.l   %d2,%d2\n"
    "        move.l  (%a1),%d3\n"
    "        sub.l   %d2,%d3\n"
    "        sats.l  %d3\n"
    "        move.l  %d3,(%a1)+\n"
    "        move.l  (%a0)+,%d2\n"
    "        muls.w  %d1,%d2\n"
    "        add.l   %d2,%d2\n"
    "        move.l  (%a1),%d3\n"
    "        sub.l   %d2,%d3\n"
    "        sats.l  %d3\n"
    "        move.l  %d3,(%a1)+\n"
    "        subq.l  #1,%d0\n"
    "        bne.s   1b\n"
    "        move.l  (%sp)+,%d3\n"
    "        move.l  (%sp)+,%d2\n"
    "        rts\n");

#ifdef METER
__asm__(
    "        .globl  fx3_m_in\n"
    "fx3_m_in:\n"                               /* ingresso dell'interrupt audio (0x400A3856) */
    "        move.l  %d0,-(%sp)\n"
    "        move.l  0xFC07000C,%d0\n"
    "        move.l  %d0,fx3_m_t0\n"
    "        move.l  (%sp)+,%d0\n"
    "        link.w  %fp,#-164\n"               /* istruzioni sostituite */
    "        movem.l %d0-%d7/%a0-%a5,(%sp)\n"
    "        jmp     0x400A385E\n"
    "        .globl  fx3_m_out\n"
    "fx3_m_out:\n"                              /* uscita (0x400A54A0): i registri vengono ripristinati */
    "        move.l  0xFC07000C,%d0\n"          /* subito dopo, si possono usare */
    "        move.l  %d0,-(%sp)\n"
    "        jsr     fx3_meter\n"
    "        addq.l  #4,%sp\n"
    "        movem.l -164(%fp),%d0-%d7/%a0-%a5\n"   /* istruzioni sostituite */
    "        unlk    %fp\n"
    "        rte\n");
#endif

/* trampolini */
__asm__(
    "        .globl  fx3_trk_hook\n"
    "fx3_trk_hook:\n"                           /* ciclo per traccia (0x4008F3A0): d0/d1 guadagni, */
    "        .word   0xae00, 0x0900\n"          /* d3 traccia, a3 struttura; istruzioni sostituite: */
    "        .word   0xae81, 0x0900\n"          /* msac.l d0,d7,acc0 ; msac.l d1,d7,acc1 */
    "        lea     -16(%sp),%sp\n"            /* bersaglio mono della traccia: */
    "        movem.l %d0-%d2/%a0,(%sp)\n"       /* ((gl/2 + gr/2) >> 16) * (2 v^2 >> 16) << 1 */
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
    "        add.l   %d2,%d2\n"
    "        bra.s   7f\n"
    "8:      moveq   #0,%d2\n"
    "7:      lea     fx3_tgt,%a0\n"
    "        move.l  %d2,(%a0,%d3.l*4)\n"
    "9:      movem.l (%sp),%d0-%d2/%a0\n"
    "        lea     16(%sp),%sp\n"
    "        rts\n"
    "        .globl  fx3_del_hook\n"
    "fx3_del_hook:\n"                           /* al posto di jsr 0x40096890 (delay), 0x4008F828 */
    "        lea     -16(%sp),%sp\n"
    "        movem.l %d0-%d1/%a0-%a1,(%sp)\n"
    "        .globl  fx3_macsr\n"
    "fx3_macsr:\n"
    "        move.l  #0xA0,%macsr\n"            /* come l'OS prima delle routine delle mandate */
    "        jsr     fx3_block\n"
    "        movem.l (%sp),%d0-%d1/%a0-%a1\n"
    "        lea     16(%sp),%sp\n"
    "        jmp     0x40096890\n"              /* il delay, con gli argomenti al loro posto */
    "        .globl  fx3_mix_hook\n"
    "fx3_mix_hook:\n"                           /* 0x4008FB04: al posto di pea -296(fp) ; pea 0x8000E0F0 */
    "        lea     -16(%sp),%sp\n"
    "        movem.l %d0-%d1/%a0-%a1,(%sp)\n"
    "        jsr     fx3_out\n"
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
