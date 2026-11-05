"""Genera mods/modulation-skip/patch.json (port di modulation-skip-st di Synfact, README.md).

    python mods/modulation-skip/make_patch.py                     # richiede gcc m68k in WSL (CONTRIBUTING.md)
    python mods/modulation-skip/make_patch.py --verify out/mskip  # variante VERIFY (diagnostica, mai salti)

La variante VERIFY scrive una cartella con lo stesso nome di mod: build.py --stock ... out/mskip mods/cpu-meter.

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

LOAD = 0x4000_0400
OFFSET, END = next((a, b) for a, b, who, _ in registry.MODAREA if who == "modulation-skip")
CODE_BASE = modarea_layout.RAM + OFFSET
SLOT = next(s for s, who in registry.SFCORE_SLOTS.items() if who == "modulation-skip")
TOOLS = "~/tools/m68k/root"
CFLAGS = ("-mcpu=54418 -O2 -ffreestanding -fno-builtin -nostdlib -fno-pic -fno-common -fno-jump-tables "
          "-fno-tree-loop-distribute-patterns -Iinclude -Wall -Wextra")
NOP = b"\x4e\x71"
# (indirizzo 1.42, byte stock, simbolo, descrizione); Synfact: 1.41 0x40097B04 e 0x400A30C4
SITES = [
    (0x4009_7B7C, "246f0040260a", "modulation_skip_entry", "modulazione: corpo dopo il prologo (movea.l 64(sp),a2; move.l a2,d3)"),
    (0x400A_313C, "4feffff448d70c04", "modulation_skip_machine_entry", "scrittore dei dati machine: scritture contate"),
]
# SRAM usata (registro, SRAM): stato, tabelle, bitmap; destinazioni
SRAM = {"state": 0x8000_FC20, "tables": 0x8000_FC60, "map": 0x8000_FD20, "map_end": 0x8000_FD9F,
        "entries": 0x8000_7780, "entries_end": 0x8000_7EB7}


def sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def wsl(cmd: str) -> str:
    r = subprocess.run(["wsl.exe", "-e", "bash", "-lc", cmd], capture_output=True, text=True)
    if r.returncode:
        raise SystemExit(f"comando WSL fallito:\n{cmd}\n{r.stdout}{r.stderr}")
    return r.stdout + r.stderr


def build_blob(verify: bool):
    with tempfile.TemporaryDirectory(prefix="mskip-") as tmp:
        tmp = Path(tmp)
        shutil.copytree(REPO / "mods" / "sfcore" / "include", tmp / "include")
        shutil.copy(HERE / "mskip.c", tmp / "mskip.c")
        w = eft.to_wsl_path(tmp)
        env = f"R={TOOLS}; export LD_LIBRARY_PATH=$R/usr/lib/x86_64-linux-gnu; cd {w}; "
        gcc = "$R/usr/bin/m68k-linux-gnu-gcc-13 -B$R/usr/libexec/gcc/m68k-linux-gnu/13/ -B$R/usr/bin/m68k-linux-gnu-"
        warn = wsl(env + f"{gcc} {CFLAGS} -DMODULATION_SKIP_VERIFY={int(verify)} -c mskip.c -o m.o")
        if "warning" in warn:
            raise SystemExit(warn)
        wsl(env + f"$R/usr/bin/m68k-linux-gnu-ld -N -Ttext={CODE_BASE:#x} -e modulation_skip_entry -o m.elf m.o")
        undef = wsl(env + "$R/usr/bin/m68k-linux-gnu-nm -u m.elf").strip()
        if undef:
            raise SystemExit(f"simboli esterni non permessi (libgcc?): {undef}")
        wsl(env + "$R/usr/bin/m68k-linux-gnu-objcopy -O binary -j .text -j .rodata -j .data m.elf m.bin")
        syms = {}
        for line in wsl(env + "$R/usr/bin/m68k-linux-gnu-nm m.elf").splitlines():
            parts = line.split()
            if len(parts) == 3:
                syms[parts[2]] = int(parts[0], 16)
        return (tmp / "m.bin").read_bytes(), syms


def main(argv: list[str]) -> None:
    verify = "--verify" in argv
    out = Path(argv[argv.index("--verify") + 1]) if verify else HERE
    stock = REPO / "firmware" / "Syntakt_OS1.42.syx"
    sec3 = eft.unpack(stock, REPO / "unpacked" / stock.stem, ids=[3])[3].read_bytes()
    blob, syms = build_blob(verify)
    end = max(syms.get("_end", 0), CODE_BASE + len(blob))
    if end > modarea_layout.RAM + END:
        raise SystemExit(f"non ci sta: fine a {end:#x}, spazio fino a {modarea_layout.RAM + END:#x}")
    table = registry.SFCORE_TABLE + 4 * SLOT
    patches = [{"section": 3, "addr": f"{modarea_layout.IMG + OFFSET:#010X}", "len": len(blob), "append": True,
                "hex": blob.hex(), "ram": f"{CODE_BASE:#010x}", "what": "(area mod) decisione, trampolini, modulo sfcore"},
               {"section": 3, "addr": f"{modarea_layout.IMG + table:#010X}", "len": 4, "append": True,
                "hex": struct.pack(">I", syms["modulation_skip_module"]).hex(),
                "ram": f"{modarea_layout.RAM + table:#010x}", "what": f"tabella dei moduli di sfcore, posto {SLOT}"}]
    for addr, orig, sym, what in SITES:
        n = len(orig) // 2
        old = sec3[addr - LOAD:addr - LOAD + n]
        if old.hex() != orig:
            raise SystemExit(f"{addr:#x}: byte inattesi {old.hex()}")
        new = struct.pack(">HI", 0x4EF9, syms[sym]) + NOP * ((n - 6) // 2)
        patches.append({"section": 3, "addr": f"{addr:#010X}", "len": n, "expect_sha256": sha(old),
                        "hex": new.hex(), "what": what})
    spec = {
        "name": "modulation-skip", "os": "1.42", "requires": ["modarea", "sfcore"],
        "description": "Salta la modulazione stock (0x40097B74) nei blocchi in cui scriverebbe gli stessi valori: "
                       "port di modulation-skip-st di Synfact, dati caldi in SRAM." + (" VARIANTE VERIFY." if verify else ""),
        "license": "GPL-2.0-or-later", "credits": "Synfact (GSM1980), elekloader (irpina)",
        "generated_by": "mods/modulation-skip/make_patch.py" + (" --verify" if verify else ""),
        "symbols": {k: f"{v:#010x}" for k, v in sorted(syms.items()) if k.startswith("modulation_skip")},
        "sram": {k: f"{v:#010x}" for k, v in SRAM.items()},
        "patches": patches,
    }
    out.mkdir(parents=True, exist_ok=True)
    (out / "patch.json").write_text(json.dumps(spec, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"{out / 'patch.json'}: {len(blob)} B a {CODE_BASE:#x}, fine con .bss {end:#x}")


if __name__ == "__main__":
    main(sys.argv[1:])
