"""Dual mono v2 (mods/dual-mono): intestazione condivisa con fx3, nell'area mod.

A RAM + OFFSET c'e' l'intestazione del codice C del dual mono: fx3 la legge per sapere in quale passata
del blocco delle mandate dell'ingresso si trova (1 = lato L, 2 = lato R) e se la pagina IN R e' aperta.
Senza dual-mono l'area e' a zero: niente magia, fx3 lavora come prima.

    +0  u32 MAGIC
    +4  u8  passata (0 = nessuna / stereo, 1 = IN L, 2 = IN R)
    +8  u32 funzione u32 (*)(void): 1 se la pagina IN R del tab MIXER e' aperta
"""

import kitstore_layout as KS
import modarea_layout

OFFSET = 0x5000
HDR = modarea_layout.RAM + OFFSET
MAGIC = 0x444D_5632                     # "DMV2"
END = modarea_layout.RAM + 0x7000       # poi projstore

# parole del kit (kitstore, blocco 0): mandate del lato R, 0..127
DEL_R, REV_R, FX3_R = (KS.word(0, k) for k in range(3))
