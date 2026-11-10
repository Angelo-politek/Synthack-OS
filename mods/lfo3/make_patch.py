"""Genera mods/lfo3/patch.json: il terzo LFO di Synfact (lfo3-st) sulla 1.42 (README.md).

    python mods/lfo3/make_patch.py          # richiede gcc m68k in WSL (CONTRIBUTING.md)

I sorgenti di Synfact stanno in synfact/ (indirizzi tradotti con tools/build/port_source.py, ORIGIN), la colla
nostra in lfo3.c. Il modulo si iscrive a sfcore (posto della tabella dal registro), che chiama la sua init al primo
tick dell'interfaccia: il nucleo va nella SRAM, i siti dell'OS li installa la build (patch.json).

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
import idspace_layout as IDS  # noqa: E402

LOAD = 0x4000_0400
OFFSET, END = next((a, b) for a, b, who, _ in registry.MODAREA if who == "lfo3")
CODE_BASE = modarea_layout.RAM + OFFSET
SLOT = next(s for s, who in registry.SFCORE_SLOTS.items() if who == "lfo3")
TOOLS = "~/tools/m68k/root"
LFO1_IDS = (86, 87, 88, 89, 90, 92, 93, 94)   # SPD MULT FADE DEST WAVE SPH MODE DEP: modelli di 530..537
LFO3_IDS = range(530, 538)
# siti che riconoscono una DEST dall'id (89 LFO1, 99 LFO2): la catena di confronti -> jsr (Z = 1 se 89/99/533)
DEST_SITES = [(0x4003_B11A, "7059b0836708103c0063b083", "lfo3_dest_d3", "menu della DEST: anche LFO3 (533)"),
              (0x4001_49E2, "7059b08267087263b282", "lfo3_dest_d2", "randomizzazione: DEST di LFO3 (533)"),
              (0x4001_4C5E, "b4806708143c0063b480", "lfo3_dest_d0", "passo relativo della DEST: anche LFO3 (533)"),
              (0x4001_4E48, "b4806708143c0063b480", "lfo3_dest_d0", "passo relativo della DEST (FX): anche LFO3")]
PAGE = 38                                      # pagina di idspace: terza della scheda LFO
TAB_COUNT, TAB_ARRAY = 0x4003_57D2, 0x4003_57D8   # scheda LFO: moveq #2,d1 ; operando di move.l #0x401C8250 ({4, 5}),d0
CFLAGS = (f"-DIDS_PAGE38={IDS.page(PAGE):#x}u -DIDS_PAGE38_E={IDS.page(PAGE) + 8 + 16:#x} " "-mcpu=54418 -Os -ffreestanding -fno-builtin -nostdlib -fno-pic -fno-common -fno-jump-tables "
          "-fno-tree-loop-distribute-patterns -I. -Iinclude -Wall -Wextra")
C_SOURCES = ["lfo3.c"]
S_SOURCES = ["synfact/render.s", "synfact/sram.s"]
NOP = b"\x4e\x71"
# (indirizzo 1.42, byte stock, simbolo, descrizione): siti dell'OS (pagina, memoria, lock: passi successivi)
SITES: list[tuple[int, str, str, str]] = [
    (0x400F_3A0C, "7201b2806672", "lfo3_wave_hook", "disegno della scheda LFO: il riquadro della forma d'onda anche per LFO3")]
SRAM = {"code": 0x8000_7340, "bank": 0x8000_F870}


def sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def wsl(cmd: str) -> str:
    r = subprocess.run(["wsl.exe", "-e", "bash", "-lc", cmd], capture_output=True, text=True)
    if r.returncode:
        raise SystemExit(f"comando WSL fallito:\n{cmd}\n{r.stdout}{r.stderr}")
    return r.stdout + r.stderr


def build_blob():
    with tempfile.TemporaryDirectory(prefix="lfo3-") as tmp:
        tmp = Path(tmp)
        shutil.copytree(REPO / "mods" / "sfcore" / "include", tmp / "include")
        for f in C_SOURCES + S_SOURCES + ["lfo3.h"]:
            (tmp / f).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy(HERE / f, tmp / f)
        w = eft.to_wsl_path(tmp)
        env = f"R={TOOLS}; export LD_LIBRARY_PATH=$R/usr/lib/x86_64-linux-gnu; cd {w}; "
        gcc = "$R/usr/bin/m68k-linux-gnu-gcc-13 -B$R/usr/libexec/gcc/m68k-linux-gnu/13/ -B$R/usr/bin/m68k-linux-gnu-"
        objs = []
        for i, f in enumerate(C_SOURCES):
            warn = wsl(env + f"{gcc} {CFLAGS} -c {f} -o c{i}.o")
            if "warning" in warn:
                raise SystemExit(warn)
            objs.append(f"c{i}.o")
        for i, f in enumerate(S_SOURCES):
            wsl(env + f"$R/usr/bin/m68k-linux-gnu-as -mcpu=54418 {f} -o s{i}.o")
            objs.append(f"s{i}.o")
        wsl(env + f"$R/usr/bin/m68k-linux-gnu-ld -N -Ttext={CODE_BASE:#x} -e lfo3_module -o l.elf {' '.join(objs)}")
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


def main() -> None:
    stock = REPO / "firmware" / "Syntakt_OS1.42.syx"
    sec3 = eft.unpack(stock, REPO / "unpacked" / stock.stem, ids=[3])[3].read_bytes()
    blob, syms = build_blob()
    end = max(syms.get("_end", 0), CODE_BASE + len(blob))
    if end > modarea_layout.RAM + END:
        raise SystemExit(f"non ci sta: fine a {end:#x}, spazio fino a {modarea_layout.RAM + END:#x}")
    kernel = syms["lfo3_render_end"] - syms["lfo3_render"]
    lo, hi = next((a, b) for a, b, who, _ in registry.SRAM if who == "lfo3")
    if SRAM["code"] + kernel > hi:
        raise SystemExit(f"nucleo di {kernel} B: non sta nella SRAM ({SRAM['code']:#x}..{hi:#x})")
    table = registry.SFCORE_TABLE + 4 * SLOT
    patches = [{"section": 3, "addr": f"{modarea_layout.IMG + OFFSET:#010X}", "len": len(blob), "append": True,
                "hex": blob.hex(), "ram": f"{CODE_BASE:#010x}", "what": "(area mod) motore LFO3 e modulo sfcore"},
               {"section": 3, "addr": f"{modarea_layout.IMG + table:#010X}", "len": 4, "append": True,
                "hex": struct.pack(">I", syms["lfo3_module"]).hex(),
                "ram": f"{modarea_layout.RAM + table:#010x}", "what": f"tabella dei moduli di sfcore, posto {SLOT}"}]
    # idspace: descrittori e oggetti 530..537 da quelli di LFO1, id interni 0x3e..0x45 (xparams, secondo gruppo),
    # gruppo -1 come le pagine di SY FM4; pagina 38 nella scheda LFO
    def ext(at: int, data: bytes, what: str) -> dict:
        return {"section": 3, "addr": f"{modarea_layout.IMG + at - modarea_layout.RAM:#010X}", "len": len(data),
                "append": True, "hex": data.hex(), "ram": f"{at:#010x}", "what": what}
    for k, (src, pid) in enumerate(zip(LFO1_IDS, LFO3_IDS)):
        d = bytearray(sec3[0x4022_D83C - LOAD + 52 * src:0x4022_D83C - LOAD + 52 * src + 52])
        d[0:8] = struct.pack(">iI", -1, 0x3E + k)
        d[24:32] = struct.pack(">II", 0xFFFF_FFFF, 0xFFFF_FFFF)               # niente CC ne' NRPN
        patches += [ext(IDS.desc(pid), bytes(d), f"idspace: descrittore dell'id {pid} (LFO3, come {src})"),
                    ext(IDS.objdef(pid), struct.pack(">4I", src, 0, 0, 0), f"idspace: oggetto dell'id {pid}, modello {src}")]
    page = struct.pack(">2I", syms["lfo3_page_s"] + 12, syms["lfo3_page_l"] + 12) + struct.pack(">9I", *LFO3_IDS, 10)
    patches.append(ext(IDS.page(PAGE), page, f"idspace: pagina {PAGE} (LFO3)"))
    for addr, orig, new, what in ((TAB_COUNT, "7202", bytes.fromhex("7203"), "scheda LFO: 3 pagine"),
                                  (TAB_ARRAY, "401c8250", struct.pack(">I", syms["lfo3_lfo_pages"]),
                                   "scheda LFO: pagine {4, 5, 38}")):
        old = sec3[addr - LOAD:addr - LOAD + len(orig) // 2]
        if old.hex() != orig:
            raise SystemExit(f"{addr:#x}: byte inattesi {old.hex()}")
        patches.append({"section": 3, "addr": f"{addr:#010X}", "len": len(new), "expect_sha256": sha(old),
                        "hex": new.hex(), "what": what})
    for addr, orig, sym, what in DEST_SITES:                                 # DEST di LFO3 come quelle di LFO1/LFO2
        old = sec3[addr - LOAD:addr - LOAD + len(orig) // 2]
        if old.hex() != orig:
            raise SystemExit(f"{addr:#x}: byte inattesi {old.hex()}")
        new = struct.pack(">HI", 0x4EB9, syms[sym]) + NOP * ((len(old) - 6) // 2)
        patches.append({"section": 3, "addr": f"{addr:#010X}", "len": len(new), "expect_sha256": sha(old),
                        "hex": new.hex(), "what": what})
    for addr, orig, sym, what in SITES:
        n = len(orig) // 2
        old = sec3[addr - LOAD:addr - LOAD + n]
        if old.hex() != orig:
            raise SystemExit(f"{addr:#x}: byte inattesi {old.hex()}")
        new = struct.pack(">HI", 0x4EF9, syms[sym]) + NOP * ((n - 6) // 2)
        patches.append({"section": 3, "addr": f"{addr:#010X}", "len": n, "expect_sha256": sha(old),
                        "hex": new.hex(), "what": what})
    spec = {
        "name": "lfo3", "os": "1.42", "requires": ["modarea", "sfcore", "idspace", "xparams"], "uses": ["sfcore:lfo"],
        "description": "Terzo LFO di Synfact (lfo3-st): 13 motori (12 tracce + FX) prima di LFO1/LFO2, nucleo e "
                       "dati nella SRAM.",
        "license": "GPL-2.0-or-later", "credits": "Synfact (GSM1980), elekloader (irpina)",
        "generated_by": "mods/lfo3/make_patch.py",
        "symbols": {k: f"{v:#010x}" for k, v in sorted(syms.items()) if k.startswith("lfo3")},
        "sram": {k: f"{v:#010x}" for k, v in SRAM.items()},
        "patches": patches,
    }
    (HERE / "patch.json").write_text(json.dumps(spec, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"patch.json: {len(blob)} B a {CODE_BASE:#x}, fine con .bss {end:#x}; nucleo {kernel} B")


if __name__ == "__main__":
    main()
