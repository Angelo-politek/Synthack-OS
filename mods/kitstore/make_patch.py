"""Genera mods/kitstore/patch.json (vedi kitstore.S).

    python mods/kitstore/make_patch.py         # richiede binutils m68k in WSL (CONTRIBUTING.md)
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools" / "build"))
import modkit  # noqa: E402


def main() -> None:
    m = modkit.Mod(__file__)
    code = m.compile(["kitstore.S"])                 # nell'area mod, dopo projstore (registro)
    m.area(code, "kitstore.S")
    m.hook(0x400A_6EE6, "2f0b2f0a246f000c", code["ks_wr"], "blocco per traccia del kit -> file: jmp ks_wr ; nop")
    m.hook(0x400A_6E7A, "4feffff448d71c00", code["ks_rd"], "file -> blocco per traccia del kit: jmp ks_rd ; nop")
    m.write(description="Parole delle mod salvate con il kit: parole 41..43 dei 12 blocchi per traccia (dati MIDI "
                        "della Digitakt), nei byte riservati +150..+155 del blocco nel file.",
            requires=["modarea"], symbols={k: code[k] for k in ("ks_wr", "ks_rd")})


if __name__ == "__main__":
    main()
