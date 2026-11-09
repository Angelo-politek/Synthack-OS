"""Genera mods/vparams/patch.json (vedi vparams.S).

    python mods/vparams/make_patch.py         # richiede binutils m68k in WSL (CONTRIBUTING.md)

Le mod registrano i loro parametri con una patch accodata a vparams.entry(slot, id, get, set).
"""

import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools" / "build"))
import modarea_layout  # noqa: E402

IMG, RAM = modarea_layout.IMG, modarea_layout.RAM     # area mod (mods/modarea)
CODE = RAM + 0x7E00                     # codice di vparams
VP_TABLE, VP_N = RAM + 0x8000, 32
HOOKS = [(0x4000_D870, "2f02747c222f0008", "vp_kit"),
         (0x4000_D94A, "2f02222f0008", "vp_get"),
         (0x4000_DA32, "2f032f02222f000c", "vp_set")]


def entry(slot: int, pid: int, get: int, put: int, what: str) -> dict:
    """Patch accodata che registra un parametro virtuale nel posto 'slot' della tabella."""
    if not 0 <= slot < VP_N or not 0 < pid < 569:              # 505..568: id delle mod (mods/idspace)
        raise ValueError((slot, pid))
    addr = VP_TABLE + 12 * slot
    return {"section": 3, "addr": f"{IMG + addr - RAM:#010X}", "len": 12, "append": True,
            "hex": struct.pack(">HHII", pid, 0, get, put).hex(), "ram": f"{addr:#010x}",
            "what": f"vparams[{slot}]: id {pid} -> {what}"}


def main() -> None:
    import modkit
    m = modkit.Mod(__file__)
    code = m.compile(["vparams.S"], base=CODE, end=VP_TABLE, defs={"VP_TABLE": VP_TABLE}, sections="")
    m.area(code, "vp_kit, vp_get, vp_set")
    for addr, orig, sym in HOOKS:
        m.hook(addr, orig, code[sym], f"aggancio: jmp {sym}" + (" ; nop" if len(orig) == 16 else ""))
    m.write(description="Parametri virtuali delle mod: agganci alle funzioni centrali dei parametri di kit "
                        "e tabella di registrazione in RAM.",
            requires=["modarea"], layout={"table": f"{VP_TABLE:#010x}", "entries": VP_N},
            symbols={k: code[k] for k in ("vp_kit", "vp_get", "vp_set", "vp_find")})


if __name__ == "__main__":
    main()
