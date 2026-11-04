/* cpu-meter: carico dell'interrupt audio (CPU #1) misurato sul dispositivo, sullo schermo.
 *
 * - Ingresso dell'interrupt (0x400A38CE: link + movem, rifatti qui) e uscita (0x400A5518: movem, rifatto qui, poi unlk e rte dell'OS):
 *   DTCN0 (0xFC07000C, contatore libero di DTIM0, lo legge anche l'OS a 0x400822B4). Durata = uscita -
 *   ingresso, periodo = ingresso - ingresso precedente: il rapporto non dipende dalla frequenza del contatore.
 * - Ogni 512 blocchi (~0.34 s): somme pubblicate per l'interfaccia e pagina da ridisegnare (byte 96 della radice).
 * - Disegno: vtable della vista dei parametri (0x401C84AC, draw 0x40032692): dopo il disegno dell'OS, in alto a
 *   destra "93.4 97.1" = media e massimo del blocco, in percento. Le pagine di parametri lo mostrano tutte.
 * Costo nell'interrupt: ~25 istruzioni per blocco. Mod diagnostica: non per le build da suonare.
 */

typedef unsigned int u32;

#define DATA __attribute__((section(".data")))
#define N_BLOCKS 512
#ifndef CM_X
#define CM_X 74
#define CM_Y 56
#define CM_SHAPE 0
#endif
#define UI_ROOT   (*(char *const volatile *)0x444E2334u)
#define DRAW_FN   ((void (*)(void *, void *))0x40032692u)
#define DRAW_STR  ((void (*)(void *, const void *, int, int, int, const char *, ...))0x400F8BD0u)
#define DRAW_TEXT ((void (*)(void *, const void *, int, int, int, int, const char *, const char *, ...))0x400F8DDCu)
#define FONT      ((const void *)0x402A9510u)              /* 4x6 */
#define FONT_RT   ((const void *)0x443DB218u)

u32 cm_t0 DATA = 0, cm_per DATA = 0, cm_sdur DATA = 0, cm_sper DATA = 0, cm_mdur DATA = 0, cm_n DATA = 0;
u32 cm_pub[3] DATA = {0, 0, 0};            /* somma durate, somma periodi, durata massima (ultimi 512 blocchi) */
static char txt[12] DATA = {0};

__asm__(
    "        .globl  cm_entry\n"
    "cm_entry:\n"                               /* al posto di 0x400A38CE: link.w %fp,#-164 ; movem.l %d0-%a5,(%sp) */
    "        link.w  %fp,#-164\n"
    "        movem.l %d0-%a5,(%sp)\n"
    "        move.l  0xFC07000C,%d0\n"
    "        move.l  cm_t0,%d1\n"
    "        move.l  %d0,cm_t0\n"
    "        sub.l   %d1,%d0\n"
    "        move.l  %d0,cm_per\n"
    "        jmp     0x400A38D6\n"
    "        .globl  cm_exit\n"
    "cm_exit:\n"                                /* al posto di 0x400A5518: movem.l -164(%fp),%d0-%a5 (6 byte) */
    "        move.l  0xFC07000C,%d0\n"
    "        sub.l   cm_t0,%d0\n"
    "        add.l   %d0,cm_sdur\n"
    "        cmp.l   cm_mdur,%d0\n"
    "        bls.s   1f\n"
    "        move.l  %d0,cm_mdur\n"
    "1:      move.l  cm_per,%d0\n"
    "        add.l   %d0,cm_sper\n"
    "        move.l  cm_n,%d0\n"
    "        addq.l  #1,%d0\n"
    "        move.l  %d0,cm_n\n"
    "        cmpi.l  #512,%d0\n"
    "        bne.s   2f\n"
    "        lea     cm_pub,%a0\n"
    "        move.l  cm_sdur,(%a0)+\n"
    "        move.l  cm_sper,(%a0)+\n"
    "        move.l  cm_mdur,(%a0)\n"
    "        clr.l   cm_sdur\n"
    "        clr.l   cm_sper\n"
    "        clr.l   cm_mdur\n"
    "        clr.l   cm_n\n"
    "        move.l  0x444E2334,%d0\n"           /* pagina da ridisegnare */
    "        beq.s   2f\n"
    "        movea.l %d0,%a0\n"
    "        move.b  #1,96(%a0)\n"
    "2:      movem.l -164(%fp),%d0-%a5\n"
    "        jmp     0x400A551E\n");                /* unlk %fp ; rte dell'OS */

static char *num(char *p, u32 permille)            /* 934 -> "93" (percento intero, arrotondato) */
{
    u32 v = (permille + 5) / 10;
    if (v > 99)
        v = 99;
    *p++ = (char)('0' + v / 10);
    *p++ = (char)('0' + v % 10);
    return p;
}

void cm_draw(void *view, void *bitmap)
{
    u32 sd = cm_pub[0], sp = cm_pub[1] / 1000, md = cm_pub[2];
    char *p = txt;

    DRAW_FN(view, bitmap);
    if (!sp)
        return;
    *p++ = ' ';
    p = num(p, sd / sp);
    *p++ = ' ';
    p = num(p, md * N_BLOCKS / sp);
    *p = 0;
    DRAW_TEXT(bitmap, FONT, CM_X, CM_Y, 0, 0, "XXXXXXX", "%s", txt);
}
