| modarea — "area mod" in RAM per le mod piu' grandi dello spazio libero dell'immagine
|
| Perche': l'immagine della sezione 3 ha solo ~2 KB liberi; tutto cio' che sta oltre la sua fine
| (0x40347B90) viene azzerato all'avvio (BSS fino a 0x45565490). Le mod grandi vengono quindi
| ACCODATE alla sezione 3 a IMG, compresse (SHLZ, tools/build/lz.py), e decompresse qui in RAM.
|
| Dove (v0.8.2): RAM = primo blocco da 64 KB dell'heap dell'OS (allocatore buddy 0x4010350C, pool di
| 16 MB nel BSS a 0x444E38C0), + 0x10. La RAM sopra il BSS, usata fino alla v0.8.1, l'OS la usa a
| runtime (caricamento dei campioni: issue #4). L'heap invece assegna un blocco a un solo chiamante:
| modarea_reserve chiede 64 KB all'allocatore alla fine della sua inizializzazione, prima di qualunque
| altra richiesta, e riceve sempre l'indice 0. Il lock dell'heap e' ricorsivo.
|
| Agganci:
| - jmp al posto dell'inizio di 0x400004B2 (azzeramento del BSS, chiamato una sola volta all'avvio, cache
|   spente): modarea_load decomprime IMG -> RAM, azzera il resto dell'area e poi il BSS SALTANDO l'area
|   (che ora sta nel BSS), poi rts al chiamante. I 16 byte prima di RAM vengono azzerati come il resto.
| - jsr al posto di "moveq #1,d0 ; move.l d0,0x402D4FD4" (fine dell'inizializzazione dell'heap,
|   0x4010358E): modarea_reserve.
|
| SHLZ: "SHLZ", lunghezza decompressa, lunghezza del flusso, poi gettoni
|   0xxxxxxx         -> x+1 byte letterali
|   1lllllll hi lo   -> l+3 byte copiati da (hi<<8|lo) byte indietro
|
| Costanti da make_patch.py (--defsym): IMG, RAM, SIZE, HEAP_BLOCK_SIZE.

        .equ    MAGIC,          0x53484C5A      | "SHLZ"
        .equ    BSS_LO,         0x40339000      | BSS dell'OS (come 0x400004B2)
        .equ    BSS_HI,         0x45565490
        .equ    HEAP_INIT,      0x402D4FD4      | 1 = heap inizializzato
        .equ    HEAP_ALLOC,     0x4010350C      | allocatore (dimensione) -> indirizzo

        .text
        .globl  modarea_load
modarea_load:
        lea     -44(%sp),%sp
        movem.l %d0-%d2/%d4-%d7/%a0-%a3,(%sp)
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
6:      cmpa.l  %a2,%a1
        bcc.s   7f
        clr.b   (%a1)+
        bra.s   6b
7:      moveq   #0,%d4                          | BSS a zero, 16 byte alla volta, tranne l'area
        moveq   #0,%d5
        moveq   #0,%d6
        moveq   #0,%d7
        lea     BSS_LO,%a0
        lea     RAM,%a2
8:      movem.l %d4-%d7,(%a0)
        lea     16(%a0),%a0
        cmpa.l  %a2,%a0
        bcs.s   8b
        lea     RAM+SIZE,%a0
        lea     BSS_HI,%a2
9:      movem.l %d4-%d7,(%a0)
        lea     16(%a0),%a0
        cmpa.l  %a2,%a0
        bcs.s   9b
        movem.l (%sp),%d0-%d2/%d4-%d7/%a0-%a3
        lea     44(%sp),%sp
        rts

        .globl  modarea_reserve
modarea_reserve:
        moveq   #1,%d0                          | istruzioni sostituite: heap inizializzato
        move.l  %d0,HEAP_INIT
        move.l  #HEAP_BLOCK_SIZE,-(%sp)         | prima richiesta: il blocco di indice 0
        jsr     HEAP_ALLOC
        addq.l  #4,%sp
        move.l  %d0,modarea_block
        rts

        .data
        .globl  modarea_block
modarea_block:
        .long   0                               | indirizzo ricevuto dall'allocatore
