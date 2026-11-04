"""Genera mods/cpu-meter/patch.json (vedi cpumeter.c).

    python mods/cpu-meter/make_patch.py       # richiede gcc m68k in WSL (CONTRIBUTING.md)
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
OFFSET = next(a for a, b, who, _ in registry.MODAREA if who == "cpu-meter")
END = next(b for a, b, who, _ in registry.MODAREA if who == "cpu-meter")
CODE_BASE = modarea_layout.RAM + OFFSET
TOOLS = "~/tools/m68k/root"
CFLAGS = "-mcpu=54418 -Os -ffreestanding -fno-builtin -nostdlib -fno-pic -fno-common -Wall -Wextra"
ISR_IN, ISR_IN_ORIG = 0x400A_38CE, "4e56ff5c48d73fff"        # link.w %fp,#-164 ; movem.l %d0-%a5,(%sp)
ISR_OUT, ISR_OUT_ORIG = 0x400A_5518, "4cee3fffff5c"          # movem.l -164(%fp),%d0-%a5
VT_DRAW, VT_DRAW_ORIG = 0x401C_84AC, "40032692"              # ParameterPageView: draw


def sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def wsl(cmd: str) -> str:
    r = subprocess.run(["wsl.exe", "-e", "bash", "-lc", cmd], capture_output=True, text=True)
    if r.returncode:
        raise SystemExit(f"comando WSL fallito:\n{cmd}\n{r.stderr}")
    return r.stdout + r.stderr


def main() -> None:
    stock = REPO / "firmware" / "Syntakt_OS1.42.syx"
    sec3 = eft.unpack(stock, REPO / "unpacked" / stock.stem, ids=[3])[3].read_bytes()
    with tempfile.TemporaryDirectory(prefix="cpumeter-") as tmp:
        tmp = Path(tmp)
        shutil.copy(HERE / "cpumeter.c", tmp / "cpumeter.c")
        w = eft.to_wsl_path(tmp)
        env = f"R={TOOLS}; export LD_LIBRARY_PATH=$R/usr/lib/x86_64-linux-gnu; cd {w}; "
        gcc = "$R/usr/bin/m68k-linux-gnu-gcc-13 -B$R/usr/libexec/gcc/m68k-linux-gnu/13/ -B$R/usr/bin/m68k-linux-gnu-"
        warn = wsl(env + f"{gcc} {CFLAGS} -c cpumeter.c -o c.o")
        if "warning" in warn:
            raise SystemExit(warn)
        wsl(env + f"$R/usr/bin/m68k-linux-gnu-ld -N -Ttext={CODE_BASE:#x} -e cm_draw -o c.elf c.o")
        if wsl(env + "$R/usr/bin/m68k-linux-gnu-nm -u c.elf").strip():
            raise SystemExit("simboli esterni non permessi")
        heads = wsl(env + "$R/usr/bin/m68k-linux-gnu-objdump -h c.elf")
        if any(n in heads for n in (" .bss ", " .sbss ")) and "ALLOC" in heads.split(".bss")[-1][:80]:
            pass
        wsl(env + "$R/usr/bin/m68k-linux-gnu-objcopy -O binary -j .text -j .rodata -j .data c.elf c.bin")
        syms = {}
        for line in wsl(env + "$R/usr/bin/m68k-linux-gnu-nm c.elf").splitlines():
            parts = line.split()
            if len(parts) == 3:
                syms[parts[2]] = int(parts[0], 16)
        blob = (tmp / "c.bin").read_bytes()
    if CODE_BASE + len(blob) > modarea_layout.RAM + END:
        raise SystemExit(f"non ci sta: {len(blob)} B")
    patches = [{"section": 3, "addr": f"{modarea_layout.IMG + OFFSET:#010X}", "len": len(blob), "append": True,
                "hex": blob.hex(), "ram": f"{CODE_BASE:#010x}", "what": "(area mod) cpumeter.c"}]
    for addr, orig, new, what in (
            (ISR_IN, ISR_IN_ORIG, struct.pack(">HIH", 0x4EF9, syms["cm_entry"], 0x4E71), "ingresso dell'interrupt audio"),
            (ISR_OUT, ISR_OUT_ORIG, struct.pack(">HI", 0x4EF9, syms["cm_exit"]), "uscita dell'interrupt audio"),
            (VT_DRAW, VT_DRAW_ORIG, struct.pack(">I", syms["cm_draw"]), "disegno della vista dei parametri")):
        old = sec3[addr - LOAD:addr - LOAD + len(new)]
        if old.hex() != orig:
            raise SystemExit(f"{addr:#x}: byte inattesi {old.hex()}")
        patches.append({"section": 3, "addr": f"{addr:#010X}", "len": len(new), "expect_sha256": sha(old),
                        "hex": new.hex(), "what": what})
    spec = {
        "name": "cpu-meter", "os": "1.42", "requires": ["modarea"],
        "description": "Diagnostica: carico dell'interrupt audio misurato con DTIM0 (media e massimo, percento del "
                       "blocco) in alto a destra sulle pagine dei parametri.",
        "generated_by": "mods/cpu-meter/make_patch.py",
        "symbols": {k: f"{v:#010x}" for k, v in sorted(syms.items()) if k.startswith("cm_")},
        "patches": patches,
    }
    (HERE / "patch.json").write_text(json.dumps(spec, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"patch.json: {len(blob)} B a {CODE_BASE:#x}")


if __name__ == "__main__":
    main()
