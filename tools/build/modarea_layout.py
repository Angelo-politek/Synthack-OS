"""Indirizzi dell'area mod, condivisi da mods/modarea e da tutte le mod che la usano (OS 1.41).

Dalla v0.8.2 l'area mod e' un blocco dell'heap dell'OS (allocatore buddy 0x4010350C, pool di 16 MB nel BSS
a 0x444E38C0..0x454E38C0): il primo blocco da 64 KB, prenotato da modarea alla prima allocazione, quindi
sempre lo stesso e mai assegnato ad altri. Fino alla v0.8.1 stava a 0x46000000, sopra il BSS: RAM che l'OS
usa a runtime (caricamento dei campioni, issue #4).
"""

HEAP_BLOCK = 0x444E_38C0        # primo blocco dell'heap (indice 0)
HEAP_BLOCK_SIZE = 0x1_0000      # richiesta all'allocatore: 64 KB (ordine 12)
RAM = HEAP_BLOCK + 0x10         # i primi 12 byte li scrive l'inizializzazione dell'heap
SIZE = HEAP_BLOCK + HEAP_BLOCK_SIZE - RAM
IMG = 0x4034_8000               # flusso compresso accodato alla sezione 3
