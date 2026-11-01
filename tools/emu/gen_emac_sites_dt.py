"""Genera emac_sites_dt154.json: le istruzioni EMAC delle funzioni della Digitakt 1.54 che
tests/test_sampler.py esegue come riferimento (sezione 3, caricata a 0x40000400).

Solo indirizzi (come emac_sites_os141.json), niente byte Elektron. Serve il file della Digitakt in firmware/
(mai nel repo) e binutils m68k in WSL:

    python tools/emu/gen_emac_sites_dt.py
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(REPO / "tools" / "unpack"))
import eft  # noqa: E402
from gen_emac_sites import emac_sites  # noqa: E402

SYX = REPO / "firmware" / "Digitakt_OS1.54.syx"
OUT = HERE / "emac_sites_dt154.json"
LOAD = 0x4000_0400
# funzioni di riferimento (tests/test_sampler.py)
RANGES = {
    "positions": (0x4007_4C9C, 0x4007_4F76),     # ONESHOT, REPITCH, SLICE, WERP
    "interpolation": (0x4007_5EA2, 0x4007_5F00),
    "grid": (0x4007_62EE, 0x4007_653E),          # ricerca dello zero-crossing, registrazione del campione
    "div64": (0x4012_3FD4, 0x4012_4400),
}


def section3() -> Path:
    return eft.unpack(SYX, REPO / "unpacked" / SYX.stem, ids=[3])[3]


def main() -> None:
    sec = section3()
    raw = eft.to_wsl_path(sec)
    sites = []
    for a, b in RANGES.values():
        cmd = ("R=~/tools/m68k/root; export LD_LIBRARY_PATH=$R/usr/lib/x86_64-linux-gnu; "
               f"$R/usr/bin/m68k-linux-gnu-objdump -b binary -m m68k:isa-c:emac --adjust-vma={LOAD:#x} "
               f'--start-address={a:#x} --stop-address={b:#x} -D "{raw}"')
        out = subprocess.run(["wsl.exe", "-e", "bash", "-lc", cmd], capture_output=True, text=True, check=True)
        sites += emac_sites(out.stdout.splitlines())
    OUT.write_text(json.dumps({
        "section3_sha256": hashlib.sha256(sec.read_bytes()).hexdigest(),
        "ranges": {k: [a, b] for k, (a, b) in RANGES.items()},
        "source": "GNU objdump 2.42, -m m68k:isa-c:emac, scansione lineare",
        "sites": sorted(sites),
    }, indent=0) + "\n")
    print(f"{len(sites)} istruzioni EMAC -> {OUT}")


if __name__ == "__main__":
    main()
