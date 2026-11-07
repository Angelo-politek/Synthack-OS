"""Id dei parametri oltre 504 (mods/idspace): dove stanno le tabelle e cosa scrivono le mod.

L'OS ha 505 id (descrittori a 0x4022D83C, 52 B; oggetti per parametro a 0x41BA0A24, 84 B). idspace copia i
descrittori all'avvio in una tabella di N voci nell'area mod e sposta lì tutti gli accessi; gli id FIRST..N-1 sono
delle mod. Ogni mod scrive, con patch accodate:
- il descrittore sorgente: EXT + 52 * (id - FIRST) (52 B, copiato in TABLE all'avvio; vuoto = come l'id 0);
- la definizione dell'oggetto: OBJDEF + 16 * (id - FIRST): id modello, prototipi +20 (testo), +36 (grafico),
  +68 (stile) o 0 (quelli del modello). L'oggetto si costruisce alla prima ricerca, dall'interfaccia;
- pagine in piu' (indici PAGE_FIRST..): elementi di 44 B a PAGEDEF + 44 * (indice - PAGE_FIRST);
- voci in piu' del menu DEST degli LFO: DESTX (machine, posizione, id). Il menu passa da 33 a 66 voci: due id da
  16 bit per ogni parola della lista dell'OS (stesse dimensioni di closure e buffer), 0xFFFF a fine riga.
"""

import modarea_layout as L

STOCK_N = 505                    # id dell'OS: 0..504
FIRST, N = 505, 537              # id delle mod: 505..536
N_EXT = N - FIRST
CODE = L.RAM + 0x3_E000          # codice (immagine)
OBJ_ENTRY = CODE                 # jmp ids_obj32: oggetto per parametro dell'id 4(sp) -> d0 (indirizzo fisso)
EXT = L.RAM + 0x3_F000           # descrittori sorgente delle mod (immagine): 32 x 52 B
OBJDEF = L.RAM + 0x3_F680        # definizioni degli oggetti (immagine): 32 x 16 B
PAGEDEF = L.RAM + 0x3_F880       # pagine in piu' (immagine): 4 x 44 B
PAGE_FIRST, PAGE_N = 37, 4
DESTX = L.RAM + 0x3_F940         # voci in piu' del menu DEST degli LFO (immagine): DESTX_N x {u8 machine, u8 dopo, u16 id}
DESTX_N = 64
TABLE = L.RAM + 0x4_0000         # descrittori, N x 52 B (solo RAM, scritta all'avvio)
OBJ = L.RAM + 0x4_7000           # oggetti delle mod, 32 x 84 B (solo RAM, costruiti alla prima ricerca)
BUILT = OBJ + N_EXT * 84         # u32: 1 = oggetti costruiti
ROWS = L.RAM + 0x4_A000          # righe del menu DEST impacchettate: 46 x 66 id da 16 bit (0xFFFF = fine), solo RAM
DEST_ROWS, DEST_N = 46, 66       # 45 machine + FX track; voci per riga (stock 33)

# id delle mod (registro: tools/build/registry.py)
IDS = {
    "fx3 page": list(range(505, 513)),
    "fx3 input SND3": [513],
    "master-comp": list(range(514, 521)),
    "sy-fm4": list(range(521, 529)),
}


def destx(k: int) -> int:
    """Voce k della tabella DESTX (immagine): {machine (0..44, 45 = FX track), dopo la voce stock n., id}."""
    assert 0 <= k < DESTX_N
    return DESTX + 4 * k


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
