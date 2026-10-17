"""Parole delle mod salvate con il kit (mods/kitstore): dove stanno e a chi sono assegnate.

Parole 41..43 dei 12 blocchi per traccia del kit (dati delle tracce MIDI della Digitakt, mai usati sulla
Syntakt): in RAM a kit + BLOCKS + STRIDE * t + 82 + 2 * k (k = 0..2), kit = *0x800030B8.
Kit salvati senza queste parole le caricano a zero: zero deve voler dire "valore di default".
"""

BLOCKS, STRIDE, FIRST = 0xE5C, 148, 82
WORDS_PER_BLOCK, N_BLOCKS = 3, 12


def word(block: int, k: int) -> int:
    """Offset nel kit della parola k (0..2) del blocco block (0..11)."""
    assert 0 <= block < N_BLOCKS and 0 <= k < WORDS_PER_BLOCK
    return BLOCKS + STRIDE * block + FIRST + 2 * k


PARTS = {"dual-mono": [(0, 0), (0, 1), (0, 2)]}   # nome della mod -> (blocco, parola): DEL R, REV R, FX3 R
