| master-comp — compressore sul master analogico della Syntakt (OS 1.41), "cervello" Digitakt
|
| Topologia (vedi docs/re-journal.md): feed-forward VCA.
|   rilevatore : bus del mixer analogico PRIMA dei VCA del master, digitalizzato dagli ADC 6/7
|                (gruppo 0x80003950, canali 6 e 7 = 0x80003C50 / 0x80003CD0, 32 campioni)
|   attuatore  : tensioni di controllo dei VCA del master (hw+70 / hw+72), ricalcolate dalla
|                funzione dei guadagni 0x400903CA a ogni blocco audio
| Algoritmo: quello del compressore della Digitakt mk1 (picco, log, soglia/ratio, tenuta con
| rilascio, attacco, makeup), riscritto in forma compatta: modello in mods/dt-comp/model.py
| (classe Compact, aritmetica identica a questo file).
|
| Chiamata dal trampolino a 0x4009053E (al posto del clamp/scrittura dei CV del master):
|   d1 = CV master sinistro, d3 = CV master destro (non ancora limitati), a3 = struttura hw.
| Scrive hw+70/hw+72; preserva tutti i registri (d1/d3 non servono dopo), MACSR e ACC puliti.
|
| Interfaccia (v0.3): 5 parametri "virtuali" THR ATK REL MUP RAT sulla pagina SYN della FX
| track (FX Drive), con gli id logici nascosti 144, 72, 91, 101, 127 (descrittori riscritti da
| make_patch.py). Tre agganci intercettano per questi id le funzioni centrali dei parametri di
| kit: "e' di kit?" 0x4000D870, lettura 0x4000D94A, scrittura 0x4000DA32. I valori stanno in
| k_params (RAM, non salvati); a ogni blocco comp_hook ne ricava le costanti come la Digitakt.
| Tabelle della Digitakt (attacco, rilascio, ratio) in k_dt (dt_tables.inc, generato).

        .equ    ADC_L,          0x80003C50
        .equ    ADC_R,          0x80003CD0
        .equ    EXP_K,          -356689313      | come la Digitakt: log -> ottave
        .equ    CV_MAX,         65535
        .equ    THR_K,          503316480       | soglia: thr = THR_K*(THR<<16) - THR_K
        .equ    MUP_K,          202017810       | makeup: mk = MUP_K*(MUP<<16) - MUP_K
        .equ    FX_SLOTS,       0x41B9F950      | pagina "SYN / FX Drive" (oggetto in BSS)
        .equ    ID_DRIVE,       150
        .equ    N_PAR,          5

        .text
        .globl  comp_hook
comp_hook:
        lea     -52(%sp),%sp
        movem.l %d0-%d7/%a0-%a2/%a4-%a5,(%sp)
        move.l  %macsr,%d0
        move.l  %d0,-(%sp)                      | 0(sp) = MACSR; 4(sp).. = d0..
        move.l  #0xA0,%macsr                    | frazionario con segno, saturazione (come la DT)
        bsr.w   fx_page
        bsr.w   convert
        lea     ADC_L,%a0
        lea     ADC_R,%a1
        lea     k_state,%a2
        lea     k_logt,%a4
        lea     k_const,%a5
        move.l  (%a2),%d5                       | st: tenuta con rilascio
        move.l  4(%a2),%d6                      | at: attacco
        moveq   #32,%d7
1:      move.l  (%a0)+,%d0                      | |L| (come la DT: x ^ (x >> 31))
        move.l  %d0,%d4
        moveq   #31,%d1
        asr.l   %d1,%d4
        eor.l   %d4,%d0
        move.l  (%a1)+,%d2                      | |R|
        move.l  %d2,%d4
        asr.l   %d1,%d4
        eor.l   %d4,%d2
        cmp.l   %d0,%d2
        ble.s   2f
        move.l  %d2,%d0
2:      cmpi.l  #256,%d0                        | pavimento come la DT
        bge.s   3f
        move.l  #256,%d0
3:      | ---- log: L = T[i] + interp - lz*C_OCT
        move.l  %d0,%d4
        ff1     %d4                             | lz
        move.l  %d4,%d2
        subq.l  #1,%d2
        asl.l   %d2,%d0                         | m in [2^30, 2^31)
        move.l  %d0,%d2
        moveq   #26,%d1
        lsr.l   %d1,%d2
        moveq   #15,%d1
        and.l   %d1,%d2                         | i
        move.l  4(%a4,%d2.l*4),%d3
        move.l  (%a4,%d2.l*4),%d1
        sub.l   %d1,%d3
        and.l   #0x03FFFFFF,%d0
        lsl.l   #5,%d0                          | frazione (Q31)
        mac.l   %d3,%d0,%acc0
        movclr.l %acc0,%d3
        add.l   %d3,%d1
        muls.l  (%a5),%d4                       | lz * C_OCT
        sub.l   %d4,%d1                         | L
        | ---- curva: gr = 0 sotto soglia, altrimenti thr + slope*(L-thr) - L
        moveq   #0,%d0
        move.l  %d1,%d2
        sub.l   4(%a5),%d2
        blt.s   4f
        move.l  8(%a5),%d3
        mac.l   %d3,%d2,%acc0
        movclr.l %acc0,%d0
        add.l   4(%a5),%d0
        sub.l   %d1,%d0
4:      | ---- tenuta con rilascio: st = min(gr, (1-r)*gr + r*st)
        move.l  12(%a5),%d3
        mac.l   %d3,%d0,%acc0
        move.l  16(%a5),%d3
        mac.l   %d3,%d5,%acc0
        movclr.l %acc0,%d2
        move.l  %d0,%d5
        cmp.l   %d2,%d0
        blt.s   5f
        move.l  %d2,%d5
5:      | ---- attacco: at = (1-a)*st + a*at
        move.l  20(%a5),%d3
        mac.l   %d3,%d5,%acc0
        move.l  24(%a5),%d3
        mac.l   %d3,%d6,%acc0
        movclr.l %acc0,%d6
        subq.l  #1,%d7
        bne.w   1b
        move.l  %d5,(%a2)
        move.l  %d6,4(%a2)
        | ---- guadagno G (Q12, 65536 = x16) = 2^(16 - v/2^23), v = EXP_K * (MK + at)
        add.l   28(%a5),%d6
        move.l  #EXP_K,%d3
        mac.l   %d3,%d6,%acc0
        movclr.l %acc0,%d0
        move.l  %d0,%d4
        moveq   #23,%d1
        asr.l   %d1,%d4                         | ottave intere
        move.l  %d0,%d2
        moveq   #19,%d1
        lsr.l   %d1,%d2
        moveq   #15,%d1
        and.l   %d1,%d2                         | i
        and.l   #0x0007FFFF,%d0
        moveq   #12,%d1
        lsl.l   %d1,%d0                         | frazione (Q31)
        lea     k_expt,%a4
        move.l  4(%a4,%d2.l*4),%d3
        move.l  (%a4,%d2.l*4),%d1
        sub.l   %d1,%d3
        mac.l   %d3,%d0,%acc0
        movclr.l %acc0,%d3
        add.l   %d3,%d1
        asr.l   %d4,%d1                         | G
        | ---- CV del master: limite originale, poi x G, poi limite
        move.l  8(%sp),%d0                      | d1 salvato (0=MACSR, 4=d0, 8=d1) = CV sinistro
        bsr.w   scale
        move.w  %d0,70(%a3)
        move.l  16(%sp),%d0                     | d3 salvato (16) = CV destro
        bsr.w   scale
        move.w  %d0,72(%a3)
        move.l  (%sp)+,%d0
        move.l  %d0,%macsr
        movem.l (%sp),%d0-%d7/%a0-%a2/%a4-%a5
        lea     52(%sp),%sp
        rts

| ---- costanti del compressore dai parametri (stesse formule della Digitakt, vedi model.Preset)
convert:
        lea     k_params,%a0
        lea     k_const,%a5
        lea     k_dt,%a1                        | attacco[128], rilascio[128], ratio[8]
        move.l  #THR_K,%d1
        mvs.w   (%a0),%d0                       | THR
        swap    %d0
        clr.w   %d0
        mac.l   %d1,%d0,%acc0
        movclr.l %acc0,%d0
        sub.l   %d1,%d0
        move.l  %d0,4(%a5)
        mvz.b   2(%a0),%d0                      | ATK (byte alto = 0..127)
        move.l  (%a1,%d0.l*4),%d1
        move.l  %d1,24(%a5)
        move.l  #0x7FFFFFFF,%d2
        sub.l   %d1,%d2
        move.l  %d2,20(%a5)
        lea     512(%a1),%a2
        mvz.b   4(%a0),%d0                      | REL
        move.l  (%a2,%d0.l*4),%d1
        move.l  %d1,16(%a5)
        move.l  #0x7FFFFFFF,%d2
        sub.l   %d1,%d2
        move.l  %d2,12(%a5)
        move.l  #MUP_K,%d1
        mvs.w   6(%a0),%d0                      | MUP
        swap    %d0
        clr.w   %d0
        mac.l   %d1,%d0,%acc0
        movclr.l %acc0,%d0
        sub.l   %d1,%d0
        move.l  %d0,28(%a5)
        lea     1024(%a1),%a2
        mvz.b   8(%a0),%d0                      | RAT (0..7)
        moveq   #7,%d1
        and.l   %d1,%d0
        move.l  (%a2,%d0.l*4),%d1
        move.l  %d1,8(%a5)
        rts

| ---- pagina FX Drive: se e' ancora quella originale (DRIVE in H, F e G vuoti) mette i 5 id in A..E
fx_page:
        lea     FX_SLOTS,%a0
        move.l  28(%a0),%d0
        cmpi.l  #ID_DRIVE,%d0
        bne.s   2f
        tst.l   20(%a0)
        bne.s   2f
        tst.l   24(%a0)
        bne.s   2f
        lea     k_ids,%a1
        moveq   #N_PAR-1,%d1
1:      mvz.w   (%a1)+,%d0
        move.l  %d0,(%a0)+
        subq.l  #1,%d1
        bge.s   1b
2:      rts

| ---- d0 = id logico -> d1 = indice in k_ids (0..4) oppure -1. Usa a0.
find:   lea     k_ids,%a0
        moveq   #N_PAR-1,%d1
1:      cmp.w   (%a0,%d1.l*2),%d0
        beq.s   2f
        subq.l  #1,%d1
        bge.s   1b
2:      rts

| ---- agganci alle funzioni centrali (entrata: 4(sp) = oggetto, 8(sp) = id, 12(sp) = valore)
        .globl  kit_hook, get_hook, set_hook
kit_hook:                                       | 0x4000D870: "parametro di kit?"
        move.l  8(%sp),%d0
        bsr.s   find
        tst.l   %d1
        bmi.s   9f
        moveq   #1,%d0
        rts
9:      move.l  %d2,-(%sp)                      | istruzioni originali sostituite
        moveq   #124,%d2
        move.l  8(%sp),%d1
        jmp     0x4000D878

get_hook:                                       | 0x4000D94A: lettura
        move.l  8(%sp),%d0
        bsr.s   find
        tst.l   %d1
        bmi.s   9f
        lea     k_params,%a0
        mvs.w   (%a0,%d1.l*2),%d0
        rts
9:      move.l  %d2,-(%sp)
        move.l  8(%sp),%d1
        jmp     0x4000D950

set_hook:                                       | 0x4000DA32: scrittura
        move.l  8(%sp),%d0
        bsr.s   find
        tst.l   %d1
        bmi.s   9f
        move.l  12(%sp),%d0
        tst.l   %d0
        bge.s   1f
        moveq   #0,%d0
1:      lea     k_max,%a0
        move.l  %d2,-(%sp)                      | d2 va preservato (convenzione del compilatore)
        mvz.w   (%a0,%d1.l*2),%d2
        cmp.l   %d2,%d0
        ble.s   2f
        move.l  %d2,%d0
2:      move.l  (%sp)+,%d2
        lea     k_params,%a0
        move.w  %d0,(%a0,%d1.l*2)
        moveq   #0,%d0
        rts
9:      move.l  %d3,-(%sp)
        move.l  %d2,-(%sp)
        move.l  12(%sp),%d1
        jmp     0x4000DA3A

| d0 = CV, d1 = G -> d0 = min(65535, CV*G >> 12) (CV negativo: lasciato com'e', come l'originale)
scale:  cmpi.l  #CV_MAX,%d0
        ble.s   6f
        move.l  #CV_MAX,%d0
6:      tst.l   %d0
        blt.s   7f
        mulu.l  %d1,%d0
        moveq   #12,%d2
        lsr.l   %d2,%d0
        cmpi.l  #CV_MAX,%d0
        bls.s   7f
        move.l  #CV_MAX,%d0
7:      rts

        .data
        .balign 4
k_const:
        .long   C_OCT, 0, 0, 0, 0, 0, 0, 0      | C_OCT, THR, SLOPE, REL1, REL, ATT1, ATT, MK
k_params:
        .word   P_THR, P_ATK, P_REL, P_MUP, P_RAT
k_ids:
        .word   ID_THR, ID_ATK, ID_REL, ID_MUP, ID_RAT
k_max:
        .word   0x7F00, 0x7F00, 0x7F00, 0x7F00, 0x0700
        .balign 4
k_state:
        .long   0, 0
k_logt:
        .long   LOG_T0, LOG_T1, LOG_T2, LOG_T3, LOG_T4, LOG_T5, LOG_T6, LOG_T7, LOG_T8
        .long   LOG_T9, LOG_T10, LOG_T11, LOG_T12, LOG_T13, LOG_T14, LOG_T15, LOG_T16
k_expt:
        .long   EXP_T0, EXP_T1, EXP_T2, EXP_T3, EXP_T4, EXP_T5, EXP_T6, EXP_T7, EXP_T8
        .long   EXP_T9, EXP_T10, EXP_T11, EXP_T12, EXP_T13, EXP_T14, EXP_T15, EXP_T16
k_dt:
        .include "dt_tables.inc"
k_names:
        .include "names.inc"
