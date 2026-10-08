| modarea — "area mod" in RAM per le mod piu' grandi dello spazio libero dell'immagine
|
| Perche': l'immagine della sezione 3 ha solo ~2 KB liberi; tutto cio' che sta oltre la sua fine
| (0x40347B90) viene azzerato all'avvio (BSS fino a 0x45565490). Le mod grandi vengono quindi
| ACCODATE alla sezione 3 a partire da IMG e copiate qui, a RAM, prima dell'azzeramento.
| RAM = 0x46000000: nella zona tra la fine del BSS e lo stack d'avvio (0x48000000) che nessuna
| istruzione e nessun dato dell'OS indirizza (docs/re-journal.md, 2026-10-09).
|
| Aggancio: jmp al posto delle prime due istruzioni di 0x400004B2 (azzeramento del BSS, chiamato
| una sola volta dall'avvio, a 0x40000542). Cache non ancora attive a questo punto.

        .equ    IMG,            0x40348000      | inizio dell'area accodata alla sezione 3
        .equ    RAM,            0x46000000      | destinazione
        .equ    SIZE,           0x8000          | 32 KB
        .equ    BACK,           0x400004BA      | dopo le istruzioni sostituite

        .text
        .globl  modarea_reloc
modarea_reloc:
        move.l  %a1,-(%sp)
        lea     IMG,%a0
        lea     RAM,%a1
        move.l  #SIZE/4,%d1
1:      move.l  (%a0)+,(%a1)+
        subq.l  #1,%d1
        bne.s   1b
        move.l  (%sp)+,%a1
        lea     -16(%sp),%sp                    | le due istruzioni originali sostituite dal jmp
        movem.l %d4-%d7,(%sp)
        jmp     BACK
