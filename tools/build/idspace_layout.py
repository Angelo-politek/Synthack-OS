"""Id dei parametri oltre 504 (mods/idspace): dove stanno le tabelle e cosa scrivono le mod.

L'OS ha 505 id (descrittori a 0x4022D83C, 52 B; oggetti per parametro a 0x41BA0A24, 84 B). idspace copia i
descrittori all'avvio in una tabella di N voci nell'area mod e sposta lì tutti gli accessi; gli id FIRST..N-1 sono
delle mod. Ogni mod scrive, con patch accodate:
- il descrittore sorgente: EXT + 52 * (id - FIRST) (52 B, copiato in TABLE all'avvio; vuoto = come l'id 0);
- la definizione dell'oggetto: OBJDEF + 16 * (id - FIRST): id modello, prototipi +20 (testo), +36 (grafico),
  +68 (stile) o 0 (quelli del modello). L'oggetto si costruisce alla prima ricerca, dall'interfaccia;
- pagine in piu' (indici PAGE_FIRST..): elementi di 44 B a PAGEDEF + 44 * (indice - PAGE_FIRST).
"""

import modarea_layout as L

STOCK_N = 505                    # id dell'OS: 0..504
FIRST, N = 505, 537              # id delle mod: 505..536
N_EXT = N - FIRST
CODE = L.RAM + 0x3_E000          # codice (immagine)
EXT = L.RAM + 0x3_F000           # descrittori sorgente delle mod (immagine): 32 x 52 B
OBJDEF = L.RAM + 0x3_F680        # definizioni degli oggetti (immagine): 32 x 16 B
PAGEDEF = L.RAM + 0x3_F880       # pagine in piu' (immagine): 4 x 44 B
PAGE_FIRST, PAGE_N = 37, 4
TABLE = L.RAM + 0x4_0000         # descrittori, N x 52 B (solo RAM, scritta all'avvio)
OBJ = L.RAM + 0x4_7000           # oggetti delle mod, 32 x 84 B (solo RAM, costruiti alla prima ricerca)
BUILT = OBJ + N_EXT * 84         # u32: 1 = oggetti costruiti

# id delle mod (registro: tools/build/registry.py)
IDS = {
    "fx3 page": list(range(505, 513)),
    "fx3 input SND3": [513],
    "master-comp": list(range(514, 521)),
    "sy-fm4": list(range(521, 529)),
}


def desc(pid: int) -> int:
    """Indirizzo del descrittore sorgente (immagine) di un id delle mod."""
    assert FIRST <= pid < N
    return EXT + 52 * (pid - FIRST)


def objdef(pid: int) -> int:
    assert FIRST <= pid < N
    return OBJDEF + 16 * (pid - FIRST)


def page(index: int) -> int:
    assert PAGE_FIRST <= index < PAGE_FIRST + PAGE_N
    return PAGEDEF + 44 * (index - PAGE_FIRST)
