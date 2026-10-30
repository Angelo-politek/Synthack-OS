/* dual mono v2: IN L e IN R con mandate proprie (DEL, REV, FX3), nell'area mod (Syntakt OS 1.41).
 *
 * Con EXTERNAL IN = mono il tab MIXER ha una quarta pagina, IN R (pagina 27, "MIDI Source" della
 * Digitakt, mai mostrata sulla Syntakt): IN R, FX3, DEL, REV. La pagina External Mixer resta quella
 * di IN L. Le mandate del lato R stanno in tre parole del kit (kitstore, blocco 0): 0..127.
 *
 * Interfaccia: la pagina IN R usa gli stessi id della pagina IN L (129 DEL, 130 REV, 269 FX3), con le
 * loro icone; 129 e 130 passano da vparams e, solo quando la pagina IN R e' quella aperta nel tab
 * MIXER, leggono e scrivono il lato R (269 lo fa fx3 leggendo dm_page_r dall'intestazione).
 * Il tab MIXER ha il vettore delle pagine {22, 23, 24, 27}: la sua lunghezza (+0x80 della vista) e' 4 in
 * mono e 3 in stereo, aggiornata alla costruzione della vista e quando cambia l'impostazione.
 *
 * Audio: il blocco originale delle mandate dell'ingresso (0x4008F4F0..0x4008F66A) gira due volte, come
 * il blocco dei VCA nella v1: passata 1 con IN L, bilanciamento al centro e DEL/REV di IN L (si tiene
 * il canale 12, ADC 4); passata 2 con IN R, centro e DEL/REV del lato R (si tiene il canale 13, ADC 5).
 * Stessa legge di volume dell'OS per entrambi; in stereo il blocco gira una volta, invariato.
 */

typedef unsigned int u32;
typedef int s32;
typedef unsigned short u16;

#define DATA __attribute__((section(".data")))
#define MONO()    (*(const volatile unsigned char *)0x80003146u == 0)   /* EXTERNAL IN: 0 = mono */
#define KIT       (*(char *const volatile *)0x800030B8u)                /* kit attivo */
#define UI_ROOT   (*(char *const volatile *)0x444E2334u)
#define PAGE_R    27
#define V_BEGIN   0x7C                                                  /* ParameterPageView: pagine */
#define V_END     0x80
#define V_CAP     0x84
#define V_IDX     0x90                                                  /* pagina corrente */

/* intestazione (deve stare all'inizio del blocco: tools/build/dualmono_layout.py) */
__asm__(
    "        .text\n"
    "        .globl  dm_hdr, dm_side\n"
    "dm_hdr: .long   0x444D5632\n"
    "dm_side:.byte   0, 0, 0, 0\n"
    "        .long   dm_page_r\n");

extern volatile unsigned char dm_side;
const s32 dm_pages[4] __attribute__((aligned(4))) = {22, 23, 24, PAGE_R};   /* tab MIXER */
char *dm_view DATA = 0;                                                 /* vista del tab MIXER */
u16 dm_sv[4] DATA = {0};                                                /* IN LR, BAL, DEL, REV */
s32 dm_fp[6] DATA = {0};                                                /* passi del canale 12 */

s32 dm_orig_get(void *obj, s32 id);
s32 dm_orig_set(void *obj, s32 id, s32 value, s32 flag);

static u32 rword(u32 off)
{
    const char *k = KIT;
    u32 v;

    if (!k)
        return 0;
    v = *(const volatile u16 *)(k + off);
    return v > 127 ? 127 : v;
}

u32 dm_page_r(void)                                                     /* pagina IN R aperta */
{
    const char *v = dm_view;
    const s32 *b;
    s32 i, n;

    if (!v || !MONO())
        return 0;
    b = *(const s32 *const *)(v + V_BEGIN);
    n = (*(const s32 *)(v + V_END) - (s32)b) >> 2;
    i = *(const s32 *)(v + V_IDX);
    return i >= 0 && i < n && b[i] == PAGE_R;
}

/* External Mixer (pagina 24): in mono FX3 in G accanto a DEL e REV (BAL non serve), in stereo in C con
 * BAL in G come prima. dm_fx3 = casella C all'avvio (269 con fx3, 0 senza), letta da dm_page_stub. */
#define MIX_C     (*(volatile s32 *)0x41BA07F8u)
#define MIX_G     (*(volatile s32 *)0x41BA0808u)
#define ID_BAL    128
s32 dm_fx3 DATA = -1;

void dm_update(void)                                                    /* 4 pagine in mono, 3 in stereo */
{
    char *v = dm_view;
    s32 *b, n;

    if (dm_fx3 >= 0) {
        MIX_C = MONO() ? 0 : dm_fx3;
        MIX_G = MONO() ? dm_fx3 : ID_BAL;
    }
    if (!v)
        return;
    b = *(s32 **)(v + V_BEGIN);
    if (!b || *(s32 *)(v + V_CAP) - (s32)b < 16 || b[3] != PAGE_R)
        return;
    n = MONO() ? 4 : 3;
    *(s32 **)(v + V_END) = b + n;
    if (*(s32 *)(v + V_IDX) >= n)
        *(s32 *)(v + V_IDX) = n - 1;
}

/* vparams: 129 DEL e 130 REV */
static u32 roff(s32 id)
{
    return id == 129 ? KS_DEL_R : KS_REV_R;
}

s32 dm_get(void *obj, s32 id)
{
    if (dm_page_r())
        return (s32)rword(roff(id)) << 8;
    return dm_orig_get(obj, id);
}

s32 dm_set(void *obj, s32 id, s32 value, s32 flag)
{
    char *k = KIT, *ui = UI_ROOT;

    if (!dm_page_r())
        return dm_orig_set(obj, id, value, flag);
    value = (value + 0x80) >> 8;
    value = value < 0 ? 0 : value > 127 ? 127 : value;
    if (k)
        *(volatile u16 *)(k + roff(id)) = (u16)value;
    if (ui)
        ui[96] = 1;
    return 0;
}

/* passata 2: parametri del lato R nell'array del mixer (a2) */
void dm_rparams(char *a2)
{
    *(volatile u16 *)(a2 + 1802) = dm_sv[1];                            /* livello = IN R (BAL) */
    *(volatile u16 *)(a2 + 1806) = 0x4000;                              /* centro */
    *(volatile u16 *)(a2 + 1808) = (u16)(rword(KS_DEL_R) << 8);
    *(volatile u16 *)(a2 + 1812) = (u16)(rword(KS_REV_R) << 8);
}

const char dm_page_s[] = "IN R";
const char dm_page_l[] = "External In R";

__asm__(
    "        .text\n"
    "        .balign 2\n"
    /* ---- 0x4008F4F0: inizio del blocco delle mandate dell'ingresso (a2 = array del mixer) */
    "        .globl  dm_pre\n"
    "dm_pre:\n"
    "        tst.b   dm_side\n"
    "        bne.s   1f\n"                      /* passata 2: gia' pronta */
    "        tst.b   0x80003146\n"
    "        bne.s   1f\n"                      /* stereo: blocco invariato */
    "        lea     dm_sv,%a0\n"               /* mono, passata 1: salva IN LR, BAL, DEL, REV */
    "        move.w  1802(%a2),(%a0)+\n"
    "        move.w  1806(%a2),(%a0)+\n"
    "        move.w  1808(%a2),(%a0)+\n"
    "        move.w  1812(%a2),(%a0)\n"
    "        move.l  #0x4000,%d0\n"
    "        move.w  %d0,1806(%a2)\n"           /* bilanciamento al centro */
    "        moveq   #1,%d0\n"
    "        move.b  %d0,dm_side\n"
    "1:      tst.b   0x80003146\n"              /* istruzione sostituita (seq d6 la segue) */
    "        rts\n"
    /* ---- 0x4008F66A: fine del blocco */
    "        .globl  dm_mid\n"
    "dm_mid:\n"
    "        moveq   #0,%d0\n"
    "        move.b  dm_side,%d0\n"
    "        beq.s   9f\n"
    "        subq.l  #1,%d0\n"
    "        bne.s   2f\n"
    "        lea     dm_fp,%a0\n"               /* passata 1: tiene i passi del canale 12 */
    "        move.l  -408(%fp),(%a0)+\n"        /* delay L, delay R, reverb L, reverb R, FX L, FX R */
    "        move.l  -376(%fp),(%a0)+\n"
    "        move.l  -344(%fp),(%a0)+\n"
    "        move.l  -312(%fp),(%a0)+\n"
    "        move.l  -280(%fp),(%a0)+\n"
    "        move.l  -248(%fp),(%a0)\n"
    "        move.l  %a2,-(%sp)\n"
    "        jsr     dm_rparams\n"
    "        addq.l  #4,%sp\n"
    "        moveq   #2,%d0\n"
    "        move.b  %d0,dm_side\n"
    "        addq.l  #4,%sp\n"                  /* niente ritorno: si rigira il blocco */
    "        jmp     0x4008F4F0\n"
    "2:      move.l  %a0,-(%sp)\n"              /* passata 2: canale 13 dalla passata, canale 12 */
    "        lea     dm_fp,%a0\n"               /* dalla prima; parametri originali ripristinati */
    "        move.l  (%a0)+,-408(%fp)\n"
    "        move.l  (%a0)+,-376(%fp)\n"
    "        move.l  (%a0)+,-344(%fp)\n"
    "        move.l  (%a0)+,-312(%fp)\n"
    "        move.l  (%a0)+,-280(%fp)\n"
    "        move.l  (%a0),-248(%fp)\n"
    "        lea     dm_sv,%a0\n"
    "        move.w  (%a0)+,1802(%a2)\n"
    "        move.w  (%a0)+,1806(%a2)\n"
    "        move.w  (%a0)+,1808(%a2)\n"
    "        move.w  (%a0),1812(%a2)\n"
    "        clr.b   dm_side\n"
    "        movea.l (%sp)+,%a0\n"
    "9:      mvs.w   1862(%a2),%d7\n"           /* istruzioni sostituite */
    "        mvs.w   24(%a2),%d1\n"
    "        rts\n"
    /* ---- vparams: get/set originali (come il ripiego di vparams) */
    "        .globl  dm_orig_get, dm_orig_set\n"
    "dm_orig_get:\n"
    "        move.l  %d2,-(%sp)\n"
    "        move.l  8(%sp),%d1\n"
    "        jmp     0x4000D950\n"
    "dm_orig_set:\n"
    "        move.l  %d3,-(%sp)\n"
    "        move.l  %d2,-(%sp)\n"
    "        move.l  12(%sp),%d1\n"
    "        jmp     0x4000DA3A\n"
    /* ---- 0x40035914: costruzione della vista del tab MIXER (vista, pagine, 0x17, 1) */
    "        .globl  dm_mixer_ctor\n"
    "dm_mixer_ctor:\n"
    "        move.l  16(%sp),-(%sp)\n"
    "        move.l  16(%sp),-(%sp)\n"
    "        move.l  16(%sp),-(%sp)\n"
    "        move.l  16(%sp),-(%sp)\n"
    "        jsr     0x40044626\n"
    "        lea     16(%sp),%sp\n"
    "        move.l  4(%sp),%d0\n"
    "        move.l  %d0,dm_view\n"
    "        jmp     dm_update\n"
    /* ---- 0x400A347C: impostazione EXTERNAL IN copiata al motore */
    "        .globl  dm_flag_hook\n"
    "dm_flag_hook:\n"
    "        move.b  %d0,0x80003146\n"          /* istruzione sostituita */
    "        lea     -16(%sp),%sp\n"
    "        movem.l %d0-%d1/%a0-%a1,(%sp)\n"
    "        jsr     dm_update\n"
    "        movem.l (%sp),%d0-%d1/%a0-%a1\n"
    "        lea     16(%sp),%sp\n"
    "        rts\n"
    /* ---- 0x401950DE: pagina 27 all'avvio (al posto di clr.l 0x41BA0894) */
    "        .globl  dm_page_stub\n"
    "dm_page_stub:\n"
    "        moveq   #125,%d0\n"                /* A: IN R (alias 125 = BAL) */
    "        move.l  %d0,0x41BA0874\n"
    "        clr.l   0x41BA0878\n"
    "        clr.l   0x41BA087C\n"
    "        clr.l   0x41BA0880\n"
    "        move.l  #129,%d0\n"                /* E: DEL, F: REV */
    "        move.l  %d0,0x41BA0884\n"
    "        move.l  #130,%d0\n"
    "        move.l  %d0,0x41BA0888\n"
    "        move.l  0x41BA07F8,%d0\n"          /* G: FX3 accanto al riverbero, come la casella C */
    "        move.l  %d0,0x41BA088C\n"          /* della pagina IN L (269 con fx3, altrimenti vuota) */
    "        move.l  %d0,dm_fx3\n"
    "        clr.l   0x41BA0890\n"
    "        clr.l   0x41BA0894\n"
    "        rts\n");
