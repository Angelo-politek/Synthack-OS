"""Genera mods/cpu-meter/patch.json (vedi cpumeter.c).

    python mods/cpu-meter/make_patch.py       # richiede gcc m68k in WSL (CONTRIBUTING.md)
"""

import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools" / "build"))
import modkit  # noqa: E402


def main() -> None:
    m = modkit.Mod(__file__)
    code = m.compile(["cpumeter.c"], entry="cm_draw")
    m.area(code, "cpumeter.c")
    # link.w %fp,#-164 ; movem.l %d0-%a5,(%sp)
    m.hook(0x400A_38CE, "4e56ff5c48d73fff", code["cm_entry"], "ingresso dell'interrupt audio")
    # movem.l -164(%fp),%d0-%a5
    m.hook(0x400A_5518, "4cee3fffff5c", code["cm_exit"], "uscita dell'interrupt audio")
    # ParameterPageView: draw
    m.replace(0x401C_84AC, "40032692", struct.pack(">I", code["cm_draw"]), "disegno della vista dei parametri")
    m.write(description="Diagnostica: carico dell'interrupt audio misurato con DTIM0 (media e massimo, percento del "
                        "blocco) in alto a destra sulle pagine dei parametri.",
            requires=["modarea"], symbols={k: v for k, v in sorted(code.items()) if k.startswith("cm_")})


if __name__ == "__main__":
    main()
