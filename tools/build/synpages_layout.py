"""Tabella delle machine con pagine SYN proprie (mods/syn-pages), condivisa dalle mod che la usano (OS 1.42).

All'inizio del blob di syn-pages nell'area mod: N voci da 20 byte {chiave, pagine, record, title, draw}. Una
machine si registra dalla lista di avvio di modarea (scrive la prima voce libera); syn-pages la usa dalla vista
SRC. La chiave e' il descrittore della manopola A sulla pagina stock della machine (190 = SY TONE, 497 = SP
TWINSHOT): lo stesso modo di riconoscerla che usava sy-fm4.
"""

import modarea_layout as M

OFF = 0x7420                    # syn-pages nell'area mod (registry.py)
TABLE = M.RAM + OFF             # sp_machines
N = 4
ENTRY = 20
