"""Genera mods/fastmix/patch.json (vedi fastmix.S).

    python mods/fastmix/make_patch.py         # richiede binutils m68k in WSL (CONTRIBUTING.md)
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

LOAD = 0x4000_0400
OFFSET = 0xF000                         # nell'area mod, dopo la linea di ritardo di fx3
CODE_BASE = modarea_layout.RAM + OFFSET
CODE_END = modarea_layout.RAM + modarea_layout.SIZE
HOOKS = [(0x4008_EF8C, "4fefffd0702048d7", "fm_sum10", "somma a 10 canali: jmp fm_sum10 ; nop"),
         (0x4008_F024, "4fefffd448d77cfc", "fm_sum9", "somma a 9 canali: jmp fm_sum9 ; nop"),
         (0x4008_F0B6, "4fefffd848d73cfc", "fm_sum8", "somma a 8 canali: jmp fm_sum8 ; nop")]
SMOOTH, SMOOTH_ORIG, SMOOTH_BACK = 0x4009_79D6, "2a3c7c290000204b2c3c03d70000", 0x4009_7A2A
WSL_BINUTILS = "~/tools/m68k/root"
SMOOTH_HOOK = False                     # vedi main(): il gancio dello smussamento costa piu' di quanto risparmia


def sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def wsl(cmd: str) -> str:
    r = subprocess.run(["wsl.exe", "-e", "bash", "-lc", cmd], capture_output=True, text=True)
    if r.returncode:
        raise SystemExit(f"comando WSL fallito:\n{cmd}\n{r.stderr}")
    return r.stdout


def emac_sites(dis: str) -> list[int]:
    """Indirizzi delle istruzioni EMAC (per l'emulatore: tools/emu/emac.py)."""
    out = []
    for line in dis.splitlines():
        parts = line.split("\t")
        if len(parts) >= 3 and parts[0].strip().endswith(":"):
            word = parts[1].split()[0] if parts[1].split() else ""
            if len(word) == 4 and word[0] in "aA":
                out.append(int(parts[0].strip()[:-1], 16))
    return out


def main() -> None:
    stock = REPO / "firmware" / "Syntakt_OS1.42.syx"
    sec3 = eft.unpack(stock, REPO / "unpacked" / stock.stem, ids=[3])[3].read_bytes()
    with tempfile.TemporaryDirectory(prefix="fastmix-") as tmp:
        tmp = Path(tmp)
        shutil.copy(HERE / "fastmix.S", tmp / "fastmix.S")
        w = eft.to_wsl_path(tmp)
        bu = f"R={WSL_BINUTILS}; export LD_LIBRARY_PATH=$R/usr/lib/x86_64-linux-gnu; cd {w}; "
        wsl(bu + "$R/usr/bin/m68k-linux-gnu-as -mcpu=54418 fastmix.S -o p.o")
        wsl(bu + f"$R/usr/bin/m68k-linux-gnu-ld -N -Ttext={CODE_BASE:#x} -o p.elf p.o")
        wsl(bu + "$R/usr/bin/m68k-linux-gnu-objcopy -O binary -j .text -j .data p.elf p.bin")
        syms = {}
        for line in wsl(bu + "$R/usr/bin/m68k-linux-gnu-nm p.elf").splitlines():
            parts = line.split()
            if len(parts) == 3:
                syms[parts[2]] = int(parts[0], 16)
        sites = emac_sites(wsl(bu + "$R/usr/bin/m68k-linux-gnu-objdump -d -j .text p.elf"))
        blob = (tmp / "p.bin").read_bytes()
    end = syms.get("_end", CODE_BASE + len(blob))                 # .bss compresa (azzerata da modarea)
    if end > CODE_END:
        raise SystemExit(f"non ci sta: fine a {end:#x}")
    patches = [{"section": 3, "addr": f"{modarea_layout.IMG + OFFSET:#010X}", "len": len(blob), "append": True,
                "hex": blob.hex(), "ram": f"{CODE_BASE:#010x}", "what": "(area mod) fastmix.S"}]
    for addr, orig, sym, what in HOOKS:
        old = sec3[addr - LOAD:addr - LOAD + 8]
        if old.hex() != orig:
            raise SystemExit(f"{addr:#x}: byte inattesi {old.hex()}")
        patches.append({"section": 3, "addr": f"{addr:#010X}", "len": 8, "expect_sha256": sha(old),
                        "hex": struct.pack(">HIH", 0x4EF9, syms[sym], 0x4E71).hex(), "what": what})
    old = sec3[SMOOTH - LOAD:SMOOTH - LOAD + 14]
    if old.hex() != SMOOTH_ORIG:
        raise SystemExit(f"{SMOOTH:#x}: byte inattesi {old.hex()}")
    # 2026-11-04: smussamento non agganciato. Sul dispositivo (cpu-meter, tools/emu/cycles.py tarato) costa piu'
    # di quanto risparmia: -5 300 istruzioni ma una copia di 1.9 KB degli ingressi in DDR, 117 righe di cache
    # mancate a ogni blocco. fm_smooth resta nel blob (tests/test_fastmix.py lo prova ancora contro l'OS).
    if SMOOTH_HOOK:
        patches.append({"section": 3, "addr": f"{SMOOTH:#010X}", "len": 14, "expect_sha256": sha(old),
                        "hex": struct.pack(">HIHIH", 0x4EB9, syms["fm_smooth"], 0x4EF9, SMOOTH_BACK, 0x4E71).hex(),
                        "what": "smussamento dei parametri: jsr fm_smooth ; jmp 0x40097A2A ; nop"})
    spec = {
        "name": "fastmix", "os": "1.42", "requires": ["modarea"],
        "description": "Routine dell'interrupt audio riscritte piu' veloci con lo stesso risultato: somme dei bus "
                       "senza i canali a guadagno nullo e senza la rampa quando i guadagni sono fermi.",
        "generated_by": "mods/fastmix/make_patch.py",
        "symbols": {k: f"{v:#010x}" for k, v in sorted(syms.items()) if k.startswith("fm_")},
        "emac_sites": [f"{a:#010x}" for a in sites],
        "patches": patches,
    }
    (HERE / "patch.json").write_text(json.dumps(spec, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"patch.json: {len(blob)} B a {CODE_BASE:#x} (fine con .bss {end:#x}), {len(sites)} istruzioni EMAC")


if __name__ == "__main__":
    main()
