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
| make_patch.py) + misuratore GR (59, sola lettura). Tre agganci intercettano per questi id le
| funzioni centrali dei parametri di kit: "e' di kit?" 0x4000D870, lettura 0x4000D94A,
| scrittura 0x4000DA32. RAT 0 = compressore spento, 1..8 = 1.5,2,3,4,6,8,16,20:1.
| Valori (v0.4) impacchettati in 32 bit e salvati nel kit del pattern o, con SYN global, nel
| contenitore globale: campi THR[31:25] ATK[24:18] REL[17:11] MUP[10:4] RAT[3:0], in XOR con
| K_DEF (cosi' due parole a zero = preset con compressore spento: i progetti esistenti non
| cambiano). A ogni blocco comp_hook ne ricava le costanti come la Digitakt.
| Tabelle della Digitakt (attacco, rilascio, ratio) in k_dt (dt_tables.inc, generato).

        .equ    ADC_L,          0x80003C50
        .equ    ADC_R,          0x80003CD0
        .equ    EXP_K,          -356689313      | come la Digitakt: log -> ottave
        .equ    CV_MAX,         65535
        .equ    THR_K,          503316480       | soglia: thr = THR_K*(THR<<16) - THR_K
        .equ    MUP_K,          202017810       | makeup: mk = MUP_K*(MUP<<16) - MUP_K
        .equ    FX_SLOTS,       0x41B9F950      | pagina "SYN / FX Drive" (oggetto in BSS)
        .equ    ID_DRIVE,       150
        .equ    N_PAR,          6               | THR ATK REL MUP RAT + GR (sola lettura)
        .equ    IDX_GR,         5
        .equ    IDX_RAT,        4
        .equ    RAT_STEP,       0xFE0           | RAT: 9 posizioni (0 = OFF) su 0..0x7F00
        .equ    METER_FS,       18              | misuratore GR: barra piena = 18 dB
        .equ    METER_DECAY,    111848          | discesa ~20 dB/s (unita' 2^23/dB per blocco)
        .equ    OBJS,           0x41B9FA24      | oggetti per-parametro in RAM (84 B, indice = id)
        .equ    DRIVE_GFX,      0x41B9FA24 + 84*150 + 36   | disegno della manopola di DRIVE
        | salvataggio: 2 parole libere del blocco "mixer esterno" del kit del pattern (L2 +82/+84;
        | L1 +40/+42), oppure le stesse del contenitore globale se SYN global (bit 2) e' attivo.
        .equ    KIT_PTR,        0x800030BC      | kit del pattern attivo (scritto da 0x400A1D18)
        .equ    KIT_OFF,        82
        .equ    GLOB_STORE,     0x41B9D3BC      | contenitore globale: blocco esterno 0x41B9D3B0 + 12
        .equ    GLOBAL_FLAGS,   0x43BDE444      | bit 2 = SYN global

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
        tst.b   k_off
        beq.s   8f
        lea     k_state,%a2                     | spento: stato azzerato, CV originali (G = 1)
        clr.l   (%a2)
        clr.l   4(%a2)
        bsr.w   meter
        move.l  #4096,%d1
        bra.w   apply
8:      lea     ADC_L,%a0
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
        bsr.w   meter
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
apply:
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
        bsr.w   load_p                          | d0 = valori decodificati
        lea     k_const,%a5
        lea     k_dt,%a1                        | attacco[128], rilascio[128], ratio[8]
        move.l  %d0,%d3
        moveq   #25,%d1                         | THR: valore<<16 = campo<<24
        lsr.l   %d1,%d0
        moveq   #24,%d1
        lsl.l   %d1,%d0
        move.l  #THR_K,%d1
        mac.l   %d1,%d0,%acc0
        movclr.l %acc0,%d0
        sub.l   %d1,%d0
        move.l  %d0,4(%a5)
        move.l  %d3,%d0                         | ATK
        moveq   #18,%d1
        lsr.l   %d1,%d0
        moveq   #0x7F,%d1
        and.l   %d1,%d0
        move.l  (%a1,%d0.l*4),%d1
        move.l  %d1,24(%a5)
        move.l  #0x7FFFFFFF,%d2
        sub.l   %d1,%d2
        move.l  %d2,20(%a5)
        lea     512(%a1),%a2                    | REL
        move.l  %d3,%d0
        moveq   #11,%d1
        lsr.l   %d1,%d0
        moveq   #0x7F,%d1
        and.l   %d1,%d0
        move.l  (%a2,%d0.l*4),%d1
        move.l  %d1,16(%a5)
        move.l  #0x7FFFFFFF,%d2
        sub.l   %d1,%d2
        move.l  %d2,12(%a5)
        move.l  %d3,%d0                         | MUP: campo<<24
        moveq   #4,%d1
        lsr.l   %d1,%d0
        moveq   #0x7F,%d1                       | (senza maschera il bit 0 di REL finirebbe nel segno)
        and.l   %d1,%d0
        moveq   #24,%d1
        lsl.l   %d1,%d0
        move.l  #MUP_K,%d1
        mac.l   %d1,%d0,%acc0
        movclr.l %acc0,%d0
        sub.l   %d1,%d0
        move.l  %d0,28(%a5)
        moveq   #15,%d0                         | RAT: 0 = spento, 1..8 -> ratio[0..7]
        and.l   %d3,%d0
        seq     %d1
        move.b  %d1,k_off
        tst.l   %d0
        beq.s   1f
        subq.l  #1,%d0
        moveq   #7,%d1
        cmp.l   %d1,%d0
        ble.s   1f
        move.l  %d1,%d0
1:      lea     1024(%a1),%a2
        move.l  (%a2,%d0.l*4),%d1
        move.l  %d1,8(%a5)
        rts

| ---- misuratore GR con balistica: sale subito, scende a ~20 dB/s (usa d0, d1)
meter:  move.l  k_state+4,%d0                   | at <= 0
        neg.l   %d0
        bpl.s   1f
        moveq   #0,%d0
1:      move.l  k_meter,%d1
        subi.l  #METER_DECAY,%d1
        bpl.s   2f
        moveq   #0,%d1
2:      cmp.l   %d1,%d0
        bge.s   3f
        move.l  %d1,%d0
3:      move.l  %d0,k_meter
        rts

| ---- dove stanno i valori: a0 = indirizzo delle 2 parole (globale con SYN global, se no kit)
stor:   moveq   #4,%d1
        and.l   GLOBAL_FLAGS,%d1
        bne.s   1f
        move.l  KIT_PTR,%d1
        beq.s   2f
        movea.l %d1,%a0
        lea     KIT_OFF(%a0),%a0
        rts
1:      lea     GLOB_STORE,%a0
        rts
2:      lea     k_fallback,%a0                  | nessun kit ancora: valori in RAM
        rts

| d0 = valori decodificati (usa d1, a0)
load_p: bsr.s   stor
        move.w  (%a0),%d0
        swap    %d0
        move.w  2(%a0),%d0
        eor.l   #K_DEF,%d0
        rts

| d0 = valori decodificati -> memoria (usa d1, a0)
store_p:
        eor.l   #K_DEF,%d0
        bsr.s   stor
        move.w  %d0,2(%a0)
        swap    %d0
        move.w  %d0,(%a0)
        rts

| ---- pagina FX Drive: se e' ancora quella originale (DRIVE in H, F e G vuoti) mette i 5 id in A..E
fx_page:
        lea     FX_SLOTS,%a0
        move.l  28(%a0),%d0
        cmpi.l  #ID_DRIVE,%d0
        bne.s   2f
        tst.l   24(%a0)                         | G vuoto
        bne.s   2f
        move.l  20(%a0),%d0                     | F vuoto o gia' nostro (GR)
        beq.s   3f
        cmpi.l  #ID_GR,%d0
        bne.s   2f
3:
        lea     k_ids,%a1
        moveq   #N_PAR-1,%d1
1:      mvz.w   (%a1)+,%d0
        move.l  %d0,(%a0)+
        subq.l  #1,%d1
        bge.s   1b
        tst.b   k_gfx                           | una sola volta: disegno di DRIVE su THR..MUP
        bne.s   2f
        moveq   #-1,%d0
        move.b  %d0,k_gfx
        tst.b   k_gfx_on
        beq.s   2f
        lea     k_ids,%a1
        moveq   #3,%d1
4:      mvz.w   (%a1)+,%d0
        mulu.w  #84,%d0
        addi.l  #(OBJS+36),%d0
        movea.l %d0,%a0
        move.l  DRIVE_GFX,(%a0)+
        move.l  DRIVE_GFX+4,(%a0)+
        move.l  DRIVE_GFX+8,(%a0)+
        move.l  DRIVE_GFX+12,(%a0)+
        subq.l  #1,%d1
        bge.s   4b
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
        bsr.w   find
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
        bsr.w   find
        tst.l   %d1
        bmi.s   9f
        moveq   #IDX_GR,%d0
        cmp.l   %d0,%d1
        beq.s   5f
        moveq   #IDX_RAT,%d0
        cmp.l   %d0,%d1
        bne.s   4f
        bsr.w   load_p                          | RAT: posizione 0..8 -> 0..0x7F00
        moveq   #15,%d1
        and.l   %d1,%d0
        mulu.w  #RAT_STEP,%d0
        rts
4:      move.l  %d2,-(%sp)
        move.l  %d1,%d2                         | indice
        bsr.w   load_p
        lea     k_shift,%a0
        mvz.b   (%a0,%d2.l),%d1
        lsr.l   %d1,%d0
        lea     k_mask,%a0
        mvz.b   (%a0,%d2.l),%d1
        and.l   %d1,%d0
        lsl.l   #8,%d0                          | campo -> valore dell'interfaccia
        move.l  (%sp)+,%d2
        rts
5:      move.l  k_meter,%d0                     | GR (con balistica), 2^23 unita' per dB
        moveq   #12,%d1
        asr.l   %d1,%d0                         | 2048 per dB
        move.l  #0x7F00,%d1
        mulu.l  %d1,%d0
        move.l  #(METER_FS*2048),%d1
        divu.l  %d1,%d0
        cmpi.l  #0x7F00,%d0
        bls.s   6f
        move.l  #0x7F00,%d0
6:      rts
9:      move.l  %d2,-(%sp)
        move.l  8(%sp),%d1
        jmp     0x4000D950

set_hook:                                       | 0x4000DA32: scrittura
        move.l  8(%sp),%d0
        bsr.w   find
        tst.l   %d1
        bmi.s   9f
        moveq   #IDX_GR,%d0                     | il misuratore e' in sola lettura
        cmp.l   %d0,%d1
        beq.w   8f
        moveq   #IDX_RAT,%d0
        cmp.l   %d0,%d1
        beq.w   rat_set
        move.l  12(%sp),%d0
        lea     -12(%sp),%sp
        movem.l %d2-%d4,(%sp)
        move.l  %d1,%d2                         | indice
        asr.l   #8,%d0                          | valore -> campo, limitato a [0, massimo]
        bge.s   1f
        moveq   #0,%d0
1:      lea     k_mask,%a0
        mvz.b   (%a0,%d2.l),%d4
        lea     k_max,%a0
        mvz.b   (%a0,%d2.l),%d1
        cmp.l   %d1,%d0
        ble.s   2f
        move.l  %d1,%d0
2:      lea     k_shift,%a0
        mvz.b   (%a0,%d2.l),%d1
        lsl.l   %d1,%d0                         | nuovo campo in posizione
        lsl.l   %d1,%d4                         | maschera in posizione
        move.l  %d0,%d3
        bsr.w   load_p
        not.l   %d4
        and.l   %d4,%d0
        or.l    %d3,%d0
        bsr.w   store_p
        movem.l (%sp),%d2-%d4
        lea     12(%sp),%sp
8:      moveq   #0,%d0
        rts
9:      move.l  %d3,-(%sp)
        move.l  %d2,-(%sp)
        move.l  12(%sp),%d1
        jmp     0x4000DA3A

| ---- RAT: 9 posizioni. Piccolo spostamento (manopola) = una posizione nella sua direzione;
| salto grande (valore assoluto, es. default) = posizione piu' vicina.
rat_set:
        move.l  12(%sp),%d0
        lea     -12(%sp),%sp
        movem.l %d2-%d4,(%sp)
        tst.l   %d0
        bge.s   1f
        moveq   #0,%d0
1:      cmpi.l  #0x7F00,%d0
        ble.s   2f
        move.l  #0x7F00,%d0
2:      move.l  %d0,%d2                         | nuovo valore
        bsr.w   load_p
        move.l  %d0,%d4                         | valori decodificati
        moveq   #15,%d3
        and.l   %d0,%d3                         | posizione attuale
        move.l  %d3,%d0
        mulu.w  #RAT_STEP,%d0                   | valore della posizione attuale
        move.l  %d2,%d1
        sub.l   %d0,%d1                         | differenza
        bge.s   3f
        neg.l   %d1
3:      cmpi.l  #(RAT_STEP/2),%d1
        blt.s   4f
        move.l  %d2,%d3                         | salto: posizione piu' vicina
        addi.l  #(RAT_STEP/2),%d3
        move.l  #RAT_STEP,%d1
        divu.l  %d1,%d3
        bra.s   6f
4:      cmp.l   %d0,%d2
        beq.s   6f
        blt.s   5f
        addq.l  #1,%d3                          | verso l'alto
        bra.s   6f
5:      subq.l  #1,%d3                          | verso il basso
6:      tst.l   %d3
        bge.s   7f
        moveq   #0,%d3
7:      moveq   #8,%d1
        cmp.l   %d1,%d3
        ble.s   9f
        move.l  %d1,%d3
9:      moveq   #-16,%d0
        and.l   %d4,%d0
        or.l    %d3,%d0
        bsr.w   store_p
        movem.l (%sp),%d2-%d4
        lea     12(%sp),%sp
        moveq   #0,%d0
        rts

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
k_fallback:
        .long   0                               | valori (codificati) se non c'e' ancora un kit
k_ids:
        .word   ID_THR, ID_ATK, ID_REL, ID_MUP, ID_RAT, ID_GR
k_shift:
        .byte   25, 18, 11, 4, 0, 0             | posizione del campo nei 32 bit
k_mask:
        .byte   0x7F, 0x7F, 0x7F, 0x7F, 0x0F, 0
k_max:
        .byte   0x7F, 0x7F, 0x7F, 0x7F, 8, 0    | massimo del campo (RAT 0..8)
k_off:
        .byte   0
k_gfx:
        .byte   0                               | disegno di DRIVE gia' copiato
k_gfx_on:
        .byte   GFX_ON                          | esperimento attivo (make_patch --no-drive-knob)
        .balign 4
k_meter:
        .long   0
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
