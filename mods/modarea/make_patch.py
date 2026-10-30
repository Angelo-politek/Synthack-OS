"""Genera mods/modarea/patch.json: rilocatore dell'area mod (vedi modarea.S).

    python mods/modarea/make_patch.py         # richiede binutils m68k in WSL (CONTRIBUTING.md)

Le mod che usano l'area mod dichiarano "requires": ["modarea"], si collegano a RAM + offset e
mettono il loro codice in una patch accodata ("append") a IMG + offset.
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
sys.path.insert(0, str(REPO / "tools" / "unpack"))
sys.path.insert(0, str(REPO / "tools" / "build"))
import eft  # noqa: E402
import modarea_layout as L  # noqa: E402

LOAD = 0x4000_0400
CODE_BASE = 0x4033_9D80                 # spazio libero dell'immagine (dopo dual-mono, con margine)
FREE_END = 0x4033_A000
HOOKS = [  # (indirizzo, byte originali, simbolo, codice operativo, descrizione)
    (0x4000_04B2, "4feffff048d700f0", "modarea_load", 0x4EF9,
     "azzeramento del BSS: jmp modarea_load ; nop (decompressione, BSS a zero tranne l'area)"),
    (0x4010_3752, "700123c0402d5324", "modarea_reserve", 0x4EB9,
     "fine dell'inizializzazione dell'heap: jsr modarea_reserve ; nop (prima allocazione = area mod)"),
]
IMG, RAM, SIZE = L.IMG, L.RAM, L.SIZE
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
    if LOAD + len(sec3) > IMG:
        raise SystemExit("l'immagine stock arriva oltre IMG")
    defs = {"IMG": IMG, "RAM": RAM, "SIZE": SIZE, "HEAP_BLOCK_SIZE": L.HEAP_BLOCK_SIZE}
    with tempfile.TemporaryDirectory(prefix="modarea-") as tmp:
        tmp = Path(tmp)
        shutil.copy(HERE / "modarea.S", tmp / "modarea.S")
        w = eft.to_wsl_path(tmp)
        bu = f"R={WSL_BINUTILS}; export LD_LIBRARY_PATH=$R/usr/lib/x86_64-linux-gnu; cd {w}; "
        sym = " ".join(f"--defsym {k}={v}" for k, v in defs.items())
        wsl(bu + f"$R/usr/bin/m68k-linux-gnu-as -mcpu=54418 {sym} modarea.S -o m.o")
        wsl(bu + f"$R/usr/bin/m68k-linux-gnu-ld -N -Ttext={CODE_BASE:#x} -o m.elf m.o")
        wsl(bu + "$R/usr/bin/m68k-linux-gnu-objcopy -O binary -j .text -j .data m.elf m.bin")
        syms = {}
        for line in wsl(bu + "$R/usr/bin/m68k-linux-gnu-nm m.elf").splitlines():
            parts = line.split()
            if len(parts) == 3:
                syms[parts[2]] = int(parts[0], 16)
        blob = (tmp / "m.bin").read_bytes()
    end = CODE_BASE + len(blob)
    if end > FREE_END or any(sec3[CODE_BASE - LOAD:end - LOAD]):
        raise SystemExit("spazio libero insufficiente o non a zero")
    if (RAM - 0x4033_A000) % 16 or (0x4556_6490 - RAM - SIZE) % 16:
        raise SystemExit("l'area deve dividere il BSS in tratti multipli di 16 byte")
    patches = [{"section": 3, "addr": f"{CODE_BASE:#010X}", "len": len(blob),
                "expect_sha256": sha(sec3[CODE_BASE - LOAD:end - LOAD]), "hex": blob.hex(),
                "what": "modarea.S: modarea_load (decompressione, BSS), modarea_reserve (heap)"}]
    for addr, orig, sym_, op, what in HOOKS:
        old = sec3[addr - LOAD:addr - LOAD + 8]
        if old.hex() != orig:
            raise SystemExit(f"{addr:#x}: byte inattesi {old.hex()}")
        new = struct.pack(">HIH", op, syms[sym_], 0x4E71)
        patches.append({"section": 3, "addr": f"{addr:#010X}", "len": 8, "expect_sha256": sha(old),
                        "hex": new.hex(), "what": what})
    spec = {
        "name": "modarea", "os": "1.42",
        "description": f"Area mod: all'avvio decomprime (SHLZ) le mod accodate alla sezione 3 ({IMG:#x}) "
                       f"nel primo blocco dell'heap dell'OS ({RAM:#x}, {SIZE} B, resto azzerato), "
                       "che prenota alla prima allocazione.",
        "generated_by": "mods/modarea/make_patch.py",
        "layout": {"img": f"{IMG:#010x}", "ram": f"{RAM:#010x}", "size": f"{SIZE:#x}", "compress": "shlz",
                   "heap_block": f"{L.HEAP_BLOCK:#010x}"},
        "symbols": {k: f"{syms[k]:#010x}" for k in ("modarea_load", "modarea_reserve", "modarea_block")},
        "patches": patches,
    }
    (HERE / "patch.json").write_text(json.dumps(spec, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"patch.json: {len(blob)} B a {CODE_BASE:#x}; area {RAM:#x}..{RAM + SIZE:#x}")


if __name__ == "__main__":
    main()
