"""Memoria delle mod salvata con il progetto (mods/projstore): indirizzi e parti assegnate.

I byte stanno in RAM a DATA (meta' solo RAM dell'area mod, azzerata dal caricatore) e nel file del progetto,
nell'area riservata delle impostazioni del progetto. Ogni mod usa solo la sua parte: offset e lunghezza qui sotto.
Progetti senza i nostri byte (OS stock o versioni precedenti) li caricano a zero: zero deve voler dire "valore di
default". Un progetto salvato con meno byte (256 fino al 2026-11-07) carica quelli che ha, il resto a zero.
"""

import modarea_layout

OFFSET = 0x7000                         # nell'area mod: codice
DATA_OFFSET = 0x58000                   # nell'area mod: i byte salvati (registry.MODAREA)
SIZE = 420                              # byte salvati (multiplo di 4, al piu' 468: fino a +0x3FF del blocco)
PARTS = {"long-samples": (0, 132),       # nome della mod -> (offset nei dati, lunghezza): lista dei campioni del progetto
         "arp": (132, 288)}              # impostazioni dell'arpeggiatore, 24 byte per traccia audio
DATA = modarea_layout.RAM + DATA_OFFSET
