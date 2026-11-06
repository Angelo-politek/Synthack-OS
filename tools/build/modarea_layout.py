"""Indirizzi dell'area mod, condivisi da mods/modarea e da tutte le mod che la usano (OS 1.42).

Dalla v0.8.2 l'area mod e' un blocco dell'heap dell'OS (allocatore buddy 0x401036D0, pool di 16 MB nel BSS
a 0x444E48C0..0x454E48C0): il primo blocco (256 KB), prenotato da modarea alla prima allocazione, quindi
sempre lo stesso e mai assegnato ad altri. Dal 2026-11-06 512 KB: la seconda meta' ospita le tabelle di
idspace (descrittori degli id oltre 504), solo RAM a runtime. Fino alla v0.8.1 stava a 0x46000000, sopra il BSS: RAM che l'OS
usa a runtime (caricamento dei campioni, issue #4).
"""

HEAP_BLOCK = 0x444E_48C0        # primo blocco dell'heap (indice 0)
HEAP_BLOCK_SIZE = 0x8_0000      # richiesta all'allocatore: 512 KB (64 KB fino al 2026-11-04, 128 KB fino al 2026-11-05, 256 KB fino al 2026-11-06)
RAM = HEAP_BLOCK + 0x10         # i primi 12 byte li scrive l'inizializzazione dell'heap
SIZE = HEAP_BLOCK + HEAP_BLOCK_SIZE - RAM
IMG = 0x4034_9000               # flusso compresso accodato alla sezione 3
BOOT_LIST = 0x7400              # offset della lista di avvio: BOOT_N puntatori a funzioni chiamate dopo la decompressione
BOOT_N = 8


def boot_slot(n: int) -> int:
    """Indirizzo nell'immagine (IMG) del posto n della lista di avvio."""
    assert 0 <= n < BOOT_N
    return IMG + BOOT_LIST + 4 * n
