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
from model import C_OCT, EXP_T, LOG_T, Tables  # noqa: E402

LOAD = 0x4000_0400
# area mod (mods/modarea): collegato in RAM a 0x46000000, byte accodati alla sezione 3 a 0x40348000
MODAREA_RAM, MODAREA_IMG, MODAREA_SIZE = 0x4600_0000, 0x4034_8000, 0x8000
CODE_BASE = MODAREA_RAM + 0x0000        # offset 0 dell'area mod
FREE_END = MODAREA_RAM + MODAREA_SIZE
HOOK, HOOK_END = 0x4009_053E, 0x4009_0562
HOOK_ORIG = "0c810000ffff6f06223c0000ffff374100460c830000ffff6f06263c0000ffff37430048"

# ---- interfaccia: id logici nascosti riusati (vedi comp.S e docs/re-journal.md)
DESC = 0x4022_D59C                      # descrittori: 52 B, indice = id logico
PARAMS = [  # (nome breve, nome lungo, id, massimo)
    ("THR", "Comp Threshold", 144, 0x7F00),
    ("ATK", "Comp Attack", 72, 0x7F00),
    ("REL", "Comp Release", 91, 0x7F00),
    ("MUP", "Comp Makeup", 101, 0x7F00),
    ("RAT", "Comp Ratio", 127, 0x7F00),        # 9 posizioni: 0 = OFF, 1..8 = 1.5..20:1
    ("GR", "Gain Reduction", 59, 0x7F00),      # misuratore, sola lettura
]
# agganci alle funzioni centrali dei parametri di kit: (indirizzo, byte originali, simbolo)
UI_HOOKS = [(0x4000_D870, "2f02747c222f0008", "kit_hook"),
            (0x4000_D94A, "2f02222f0008", "get_hook"),
            (0x4000_DA32, "2f032f02222f000c", "set_hook")]
# inizializzatore degli oggetti per-parametro: grafico a barra per 91, 101 e 127 (127 = come 125)
INIT_FIX = [(0x4018_B986, "41b9d660", "41b9d670", "id 91 +68: renderer clessidra -> barra (come 144)"),
            (0x4018_BCA4, "41b9d660", "41b9d670", "id 101 +68: renderer clessidra -> barra"),
            (0x4018_C4B0, "2f04", "2f02", "id 127 +4: prototipo bipolare -> come 125/126"),
            (0x4018_C4C4, "41b9df10", "41b9dfb0", "id 127 +20: formattatore pan -> numerico"),
            (0x4018_C4D6, "41b9db80", "41b9dc00", "id 127 +36: come 125/126"),
            (0x4018_C4E4, "41b9d660", "41b9d5d0", "id 127 +68: renderer clessidra -> barra"),
            (0x4018_AEE6, "41b9dcd0", "41b9dc00", "id 59 (GR) +36: come IN LR"),
            (0x4018_AF06, "41b9d5b0", "41b9d5d0", "id 59 (GR) +68: manopola -> barra (come IN LR)")]
RAT_STEP = 0xFE0
WSL_BINUTILS = "~/tools/m68k/root"


def sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def wsl(cmd: str) -> str:
    r = subprocess.run(["wsl.exe", "-e", "bash", "-lc", cmd], capture_output=True, text=True)
    if r.returncode:
        raise SystemExit(f"comando WSL fallito:\n{cmd}\n{r.stderr}")
    return r.stdout


def build_blob(defs: dict[str, int], incs: dict[str, str]) -> tuple[bytes, dict[str, int], list[int], str]:
    with tempfile.TemporaryDirectory(prefix="mcomp-") as tmp:
        tmp = Path(tmp)
        shutil.copy(HERE / "comp.S", tmp / "comp.S")
        for name, text in incs.items():
            (tmp / name).write_text(text, encoding="ascii")
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
    for k, v in (("thr", 0x4000), ("atk", 0x1800), ("rel", 0x2000), ("mup", 0x2000)):
        ap.add_argument(f"--{k}", type=lambda s: int(s, 0), default=v)
    ap.add_argument("--rat", type=int, default=4, help="ratio di default quando acceso (1..8)")
    ap.add_argument("--no-drive-knob", action="store_true",
                    help="non copiare il disegno della manopola di DRIVE su THR..MUP")
    a = ap.parse_args()
    params = [a.thr, a.atk, a.rel, a.mup, a.rat]

    dt = eft.unpack(REPO / "firmware" / "Digitakt_OS1.54.syx", REPO / "unpacked" / "DT1.54", ids=[3])[3]
    t = Tables(dt)
    # salvataggio: 4 parole = valore XOR default (15 bit) + un bit di RAT ciascuna; zero = default, spento
    defs = {"C_OCT": C_OCT, "D_THR": a.thr, "D_ATK": a.atk, "D_REL": a.rel, "D_MUP": a.mup,
            "GFX_ON": 0 if a.no_drive_knob else 1}
    defs.update({f"ID_{n}": i for n, _, i, _ in PARAMS})
    nl = "\n"
    tables = "".join(f"        .long   {', '.join(str(v) for v in tab[k:k + 8])}{nl}"
                     for tab in (t.attack, t.release, t.ratio) for k in range(0, len(tab), 8))
    names = "".join(f'n_{n.lower()}_s: .asciz "{n}"{nl}n_{n.lower()}_l: .asciz "{ln}"{nl}'
                    for n, ln, _, _ in PARAMS)
    incs = {"dt_tables.inc": tables, "names.inc": names}
    defs.update({f"LOG_T{i}": v for i, v in enumerate(LOG_T)})
    defs.update({f"EXP_T{i}": v for i, v in enumerate(EXP_T)})

    stock = REPO / "firmware" / "Syntakt_OS1.41.syx"
    sec3 = eft.unpack(stock, REPO / "unpacked" / stock.stem, ids=[3])[3].read_bytes()
    blob, syms, emac, dis = build_blob(defs, incs)
    end = CODE_BASE + len(blob)
    if end > FREE_END:
        raise SystemExit(f"non ci sta: {len(blob)} B (liberi {FREE_END - CODE_BASE})")
    site = sec3[HOOK - LOAD:HOOK_END - LOAD]
    if site.hex() != HOOK_ORIG:
        raise SystemExit("i byte del punto d'aggancio non sono quelli attesi")
    tramp = struct.pack(">HIHH", 0x4EB9, syms["comp_hook"], 0x6000, HOOK_END - (HOOK + 8))

    def fixed(addr: int, new: bytes, what: str, expect: str | None = None) -> dict:
        old = sec3[addr - LOAD:addr - LOAD + len(new)]
        if expect is not None and old.hex() != expect:
            raise SystemExit(f"{addr:#x}: byte inattesi {old.hex()} (attesi {expect})")
        return {"section": 3, "addr": f"{addr:#010X}", "len": len(new),
                "expect_sha256": sha(old), "hex": new.hex(), "what": what}

    ui = []
    for addr, orig, sym in UI_HOOKS:
        code = struct.pack(">HI", 0x4EF9, syms[sym]) + (b"Nq" if len(orig) == 16 else b"")
        ui.append(fixed(addr, code, f"aggancio: jmp {sym}" + (" ; nop" if len(orig) == 16 else ""), orig))
    defaults = {"THR": a.thr, "ATK": a.atk, "REL": a.rel, "MUP": a.mup, "RAT": a.rat * RAT_STEP, "GR": 0}
    for n, ln, i, mx in PARAMS:
        r = DESC + 52 * i
        ui.append(fixed(r + 8, struct.pack(">III", 0, mx, defaults[n]), f"id {i} -> {n}: min, max, default"))
        ui.append(fixed(r + 40, struct.pack(">I", syms[f"n_{n.lower()}_l"]), f"id {i}: nome lungo '{ln}'"))
        ui.append(fixed(r + 48, struct.pack(">I", syms[f"n_{n.lower()}_s"]), f"id {i}: nome breve '{n}'"))
    for addr, orig, new, what in INIT_FIX:
        ui.append(fixed(addr, bytes.fromhex(new), what, orig))

    spec = {
        "name": "master-comp", "os": "1.41", "requires": ["modarea"],
        "description": "Compressore sul master analogico (VCA del master) con l'algoritmo del "
                       "compressore della Digitakt; manopole THR ATK REL MUP RAT (0 = OFF) e misuratore GR "
                       "sulla pagina SYN della FX track; valori salvati nel kit del pattern (o globali con "
                       "SYN global). Valori di partenza " +
                       " ".join(f"{k.upper()}={getattr(a, k):#06x}" for k in ("thr", "atk", "rel", "mup")) +
                       f" RAT={a.rat}",
        "generated_by": "mods/master-comp/make_patch.py",
        "params": [f"{v:#06x}" for v in params],   # THR ATK REL MUP (0..0x7F00), RAT (1..8)
        "storage": {"kit_block": "L2+70 (puntatore 0x800030BC)", "global_block": "0x41B9D3B0",
                    "word_offsets": [12, 14, 2, 8]},
        "symbols": {k: f"{v:#010x}" for k, v in sorted(syms.items())
                    if k in ("comp_hook", "scale", "k_const", "k_state", "k_logt", "k_expt", "k_fallback",
                             "k_ids", "k_dt", "k_off", "kit_hook", "get_hook", "set_hook", "convert",
                             "fx_page", "stor", "getv", "setv", "getr", "setr", "rat_fmt", "null_mgr",
                             "meter", "meter_val", "k_meter", "k_tick", "k_shown", "k_ratstr")},
        "emac_sites": [f"{x:#010x}" for x in emac],
        "patches": [
            {"section": 3, "addr": f"{MODAREA_IMG + CODE_BASE - MODAREA_RAM:#010X}", "len": len(blob),
             "append": True, "hex": blob.hex(), "ram": f"{CODE_BASE:#010x}",
             "what": "(area mod) routine del compressore + costanti del preset + stato + tabelline"},
            {"section": 3, "addr": f"{HOOK:#010X}", "len": len(tramp),
             "expect_sha256": sha(sec3[HOOK - LOAD:HOOK - LOAD + len(tramp)]), "hex": tramp.hex(),
             "what": "trampolino: jsr comp_hook ; bra.w 0x40090562 (sostituisce limite e scrittura dei CV del master)"},
        ] + ui,
    }
    (HERE / "patch.json").write_text(json.dumps(spec, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    (REPO / "out" / "master-comp").mkdir(parents=True, exist_ok=True)
    (REPO / "out" / "master-comp" / "comp.lst").write_text(dis, encoding="utf-8")
    print(f"patch.json: {len(blob)} B in area mod a {CODE_BASE:#x}..{end:#x} (liberi ancora {FREE_END - end} B), "
          f"{len(emac)} istruzioni EMAC; trampolino {tramp.hex()}")


if __name__ == "__main__":
    main()
