"""Posto di xparams nell'area mod (mods/xparams), condiviso dalle mod che lo usano (OS 1.42).

All'inizio del blob di xparams la sua tabella (xparams.h, xp_table_t): una machine vi registra dalla lista di
avvio cosa scrivere negli indici 0x36..0x3d di un suono salvato da un OS stock (xp_on_empty).
"""

import modarea_layout as M

OFF = 0x6700                    # xparams nell'area mod (registry.py)
TABLE = M.RAM + OFF             # xp_table
