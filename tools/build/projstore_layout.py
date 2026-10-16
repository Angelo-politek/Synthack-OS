"""Memoria delle mod salvata con il progetto (mods/projstore): indirizzi e parti assegnate.

I byte stanno in RAM a DATA (area mod) e nel file del progetto, nell'area riservata delle impostazioni del
progetto. Ogni mod usa solo la sua parte: offset e lunghezza qui sotto. Progetti senza i nostri byte (OS
stock o versioni precedenti) li caricano a zero: zero deve voler dire "valore di default".
"""

import modarea_layout

OFFSET = 0x7000                         # nell'area mod: codice, poi i dati
SIZE = 256                              # byte salvati (multiplo di 4)
PARTS = {}                              # nome della mod -> (offset nei dati, lunghezza)
