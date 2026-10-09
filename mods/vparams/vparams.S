| vparams — parametri "virtuali" per le mod: id logici nascosti che le mod leggono e scrivono
| a modo loro (stato in RAM, parole libere del kit...), al posto dell'OS.
|
| Agganci alle tre funzioni centrali dei parametri di kit (entrata: 4(sp) = oggetto, 8(sp) = id,
| 12(sp) = valore): "e' di kit?" 0x4000D870, lettura 0x4000D94A, scrittura 0x4000DA32.
| Per un id registrato in VP_TABLE: "di kit" = 1, lettura e scrittura saltano alle funzioni della
| mod con lo stesso stack; per gli altri id si riprende il codice originale.
| VP_TABLE: 32 voci da 12 byte {id.w, 0.w, lettura, scrittura}, scritte da ogni mod nel suo posto.

        .equ    VP_TABLE,       0x46008000
        .equ    VP_N,           32

        .text
        .globl  vp_kit, vp_get, vp_set

| d0 = id -> a1 = voce, oppure 0 (Z = 1). Usa d1, a1.
vp_find:
        lea     VP_TABLE,%a1
        moveq   #VP_N-1,%d1
1:      cmp.w   (%a1),%d0
        beq.s   2f
        lea     12(%a1),%a1
        subq.l  #1,%d1
        bge.s   1b
        suba.l  %a1,%a1
2:      move.l  %a1,%d1
        rts

vp_kit:                                         | 0x4000D870: "parametro di kit?"
        move.l  8(%sp),%d0
        beq.s   9f                              | id 0: mai registrato (voci vuote)
        bsr.s   vp_find
        beq.s   9f
        moveq   #1,%d0
        rts
9:      move.l  %d2,-(%sp)                      | istruzioni originali sostituite
        moveq   #124,%d2
        move.l  8(%sp),%d1
        jmp     0x4000D878

vp_get:                                         | 0x4000D94A: lettura
        move.l  8(%sp),%d0
        beq.s   9f
        bsr.s   vp_find
        beq.s   9f
        movea.l 4(%a1),%a0
        jmp     (%a0)
9:      move.l  %d2,-(%sp)
        move.l  8(%sp),%d1
        jmp     0x4000D950

vp_set:                                         | 0x4000DA32: scrittura
        move.l  8(%sp),%d0
        beq.s   9f
        bsr.s   vp_find
        beq.s   9f
        movea.l 8(%a1),%a0
        jmp     (%a0)
9:      move.l  %d3,-(%sp)
        move.l  %d2,-(%sp)
        move.l  12(%sp),%d1
        jmp     0x4000DA3A
