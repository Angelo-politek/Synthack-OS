"""Genera mods/poly/patch.json: POLY di Synfact (poly-st 1.0) sopra sfcore, OS 1.42 (README.md).

    python mods/poly/make_patch.py          # richiede gcc m68k in WSL (CONTRIBUTING.md)

I sorgenti stanno in synfact/ come in Synfact (mods/poly-st, commit in ORIGIN), con gli indirizzi tradotti da
tools/build/port_source.py e poche modifiche locali segnate "SyntHack:". Nessun sito proprio: tutto passa da sfcore
(transazioni native, render_in, pagine e contesti di vista). Il modulo va nel posto della tabella di sfcore.

SPDX-License-Identifier: GPL-2.0-or-later
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

OFFSET, END = next((a, b) for a, b, who, _ in registry.MODAREA if who == "poly")
CODE_BASE = modarea_layout.RAM + OFFSET
SLOT = next(s for s, who in registry.SFCORE_SLOTS.items() if who == "poly")
TOOLS = "~/tools/m68k/root"
# -Os come gli altri port (Synfact: -O3); -fno-strict-aliasing: il codice legge record nativi con tipi diversi
CFLAGS = ("-mcpu=54418 -Os -ffreestanding -fno-builtin -nostdlib -fno-pic -fno-common -fno-jump-tables "
          "-fno-strict-aliasing -fno-tree-loop-distribute-patterns -Iinclude -Isynfact -Wall -Wno-unused-function -Wno-misleading-indentation")
SOURCES = sorted(p.name for p in (HERE / "synfact").iterdir())
USES = ["sfcore:native", "sfcore:pages", "sfcore:render_in"]


def sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def wsl(cmd: str) -> str:
    r = subprocess.run(["wsl.exe", "-e", "bash", "-lc", cmd], capture_output=True, text=True)
    if r.returncode:
        raise SystemExit(f"comando WSL fallito:\n{cmd}\n{r.stdout}{r.stderr}")
    return r.stdout + r.stderr


def build_blob():
    with tempfile.TemporaryDirectory(prefix="poly-") as tmp:
        tmp = Path(tmp)
        shutil.copytree(REPO / "mods" / "sfcore" / "include", tmp / "include")
        shutil.copytree(HERE / "synfact", tmp / "synfact")
        shutil.copy(HERE / "glue.c", tmp / "glue.c")
        w = eft.to_wsl_path(tmp)
        env = f"R={TOOLS}; export LD_LIBRARY_PATH=$R/usr/lib/x86_64-linux-gnu; cd {w}; "
        gcc = "$R/usr/bin/m68k-linux-gnu-gcc-13 -B$R/usr/libexec/gcc/m68k-linux-gnu/13/ -B$R/usr/bin/m68k-linux-gnu-"
        warn = wsl(env + f"{gcc} {CFLAGS} -c synfact/main.c -o c.o")
        warn += wsl(env + f"{gcc} {CFLAGS} -c glue.c -o g.o")
        if "warning" in warn:
            raise SystemExit(warn)
        for s in ("native", "publication"):
            wsl(env + f"$R/usr/bin/m68k-linux-gnu-as -mcpu=54418 synfact/{s}.s -o {s}.o")
        wsl(env + f"$R/usr/bin/m68k-linux-gnu-ld -N -Ttext={CODE_BASE:#x} -e poly_module -o p.elf c.o g.o "
                  "native.o publication.o")
        undef = wsl(env + "$R/usr/bin/m68k-linux-gnu-nm -u p.elf").strip()
        if undef:
            raise SystemExit(f"simboli esterni non permessi (libgcc?): {undef}")
        wsl(env + "$R/usr/bin/m68k-linux-gnu-objcopy -O binary -j .text -j .rodata -j .data p.elf p.bin")
        syms = {}
        for line in wsl(env + "$R/usr/bin/m68k-linux-gnu-nm p.elf").splitlines():
            parts = line.split()
            if len(parts) == 3:
                syms[parts[2]] = int(parts[0], 16)
        return (tmp / "p.bin").read_bytes(), syms


def main() -> None:
    blob, syms = build_blob()
    end = max(syms.get("_end", 0), CODE_BASE + len(blob))
    if end > modarea_layout.RAM + END:
        raise SystemExit(f"non ci sta: fine a {end:#x}, spazio fino a {modarea_layout.RAM + END:#x}")
    table = registry.SFCORE_TABLE + 4 * SLOT
    patches = [{"section": 3, "addr": f"{modarea_layout.IMG + OFFSET:#010X}", "len": len(blob), "append": True,
                "hex": blob.hex(), "ram": f"{CODE_BASE:#010x}", "what": "(area mod) POLY: gruppi, voci, pagina TRIG 3"},
               {"section": 3, "addr": f"{modarea_layout.IMG + table:#010X}", "len": 4, "append": True,
                "hex": struct.pack(">I", syms["poly_module"]).hex(),
                "ram": f"{modarea_layout.RAM + table:#010x}", "what": f"tabella dei moduli di sfcore, posto {SLOT}"}]
    spec = {
        "name": "poly", "os": "1.42", "requires": ["modarea", "sfcore", "idspace"], "uses": USES,
        "description": "POLY di Synfact: gruppi di 2-4 tracce digitali suonate come voci di una (pagina TRIG 3), "
                       "topologia salvata nel pattern (PatternSettings 0x21..0x27).",
        "license": "GPL-2.0-or-later", "credits": "Synfact (GSM1980), elekloader (irpina)",
        "generated_by": "mods/poly/make_patch.py",
        "sources_sha256": {f"synfact/{n}": sha((HERE / "synfact" / n).read_bytes().replace(b"\r\n", b"\n"))
                           for n in SOURCES},
        "symbols": {k: f"{v:#010x}" for k, v in sorted(syms.items()) if k.startswith(("poly_", "native_"))
                    and v >= CODE_BASE},
        "patches": patches,
    }
    (HERE / "patch.json").write_text(json.dumps(spec, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"patch.json: {len(blob)} B a {CODE_BASE:#x}, fine con .bss {end:#x}")


if __name__ == "__main__":
    main()
