| Dual mono — INPUT L e INPUT R come due ingressi separati (sezione 3, Syntakt OS 1.41)
|
| Il blocco originale che calcola i guadagni dell'ingresso esterno (0x40090872..0x400908FC, nella
| funzione dei guadagni 0x400903CA) resta al suo posto: due agganci minimi lo circondano.
|   ingresso 0x40090872: jsr pre_hook ; nop     (al posto di due move.w, rieseguite qui)
|   uscita   0x400908FC: jsr post_hook          (al posto di move.l #32639,d1, rieseguita qui)
| a2 = parametri del mixer (array del motore), a3 = struttura hw (CV), d4 = legge di bilanciamento.
|
| STEREO (flag EXTERNAL IN != 0): il blocco gira una volta, identico all'originale.
| MONO: il blocco gira DUE volte con il bilanciamento al centro:
|   passata 1: livello = IN LR  -> si tiene il VCA sinistro (hw+8)
|   passata 2: livello = BAL    -> si tiene il VCA destro (hw+0x12)
| poi i parametri originali di a2 vengono ripristinati.
| La pagina EXTERNAL MIXER mostra IN L e IN R affiancati. IN R e' l'alias 125 ("Input Level",
| disegnato a barra) con id interno reso 0x25 da make_patch.py, cosi' legge e scrive BAL.

        .equ    DUALMONO_FLAG,  0x80003146      | byte globale EXTERNAL IN: 0 = MONO, != 0 = stereo
        .equ    P_LEVEL,        0x70A           | a2: IN LR
        .equ    P_X,            0x740           | a2: parametro della tabella di livello
        .equ    P_PAN,          0x70E           | a2: BAL
        .equ    PAN_CENTER,     0x4000
        .equ    HW_EXTIN_L,     0x08            | a3 + 8:  CV extin_left
        .equ    BLOCK,          0x40090872      | inizio del blocco originale

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
        .equ    ORIG_INLR,      0x40253B6E      | "IN LR"
        .equ    NAME_INR,       0x4022E164 + 52*67 + 48 | alias 125
        .equ    ORIG_IN,        0x4024F8A7      | "IN"
        | nomi lunghi (titolo in alto mentre si gira la manopola): 0x4022D59C + 52*id + 40
        .equ    LONG_INLR,      0x4022D59C + 52*126 + 40
        .equ    LONG_INR,       0x4022D59C + 52*125 + 40
        .equ    ORIG_LONG_INLR, 0x40253B60      | "In Left/Right"
        .equ    ORIG_LONG_INR,  0x40253B4D      | "Input Level"

        .text
        .globl  pre_hook, post_hook
| ---- ingresso del blocco (registri liberi: d0 d1 d2 a0 a1, come nel blocco originale)
pre_hook:
        tst.b   dm_pass                         | seconda passata: niente da preparare
        bne.s   2f
        tst.b   DUALMONO_FLAG
        bne.s   1f
        bsr.w   ui_mono                         | mono, passata 1
        move.w  P_LEVEL(%a2),%d0                | salva IN LR e BAL
        move.w  %d0,dm_save_lr
        move.w  P_PAN(%a2),%d0
        move.w  %d0,dm_save_bal
        move.w  #PAN_CENTER,%d0                 | bilanciamento al centro per entrambe le passate
        move.w  %d0,P_PAN(%a2)
        bra.s   2f
1:      bsr.w   ui_stereo
2:      move.w  P_LEVEL(%a2),%d2                | le due istruzioni spostate dal trampolino
        move.w  P_X(%a2),%d0
        rts

| ---- uscita del blocco (chiamata al posto di "move.l #32639,d1")
post_hook:
        tst.b   DUALMONO_FLAG
        bne.s   9f                              | stereo: come l'originale
        tst.b   dm_pass
        bne.s   2f
        move.w  HW_EXTIN_L(%a3),%d0             | passata 1: tiene il VCA sinistro = curva(IN LR)
        move.w  %d0,dm_save_l
        move.w  dm_save_bal,%d0                 | livello = BAL per la passata 2
        move.w  %d0,P_LEVEL(%a2)
        moveq   #1,%d0
        move.b  %d0,dm_pass
        addq.l  #4,%sp                          | niente ritorno: si rigira il blocco
        jmp     BLOCK
2:      move.w  dm_save_l,%d0                   | passata 2: VCA destro = curva(BAL) resta,
        move.w  %d0,HW_EXTIN_L(%a3)             | il sinistro torna quello della passata 1
        move.w  dm_save_lr,%d0                  | parametri originali ripristinati
        move.w  %d0,P_LEVEL(%a2)
        move.w  dm_save_bal,%d0
        move.w  %d0,P_PAN(%a2)
        clr.b   dm_pass
9:      move.l  #32639,%d1                      | istruzione spostata dal trampolino
        rts

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
dm_pass:  .byte 0
        .balign 2
dm_save_lr:  .word 0
dm_save_bal: .word 0
dm_save_l:   .word 0
str_inl: .asciz "IN L"
str_inr: .asciz "IN R"
str_long_inl: .asciz "Input Left"
str_long_inr: .asciz "Input Right"
