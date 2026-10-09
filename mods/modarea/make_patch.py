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
import eft  # noqa: E402

LOAD = 0x4000_0400
CODE_BASE = 0x4033_8D74                 # spazio libero dell'immagine (dopo dual-mono)
FREE_END = 0x4033_9000
HOOK = 0x4000_04B2
HOOK_ORIG = "4feffff048d700f0"          # lea -16(sp),sp ; movem.l d4-d7,(sp)
IMG, RAM, SIZE = 0x4034_8000, 0x4600_0000, 0x10000
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
    if LOAD + len(sec3) > IMG:
        raise SystemExit("l'immagine stock arriva oltre IMG")
    with tempfile.TemporaryDirectory(prefix="modarea-") as tmp:
        tmp = Path(tmp)
        shutil.copy(HERE / "modarea.S", tmp / "modarea.S")
        w = eft.to_wsl_path(tmp)
        bu = f"R={WSL_BINUTILS}; export LD_LIBRARY_PATH=$R/usr/lib/x86_64-linux-gnu; cd {w}; "
        wsl(bu + "$R/usr/bin/m68k-linux-gnu-as -mcpu=54418 modarea.S -o m.o")
        wsl(bu + f"$R/usr/bin/m68k-linux-gnu-ld -N -Ttext={CODE_BASE:#x} -o m.elf m.o")
        wsl(bu + "$R/usr/bin/m68k-linux-gnu-objcopy -O binary m.elf m.bin")
        blob = (tmp / "m.bin").read_bytes()
    end = CODE_BASE + len(blob)
    if end > FREE_END or any(sec3[CODE_BASE - LOAD:end - LOAD]):
        raise SystemExit("spazio libero insufficiente o non a zero")
    if sec3[HOOK - LOAD:HOOK - LOAD + 8].hex() != HOOK_ORIG:
        raise SystemExit("i byte del punto d'aggancio non sono quelli attesi")
    jmp = struct.pack(">HIH", 0x4EF9, CODE_BASE, 0x4E71)      # jmp modarea_reloc.l ; nop
    spec = {
        "name": "modarea", "os": "1.41",
        "description": f"Area mod: all'avvio decomprime (SHLZ) le mod accodate alla sezione 3 ({IMG:#x}) "
                       f"in RAM a {RAM:#x} ({SIZE // 1024} KB, resto azzerato), prima dell'azzeramento del BSS.",
        "generated_by": "mods/modarea/make_patch.py",
        "layout": {"img": f"{IMG:#010x}", "ram": f"{RAM:#010x}", "size": f"{SIZE:#x}", "compress": "shlz"},
        "patches": [
            {"section": 3, "addr": f"{CODE_BASE:#010X}", "len": len(blob),
             "expect_sha256": sha(sec3[CODE_BASE - LOAD:end - LOAD]), "hex": blob.hex(),
             "what": "modarea_reloc: decomprime IMG -> RAM, azzera il resto, istruzioni sostituite, jmp 0x400004BA"},
            {"section": 3, "addr": f"{HOOK:#010X}", "len": 8,
             "expect_sha256": sha(sec3[HOOK - LOAD:HOOK - LOAD + 8]), "hex": jmp.hex(),
             "what": "inizio dell'azzeramento del BSS: jmp modarea_reloc ; nop"},
        ],
    }
    (HERE / "patch.json").write_text(json.dumps(spec, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"patch.json: rilocatore {len(blob)} B a {CODE_BASE:#x}; aggancio {jmp.hex()} a {HOOK:#x}")


if __name__ == "__main__":
    main()
