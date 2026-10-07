"""Genera emac_sites_os141.json: gli indirizzi delle istruzioni EMAC nel codice della sezione 7.

Serve una mappa ESATTA degli inizi di istruzione: una parola 0xAxxx puo' essere anche
una costante dentro un'altra istruzione. La ricaviamo dal disassemblatore di GNU binutils
(il riferimento ufficiale per il ColdFire ISA_C + EMAC), con una scansione lineare limitata
alla zona di codice (0x40000404..0x40009F88: dopo iniziano le tabelle di dati).

Uso (una tantum, richiede binutils m68k in WSL o Linux):
    python tools/emu/gen_emac_sites.py --objdump "wsl:~/tools/m68k/root"
Il file prodotto contiene solo indirizzi (informazione di compatibilita'), niente byte Elektron.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
from pathlib import Path

import memmap

CODE_START, CODE_END = 0x4000_0404, 0x4000_9F88
OUT = Path(__file__).with_name("emac_sites_os141.json")
EMAC_RE = re.compile(r"^\s*([0-9a-f]{8}):\s+((?:[0-9a-f]{4} ?)+)\s+(\S+)\s*(.*)$")
EMAC_MNEMONICS = re.compile(r"^(mac[lw]|msac[lw]|movclrl)$")


def objdump_lines(section7: Path, wsl_root: str) -> list[str]:
    raw = memmap.eft.to_wsl_path(section7)
    cmd = (f'R={wsl_root}; export LD_LIBRARY_PATH=$R/usr/lib/x86_64-linux-gnu; '
           f'$R/usr/bin/m68k-linux-gnu-objdump -b binary -m m68k:isa-c:emac '
           f'--adjust-vma={memmap.LOAD_ADDR:#x} --start-address={CODE_START:#x} '
           f'--stop-address={CODE_END:#x} -D "{raw}"')
    out = subprocess.run(["wsl.exe", "-e", "bash", "-lc", cmd], capture_output=True,
                         text=True, check=True).stdout
    return out.splitlines()


def emac_sites(lines: list[str]) -> list[int]:
    sites = []
    for line in lines:
        m = EMAC_RE.match(line)
        if not m:
            continue
        mnem, ops = m[3], m[4]
        if EMAC_MNEMONICS.match(mnem) or re.search(r"%acc|%macsr|%mask", ops):
            sites.append(int(m[1], 16))
    return sites


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--objdump", default="wsl:~/tools/m68k/root",
                    help="radice dei binutils m68k estratti (prefisso wsl: per WSL)")
    args = ap.parse_args()
    section7 = memmap.default_section7()
    memmap.load_section7(section7)                       # verifica l'hash: siti validi solo per 1.41
    sites = emac_sites(objdump_lines(section7, args.objdump.removeprefix("wsl:")))
    OUT.write_text(json.dumps({
        "section7_sha256": memmap.SECTION7_SHA256,
        "code_range": [CODE_START, CODE_END],
        "source": "GNU objdump 2.42, -m m68k:isa-c:emac, scansione lineare",
        "sites": sites,
    }, indent=0) + "\n")
    print(f"{len(sites)} istruzioni EMAC -> {OUT}")


if __name__ == "__main__":
    main()
