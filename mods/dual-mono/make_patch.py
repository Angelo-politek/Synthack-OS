"""Genera mods/dual-mono/patch.json: INPUT L e INPUT R come due ingressi separati.

1. assembla dualmono.S e lo collega all'indirizzo CODE_BASE (spazio libero della sezione 3);
2. scrive patch.json: codice+dati nello spazio libero e due agganci attorno al blocco originale
   (che resta al suo posto):
       0x40090872: jsr pre_hook.l ; nop   (al posto di due move.w, rieseguite da pre_hook)
       0x400908FC: jsr post_hook.l        (al posto di move.l #32639,d1, rieseguita da post_hook)

    python mods/dual-mono/make_patch.py         # richiede binutils m68k in WSL (CONTRIBUTING.md)
"""

from __future__ import annotations

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
sys.path.insert(0, str(REPO / "tools" / "unpack"))
import eft  # noqa: E402

LOAD = 0x4000_0400
CODE_BASE = 0x4033_8BE0                 # dopo lo splash (0x40338740..0x40338BD8), stesso riempimento libero
FREE_END = 0x4033_8D80                  # inizio del rilocatore di modarea
BLOCK_START, BLOCK_END = 0x4009_0872, 0x4009_08FC
ENTRY_ORIG = "342a070a302a0740"         # move.w 1802(a2),d2 ; move.w 1856(a2),d0
EXIT_ORIG = "223c00007f7f"              # move.l #32639,d1
WSL_BINUTILS = "~/tools/m68k/root"


def sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def wsl(cmd: str) -> str:
    r = subprocess.run(["wsl.exe", "-e", "bash", "-lc", cmd], capture_output=True, text=True)
    if r.returncode:
        raise SystemExit(f"comando WSL fallito:\n{cmd}\n{r.stderr}")
    return r.stdout


def build_blob() -> tuple[bytes, dict[str, int], list[int], str]:
    """Ritorna (byte di .text+.data contigui, simboli, siti EMAC, disassemblato)."""
    with tempfile.TemporaryDirectory(prefix="dualmono-") as tmp:
        tmp = Path(tmp)
        shutil.copy(HERE / "dualmono.S", tmp / "dualmono.S")
        w = eft.to_wsl_path(tmp)
        bu = f"R={WSL_BINUTILS}; export LD_LIBRARY_PATH=$R/usr/lib/x86_64-linux-gnu; cd {w}; "
        wsl(bu + "$R/usr/bin/m68k-linux-gnu-as -mcpu=54418 dualmono.S -o dm.o")
        # .text a CODE_BASE, .data subito dopo (allineata a 4): un unico blocco contiguo
        wsl(bu + f"$R/usr/bin/m68k-linux-gnu-ld -N -Ttext={CODE_BASE:#x} -o dm.elf dm.o")
        wsl(bu + "$R/usr/bin/m68k-linux-gnu-objcopy -O binary dm.elf dm.bin")
        syms = {}
        for line in wsl(bu + "$R/usr/bin/m68k-linux-gnu-nm dm.elf").splitlines():
            parts = line.split()
            if len(parts) == 3:                      # (le righe da 2 campi sono simboli non definiti)
                syms[parts[2]] = int(parts[0], 16)
        dis = wsl(bu + "$R/usr/bin/m68k-linux-gnu-objdump -d -m m68k:isa-c:emac dm.elf")
        blob = (tmp / "dm.bin").read_bytes()
    emac = [int(m[1], 16) for m in re.finditer(
        r"^\s*([0-9a-f]+):\s+(?:[0-9a-f]{4} ?)+\s+(macl|msacl|movclrl)\b", dis, re.M)]
    return blob, syms, emac, dis


def main() -> None:
    stock = REPO / "firmware" / "Syntakt_OS1.41.syx"
    sec3 = eft.unpack(stock, REPO / "unpacked" / stock.stem, ids=[3])[3].read_bytes()
    blob, syms, emac, dis = build_blob()
    end = CODE_BASE + len(blob)
    if end > FREE_END:
        raise SystemExit(f"non ci sta: {len(blob)} B")
    if any(sec3[CODE_BASE - LOAD:end - LOAD]):
        raise SystemExit("lo spazio libero non e' a zero")
    entry = sec3[BLOCK_START - LOAD:BLOCK_START - LOAD + 8]
    exit_ = sec3[BLOCK_END - LOAD:BLOCK_END - LOAD + 6]
    if entry.hex() != ENTRY_ORIG or exit_.hex() != EXIT_ORIG:
        raise SystemExit("i byte dei punti d'aggancio non sono quelli attesi")

    # IN R = alias 125 ("Input Level"): nessuna pagina, nessun CC/NRPN, e il suo oggetto in RAM
    # usa gli stessi prototipi di IN LR (renderer a barra). Lo facciamo diventare un alias di BAL:
    #  - id interno 0x23 (IN LR) -> 0x25 (BAL) nel descrittore (0x4022D59C + 52*125 + 4);
    #  - lettura/scrittura del valore: switch sull'id logico 125..132 in 0x4000C87E (get) e
    #    0x4000C922 (set); voce 125 = 0x0010 (campo di IN LR) -> 0x0022 (campo di BAL, come 127/128).
    alias_id = 0x4022D59C + 52 * 125 + 4
    if sec3[alias_id - LOAD:alias_id - LOAD + 4] != bytes.fromhex("00000023"):
        raise SystemExit("l'alias 125 non ha l'id interno atteso (0x23)")
    switches = {"lettura": 0x4000C8B0, "scrittura": 0x4000C9A4}      # tabelle: 8 voci .w (id 125..132)
    for what, tab in switches.items():
        entries = struct.unpack(">8h", sec3[tab - LOAD:tab - LOAD + 16])
        if entries[:4] != (0x10, 0x10, 0x22, 0x22):
            raise SystemExit(f"switch di {what} a {tab:#x}: voci inattese {entries[:4]}")

    t_in = struct.pack(">HIH", 0x4EB9, syms["pre_hook"], 0x4E71)        # jsr.l pre_hook ; nop
    t_out = struct.pack(">HI", 0x4EB9, syms["post_hook"])               # jsr.l post_hook
    spec = {
        "name": "dual-mono", "os": "1.41",
        "description": "EXTERNAL IN in modalità mono: INPUT L e INPUT R come due ingressi separati. "
                       "Pagina EXTERNAL MIXER: IN L (manopola A) e IN R (manopola B: alias 125 "
                       "reso alias di BAL, disegnato a barra); "
                       "in stereo tutto come l'originale.",
        "generated_by": "mods/dual-mono/make_patch.py",
        "symbols": {k: f"{v:#010x}" for k, v in sorted(syms.items()) if k in
                    ("pre_hook", "post_hook", "page_ok", "ui_mono", "ui_stereo", "dm_pass", "dm_save_lr",
                     "dm_save_bal", "dm_save_l", "str_inl", "str_inr")},
        "emac_sites": [f"{a:#010x}" for a in emac],
        "patches": [
            {"section": 3, "addr": f"{CODE_BASE:#010X}", "len": len(blob),
             "expect_sha256": sha(sec3[CODE_BASE - LOAD:end - LOAD]), "hex": blob.hex(),
             "what": "agganci del dual mono (pre_hook, post_hook), interfaccia, stringhe IN L / IN R"},
            {"section": 3, "addr": f"{BLOCK_START:#010X}", "len": 8,
             "expect_sha256": sha(entry), "hex": t_in.hex(),
             "what": "ingresso del blocco originale: jsr pre_hook ; nop"},
            {"section": 3, "addr": f"{BLOCK_END:#010X}", "len": 6,
             "expect_sha256": sha(exit_), "hex": t_out.hex(),
             "what": "uscita del blocco originale: jsr post_hook"},
            {"section": 3, "addr": f"{alias_id:#010X}", "len": 4,
             "expect_sha256": sha(sec3[alias_id - LOAD:alias_id - LOAD + 4]), "hex": "00000025",
             "what": "alias 125 'Input Level': id interno 0x23 (IN LR) -> 0x25 (BAL), usato come IN R"},
        ] + [
            {"section": 3, "addr": f"{tab:#010X}", "len": 2,
             "expect_sha256": sha(sec3[tab - LOAD:tab - LOAD + 2]), "hex": "0022",
             "what": f"switch di {what} per id logico 125..132: voce 125 -> ramo di BAL (come 127/128)"}
            for what, tab in switches.items()
        ],
    }
    (HERE / "patch.json").write_text(json.dumps(spec, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    (REPO / "out" / "dual-mono").mkdir(parents=True, exist_ok=True)
    (REPO / "out" / "dual-mono" / "dualmono.lst").write_text(dis, encoding="utf-8")
    print(f"patch.json: {len(blob)} B a {CODE_BASE:#x}..{end:#x}; agganci {t_in.hex()} a {BLOCK_START:#x}, "
          f"{t_out.hex()} a {BLOCK_END:#x}; {len(emac)} istruzioni EMAC nel nostro codice")


if __name__ == "__main__":
    main()
