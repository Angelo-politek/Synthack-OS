"""Genera mods/master-comp/patch.json: compressore sui VCA del master con il cervello della Digitakt.

SOLO LOCALE (branch dt-compressor): le costanti del preset (coefficienti di attacco/rilascio,
pendenza del ratio) sono lette dall'OS Digitakt dell'utente e finiscono nel patch.json.

    python mods/master-comp/make_patch.py [--thr 0x4000 --atk 0x1800 --rel 0x2000 --mup 0x2000 --rat 0x300]

Valori come nell'interfaccia della Digitakt (0..0x7F00; RAT 0x000..0x700 = 1.5,2,3,4,6,8,16,20:1).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import struct
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path[:0] = [str(REPO / "tools" / "unpack"), str(REPO / "mods" / "dt-comp")]
import eft  # noqa: E402
from model import C_OCT, EXP_T, LOG_T, Preset, Tables  # noqa: E402

LOAD = 0x4000_0400
# area mod (mods/modarea): collegato in RAM a 0x46000000, byte accodati alla sezione 3 a 0x40348000
MODAREA_RAM, MODAREA_IMG, MODAREA_SIZE = 0x4600_0000, 0x4034_8000, 0x8000
CODE_BASE = MODAREA_RAM + 0x0000        # offset 0 dell'area mod
FREE_END = MODAREA_RAM + MODAREA_SIZE
HOOK, HOOK_END = 0x4009_053E, 0x4009_0562
HOOK_ORIG = "0c810000ffff6f06223c0000ffff374100460c830000ffff6f06263c0000ffff37430048"
WSL_BINUTILS = "~/tools/m68k/root"


def sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def wsl(cmd: str) -> str:
    r = subprocess.run(["wsl.exe", "-e", "bash", "-lc", cmd], capture_output=True, text=True)
    if r.returncode:
        raise SystemExit(f"comando WSL fallito:\n{cmd}\n{r.stderr}")
    return r.stdout


def build_blob(defs: dict[str, int]) -> tuple[bytes, dict[str, int], list[int], str]:
    with tempfile.TemporaryDirectory(prefix="mcomp-") as tmp:
        tmp = Path(tmp)
        shutil.copy(HERE / "comp.S", tmp / "comp.S")
        w = eft.to_wsl_path(tmp)
        bu = f"R={WSL_BINUTILS}; export LD_LIBRARY_PATH=$R/usr/lib/x86_64-linux-gnu; cd {w}; "
        sym = " ".join(f"--defsym {k}={v & 0xFFFFFFFF}" for k, v in defs.items())
        wsl(bu + f"$R/usr/bin/m68k-linux-gnu-as -mcpu=54418 {sym} comp.S -o c.o")
        wsl(bu + f"$R/usr/bin/m68k-linux-gnu-ld -N -Ttext={CODE_BASE:#x} -o c.elf c.o")
        wsl(bu + "$R/usr/bin/m68k-linux-gnu-objcopy -O binary c.elf c.bin")
        syms = {}
        for line in wsl(bu + "$R/usr/bin/m68k-linux-gnu-nm c.elf").splitlines():
            parts = line.split()
            if len(parts) == 3:
                syms[parts[2]] = int(parts[0], 16)
        dis = wsl(bu + "$R/usr/bin/m68k-linux-gnu-objdump -d -m m68k:isa-c:emac c.elf")
        blob = (tmp / "c.bin").read_bytes()
    emac = []
    for m in re.finditer(r"^\s*([0-9a-f]+):\s+(?:[0-9a-f]{4} ?)+\s+(\S+)\s*(.*)$", dis, re.M):
        if re.match(r"^(mac[lw]|msac[lw]|movclrl)$", m[2]) or re.search(r"%(acc|macsr|mask)", m[3]):
            emac.append(int(m[1], 16))
    return blob, syms, emac, dis


def main() -> None:
    ap = argparse.ArgumentParser()
    for k, v in (("thr", 0x4000), ("atk", 0x1800), ("rel", 0x2000), ("mup", 0x2000), ("rat", 0x300)):
        ap.add_argument(f"--{k}", type=lambda s: int(s, 0), default=v)
    a = ap.parse_args()
    params = [a.thr, a.atk, a.rel, a.mup, a.rat, 0, 0, 0x7F00]

    dt = eft.unpack(REPO / "firmware" / "Digitakt_OS1.54.syx", REPO / "unpacked" / "DT1.54", ids=[3])[3]
    pr = Preset(Tables(dt), params)
    one = (1 << 31) - 1
    defs = {"C_OCT": C_OCT, "THR": pr.thr, "SLOPE": pr.slope, "REL1": one - pr.rel, "REL": pr.rel,
            "ATT1": one - pr.att, "ATT": pr.att, "MK": pr.mk}
    defs.update({f"LOG_T{i}": v for i, v in enumerate(LOG_T)})
    defs.update({f"EXP_T{i}": v for i, v in enumerate(EXP_T)})

    stock = REPO / "firmware" / "Syntakt_OS1.41.syx"
    sec3 = eft.unpack(stock, REPO / "unpacked" / stock.stem, ids=[3])[3].read_bytes()
    blob, syms, emac, dis = build_blob(defs)
    end = CODE_BASE + len(blob)
    if end > FREE_END:
        raise SystemExit(f"non ci sta: {len(blob)} B (liberi {FREE_END - CODE_BASE})")
    site = sec3[HOOK - LOAD:HOOK_END - LOAD]
    if site.hex() != HOOK_ORIG:
        raise SystemExit("i byte del punto d'aggancio non sono quelli attesi")
    tramp = struct.pack(">HIHH", 0x4EB9, syms["comp_hook"], 0x6000, HOOK_END - (HOOK + 8))

    spec = {
        "name": "master-comp", "os": "1.41", "requires": ["modarea"],
        "description": "Compressore sul master analogico (VCA del master) con l'algoritmo del "
                       "compressore della Digitakt; preset fisso " +
                       " ".join(f"{k.upper()}={getattr(a, k):#06x}" for k in ("thr", "atk", "rel", "mup", "rat")),
        "generated_by": "mods/master-comp/make_patch.py",
        "params": [f"{v:#06x}" for v in params],
        "symbols": {k: f"{v:#010x}" for k, v in sorted(syms.items())
                    if k in ("comp_hook", "scale", "k_const", "k_state", "k_logt", "k_expt")},
        "emac_sites": [f"{x:#010x}" for x in emac],
        "patches": [
            {"section": 3, "addr": f"{MODAREA_IMG + CODE_BASE - MODAREA_RAM:#010X}", "len": len(blob),
             "append": True, "hex": blob.hex(), "ram": f"{CODE_BASE:#010x}",
             "what": "(area mod) routine del compressore + costanti del preset + stato + tabelline"},
            {"section": 3, "addr": f"{HOOK:#010X}", "len": len(tramp),
             "expect_sha256": sha(sec3[HOOK - LOAD:HOOK - LOAD + len(tramp)]), "hex": tramp.hex(),
             "what": "trampolino: jsr comp_hook ; bra.w 0x40090562 (sostituisce limite e scrittura dei CV del master)"},
        ],
    }
    (HERE / "patch.json").write_text(json.dumps(spec, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    (REPO / "out" / "master-comp").mkdir(parents=True, exist_ok=True)
    (REPO / "out" / "master-comp" / "comp.lst").write_text(dis, encoding="utf-8")
    print(f"patch.json: {len(blob)} B in area mod a {CODE_BASE:#x}..{end:#x} (liberi ancora {FREE_END - end} B), "
          f"{len(emac)} istruzioni EMAC; trampolino {tramp.hex()}")


if __name__ == "__main__":
    main()
