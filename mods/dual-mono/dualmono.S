| Dual mono — INPUT L e INPUT R come due ingressi separati (sezione 3, Syntakt OS 1.41)
|
| Chiamata da un trampolino al posto del blocco 0x40090872..0x400908F8 della funzione dei
| guadagni del mixer analogico (0x400903CA). Analisi completa in docs/.
|
| Ingresso (impostati dalla funzione originale):
|   a2 = parametri globali del mixer   a3 = struttura hardware (CV)   d4 = legge di bilanciamento
| Registri usati: d0 d1 d2 a0 a1, come il blocco originale (gli altri sono preservati).
|
| STEREO (impostazione EXTERNAL IN = stereo, flag != 0): calcolo IDENTICO all'originale.
| MONO:   VCA sinistro = curva(IN LR) al centro, VCA destro = curva(BAL) al centro;
|         la pagina EXTERNAL MIXER mostra IN L e IN R affiancati. IN R e' l'alias 125
|         ("Input Level", disegnato a barra) con id interno reso 0x25 da make_patch.py, cosi'
|         legge e scrive il valore di BAL (BAL ha il grafico "clessidra", non modificabile).

        .equ    DUALMONO_FLAG,  0x80003146      | byte globale EXTERNAL IN: 0 = MONO, != 0 = stereo
                                                | (verificato sulla macchina il 2026-10-08: la v1
                                                |  assumeva il contrario e le modalita' erano invertite)
        .equ    P_LEVEL,        0x70A           | a2: IN LR
        .equ    P_X,            0x740           | a2: parametro della tabella di livello
        .equ    P_PAN,          0x70E           | a2: BAL
        .equ    P_PREPOST,      0x71A           | a2: In FX Routing
        .equ    PAN_CENTER,     0x4000
        .equ    LEVEL_TABLE,    0x401DC9E0
        .equ    HW_EXTIN_L,     0x08            | a3 + 8:  CV extin_left
        .equ    HW_EXTIN_R,     0x12            | a3 + 18: CV extin_right

        | pagina "MIX3 / External Mixer" (oggetto statico in RAM), 8 manopole da +8
        .equ    MIX3_SLOTS,     0x41B9F7F0
        .equ    ID_INLR,        126
        .equ    ID_BAL,         128
        .equ    ID_INR,         125             | alias "Input Level" (barra), id interno reso 0x25 = BAL
        .equ    ID_DEL,         129
        .equ    ID_REV,         130
        .equ    ID_FXROUT,      132
        | nomi brevi nella tabella dei parametri (0x4022E164 + 52*indice + 48)
        .equ    NAME_INLR,      0x4022E164 + 52*68 + 48
        .equ    NAME_PAN,       0x4022E164 + 52*69 + 48
        .equ    NAME_BAL,       0x4022E164 + 52*70 + 48
        .equ    ORIG_INLR,      0x40253B6E      | "IN LR"
        .equ    ORIG_PAN,       0x40266015      | "PAN"
        .equ    ORIG_BAL,       0x40265CC9      | "BAL"
        .equ    NAME_INR,       0x4022E164 + 52*67 + 48 | alias 125
        .equ    ORIG_IN,        0x4024F8A7      | "IN"
        | nomi lunghi (titolo in alto mentre si gira la manopola): 0x4022D59C + 52*id + 40
        .equ    LONG_INLR,      0x4022D59C + 52*126 + 40
        .equ    LONG_INR,       0x4022D59C + 52*125 + 40
        .equ    ORIG_LONG_INLR, 0x40253B60      | "In Left/Right"
        .equ    ORIG_LONG_INR,  0x40253B4D      | "Input Level"

        .text
        .globl  dm_hook
dm_hook:
        tst.b   DUALMONO_FLAG
        beq.s   mono
| ---- stereo: esattamente il blocco originale
        move.w  P_LEVEL(%a2),%d2
        move.w  P_PAN(%a2),%d1
        bsr.s   gains
        move.w  %d0,HW_EXTIN_L(%a3)
        move.w  %d2,HW_EXTIN_R(%a3)
        bra.w   ui_stereo
| ---- mono: due ingressi indipendenti, ciascuno con la legge di bilanciamento al centro
mono:
        move.w  P_LEVEL(%a2),%d2                | IN L = IN LR
        move.w  #PAN_CENTER,%d1
        bsr.s   gains
        move.w  %d0,HW_EXTIN_L(%a3)
        move.w  P_PAN(%a2),%d2                  | IN R = valore di BAL usato come livello
        move.w  #PAN_CENTER,%d1
        bsr.s   gains
        move.w  %d2,HW_EXTIN_R(%a3)
        bra.w   ui_mono

| gains: trascrizione fedele del blocco 0x40090872..0x400908F8.
| Ingresso: d2.w = livello grezzo, d1.w = bilanciamento grezzo (nell'originale letto da P_PAN).
| Uscita:   d0 = valore per extin_left, d2 = valore per extin_right (limitati a 0xFFFF).
gains:
        move.w  P_X(%a2),%d0
        muls.w  #32512,%d2
        add.l   %d2,%d2
        mac.l   %d2,%d2,%acc0
        movclr.l %acc0,%d2
        tst.w   P_PREPOST(%a2)
        beq.s   1f
        move.l  #25998,%d0
        mac.l   %d0,%d2,%acc0
        movclr.l %acc0,%d2
        bra.s   2f
1:      mvs.w   %d0,%d0
        asr.l   #8,%d0
        lea     LEVEL_TABLE,%a1
        movea.l #65535,%a0
        mac.l   %a0,%d2,%acc0
        movclr.l %acc0,%a0
        move.l  (%a1,%d0.l*4),%d2
        lea     (%a0,%a0.l*2),%a0
        msac.l  %a0,%d2,%acc0
        movclr.l %acc0,%d2
2:      mvs.w   %d1,%d0                         | originale: mvs.w P_PAN(%a2),%d0
        movea.l %d4,%a0
        move.l  %d0,-(%sp)
        jsr     (%a0)
        addq.l  #4,%sp
        msac.l  %d2,%d0,%acc0
        msac.l  %d2,%d1,%acc1
        movclr.l %acc0,%d0
        movclr.l %acc1,%d1
        cmpi.l  #65535,%d0
        ble.s   3f
        move.l  #65535,%d0
3:      move.l  %d1,%d2
        cmpi.l  #65535,%d1
        ble.s   4f
        move.l  #65535,%d2
4:      rts

| ---- interfaccia: tocca la pagina SOLO se la riconosce (IN LR, DEL, REV, FX al loro posto)
page_ok:                                        | Z=1 se la pagina e' quella attesa; a0 = slot
        lea     MIX3_SLOTS,%a0
        moveq   #ID_INLR,%d0
        cmp.l   (%a0),%d0
        bne.s   5f
        move.l  #ID_DEL,%d0
        cmp.l   16(%a0),%d0
        bne.s   5f
        move.l  #ID_REV,%d0
        cmp.l   20(%a0),%d0
        bne.s   5f
        move.l  #ID_FXROUT,%d0
        cmp.l   28(%a0),%d0
5:      rts

ui_mono:
        bsr.s   page_ok
        bne.s   6f
        | (il ColdFire non ammette move.l #imm verso memoria indirizzata: passiamo da d0/a1)
        moveq   #ID_INR,%d0
        move.l  %d0,4(%a0)                      | manopola B: alias 125 (barra) = valore di BAL
        clr.l   24(%a0)                         | manopola G: vuota (BAL non serve in mono)
        lea     str_inl,%a1
        move.l  %a1,NAME_INLR
        lea     str_inr,%a1
        move.l  %a1,NAME_INR
        lea     str_long_inl,%a1
        move.l  %a1,LONG_INLR
        lea     str_long_inr,%a1
        move.l  %a1,LONG_INR
6:      rts

ui_stereo:
        bsr.s   page_ok
        bne.s   7f
        clr.l   4(%a0)                          | disposizione originale
        move.l  #ID_BAL,%d0
        move.l  %d0,24(%a0)
        move.l  #ORIG_INLR,%d0
        move.l  %d0,NAME_INLR
        move.l  #ORIG_IN,%d0
        move.l  %d0,NAME_INR
        move.l  #ORIG_LONG_INLR,%d0
        move.l  %d0,LONG_INLR
        move.l  #ORIG_LONG_INR,%d0
        move.l  %d0,LONG_INR
7:      rts

        .data
str_inl: .asciz "IN L"
str_inr: .asciz "IN R"
str_long_inl: .asciz "Input Left"
str_long_inr: .asciz "Input Right"
