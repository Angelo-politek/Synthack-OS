"""Area dei motori delle machine sulla CPU #2 (mods/modarea7), condivisa da modarea7 e dalle machine (OS 1.42).

La sezione 7 si carica a LOAD; lo stock finisce a IMG (0x4005DF10). Una machine accoda il suo codice per la
CPU #2 a IMG + offset e lo collega a RAM + offset: lo stub di modarea7 lo decomprime li' all'avvio.
RAM sta sopra il BSS della CPU #2 (memoria dei campioni compresa, fino a ~0x4405F750) e sotto la pila (0x48000000).
"""

LOAD = 0x4000_0400
ENTRY = 0x4000_1070             # entry originale della sezione 7 (primi 4 byte dello stock)
IMG = 0x4005_DF10               # fine della sezione 7 stock: qui iniziano le patch accodate
RAM = 0x4700_0000               # area motori nella RAM della CPU #2
SIZE = 0x4_0000                 # 256 KB: dati e BSS dei motori (il resto dopo il codice viene azzerato)
MAX = 0x6_0000 - 5              # staging della CPU #1 (0x40082D66): limite della sezione 7 spedita
