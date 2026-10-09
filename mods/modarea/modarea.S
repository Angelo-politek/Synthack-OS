| modarea — "area mod" in RAM per le mod piu' grandi dello spazio libero dell'immagine
|
| Perche': l'immagine della sezione 3 ha solo ~2 KB liberi; tutto cio' che sta oltre la sua fine
| (0x40347B90) viene azzerato all'avvio (BSS fino a 0x45565490). Le mod grandi vengono quindi
| ACCODATE alla sezione 3 a IMG, compresse (SHLZ, tools/build/lz.py), e decompresse qui in RAM
| prima dell'azzeramento. Compresse non consumano il margine di decompressione del bootstrap.
| RAM = 0x46000000: nella zona tra la fine del BSS e lo stack d'avvio (0x48000000) che nessuna
| istruzione e nessun dato dell'OS indirizza (docs/).
|
| Aggancio: jmp al posto delle prime due istruzioni di 0x400004B2 (azzeramento del BSS, chiamato
| una sola volta dall'avvio, a 0x40000542). Cache non ancora attive a questo punto.
|
| SHLZ: "SHLZ", lunghezza decompressa, lunghezza del flusso, poi gettoni
|   0xxxxxxx         -> x+1 byte letterali
|   1lllllll hi lo   -> l+3 byte copiati da (hi<<8|lo) byte indietro

        .equ    IMG,            0x40348000      | flusso compresso accodato alla sezione 3
        .equ    RAM,            0x46000000      | destinazione
        .equ    SIZE,           0x10000         | 64 KB: il resto oltre i dati viene azzerato
        .equ    MAGIC,          0x53484C5A      | "SHLZ"
        .equ    BACK,           0x400004BA      | dopo le istruzioni sostituite

        .text
        .globl  modarea_reloc
modarea_reloc:
        lea     -20(%sp),%sp
        movem.l %d0/%d2/%a1-%a3,(%sp)
        lea     IMG,%a0
        lea     RAM,%a1
        move.l  (%a0),%d0
        cmpi.l  #MAGIC,%d0
        bne.s   4f                              | nessun flusso: area solo azzerata
        move.l  4(%a0),%d2                      | lunghezza decompressa
        lea     12(%a0),%a0
        movea.l %a1,%a2
        adda.l  %d2,%a2                         | fine dei dati
1:      cmpa.l  %a2,%a1
        bcc.s   4f
        moveq   #0,%d0
        move.b  (%a0)+,%d0
        bmi.s   3f
2:      move.b  (%a0)+,(%a1)+                   | d0+1 letterali
        subq.l  #1,%d0
        bge.s   2b
        bra.s   1b
3:      andi.l  #0x7F,%d0                       | l+3 byte: contatore da l+2 a 0
        addq.l  #2,%d0
        moveq   #0,%d1
        move.b  (%a0)+,%d1
        lsl.l   #8,%d1
        move.b  (%a0)+,%d1                      | distanza
        movea.l %a1,%a3
        suba.l  %d1,%a3
5:      move.b  (%a3)+,(%a1)+
        subq.l  #1,%d0
        bge.s   5b
        bra.s   1b
4:      lea     RAM+SIZE,%a2                    | azzera il resto dell'area
6:      move.l  %a1,%d0                         | prima byte fino all'allineamento a 4...
        andi.l  #3,%d0
        beq.s   8f
        clr.b   (%a1)+
        bra.s   6b
8:      cmpa.l  %a2,%a1                         | ...poi parole lunghe (SIZE e' multiplo di 4)
        bcc.s   7f
        clr.l   (%a1)+
        bra.s   8b
7:      movem.l (%sp),%d0/%d2/%a1-%a3
        lea     20(%sp),%sp
        lea     -16(%sp),%sp                    | le due istruzioni originali sostituite dal jmp
        movem.l %d4-%d7,(%sp)
        jmp     BACK
