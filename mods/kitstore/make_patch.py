"""Genera mods/kitstore/patch.json (vedi kitstore.S).

    python mods/kitstore/make_patch.py         # richiede binutils m68k in WSL (CONTRIBUTING.md)
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

LOAD = 0x4000_0400
OFFSET = 0x7200                         # nell'area mod, dopo projstore
CODE_BASE = modarea_layout.RAM + OFFSET
CODE_END = modarea_layout.RAM + 0x7400
HOOKS = [(0x400A_6EE6, "2f0b2f0a246f000c", "ks_wr", "blocco per traccia del kit -> file: jmp ks_wr ; nop"),
         (0x400A_6E7A, "4feffff448d71c00", "ks_rd", "file -> blocco per traccia del kit: jmp ks_rd ; nop")]
WSL_BINUTILS = "~/tools/m68k/root"


def sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def wsl(cmd: str) -> str:
    r = subprocess.run(["wsl.exe", "-e", "bash", "-lc", cmd], capture_output=True, text=True)
    if r.returncode:
        raise SystemExit(f"comando WSL fallito:\n{cmd}\n{r.stderr}")
    return r.stdout


def main() -> None:
    stock = REPO / "firmware" / "Syntakt_OS1.42.syx"
    sec3 = eft.unpack(stock, REPO / "unpacked" / stock.stem, ids=[3])[3].read_bytes()
    with tempfile.TemporaryDirectory(prefix="kitstore-") as tmp:
        tmp = Path(tmp)
        shutil.copy(HERE / "kitstore.S", tmp / "kitstore.S")
        w = eft.to_wsl_path(tmp)
        bu = f"R={WSL_BINUTILS}; export LD_LIBRARY_PATH=$R/usr/lib/x86_64-linux-gnu; cd {w}; "
        wsl(bu + f"$R/usr/bin/m68k-linux-gnu-as -mcpu=54418 kitstore.S -o p.o")
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
    patches = [{"section": 3, "addr": f"{modarea_layout.IMG + OFFSET:#010X}", "len": len(blob), "append": True,
                "hex": blob.hex(), "ram": f"{CODE_BASE:#010x}", "what": "(area mod) kitstore.S"}]
    for addr, orig, sym, what in HOOKS:
        old = sec3[addr - LOAD:addr - LOAD + 8]
        if old.hex() != orig:
            raise SystemExit(f"{addr:#x}: byte inattesi {old.hex()}")
        patches.append({"section": 3, "addr": f"{addr:#010X}", "len": 8, "expect_sha256": sha(old),
                        "hex": struct.pack(">HIH", 0x4EF9, syms[sym], 0x4E71).hex(), "what": what})
    spec = {
        "name": "kitstore", "os": "1.42", "requires": ["modarea"],
        "description": "Parole delle mod salvate con il kit: parole 41..43 dei 12 blocchi per traccia (dati MIDI "
                       "della Digitakt), nei byte riservati +150..+155 del blocco nel file.",
        "generated_by": "mods/kitstore/make_patch.py",
        "symbols": {k: f"{syms[k]:#010x}" for k in ("ks_wr", "ks_rd")},
        "patches": patches,
    }
    (HERE / "patch.json").write_text(json.dumps(spec, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"patch.json: {len(blob)} B a {CODE_BASE:#x}")


if __name__ == "__main__":
    main()
