"""Genera mods/long-samples/patch.json (synfact/ da Synfact, glue.S e pool.c nostri; vedi README.md).

    python mods/long-samples/make_patch.py    # richiede gcc m68k in WSL (CONTRIBUTING.md)

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
import engine_layout  # noqa: E402
import modarea_layout  # noqa: E402
import projstore_layout  # noqa: E402
import registry  # noqa: E402

LOAD = 0x4000_0400
OFFSET, END = next((a, b) for a, b, who, _ in registry.MODAREA if who == "long-samples")
CODE_BASE = modarea_layout.RAM + OFFSET
PS_POOL = (int(json.loads((REPO / "mods" / "projstore" / "patch.json").read_text(encoding="utf-8"))["layout"]["data"], 16)
           + projstore_layout.PARTS["long-samples"][0])          # lista dei campioni del progetto (pool.c)
TOOLS = "~/tools/m68k/root"
CFLAGS = ("-mcpu=54418 -Os -ffreestanding -fno-builtin -nostdlib -fno-pic -fno-common -fno-tree-loop-distribute-patterns "
          f"-DPS_POOL={PS_POOL:#x}u -Isynfact -Wall -Wextra -Wno-unused-parameter -Wno-sign-compare -Wno-misleading-indentation")
SOURCES = ["synfact/hzfs.c", "synfact/crc.c", "synfact/high-storage.c", "pool.c", "transfer.c", "upload.c"]
NOP = b"\x4e\x71"
# (indirizzo 1.42, byte stock, istruzione, simbolo, descrizione); Synfact: mods/core-st/mod.json, siti 1.41
HOOKS = [
    (0x400B_8100, "4e56ffd848d73c0c", "jmp", "core_fs_route", "Data RPC: percorso -> FileInfo (finestre alte HZFS)"),
    (0x400B_6204, "4e56ffb448d71c3c", "jmp", "core_fs_write", "Data RPC: scrittura (slot stock <= 5 s, finestre alte)"),
    (0x4008_271E, "4eb9400bd74e", "jsr", "ls_boot", "avvio: cataloghi HZFS (core_hzfs_ensure)"),
    (0x4008_287A, "4ebafab84eb940082e9c", "jsr", "ls_blob", "immagine dei campioni costruita: piano dei file HZFS"),
    (0x4008_2FB6, "24394d84f2c1", "jsr", "ls_count_hook", "upload alla CPU #2: byte da inviare"),
    (0x4008_2FCE, "203941bbf42433c01000000ce3a8", "jsr", "ls_map_hook", "upload alla CPU #2: sorgente della pagina"),
    (0x4001_D6FE, "4fefffdc48d7043c", "jmp", "ls_load_hook", "progetto caricato: la sua lista dei campioni lunghi "
                                                               "(core_pool_load di Synfact)"),
    (0x4001_D16A, "4e56ffa848d71c3c", "jmp", "ls_new_hook", "NEW PROJECT: lista nell'ordine di caricamento "
                                                             "(core_pool_initialize di Synfact)"),
]


def sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def wsl(cmd: str) -> str:
    r = subprocess.run(["wsl.exe", "-e", "bash", "-lc", cmd], capture_output=True, text=True)
    if r.returncode:
        raise SystemExit(f"comando WSL fallito:\n{cmd}\n{r.stderr}")
    return r.stdout + r.stderr


def build_blob():
    with tempfile.TemporaryDirectory(prefix="longsamples-") as tmp:
        tmp = Path(tmp)
        shutil.copytree(HERE / "synfact", tmp / "synfact")
        for f in ("pool.c", "transfer.c", "upload.c"):
            shutil.copy(HERE / f, tmp / f)
        shutil.copy(HERE / "glue.S", tmp / "glue.S")
        w = eft.to_wsl_path(tmp)
        env = f"R={TOOLS}; export LD_LIBRARY_PATH=$R/usr/lib/x86_64-linux-gnu; cd {w}; "
        gcc = "$R/usr/bin/m68k-linux-gnu-gcc-13 -B$R/usr/libexec/gcc/m68k-linux-gnu/13/ -B$R/usr/bin/m68k-linux-gnu-"
        objs = []
        for i, src in enumerate(SOURCES):
            o = f"o{i}.o"
            warn = wsl(env + f"{gcc} {CFLAGS} -c {src} -o {o}")
            if "warning" in warn:
                raise SystemExit(warn)
            objs.append(o)
        wsl(env + "$R/usr/bin/m68k-linux-gnu-as -mcpu=54418 glue.S -o g.o")
        wsl(env + f"$R/usr/bin/m68k-linux-gnu-ld -N -Ttext={CODE_BASE:#x} -e ls_boot -o l.elf g.o {' '.join(objs)}")
        undef = wsl(env + "$R/usr/bin/m68k-linux-gnu-nm -u l.elf").strip()
        if undef:
            raise SystemExit(f"simboli esterni non permessi (libgcc?): {undef}")
        wsl(env + "$R/usr/bin/m68k-linux-gnu-objcopy -O binary -j .text -j .rodata -j .data l.elf l.bin")
        syms = {}
        for line in wsl(env + "$R/usr/bin/m68k-linux-gnu-nm l.elf").splitlines():
            parts = line.split()
            if len(parts) == 3:
                syms[parts[2]] = int(parts[0], 16)
        return (tmp / "l.bin").read_bytes(), syms


# CPU #2 (engine/): the runtime receiver in the engine area, called at the end of the audio interrupt
OFF7, END7 = next((a, b) for a, b, who, _ in registry.ENGINE if who == "long-samples")
EXIT_SITE = 0x4000_0B04                 # tst.l 0x40040050 (Synfact's audio_machine_exit site)


def build_engine():
    with tempfile.TemporaryDirectory(prefix="longsamples7-") as tmp:
        tmp = Path(tmp)
        shutil.copytree(HERE / "engine", tmp / "engine")
        w = eft.to_wsl_path(tmp)
        env = f"R={TOOLS}; export LD_LIBRARY_PATH=$R/usr/lib/x86_64-linux-gnu; cd {w}; "
        gcc = "$R/usr/bin/m68k-linux-gnu-gcc-13 -B$R/usr/libexec/gcc/m68k-linux-gnu/13/ -B$R/usr/bin/m68k-linux-gnu-"
        warn = wsl(env + f"{gcc} -mcpu=54418 -Os -ffreestanding -fno-builtin -nostdlib -fno-pic -fno-common "
                         "--param=min-pagesize=0 -Wall -Wextra -c engine/rx.c -o r.o")
        if "warning" in warn:
            raise SystemExit(warn)
        wsl(env + "$R/usr/bin/m68k-linux-gnu-as -mcpu=54418 engine/entry.S -o e.o")
        base = engine_layout.RAM + OFF7
        wsl(env + f"$R/usr/bin/m68k-linux-gnu-ld -N -Ttext={base:#x} -e ls_rx_exit -o r.elf e.o r.o")
        undef = wsl(env + "$R/usr/bin/m68k-linux-gnu-nm -u r.elf").strip()
        if undef:
            raise SystemExit(f"simboli esterni non permessi: {undef}")
        wsl(env + "$R/usr/bin/m68k-linux-gnu-objcopy -O binary -j .text -j .rodata -j .data r.elf r.bin")
        syms = {}
        for line in wsl(env + "$R/usr/bin/m68k-linux-gnu-nm r.elf").splitlines():
            parts = line.split()
            if len(parts) == 3:
                syms[parts[2]] = int(parts[0], 16)
        blob = (tmp / "r.bin").read_bytes()
    if max(syms.get("_end", 0), base + len(blob)) > engine_layout.RAM + END7:
        raise SystemExit("CPU #2: non ci sta")
    return blob, syms


def main() -> None:
    stock = REPO / "firmware" / "Syntakt_OS1.42.syx"
    sec3 = eft.unpack(stock, REPO / "unpacked" / stock.stem, ids=[3])[3].read_bytes()
    blob, syms = build_blob()
    sec7 = eft.unpack(stock, REPO / "unpacked" / stock.stem, ids=[7])[7].read_bytes()
    blob7, syms7 = build_engine()
    end = max(syms.get("_end", 0), CODE_BASE + len(blob))
    if end > modarea_layout.RAM + END:
        raise SystemExit(f"non ci sta: fine a {end:#x}, spazio fino a {modarea_layout.RAM + END:#x}")
    patches = [{"section": 3, "addr": f"{modarea_layout.IMG + OFFSET:#010X}", "len": len(blob), "append": True,
                "hex": blob.hex(), "ram": f"{CODE_BASE:#010x}", "what": "(area mod) HZFS di Synfact, piano e upload"}]
    for addr, orig, op, sym, what in HOOKS:
        n = len(orig) // 2
        old = sec3[addr - LOAD:addr - LOAD + n]
        if old.hex() != orig:
            raise SystemExit(f"{addr:#x}: byte inattesi {old.hex()}")
        new = struct.pack(">HI", 0x4EF9 if op == "jmp" else 0x4EB9, syms[sym])
        new += NOP * ((n - len(new)) // 2)
        patches.append({"section": 3, "addr": f"{addr:#010X}", "len": n, "expect_sha256": sha(old),
                        "hex": new.hex(), "what": what})
    old7 = sec7[EXIT_SITE - LOAD:EXIT_SITE - LOAD + 6]
    if old7.hex() != "4ab940040050":
        raise SystemExit(f"{EXIT_SITE:#x}: byte inattesi {old7.hex()}")
    patches += [
        {"section": 7, "addr": f"{engine_layout.IMG + OFF7:#010X}", "len": len(blob7), "append": True,
         "hex": blob7.hex(), "ram": f"{engine_layout.RAM + OFF7:#010x}",
         "what": "(area motori) ricevitore dei campioni lunghi a runtime (engine/rx.c)"},
        {"section": 7, "addr": f"{EXIT_SITE:#010X}", "len": 6, "expect_sha256": sha(old7),
         "hex": struct.pack(">HI", 0x4EB9, syms7["ls_rx_exit"]).hex(),
         "what": "fine dell'interrupt audio: ricevitore (sito audio_machine_exit di Synfact)"}]
    syms.update({k: v for k, v in syms7.items() if k.startswith("ls_rx")})
    spec = {
        "name": "long-samples", "os": "1.42", "requires": ["modarea", "modarea7", "projstore"],
        "description": "Campioni lunghi di Synfact (HZFS nella zona alta della eMMC, caricati con il tool di Synfact) "
                       "inviati alla CPU #2 all'avvio dopo i campioni stock; le machine SAMPLER li suonano come slot 65-128.",
        "license": "GPL-2.0-or-later", "credits": "Synfact (GSM1980), elekloader (irpina)",
        "generated_by": "mods/long-samples/make_patch.py",
        "symbols": {k: f"{v:#010x}" for k, v in sorted(syms.items())
                    if k.startswith(("ls_", "core_hzfs", "core_high", "core_fs_", "core_sample", "core_crc"))},
        "patches": patches,
    }
    (HERE / "patch.json").write_text(json.dumps(spec, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"patch.json: {len(blob)} B a {CODE_BASE:#x}, fine con .bss {end:#x}")


if __name__ == "__main__":
    main()
