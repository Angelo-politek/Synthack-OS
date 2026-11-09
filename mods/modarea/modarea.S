| modarea — "area mod" in RAM per le mod piu' grandi dello spazio libero dell'immagine
|
| Perche': l'immagine della sezione 3 ha solo ~2 KB liberi; tutto cio' che sta oltre la sua fine
| (0x40348B90) viene azzerato all'avvio (BSS fino a 0x45566490). Le mod grandi vengono quindi
| ACCODATE alla sezione 3 a IMG, compresse (SHLZ, tools/build/lz.py), e decompresse qui in RAM.
|
| Dove (v0.8.2): RAM = primo blocco da 64 KB dell'heap dell'OS (allocatore buddy 0x401036D0, pool di
| 16 MB nel BSS a 0x444E48C0), + 0x10. La RAM sopra il BSS, usata fino alla v0.8.1, l'OS la usa a
| runtime (caricamento dei campioni: issue #4). L'heap invece assegna un blocco a un solo chiamante:
| modarea_reserve chiede 64 KB all'allocatore alla fine della sua inizializzazione, prima di qualunque
| altra richiesta, e riceve sempre l'indice 0. Il lock dell'heap e' ricorsivo.
|
| Agganci:
| - jmp al posto dell'inizio di 0x400004B2 (azzeramento del BSS, chiamato una sola volta all'avvio, cache
|   spente): modarea_load decomprime IMG -> RAM, azzera il resto dell'area e poi il BSS SALTANDO l'area
|   (che ora sta nel BSS), poi rts al chiamante. I 16 byte prima di RAM vengono azzerati come il resto.
| - jsr al posto di "moveq #1,d0 ; move.l d0,0x402D5324" (fine dell'inizializzazione dell'heap,
|   0x40103752): modarea_reserve.
|
| SHLZ: "SHLZ", lunghezza decompressa, lunghezza del flusso, poi gettoni
|   0xxxxxxx         -> x+1 byte letterali
|   1lllllll hi lo   -> l+3 byte copiati da (hi<<8|lo) byte indietro
|
| SHLW (dal 2026-11-09): lo stesso flusso con la sigla "SHLW" e il corpo in XOR, una parola alla volta, con un
|   xorshift32 (tools/build/lz.py, whiten). Un flusso SHLZ e' ancora comprimibile da aPLib: nella decompressione
|   d'avvio della sezione 3 l'uscita corre allora piu' dell'ingresso e il margine (bootcheck.py) cala con ogni
|   byte di codice delle mod. Sbiancato non lo e' piu': il margine non dipende dalle mod. modarea_load toglie
|   l'XOR sul posto (IMG e' RAM, letta una volta sola) e poi decomprime come prima.
|
| Lista di avvio (RAM + BOOT_LIST, BOOT_N puntatori): dopo la decompressione e il BSS, modarea_load chiama ogni
| puntatore diverso da zero (funzioni C senza argomenti; cache spente, pila dell'avvio). Una mod ci scrive il suo
| con una patch accodata a IMG + BOOT_LIST + 4 * posto (posti in tools/build/registry.py).
|
| Costanti da make_patch.py (--defsym): IMG, RAM, SIZE, HEAP_BLOCK_SIZE, BOOT_LIST, BOOT_N.

        .equ    MAGIC,          0x53484C5A      | "SHLZ"
        .equ    MAGIC_W,        0x53484C57      | "SHLW", anche seme dell'xorshift32
        .equ    BSS_LO,         0x4033A000      | BSS dell'OS (come 0x400004B2)
        .equ    BSS_HI,         0x45566490
        .equ    HEAP_INIT,      0x402D5324      | 1 = heap inizializzato
        .equ    HEAP_ALLOC,     0x401036D0      | allocatore (dimensione) -> indirizzo

        .text
        .globl  modarea_load
modarea_load:
        lea     -44(%sp),%sp
        movem.l %d0-%d2/%d4-%d7/%a0-%a3,(%sp)
        lea     IMG,%a0
        lea     RAM,%a1
        move.l  (%a0),%d0
        cmpi.l  #MAGIC_W,%d0
        bne.s   21f
        move.l  8(%a0),%d2                      | SHLW: lunghezza del flusso -> parole (per eccesso)
        addq.l  #3,%d2
        lsr.l   #2,%d2
        lea     12(%a0),%a3
        move.l  %d0,%d1                         | stato = seme
        moveq   #13,%d4
        moveq   #17,%d5
20:     tst.l   %d2
        beq.s   22f
        move.l  %d1,%d0                         | xorshift32: 13 a sinistra, 17 a destra, 5 a sinistra
        lsl.l   %d4,%d0
        eor.l   %d0,%d1
        move.l  %d1,%d0
        lsr.l   %d5,%d0
        eor.l   %d0,%d1
        move.l  %d1,%d0
        lsl.l   #5,%d0
        eor.l   %d0,%d1
        move.l  (%a3),%d0
        eor.l   %d1,%d0
        move.l  %d0,(%a3)+
        subq.l  #1,%d2
        bra.s   20b
21:     cmpi.l  #MAGIC,%d0
        bne.s   4f                              | nessun flusso: area solo azzerata
22:     move.l  4(%a0),%d2                      | lunghezza decompressa
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
        lea     RAM+BOOT_LIST,%a3               | lista di avvio: le mod che devono preparare dati
        moveq   #BOOT_N,%d4                     | prima che l'OS li legga (BOOT_N puntatori, 0 = vuoto)
10:     move.l  (%a3)+,%d0
        beq.s   11f
        movea.l %d0,%a0
        jsr     (%a0)
11:     subq.l  #1,%d4
        bne.s   10b
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
