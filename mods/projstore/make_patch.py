"""Genera mods/projstore/patch.json (vedi projstore.S).

    python mods/projstore/make_patch.py        # richiede binutils m68k in WSL (CONTRIBUTING.md)
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools" / "build"))
import modkit  # noqa: E402
import projstore_layout as L  # noqa: E402


def main() -> None:
    assert L.SIZE % 4 == 0 and L.SIZE <= 0x400 - 0x22C and max(o + n for o, n in L.PARTS.values()) <= L.SIZE
    m = modkit.Mod(__file__)
    code = m.compile(["projstore.S"], defs={"PS_SIZE": L.SIZE, "ps_data": L.DATA})     # codice: poi kitstore
    m.area(code, "projstore.S")
    m.hook(0x400A_9134, "4feffff448d70c04", code["ps_wr"], "impostazioni del progetto -> file: jmp ps_wr ; nop")
    m.hook(0x400A_84F0, "4feffff048d70c0c", code["ps_rd"], "file -> impostazioni del progetto: jmp ps_rd ; nop")
    m.write(description=f"Memoria delle mod salvata con il progetto: {L.SIZE} byte a ps_data (RAM), nell'area riservata "
                        "delle impostazioni del progetto nel file.",
            requires=["modarea"], layout={"data": f"{code['ps_data']:#010x}", "size": L.SIZE},
            symbols={k: code[k] for k in ("ps_wr", "ps_rd", "ps_data")})


if __name__ == "__main__":
    main()
