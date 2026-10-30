| kitstore — parole delle mod salvate con il kit (Syntakt OS 1.41)
|
| Il kit ha 12 blocchi per traccia da 148 byte (kit + 0xE5C + 148 * t): sono i dati delle tracce MIDI della
| Digitakt, 71 parole. L'OS salva le parole 0..40 (id interni 17..40 dei gruppi MIDI 56..58) con
| 0x400A6EE6 e le rilegge con 0x400A6E7A; le parole 41..70 non sono salvate, rilette ne' usate (solo
| copiate in 0x444B5B48), e nel blocco del file i byte +150..+155 sono azzerati e mai letti.
| Qui: le parole 41..43 di ogni blocco (RAM, byte +82..+87) vanno nei byte +150..+155 del file e
| tornano indietro alla lettura. 36 parole per kit; un kit salvato senza (OS stock o versioni
| precedenti) le carica a zero, come un kit nuovo: zero deve voler dire "valore di default".

        .equ    WR_BACK,        0x400A6EEE      | dopo le istruzioni sostituite
        .equ    RD_BACK,        0x400A6E82

        .text
        .globl  ks_wr
ks_wr:                                          | al posto di 0x400A6EE6 (file, blocco in RAM)
        move.l  8(%sp),-(%sp)
        move.l  8(%sp),-(%sp)
        bsr.s   1f
        addq.l  #8,%sp
        tst.b   %d0
        beq.s   2f
        movea.l 4(%sp),%a0                      | file
        movea.l 8(%sp),%a1                      | RAM
        move.w  82(%a1),150(%a0)
        move.w  84(%a1),152(%a0)
        move.w  86(%a1),154(%a0)
2:      rts
1:      move.l  %a3,-(%sp)                      | istruzioni sostituite
        move.l  %a2,-(%sp)
        movea.l 12(%sp),%a2
        jmp     WR_BACK

        .globl  ks_rd
ks_rd:                                          | al posto di 0x400A6E7A (blocco in RAM, file)
        move.l  8(%sp),-(%sp)
        move.l  8(%sp),-(%sp)
        bsr.s   1f
        addq.l  #8,%sp
        tst.b   %d0
        beq.s   2f
        movea.l 4(%sp),%a0                      | RAM
        movea.l 8(%sp),%a1                      | file
        move.w  150(%a1),82(%a0)
        move.w  152(%a1),84(%a0)
        move.w  154(%a1),86(%a0)
2:      rts
1:      lea     -12(%sp),%sp                    | istruzioni sostituite
        movem.l %a2-%a4,(%sp)
        jmp     RD_BACK
