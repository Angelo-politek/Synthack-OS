| modarea7 — sezione 7 (CPU #2, motore delle voci) compressa, con un'area per i motori delle machine
|
| Perche': la CPU #1 mette la sezione 7 in uno staging di 0x60000 byte (0x40082D66, 5 di intestazione) e
| lo stock ne usa 383 760: restano 9 451 byte. Il bootloader della CPU #2 (sezione 6) ne accetta fino a
| 2 MB (0x800003F8: destinazione 0x40000400, massimo 0x200000). Quindi la sezione viaggia compressa e la
| decomprime questo stub, sulla CPU #2, prima dell'entry originale. CPU #1, staging, bootloader e
| rispedizione (0x40083202) restano quelli stock.
|
| Immagine (caricata dal bootloader a 0x40000400, che salta a *(0x40000400)):
|   +0    puntatore d'ingresso = stub
|   +4    stub
|         hdr: lunghezza totale, entry originale, RAM dell'area motori, byte da azzerare dopo l'area
|         flusso SHLZ della sezione 7 (stock + patch)        -> 0x40000400
|         flusso SHLZ dell'area motori (facoltativo)         -> ENGINE_RAM (0x47000000, sopra il BSS
|                                                               della CPU #2 che finisce a ~0x4405F750)
|
| Lo stub copia l'immagine a HIGH, prosegue da li', decomprime, invalida le cache (CACR come lo lascia
| il bootloader, 0x800005E0..0x80000628: ICINVA e BCINVA) e salta all'entry originale con la pila com'era.
| Usa solo registri e la pila del bootloader (SRAM), bilanciata.
|
| SHLZ (tools/build/lz.py): "SHLZ", lunghezza decompressa, lunghezza del flusso, poi gettoni
|   0xxxxxxx         -> x+1 byte letterali
|   1lllllll hi lo   -> l+3 byte copiati da (hi<<8|lo) byte indietro

        .equ    LOAD,   0x40000400
        .equ    HIGH,   0x46000000              | appoggio: sopra il BSS, sotto l'area motori
        .equ    MAGIC,  0x53484C5A              | "SHLZ"
        .equ    CACR,   0x000CC100              | valore del bootloader: cache istruzioni + invalidazione

        .text
        .globl  image
image:  .long   LOAD + (stub - image)           | il bootloader salta qui
stub:   lea     image(%pc),%a0
        movea.l #HIGH,%a1
        move.l  hdr_total(%pc),%d0
        addq.l  #3,%d0
        lsr.l   #2,%d0
1:      move.l  (%a0)+,(%a1)+
        subq.l  #1,%d0
        bne.s   1b
        move.l  #CACR,%d0
        movec   %d0,%cacr
        nop
        jmp     HIGH + (cont - image)           | stesso codice, nella copia

cont:   lea     stream(%pc),%a0
        movea.l #LOAD,%a1
        bsr.s   depack                          | a0 -> fine del flusso
        move.l  %a0,%d0                         | il secondo flusso parte allineato a 4
        addq.l  #3,%d0
        andi.l  #-4,%d0
        movea.l %d0,%a0
        movea.l hdr_engine(%pc),%a1
        bsr.s   depack                          | niente flusso: a1 resta all'inizio dell'area
        move.l  hdr_clear(%pc),%d0              | azzera il resto dell'area (BSS dei motori)
        beq.s   3f
2:      clr.b   (%a1)+
        subq.l  #1,%d0
        bne.s   2b
3:      move.l  #CACR,%d0
        movec   %d0,%cacr
        nop
        movea.l hdr_entry(%pc),%a1
        jmp     (%a1)

| a0 = flusso SHLZ, a1 = destinazione; ritorna a0 dopo il flusso, a1 dopo i dati
depack: move.l  (%a0),%d0
        cmpi.l  #MAGIC,%d0
        bne.s   9f
        move.l  4(%a0),%d2                      | lunghezza decompressa
        lea     12(%a0),%a0
        movea.l %a1,%a2
        adda.l  %d2,%a2
4:      cmpa.l  %a2,%a1
        bcc.s   9f
        moveq   #0,%d0
        move.b  (%a0)+,%d0
        bmi.s   6f
5:      move.b  (%a0)+,(%a1)+                   | d0+1 letterali
        subq.l  #1,%d0
        bge.s   5b
        bra.s   4b
6:      andi.l  #0x7F,%d0                       | l+3 byte: contatore da l+2 a 0
        addq.l  #2,%d0
        moveq   #0,%d1
        move.b  (%a0)+,%d1
        lsl.l   #8,%d1
        move.b  (%a0)+,%d1
        movea.l %a1,%a3
        suba.l  %d1,%a3
7:      move.b  (%a3)+,(%a1)+
        subq.l  #1,%d0
        bge.s   7b
        bra.s   4b
9:      rts

        .balign 4
        .globl  hdr_total, hdr_entry, hdr_engine, hdr_clear, stream
hdr_total:  .long 0                             | scritti da build.py
hdr_entry:  .long 0
hdr_engine: .long 0
hdr_clear:  .long 0
stream:
