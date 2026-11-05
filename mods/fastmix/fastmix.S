| fastmix — routine dell'interrupt audio dell'OS (CPU #1, OS 1.42) riscritte piu' veloci, stesso risultato
|
| Somme dei bus: 0x4008EF8C (10 canali), 0x4008F024 (9), 0x4008F0B6 (8). Firma f(dst, src, g, inc): 32
| campioni, dst a passi di 8 B (un lato di un bus stereo), canali di src a passi di 128 B, EMAC msac con
| load (dst[n] = acc0 - somma g*x, acc0 vuoto dopo ogni campione), guadagni g += inc a ogni campione e
| riscritti in g alla fine. 14 chiamate per blocco: ~10 000 istruzioni con l'OS stock.
|
| Qui, quando nessun inc e' diverso da zero (guadagni fermi: il caso normale, la rampa dura un blocco dopo
| che un bersaglio cambia):
|   - nessun guadagno: uscita a zero (il primo campione resta acc0, come nell'OS);
|   - da 1 a 5 guadagni non nulli: solo quei canali (bus delle mandate, bus della FX track);
|   - di piu': tutti i canali, senza le somme dei guadagni e senza riscriverli (non cambiano).
| Con un inc diverso da zero gira la routine dell'OS.
|
| Perche' e' identico: un prodotto con guadagno nullo vale 0 e l'accumulatore somma interi (nessuna
| saturazione intermedia: <= 10 prodotti in un accumulatore con 8 bit di guardia), quindi saltarlo o
| cambiare l'ordine dei canali non cambia acc0 ne' il valore scritto. Restano uguali registri salvati,
| acc1..acc3, MACSR (modo); diversi solo i flag N/Z/V/EV dell'ultima operazione (l'OS non li legge) e i
| registri di lavoro d0/d1/a0/a1.

        .equ    R10_BACK,       0x4008EF96      | dopo lea, moveq, movem sostituiti
        .equ    R9_BACK,        0x4008F02C
        .equ    R8_BACK,        0x4008F0BE
        .equ    KMAX,           5               | canali per il percorso a canali scelti

| ---- ingressi per n canali (10, 9, 8), un solo codice: prima gli inc (in rampa: subito la routine dell'OS,
| senza salvare nulla), poi d4 = guadagni non nulli e la scelta del percorso. L'interrupt non sta nella cache
| istruzioni: ogni riga di codice eseguita costa una lettura dalla DDR a ogni blocco (tools/emu/cycles.py),
| quindi una catena sola con tre punti d'ingresso invece di tre copie.
        .text
        .globl  fm_sum10, fm_sum9, fm_sum8
fm_sum10:                                       | al posto di 0x4008EF8C: jmp fm_sum10 ; nop
        movea.l 16(%sp),%a0                     | inc
        moveq   #0,%d0
        bra.s   1f
fm_sum9:                                        | al posto di 0x4008F024
        movea.l 16(%sp),%a0
        moveq   #0,%d0
        bra.s   2f
fm_sum8:                                        | al posto di 0x4008F0B6
        movea.l 16(%sp),%a0
        moveq   #0,%d0
        bra.s   3f
1:      or.l    (%a0)+,%d0
2:      or.l    (%a0)+,%d0
3:      .rept   8
        or.l    (%a0)+,%d0
        .endr
        bne.w   fm_os
        move.l  %a0,%d1                         | a0 = inc + 4n
        sub.l   16(%sp),%d1
        lsr.l   #2,%d1                          | n
        lea     -44(%sp),%sp
        movem.l %d2-%d7/%a2-%a6,(%sp)
        movem.l 48(%sp),%a0-%a2                 | dst, src, g
        moveq   #0,%d4
        moveq   #9,%d2
        cmp.l   %d2,%d1
        blt.s   .Lc8
        beq.s   .Lc9
        tst.l   (%a2)+
        beq.s   .Lc9
        addq.l  #1,%d4
.Lc9:   tst.l   (%a2)+
        beq.s   .Lc8
        addq.l  #1,%d4
.Lc8:   .rept   8
        tst.l   (%a2)+
        beq.s   1f
        addq.l  #1,%d4
1:
        .endr
        tst.l   %d4
        beq.s   fm_zero
        moveq   #KMAX,%d0
        cmp.l   %d0,%d4
        bgt.w   fm_dense
        move.l  %d1,%d0
        bra.w   fm_some

| ---- in rampa: le istruzioni sostituite, poi la routine dell'OS (n dalla fine degli inc)
fm_os:  move.l  %a0,%d0
        sub.l   16(%sp),%d0
        cmpi.l  #40,%d0
        beq.s   os10
        cmpi.l  #36,%d0
        beq.s   os9
os8:    lea     -40(%sp),%sp
        movem.l %d2-%d7/%a2-%a5,(%sp)
        jmp     R8_BACK
os10:   lea     -48(%sp),%sp
        moveq   #32,%d0
        movem.l %d2-%d7/%a2-%fp,(%sp)
        jmp     R10_BACK
os9:    lea     -44(%sp),%sp
        movem.l %d2-%d7/%a2-%fp,(%sp)
        jmp     R9_BACK

| ---- fine comune
fm_out:
        movem.l (%sp),%d2-%d7/%a2-%a6
        lea     44(%sp),%sp
        rts

| ---- nessun guadagno: dst = acc0 nel primo campione, poi zeri (a passi di 8 B). a0 = dst. Gli stessi valori
| agli stessi indirizzi dell'OS; il primo si scrive due volte (0, poi acc0)
fm_zero:
        movclr.l %acc0,%d2
        moveq   #0,%d0
        movea.l %a0,%a1
        moveq   #8,%d1
1:      move.l  %d0,(%a1)
        move.l  %d0,8(%a1)
        move.l  %d0,16(%a1)
        move.l  %d0,24(%a1)
        lea     32(%a1),%a1
        subq.l  #1,%d1
        bne.s   1b
        move.l  %d2,(%a0)
        bra.w   fm_out

| ---- da 1 a KMAX canali: a0 = dst, a1 = src, a2 = g + 4n, d0 = n, d4 = guadagni non nulli.
| Guadagni in d0..d4, puntatori ai canali in a0..a4, dato in d6, d5 di lavoro, a6 = dst, d7 = coppie di
| campioni. Catena dell'EMAC come nell'OS: ogni msac carica il campione del canale dopo, l'ultimo quello
| del primo canale al campione dopo.
fm_some:
        movea.l %a0,%a6
        move.l  %d0,%d1
        lsl.l   #2,%d1
        suba.l  %d1,%a2                         | g
        lea     fm_g,%a4
        lea     fm_p,%a5
1:      move.l  (%a2)+,%d1
        beq.s   2f
        move.l  %d1,(%a4)+
        move.l  %a1,(%a5)+
2:      lea     128(%a1),%a1
        subq.l  #1,%d0
        bne.s   1b
        move.l  %d4,%d7
        lea     fm_g,%a0
        movem.l (%a0),%d0-%d4
        lea     fm_p,%a0
        movem.l (%a0),%a0-%a4
        subq.l  #1,%d7
        beq.s   k1
        subq.l  #1,%d7
        beq.s   k2
        subq.l  #1,%d7
        beq.w   k3
        subq.l  #1,%d7
        beq.w   k4
        bra.w   k5

        .macro  CHAIN k
        .if     \k == 1
        msac.l  %d0,%d6,(%a0)+,%d6,%acc0
        .elseif \k == 2
        msac.l  %d0,%d6,(%a1)+,%d6,%acc0
        msac.l  %d1,%d6,(%a0)+,%d6,%acc0
        .elseif \k == 3
        msac.l  %d0,%d6,(%a1)+,%d6,%acc0
        msac.l  %d1,%d6,(%a2)+,%d6,%acc0
        msac.l  %d2,%d6,(%a0)+,%d6,%acc0
        .elseif \k == 4
        msac.l  %d0,%d6,(%a1)+,%d6,%acc0
        msac.l  %d1,%d6,(%a2)+,%d6,%acc0
        msac.l  %d2,%d6,(%a3)+,%d6,%acc0
        msac.l  %d3,%d6,(%a0)+,%d6,%acc0
        .else
        msac.l  %d0,%d6,(%a1)+,%d6,%acc0
        msac.l  %d1,%d6,(%a2)+,%d6,%acc0
        msac.l  %d2,%d6,(%a3)+,%d6,%acc0
        msac.l  %d3,%d6,(%a4)+,%d6,%acc0
        msac.l  %d4,%d6,(%a0)+,%d6,%acc0
        .endif
        .endm

        .macro  KERN k                          | due campioni a giro
k\k:    moveq   #16,%d7
        move.l  (%a0)+,%d6
1:      CHAIN   \k
        movclr.l %acc0,%d5
        move.l  %d5,(%a6)
        CHAIN   \k
        movclr.l %acc0,%d5
        move.l  %d5,8(%a6)
        lea     16(%a6),%a6
        subq.l  #1,%d7
        bne.s   1b
        bra.w   fm_out
        .endm

        KERN    1
        KERN    2
        KERN    3
        KERN    4
        KERN    5

| ---- tutti i canali, guadagni fermi: il ciclo dell'OS senza g += inc e senza riscrivere g, due campioni
| a giro. a0 = dst, a1 = src, a2 = g + 4n, d1 = n. Un ciclo solo, a 10 canali: con 9 o 8 i guadagni che
| mancano valgono 0 (prodotti nulli, accumulatore invariato) e la catena legge uno o due canali in piu'
| dopo src, sempre nella SRAM (le chiamate dell'OS hanno src = 0x80003950 o 0x80003D50, fino a 0x80004250).
fm_dense:
        movea.l %a0,%a3                         | dst
        movea.l %a1,%a4                         | src
        moveq   #9,%d0
        cmp.l   %d0,%d1
        blt.s   2f
        beq.s   1f
        lea     -40(%a2),%a5
        movem.l (%a5),%d0-%d5/%a0-%a2/%a5
        bra.s   3f
1:      lea     -36(%a2),%a5
        movem.l (%a5),%d0-%d5/%a0-%a2
        suba.l  %a5,%a5
        bra.s   3f
2:      lea     -32(%a2),%a5
        movem.l (%a5),%d0-%d5/%a0-%a1
        suba.l  %a2,%a2
        suba.l  %a5,%a5
3:      moveq   #16,%d7
        move.l  (%a4)+,%d6
1:      .rept   2
        msac.l  %d0,%d6,124(%a4),%d6,%acc0
        msac.l  %d1,%d6,252(%a4),%d6,%acc0
        msac.l  %d2,%d6,380(%a4),%d6,%acc0
        msac.l  %d3,%d6,508(%a4),%d6,%acc0
        msac.l  %d4,%d6,636(%a4),%d6,%acc0
        msac.l  %d5,%d6,764(%a4),%d6,%acc0
        msac.l  %a0,%d6,892(%a4),%d6,%acc0
        msac.l  %a1,%d6,1020(%a4),%d6,%acc0
        msac.l  %a2,%d6,1148(%a4),%d6,%acc0
        msac.l  %a5,%d6,(%a4)+,%d6,%acc0
        movclr.l %acc0,%a6
        move.l  %a6,(%a3)
        addq.l  #8,%a3
        .endr
        subq.l  #1,%d7
        bne.w   1b
        bra.w   fm_out

| ==== 2. smussamento dei parametri (0x400979CA, ~7 000 istruzioni a blocco nell'OS)
| A ogni blocco l'OS smussa le 938 parole della copia dei parametri del motore (0x800021B0, x) in uno stato
| a 32 bit (0x8000E9B0, s) e scrive l'uscita a 16 bit (0x80006348, una coppia di parole per long):
|   s = C*x + K*s (EMAC frazionaria, C = 0x03D7, K = 0x7C29: C + K = 1), uscita = parte alta di s + 0x8000.
| Su LFO, modulazioni e tracce l'OS riscrive poi parte dell'uscita: va riscritta tutta a ogni blocco.
| A regime s non cambia piu' (s = x << 16, o pochi bit sotto: punto fisso dell'arrotondamento) e
| l'uscita vale x. Qui a blocchi di 8 coppie:
|   - blocco fermo (marcato quando l'ultimo calcolo non ha cambiato s) e x uguale a quello di allora:
|     uscita = x, nient'altro (stesso s, stessa uscita dell'OS);
|   - altrimenti il calcolo dell'OS; a turno (ogni 16 blocchi audio per ogni blocco di coppie) con il
|     confronto di s prima e dopo, che marca il blocco fermo e salva x.
| Le funzioni dell'OS che scrivono s (0x40097766, 0x400977AA, 0x400977D8, 0x4009787A, 0x4009790C,
| 0x4009792C) scrivono anche x con lo stesso valore (s = x << 16, punto fisso): x cambia o s resta fermo.
| Le ultime 5 coppie (469 = 58 * 8 + 5) sempre col calcolo dell'OS.

        .equ    SM_X,           0x800021B0      | x: parole dei parametri (a3 nell'OS)
        .equ    SM_S,           0x8000E9B0      | s
        .equ    SM_OUT,         0x80006348      | uscita
        .equ    SM_K,           0x7C290000
        .equ    SM_C,           0x03D70000
        .equ    SM_BLOCKS,      58              | blocchi di 8 coppie
        .equ    SM_TAIL,        5
        .equ    SM_BACK,        0x40097A2A      | dopo il ciclo dell'OS

| una coppia col calcolo dell'OS: d0 = x (poi x della coppia dopo, letto in anticipo), a0 = x dopo,
| a1 = s, a2 = uscita (avanzano); a3 = K, a6 = C, d2 = 0x8000
        .macro  SM_PAIR
        mac.w   %a6u,%d0u,(%a1),%d4,%acc0
        mac.l   %a3,%d4,%acc0
        mac.w   %a6u,%d0l,4(%a1),%d0,%acc1
        mac.l   %a3,%d0,(%a0)+,%d0,%acc1
        movclr.l %acc0,%d1
        move.l  %d1,(%a1)+
        movclr.l %acc1,%d4
        move.l  %d4,(%a1)+
        add.l   %d2,%d4
        swap    %d4
        add.l   %d2,%d1
        move.w  %d4,%d1
        move.l  %d1,(%a2)+
        .endm

        .globl  fm_smooth
fm_smooth:                                      | al posto di 0x400979D6: jsr fm_smooth ; jmp SM_BACK
        lea     -20(%sp),%sp                    | d2-d6/a2 li salva e rimette l'OS; a3 = x va rimesso
        movem.l %d7/%a3-%a6,(%sp)
        lea     fm_sm_ok,%a5
        move.l  %macsr,%d0
        andi.l  #0xF0,%d0
        cmp.l   fm_sm_mode,%d0
        beq.s   1f
        move.l  %d0,fm_sm_mode                  | modo dell'EMAC cambiato: nessun blocco fermo
        moveq   #SM_BLOCKS - 1,%d1
2:      clr.b   (%a5,%d1.l)
        subq.l  #1,%d1
        bge.s   2b
1:      move.l  %acc0,%d0                       | acc0/acc1 non vuoti: l'OS li somma alla prima coppia
        move.l  %acc1,%d1
        or.l    %d1,%d0
        move.l  %accext01,%d1
        or.l    %d1,%d0
        beq.s   1f
        clr.b   (%a5)
1:      addq.l  #1,fm_sm_turn
        lea     SM_X,%a0
        lea     SM_S,%a1
        lea     SM_OUT,%a2
        lea     fm_sm_x,%a4
        movea.l #SM_K,%a3
        movea.l #SM_C,%a6
| ---- per ogni blocco di 8 coppie
3:      tst.b   (%a5)
        beq.s   5f
        movem.l (%a4),%d0-%d7                   | fermo: x come allora?
        cmp.l   (%a0),%d0
        bne.s   4f
        cmp.l   4(%a0),%d1
        bne.s   4f
        cmp.l   8(%a0),%d2
        bne.s   4f
        cmp.l   12(%a0),%d3
        bne.s   4f
        cmp.l   16(%a0),%d4
        bne.s   4f
        cmp.l   20(%a0),%d5
        bne.s   4f
        cmp.l   24(%a0),%d6
        bne.s   4f
        cmp.l   28(%a0),%d7
        bne.s   4f
        movem.l %d0-%d7,(%a2)                   | uscita = x
        lea     32(%a0),%a0
        lea     64(%a1),%a1
        lea     32(%a2),%a2
        bra.w   7f
4:      clr.b   (%a5)
5:      move.l  %a5,%d0                         | a turno: (blocco + turno) & 15 == 0
        sub.l   #fm_sm_ok,%d0
        add.l   fm_sm_turn,%d0
        andi.l  #15,%d0
        beq.w   6f
        move.l  #0x8000,%d2                     | calcolo dell'OS, 8 coppie di fila
        move.l  (%a0)+,%d0
        .rept   8
        SM_PAIR
        .endr
        subq.l  #4,%a0                          | la lettura in anticipo
        bra.w   7f
6:      moveq   #0,%d7                          | con il confronto: s cambiato?
        moveq   #8,%d5
        move.l  #0x8000,%d2
        move.l  (%a0)+,%d0
1:      move.l  %d0,(%a4)+
        mac.w   %a6u,%d0u,(%a1),%d4,%acc0
        mac.l   %a3,%d4,%acc0
        mac.w   %a6u,%d0l,4(%a1),%d3,%acc1
        mac.l   %a3,%d3,(%a0)+,%d0,%acc1
        movclr.l %acc0,%d1
        sub.l   %d1,%d4
        or.l    %d4,%d7
        move.l  %d1,(%a1)+
        movclr.l %acc1,%d4
        sub.l   %d4,%d3
        or.l    %d3,%d7
        move.l  %d4,(%a1)+
        add.l   %d2,%d4
        swap    %d4
        add.l   %d2,%d1
        move.w  %d4,%d1
        move.l  %d1,(%a2)+
        subq.l  #1,%d5
        bne.s   1b
        subq.l  #4,%a0
        lea     -32(%a4),%a4
        tst.l   %d7
        seq     %d0
        move.b  %d0,(%a5)
7:      lea     32(%a4),%a4
        addq.l  #1,%a5
        cmpa.l  #fm_sm_ok + SM_BLOCKS,%a5
        bne.w   3b
| ---- le ultime coppie
        moveq   #SM_TAIL,%d3
        move.l  #0x8000,%d2
        move.l  (%a0)+,%d0
1:      SM_PAIR
        subq.l  #1,%d3
        bne.s   1b
        movem.l (%sp),%d7/%a3-%a6
        lea     20(%sp),%sp
        rts

        .data
fm_g:   .long   0, 0, 0, 0, 0                   | guadagni dei canali scelti
fm_p:   .long   0, 0, 0, 0, 0                   | e i loro puntatori
fm_sm_mode:
        .long   -1                              | modo dell'EMAC dell'ultimo calcolo (bit 7..4 di MACSR)
fm_sm_turn:
        .long   0                               | contatore dei blocchi audio (turni del confronto)

        .bss
fm_sm_ok:
        .space  SM_BLOCKS                       | blocchi fermi
        .balign 4
fm_sm_x:
        .space  SM_BLOCKS * 32                  | x dell'ultimo calcolo con confronto

