"""Genera mods/recorder/patch.json: il registratore di Synfact (recorder-st) sulla 1.42 (README.md).

    python mods/recorder/make_patch.py          # richiede gcc m68k in WSL (CONTRIBUTING.md)

Sorgenti di Synfact in synfact/ (indirizzi tradotti con tools/build/port_source.py, ORIGIN). Il modulo si iscrive a
sfcore (posto del registro); il salvataggio usa l'HZFS di long-samples (host API di sfcore) e, al posto del pool di
progetto di Synfact, la lista dei campioni lunghi con l'invio a caldo alla CPU #2 e la machine SAMPLER.

SPDX-License-Identifier: GPL-2.0-or-later
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
sys.path[:0] = [str(REPO / "tools" / "unpack"), str(REPO / "tools" / "build")]
import eft  # noqa: E402
import modarea_layout  # noqa: E402
import registry  # noqa: E402
import idspace_layout as IDS  # noqa: E402

OFFSET, END = next((a, b) for a, b, who, w in registry.MODAREA if who == "recorder" and "BSS" not in w)
CODE_BASE = modarea_layout.RAM + OFFSET
BSS_OFF, BSS_END = next((a, b) for a, b, who, w in registry.MODAREA if who == "recorder" and "BSS" in w)
BSS_BASE = modarea_layout.RAM + BSS_OFF            # BSS nella meta' dell'area solo RAM (azzerata dal caricatore)
SLOT = next(s for s, who in registry.SFCORE_SLOTS.items() if who == "recorder")
TOOLS = "~/tools/m68k/root"
CFLAGS = (f"-DIDS_TABLE={IDS.TABLE:#x}u " "-mcpu=54418 -Os -ffreestanding -fno-builtin -nostdlib -fno-pic -fno-common -fno-jump-tables "
          "-fno-tree-loop-distribute-patterns -Isynfact -Iinclude -Wall -Wextra -Wno-unused-parameter")
C_SOURCES = ["synfact/main.c", "glue.c"]
S_SOURCES = ["synfact/irq.s"]
# simboli di altre mod usati dal registratore: (mod, simbolo)
EXTERN = [("long-samples", "ls_refresh"), ("long-samples", "ls_file_index"), ("long-samples", "ls_pos"),
          ("long-samples", "ls_table"), ("sampler", "sm_long_samp")]


def wsl(cmd: str) -> str:
    r = subprocess.run(["wsl.exe", "-e", "bash", "-lc", cmd], capture_output=True, text=True)
    if r.returncode:
        raise SystemExit(f"comando WSL fallito:\n{cmd}\n{r.stdout}{r.stderr}")
    return r.stdout + r.stderr


def extern_syms() -> dict[str, int]:
    out = {}
    for mod, name in EXTERN:
        spec = json.loads((REPO / "mods" / mod / "patch.json").read_text(encoding="utf-8"))
        if name not in spec["symbols"]:
            raise SystemExit(f"{mod}: simbolo {name} non esportato")
        out[name] = int(spec["symbols"][name], 16)
    return out


def build_blob():
    ext = extern_syms()
    with tempfile.TemporaryDirectory(prefix="recorder-") as tmp:
        tmp = Path(tmp)
        shutil.copytree(REPO / "mods" / "sfcore" / "include", tmp / "include")
        shutil.copytree(HERE / "synfact", tmp / "synfact")
        shutil.copy(HERE / "glue.c", tmp / "glue.c")
        w = eft.to_wsl_path(tmp)
        env = f"R={TOOLS}; export LD_LIBRARY_PATH=$R/usr/lib/x86_64-linux-gnu; cd {w}; "
        gcc = "$R/usr/bin/m68k-linux-gnu-gcc-13 -B$R/usr/libexec/gcc/m68k-linux-gnu/13/ -B$R/usr/bin/m68k-linux-gnu-"
        objs = []
        for i, f in enumerate(C_SOURCES):
            warn = wsl(env + f"{gcc} {CFLAGS} -c {f} -o c{i}.o 2>&1")
            if "error" in warn:
                raise SystemExit(warn)
            objs.append(f"c{i}.o")
        for i, f in enumerate(S_SOURCES):
            wsl(env + f"$R/usr/bin/m68k-linux-gnu-as -mcpu=54418 {f} -o s{i}.o")
            objs.append(f"s{i}.o")
        defs = " ".join(f"--defsym={k}={v:#x}" for k, v in ext.items())
        wsl(env + f"$R/usr/bin/m68k-linux-gnu-ld -N -Ttext={CODE_BASE:#x} -Tbss={BSS_BASE:#x} -e recorder_module {defs} -o r.elf "
                  f"{' '.join(objs)}")
        undef = wsl(env + "$R/usr/bin/m68k-linux-gnu-nm -u r.elf").strip()
        if undef:
            raise SystemExit(f"simboli esterni non risolti: {undef}")
        wsl(env + "$R/usr/bin/m68k-linux-gnu-objcopy -O binary -j .text -j .rodata -j .data r.elf r.bin")
        syms = {}
        for line in wsl(env + "$R/usr/bin/m68k-linux-gnu-nm r.elf").splitlines():
            parts = line.split()
            if len(parts) == 3:
                syms[parts[2]] = int(parts[0], 16)
        return (tmp / "r.bin").read_bytes(), syms


def main() -> None:
    blob, syms = build_blob()
    end = syms.get("_end", BSS_BASE)
    if CODE_BASE + len(blob) > modarea_layout.RAM + END or end > modarea_layout.RAM + BSS_END:
        raise SystemExit(f"non ci sta: codice {len(blob)} B, BSS fino a {end:#x}")
    table = registry.SFCORE_TABLE + 4 * SLOT
    patches = [{"section": 3, "addr": f"{modarea_layout.IMG + OFFSET:#010X}", "len": len(blob), "append": True,
                "hex": blob.hex(), "ram": f"{CODE_BASE:#010x}", "what": "(area mod) registratore e modulo sfcore"},
               {"section": 3, "addr": f"{modarea_layout.IMG + table:#010X}", "len": 4, "append": True,
                "hex": struct.pack(">I", syms["recorder_module"]).hex(),
                "ram": f"{modarea_layout.RAM + table:#010x}", "what": f"tabella dei moduli di sfcore, posto {SLOT}"}]
    spec = {
        "name": "recorder", "os": "1.42",
        "requires": ["modarea", "sfcore", "long-samples", "sampler", "idspace"],
        "uses": ["sfcore:main_mix", "sfcore:fs", "sfcore:view"],
        "description": "Registratore di Synfact (recorder-st): doppio SOUND apre la vista; ripresa mono a 48 kHz fino "
                       "a 60 s, rifilo, normalizzazione, salvataggio tra i campioni lunghi, subito suonabile.",
        "license": "GPL-2.0-or-later", "credits": "Synfact (GSM1980), elekloader (irpina)",
        "generated_by": "mods/recorder/make_patch.py",
        "symbols": {k: f"{v:#010x}" for k, v in sorted(syms.items()) if k.startswith(("recorder", "sam_"))},
        "patches": patches,
    }
    (HERE / "patch.json").write_text(json.dumps(spec, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"patch.json: {len(blob)} B a {CODE_BASE:#x}, fine con .bss {end:#x}")


if __name__ == "__main__":
    main()
