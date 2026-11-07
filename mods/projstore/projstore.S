| projstore — memoria delle mod salvata con il progetto (Syntakt OS 1.42)
|
| Le impostazioni del progetto passano nel file da 0x400A9134 (scrittura: RAM -> blocco di 1024 byte) e
| 0x400A84F0 (lettura, solo blocchi di versione 4). La scrittura azzera i byte +0x227..+0x3FF del blocco e
| la lettura non li guarda: qui ci vanno PS_SIZE byte delle mod, dopo il marcatore "SH" e la versione.
| In RAM stanno a ps_data (meta' solo RAM dell'area mod): ogni mod usa la sua parte (tools/build/projstore_layout.py).
| Progetto senza marcatore (OS stock o versioni precedenti): ps_data a zero = valori di default.
| Progetto salvato con meno byte (marcatore con lunghezza minore): quelli che ha, il resto a zero.
|
| Costanti da make_patch.py (--defsym): PS_SIZE, ps_data.

        .equ    OFF,            0x228           | primo byte pari dell'area riservata
        .equ    VER,            1
        .equ    WR_BACK,        0x400A913C      | dopo le istruzioni sostituite
        .equ    RD_BACK,        0x400A84F8

        .text
        .globl  ps_wr
ps_wr:                                          | al posto di 0x400A9134 (file, impostazioni, x)
        move.l  12(%sp),-(%sp)
        move.l  12(%sp),-(%sp)
        move.l  12(%sp),-(%sp)
        bsr.s   1f
        lea     12(%sp),%sp
        tst.b   %d0
        beq.s   2f
        movea.l 4(%sp),%a0                      | blocco nel file
        lea     OFF(%a0),%a0
        moveq   #0x53,%d1                       | "SH", versione, lunghezza / 4
        move.b  %d1,(%a0)+
        moveq   #0x48,%d1
        move.b  %d1,(%a0)+
        moveq   #VER,%d1
        move.b  %d1,(%a0)+
        moveq   #PS_SIZE/4,%d1
        move.b  %d1,(%a0)+
        lea     ps_data,%a1
        move.l  #PS_SIZE-1,%d1
3:      move.b  (%a1)+,(%a0)+
        subq.l  #1,%d1
        bge.s   3b
        moveq   #1,%d0
2:      rts
1:      lea     -12(%sp),%sp                    | istruzioni sostituite
        movem.l %d2/%a2-%a3,(%sp)
        jmp     WR_BACK

        .globl  ps_rd
ps_rd:                                          | al posto di 0x400A84F0 (impostazioni, file)
        move.l  8(%sp),-(%sp)
        move.l  8(%sp),-(%sp)
        bsr.s   1f
        addq.l  #8,%sp
        tst.b   %d0
        beq.s   6f
        move.l  %d0,-(%sp)
        move.l  %d2,-(%sp)
        movea.l 8+8(%sp),%a0                    | blocco nel file
        lea     OFF(%a0),%a0
        lea     ps_data,%a1
        moveq   #3,%d0                          | marcatore letto a byte (indirizzo pari, ma prudenza)
        moveq   #0,%d2
8:      lsl.l   #8,%d2
        move.b  (%a0)+,%d2
        subq.l  #1,%d0
        bge.s   8b
        move.l  %d2,%d0
        lsr.l   #8,%d0
        cmpi.l  #0x534800+VER,%d0
        bne.s   4f
        andi.l  #0xff,%d2                       | parole salvate: 1..PS_SIZE/4
        beq.s   4f
        cmpi.l  #PS_SIZE/4,%d2
        bhi.s   4f
        lsl.l   #2,%d2
        move.l  #PS_SIZE,%d1
        sub.l   %d2,%d1                         | byte da azzerare dopo
3:      move.b  (%a0)+,(%a1)+
        subq.l  #1,%d2
        bne.s   3b
        tst.l   %d1
        beq.s   5f
        bra.s   7f
4:      move.l  #PS_SIZE,%d1                    | nessun marcatore: default
7:      clr.b   (%a1)+
        subq.l  #1,%d1
        bne.s   7b
5:      move.l  (%sp)+,%d2
        move.l  (%sp)+,%d0
6:      rts
1:      lea     -16(%sp),%sp                    | istruzioni sostituite
        movem.l %d2-%d3/%a2-%a3,(%sp)
        jmp     RD_BACK

        .globl  ps_data                         | indirizzo assoluto (--defsym)
