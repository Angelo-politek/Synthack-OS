"""Genera mods/projstore/patch.json (vedi projstore.S).

    python mods/projstore/make_patch.py         # richiede binutils m68k in WSL (CONTRIBUTING.md)
"""

from __future__ import annotations

import hashlib
import json
import shutil
import struct
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path[:0] = [str(REPO / "tools" / "unpack"), str(REPO / "tools" / "build")]
import eft  # noqa: E402
import modarea_layout  # noqa: E402
import registry  # noqa: E402
import projstore_layout as L  # noqa: E402

LOAD = 0x4000_0400
CODE_BASE = modarea_layout.RAM + L.OFFSET
CODE_END = modarea_layout.RAM + next(e for a, e, who, _ in registry.MODAREA if who == "projstore")   # poi kitstore
HOOKS = [(0x400A_90BC, "4feffff448d70c04", "ps_wr", "impostazioni del progetto -> file: jmp ps_wr ; nop"),
         (0x400A_8478, "4feffff048d70c0c", "ps_rd", "file -> impostazioni del progetto: jmp ps_rd ; nop")]
WSL_BINUTILS = "~/tools/m68k/root"


def sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def wsl(cmd: str) -> str:
    r = subprocess.run(["wsl.exe", "-e", "bash", "-lc", cmd], capture_output=True, text=True)
    if r.returncode:
        raise SystemExit(f"comando WSL fallito:\n{cmd}\n{r.stderr}")
    return r.stdout


def main() -> None:
    stock = REPO / "firmware" / "Syntakt_OS1.41.syx"
    sec3 = eft.unpack(stock, REPO / "unpacked" / stock.stem, ids=[3])[3].read_bytes()
    with tempfile.TemporaryDirectory(prefix="projstore-") as tmp:
        tmp = Path(tmp)
        shutil.copy(HERE / "projstore.S", tmp / "projstore.S")
        w = eft.to_wsl_path(tmp)
        bu = f"R={WSL_BINUTILS}; export LD_LIBRARY_PATH=$R/usr/lib/x86_64-linux-gnu; cd {w}; "
        wsl(bu + f"$R/usr/bin/m68k-linux-gnu-as -mcpu=54418 --defsym PS_SIZE={L.SIZE} projstore.S -o p.o")
        wsl(bu + f"$R/usr/bin/m68k-linux-gnu-ld -N -Ttext={CODE_BASE:#x} -o p.elf p.o")
        wsl(bu + "$R/usr/bin/m68k-linux-gnu-objcopy -O binary -j .text -j .data p.elf p.bin")
        syms = {}
        for line in wsl(bu + "$R/usr/bin/m68k-linux-gnu-nm p.elf").splitlines():
            parts = line.split()
            if len(parts) == 3:
                syms[parts[2]] = int(parts[0], 16)
        blob = (tmp / "p.bin").read_bytes()
    if CODE_BASE + len(blob) > CODE_END:
        raise SystemExit(f"non ci sta: {len(blob)} B")
    patches = [{"section": 3, "addr": f"{modarea_layout.IMG + L.OFFSET:#010X}", "len": len(blob), "append": True,
                "hex": blob.hex(), "ram": f"{CODE_BASE:#010x}", "what": "(area mod) projstore.S"}]
    for addr, orig, sym, what in HOOKS:
        old = sec3[addr - LOAD:addr - LOAD + 8]
        if old.hex() != orig:
            raise SystemExit(f"{addr:#x}: byte inattesi {old.hex()}")
        patches.append({"section": 3, "addr": f"{addr:#010X}", "len": 8, "expect_sha256": sha(old),
                        "hex": struct.pack(">HIH", 0x4EF9, syms[sym], 0x4E71).hex(), "what": what})
    spec = {
        "name": "projstore", "os": "1.41", "requires": ["modarea"],
        "description": f"Memoria delle mod salvata con il progetto: {L.SIZE} byte a ps_data, nell'area riservata "
                       "delle impostazioni del progetto nel file.",
        "generated_by": "mods/projstore/make_patch.py",
        "layout": {"data": f"{syms['ps_data']:#010x}", "size": L.SIZE},
        "symbols": {k: f"{syms[k]:#010x}" for k in ("ps_wr", "ps_rd", "ps_data")},
        "patches": patches,
    }
    (HERE / "patch.json").write_text(json.dumps(spec, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"patch.json: {len(blob)} B a {CODE_BASE:#x}; dati a {syms['ps_data']:#x}")


if __name__ == "__main__":
    main()
