"""Genera mods/arp/patch.json: l'arpeggiatore di Synfact (arp-st) sopra sfcore, OS 1.42 (README.md).

    python mods/arp/make_patch.py          # richiede gcc m68k in WSL (CONTRIBUTING.md)

Sorgenti di Synfact in synfact/ (indirizzi tradotti con tools/build/port_source.py, modifiche in ORIGIN). Il modulo
va nel suo posto della tabella di sfcore. Le impostazioni per traccia stanno nella parte "arp" di projstore; i lock
MODE/SPEED/RANGE/LEN sono un lock nativo impacchettato sull'indice logico 0x46 (xparams lo salva come corsia 0x60).

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
import projstore_layout  # noqa: E402
import registry  # noqa: E402

OFFSET, END = next((a, b) for a, b, who, w in registry.MODAREA if who == "arp" and "BSS" not in w)
CODE_BASE = modarea_layout.RAM + OFFSET
BSS_OFF, BSS_END = next((a, b) for a, b, who, w in registry.MODAREA if who == "arp" and "BSS" in w)
BSS_BASE = modarea_layout.RAM + BSS_OFF            # BSS nella meta' dell'area solo RAM (azzerata dal caricatore)
SLOT = next(s for s, who in registry.SFCORE_SLOTS.items() if who == "arp")
PS_ARP = projstore_layout.DATA + projstore_layout.PARTS["arp"][0]
TOOLS = "~/tools/m68k/root"
CFLAGS = (f"-DPS_ARP={PS_ARP:#x}u -mcpu=54418 -Os -ffreestanding -fno-builtin -nostdlib -fno-pic -fno-common "
          "-fno-jump-tables -fno-strict-aliasing -fno-tree-loop-distribute-patterns -Iinclude -Isynfact "
          "-Wall -Wno-unused-function -Wno-misleading-indentation -Wno-missing-braces")
C_SOURCES = ["synfact/module.c", "synfact/selector.c", "synfact/clock.c", "synfact/input.c", "synfact/keyboard.c",
             "synfact/length.c", "synfact/runtime.c", "synfact/ui.c", "glue.c"]
USES = ["sfcore:native", "sfcore:pages", "sfcore:render_in"]


def sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def wsl(cmd: str) -> str:
    r = subprocess.run(["wsl.exe", "-e", "bash", "-lc", cmd], capture_output=True, text=True)
    if r.returncode:
        raise SystemExit(f"comando WSL fallito:\n{cmd}\n{r.stdout}{r.stderr}")
    return r.stdout + r.stderr


def build_blob():
    with tempfile.TemporaryDirectory(prefix="arp-") as tmp:
        tmp = Path(tmp)
        shutil.copytree(REPO / "mods" / "sfcore" / "include", tmp / "include")
        shutil.copytree(HERE / "synfact", tmp / "synfact")
        shutil.copy(HERE / "glue.c", tmp / "glue.c")
        w = eft.to_wsl_path(tmp)
        env = f"R={TOOLS}; export LD_LIBRARY_PATH=$R/usr/lib/x86_64-linux-gnu; cd {w}; "
        gcc = "$R/usr/bin/m68k-linux-gnu-gcc-13 -B$R/usr/libexec/gcc/m68k-linux-gnu/13/ -B$R/usr/bin/m68k-linux-gnu-"
        objs, warn = [], ""
        for i, f in enumerate(C_SOURCES):
            warn += wsl(env + f"{gcc} {CFLAGS} -c {f} -o c{i}.o 2>&1")
            objs.append(f"c{i}.o")
        if "warning" in warn or "error" in warn:
            raise SystemExit(warn)
        wsl(env + f"$R/usr/bin/m68k-linux-gnu-ld -N -Ttext={CODE_BASE:#x} -Tbss={BSS_BASE:#x} -e arp_module "
                  f"-o a.elf {' '.join(objs)}")
        undef = wsl(env + "$R/usr/bin/m68k-linux-gnu-nm -u a.elf").strip()
        if undef:
            raise SystemExit(f"simboli esterni non permessi (libgcc?): {undef}")
        wsl(env + "$R/usr/bin/m68k-linux-gnu-objcopy -O binary -j .text -j .rodata -j .data a.elf a.bin")
        syms = {}
        for line in wsl(env + "$R/usr/bin/m68k-linux-gnu-nm a.elf").splitlines():
            parts = line.split()
            if len(parts) == 3:
                syms[parts[2]] = int(parts[0], 16)
        return (tmp / "a.bin").read_bytes(), syms


def main() -> None:
    blob, syms = build_blob()
    end = syms.get("_end", BSS_BASE)
    if CODE_BASE + len(blob) > modarea_layout.RAM + END or end > modarea_layout.RAM + BSS_END:
        raise SystemExit(f"non ci sta: codice {len(blob)} B, BSS fino a {end:#x}")
    table = registry.SFCORE_TABLE + 4 * SLOT
    patches = [{"section": 3, "addr": f"{modarea_layout.IMG + OFFSET:#010X}", "len": len(blob), "append": True,
                "hex": blob.hex(), "ram": f"{CODE_BASE:#010x}", "what": "(area mod) arpeggiatore e modulo sfcore"},
               {"section": 3, "addr": f"{modarea_layout.IMG + table:#010X}", "len": 4, "append": True,
                "hex": struct.pack(">I", syms["arp_module"]).hex(),
                "ram": f"{modarea_layout.RAM + table:#010x}", "what": f"tabella dei moduli di sfcore, posto {SLOT}"}]
    spec = {
        "name": "arp", "os": "1.42", "requires": ["modarea", "sfcore", "projstore", "xparams"], "uses": USES,
        "description": "Arpeggiatore di Synfact (arp-st): doppio TRIG apre la vista; MODE, SPEED, RANGE, LEN, "
                       "16 passi con OFS; impostazioni per traccia salvate con il progetto; p-lock su A..D.",
        "license": "GPL-2.0-or-later", "credits": "Synfact (GSM1980), elekloader (irpina)",
        "generated_by": "mods/arp/make_patch.py",
        "sources_sha256": {f"synfact/{n.name}": sha(n.read_bytes().replace(b"\r\n", b"\n"))
                           for n in sorted((HERE / "synfact").iterdir()) if n.suffix in (".c", ".h")},
        "symbols": {k: f"{v:#010x}" for k, v in sorted(syms.items()) if k.startswith(("arp_", "synfact_"))
                    and v >= CODE_BASE},
        "patches": patches,
    }
    (HERE / "patch.json").write_text(json.dumps(spec, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"patch.json: {len(blob)} B a {CODE_BASE:#x}, fine con .bss {end:#x}")


if __name__ == "__main__":
    main()
