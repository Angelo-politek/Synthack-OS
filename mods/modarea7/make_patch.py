"""Genera mods/modarea7/patch.json: sezione 7 compressa e area dei motori delle machine (vedi stub.S).

    python mods/modarea7/make_patch.py         # richiede binutils m68k in WSL (CONTRIBUTING.md)

Le machine che usano l'area motori dichiarano "requires": ["modarea7"], collegano il loro codice per la
CPU #2 a ENGINE_RAM + offset e lo mettono in una patch accodata alla sezione 7 a ENGINE_IMG + offset.
build.py comprime allora tutta la sezione 7 (stock + patch) e l'area motori dietro allo stub.
"""

from __future__ import annotations

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
import engine_layout as E  # noqa: E402

WSL_BINUTILS = "~/tools/m68k/root"


def wsl(cmd: str) -> str:
    r = subprocess.run(["wsl.exe", "-e", "bash", "-lc", cmd], capture_output=True, text=True)
    if r.returncode:
        raise SystemExit(f"comando WSL fallito:\n{cmd}\n{r.stderr}")
    return r.stdout


def main() -> None:
    stock = REPO / "firmware" / "Syntakt_OS1.42.syx"
    sec7 = eft.unpack(stock, REPO / "unpacked" / stock.stem, ids=[7])[7].read_bytes()
    if E.LOAD + len(sec7) != E.IMG or struct.unpack_from(">I", sec7)[0] != E.ENTRY:
        raise SystemExit("la sezione 7 stock non ha la lunghezza o l'entry attesi")
    with tempfile.TemporaryDirectory(prefix="modarea7-") as tmp:
        tmp = Path(tmp)
        shutil.copy(HERE / "stub.S", tmp / "stub.S")
        w = eft.to_wsl_path(tmp)
        bu = f"R={WSL_BINUTILS}; export LD_LIBRARY_PATH=$R/usr/lib/x86_64-linux-gnu; cd {w}; "
        wsl(bu + "$R/usr/bin/m68k-linux-gnu-as -mcpu=54418 stub.S -o s.o")
        wsl(bu + f"$R/usr/bin/m68k-linux-gnu-ld -N -Ttext={E.LOAD:#x} -o s.elf s.o")
        wsl(bu + "$R/usr/bin/m68k-linux-gnu-objcopy -O binary -j .text s.elf s.bin")
        syms = {}
        for line in wsl(bu + "$R/usr/bin/m68k-linux-gnu-nm s.elf").splitlines():
            parts = line.split()
            if len(parts) == 3:
                syms[parts[2]] = int(parts[0], 16)
        blob = (tmp / "s.bin").read_bytes()
    if syms["stream"] - E.LOAD != len(blob) or syms["hdr_total"] != syms["stream"] - 16:
        raise SystemExit("disposizione dello stub inattesa")
    spec = {
        "name": "modarea7", "os": "1.42",
        "description": "Sezione 7 (CPU #2) compressa: uno stub la decomprime all'avvio prima dell'entry originale, "
                       f"insieme all'area dei motori delle machine ({E.RAM:#x}, {E.SIZE:#x} B). Spazio per i motori: "
                       "~125 KB compressi invece di 9 KB.",
        "generated_by": "mods/modarea7/make_patch.py",
        "layout7": {"stub": blob.hex(), "hdr": f"{syms['hdr_total'] - E.LOAD:#x}", "entry": f"{E.ENTRY:#010x}",
                    "img": f"{E.IMG:#010x}", "ram": f"{E.RAM:#010x}", "size": f"{E.SIZE:#x}",
                    "max": f"{E.MAX:#x}", "compress": "shlz"},
        "patches": [],
    }
    (HERE / "patch.json").write_text(json.dumps(spec, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"patch.json: stub {len(blob)} B; area motori {E.RAM:#x}..{E.RAM + E.SIZE:#x}")


if __name__ == "__main__":
    main()
