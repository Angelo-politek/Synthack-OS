"""Mod perf-fx: costruisce patch.json da perf.c.

- compila perf.c per ColdFire e lo collega nell'area mod a +0x4000;
- aggancia l'avanzamento degli step del sequencer (0x4008D1CA), i tasti 13-16 di KeyboardView
  (0x4002EA92) e il dispatcher degli eventi (0x4000B420);
- pagina di impostazione di Mod A: M1..M4 (id 48..51) scelgono l'effetto di ogni tasto (testo, valore
  discreto); TRIG e DEST tolti dalla pagina; nomi "Perf FX".
- retrig quantizzato: ingresso di FUN_4002E18C (nota con retrig dei tasti) e QNT (id 47, DEST di Mod A)
  nella casella D della pagina Retrig.

    python mods/perf-fx/make_patch.py
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
sys.path[:0] = [str(REPO / "tools" / "unpack"), str(REPO / "tools" / "build")]
import eft  # noqa: E402
import modarea_layout  # noqa: E402

LOAD = 0x4000_0400
MODAREA_RAM, MODAREA_IMG = modarea_layout.RAM, modarea_layout.IMG
CODE_BASE, CODE_END = MODAREA_RAM + 0x4000, MODAREA_RAM + 0x5000
TOOLS = "~/tools/m68k/root"
CFLAGS = "-mcpu=54418 -O2 -ffreestanding -fno-builtin -nostdlib -fno-pic -fno-common -Wall -Wextra"
DESC = 0x4022_D83C                      # descrittori dei parametri: 52 B, indice = id
STEP_HOOK, STEP_ORIG = 0x4008_D1CA, "5283528e528d"      # addq d3 ; addq a6 ; addq a5
KBD_HOOK, KBD_ORIG = 0x4002_EA92, "7223b2806c00010e"    # moveq #35,d1 ; cmp.l d0,d1 ; bge.w 0x4002EBA6
EV_HOOK, EV_ORIG = 0x4000_B420, "4eb94000839e"          # jsr 0x4000839e (dispatcher degli eventi)
PAGE_HOOK, PAGE_ORIG = 0x4019_5458, "42b941ba09dc"      # clr.l 0x41BA09DC (pagina Mod A)
QR_HOOK, QR_ORIG = 0x4002_E18C, "4e56ff68700b"            # link.w fp,#-152 ; moveq #11,d0
QR_PAGE, QR_PAGE_ORIG = 0x4019_5384, "42b941ba0988"      # clr.l 0x41BA0988 (pagina Retrig, casella D)
QNT_ID = 47
DEST_MENU = (0x4004_7D7A, "722f", "72fe")              # moveq #47,d1: id sotto l'encoder = DEST di Mod A -> menu
QNT_OBJ = (0x4018_AD5A, 0x4018_AD7A, 0x4018_AD8C)          # push del prototipo, +20, +36 dell'oggetto 47
NAMES = [(0x4019_53C6, "4024fb9b", "pf_page_s", "pagina Mod A: nome breve 'PERF'"),
         (0x4019_53FA, "40251e79", "pf_page_l", "pagina Mod A: nome lungo 'Perf FX'"),
         (0x4004_0B68, "4024eb5b", "pf_on", "FUNC+15: messaggio 'Perf FX ON'")]
NFX, DEFAULTS = 12, (1, 2, 8, 11)       # effetti (perf.c); M1..M4 di default: 1/16 1/8 R1/4 HALF
# oggetti dei parametri 48..51 (M1..M4 di Mod A) nell'inizializzatore: (push del prototipo +4,
# operando della std::function +20, operando della grafica +36)
OBJ_SITES = {48: (0x4018_AD9C, 0x4018_ADBC, 0x4018_ADCA), 49: (0x4018_ADDE, 0x4018_ADFE, 0x4018_AE0C),
             50: (0x4018_AE1C, 0x4018_AE40, 0x4018_AE4E), 51: (0x4018_AE5E, 0x4018_AE7E, 0x4018_AE90)}


def sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def wsl(cmd: str) -> str:
    r = subprocess.run(["wsl.exe", "-e", "bash", "-lc", cmd], capture_output=True, text=True)
    if r.returncode:
        raise SystemExit(f"comando WSL fallito:\n{cmd}\n{r.stderr}")
    return r.stdout + r.stderr


def build_blob() -> tuple[bytes, dict[str, int], str]:
    with tempfile.TemporaryDirectory(prefix="pf-") as tmp:
        tmp = Path(tmp)
        shutil.copy(HERE / "perf.c", tmp / "perf.c")
        w = eft.to_wsl_path(tmp)
        env = f"R={TOOLS}; export LD_LIBRARY_PATH=$R/usr/lib/x86_64-linux-gnu; cd {w}; "
        gcc = "$R/usr/bin/m68k-linux-gnu-gcc-13 -B$R/usr/libexec/gcc/m68k-linux-gnu/13/ -B$R/usr/bin/m68k-linux-gnu-"
        warn = wsl(env + f"{gcc} {CFLAGS} -c perf.c -o pf.o")
        if "warning" in warn:
            raise SystemExit(warn)
        wsl(env + f"$R/usr/bin/m68k-linux-gnu-ld -N -Ttext={CODE_BASE:#x} -e pf_step -o pf.elf pf.o")
        undef = wsl(env + "$R/usr/bin/m68k-linux-gnu-nm -u pf.elf").strip()
        if undef:
            raise SystemExit(f"simboli esterni non permessi (libgcc?): {undef}")
        heads = wsl(env + "$R/usr/bin/m68k-linux-gnu-objdump -h pf.elf")
        for name, size in re.findall(r"^\s*\d+\s+(\.\S+)\s+([0-9a-f]+)", heads, re.M):
            if name in (".bss", ".sbss") and int(size, 16):
                raise SystemExit("perf.c non deve avere variabili in .bss (l'area mod e' copiata, non azzerata)")
        wsl(env + "$R/usr/bin/m68k-linux-gnu-objcopy -O binary -j .text -j .rodata -j .data pf.elf pf.bin")
        syms = {}
        for line in wsl(env + "$R/usr/bin/m68k-linux-gnu-nm pf.elf").splitlines():
            parts = line.split()
            if len(parts) == 3:
                syms[parts[2]] = int(parts[0], 16)
        dis = wsl(env + "$R/usr/bin/m68k-linux-gnu-objdump -d -m m68k:isa-c:emac pf.elf")
        blob = (tmp / "pf.bin").read_bytes()
    return blob, syms, dis


def main() -> None:
    stock = REPO / "firmware" / "Syntakt_OS1.42.syx"
    sec3 = eft.unpack(stock, REPO / "unpacked" / stock.stem, ids=[3])[3].read_bytes()
    blob, syms, dis = build_blob()
    if CODE_BASE + len(blob) > CODE_END:
        raise SystemExit(f"non ci sta: {len(blob)} B")
    if re.search(r"\b(mac|msac|movclr)\w*\b|%acc|%macsr", dis):
        raise SystemExit("perf.c non deve usare l'EMAC")

    def fixed(addr: int, new: bytes, what: str, expect: str | None = None) -> dict:
        old = sec3[addr - LOAD:addr - LOAD + len(new)]
        if expect is not None and old.hex() != expect:
            raise SystemExit(f"{addr:#x}: byte inattesi {old.hex()} (attesi {expect})")
        return {"section": 3, "addr": f"{addr:#010X}", "len": len(new), "expect_sha256": sha(old),
                "hex": new.hex(), "what": what}

    jsr = lambda sym: struct.pack(">HI", 0x4EB9, syms[sym])
    jmp = lambda sym: struct.pack(">HI", 0x4EF9, syms[sym])
    long = lambda v: struct.pack(">I", v)
    patches = [
        {"section": 3, "addr": f"{MODAREA_IMG + CODE_BASE - MODAREA_RAM:#010X}", "len": len(blob),
         "append": True, "hex": blob.hex(), "ram": f"{CODE_BASE:#010x}", "what": "(area mod) perf.c"},
        fixed(STEP_HOOK, jsr("pf_step_hook"), "avanzamento degli step: jsr pf_step_hook", STEP_ORIG),
        fixed(KBD_HOOK, jmp("pf_kbd_hook") + bytes.fromhex("4e71"),
              "tasti 13-16 (KeyboardView): jmp pf_kbd_hook ; nop", KBD_ORIG),
        fixed(EV_HOOK, jsr("pf_ev_hook"), "dispatcher degli eventi: jsr pf_ev_hook (rilascio)", EV_ORIG),
        fixed(PAGE_HOOK, jsr("pf_page_stub"), "pagina Mod A all'avvio: solo M1..M4, oggetti di tipo 0", PAGE_ORIG),
    ]
    patches += [
        fixed(QR_HOOK, jmp("qr_hook"), "FUN_4002E18C (nota con retrig dei tasti): jmp qr_hook", QR_ORIG),
        fixed(QR_PAGE, jsr("qr_page_stub"), "pagina Retrig all'avvio: QNT (47) nella casella D", QR_PAGE_ORIG),
        fixed(DEST_MENU[0], bytes.fromhex(DEST_MENU[2]),
              "encoder sull'id 47: niente menu delle destinazioni (moveq #-2), Mod B (53) invariato", DEST_MENU[1]),
        fixed(QNT_OBJ[0], bytes.fromhex("2f03"), "id 47 +4: prototipo discreto (come 48..51)", "2f04"),
        fixed(QNT_OBJ[1], long(syms["qr_proto"]), "id 47 +20: testo OFF/ON", "41b9efd0"),
        fixed(QNT_OBJ[2], long(syms["qr_gfx_proto"]), "id 47 +36: casella a testo", "41b9eaa0"),
        fixed(DESC + 52 * QNT_ID + 8, struct.pack(">III", 0, 1 << 8, 0), "id 47 -> QNT: min 0, max 1, default 0"),
        fixed(DESC + 52 * QNT_ID + 40, long(syms["qr_name_l"]), "id 47: nome lungo 'Quantize'"),
        fixed(DESC + 52 * QNT_ID + 48, long(syms["qr_name_s"]), "id 47: nome breve 'QNT'"),
    ]
    for addr, orig, sym, what in NAMES:
        patches.append(fixed(addr, long(syms[sym]), what, orig))
    for n, (pid, (proto, g20, g36)) in enumerate(OBJ_SITES.items()):
        r = DESC + 52 * pid
        patches += [
            fixed(proto, bytes.fromhex("2f03"), f"id {pid} +4: prototipo discreto (come 93)", "2f02"),
            fixed(g20, long(syms["pf_proto"]), f"id {pid} +20: testo dell'effetto", "41b9efd0"),
            fixed(g36, long(syms["pf_gfx_proto"]), f"id {pid} +36: casella a testo", "41b9ecd0"),
            fixed(r + 8, struct.pack(">III", 0, (NFX - 1) << 8, DEFAULTS[n] << 8),
                  f"id {pid}: min 0, max {NFX - 1}, default {DEFAULTS[n]}"),
            fixed(r + 40, long(syms[f"pf_name{n + 1}_l"]), f"id {pid}: nome lungo 'Perf FX {n + 1}'"),
        ]
    spec = {
        "name": "perf-fx", "os": "1.42", "requires": ["modarea"],
        "description": "Effetti di performance sul sequencer: con il modificatore Mod A (FUNC+15) i tasti 13-16 "
                       "suonano ripetizione, ripetizione all'indietro o mezza velocita' su tutte le tracce, a "
                       "tempo; l'effetto di ogni tasto si sceglie in M1..M4 della pagina Mod A (salvati con il kit). "
                       "Retrig quantizzato allo step successivo (QNT nella pagina Retrig).",
        "generated_by": "mods/perf-fx/make_patch.py",
        "symbols": {k: f"{syms[k]:#010x}" for k in ("pf_step", "pf_step_hook", "pf_kbd", "pf_kbd_hook", "pf_ev",
                                                     "pf_ev_hook", "pf_page_stub", "pf_invoke", "pf_gfx",
                                                     "pf_proto", "pf_gfx_proto", "pf_held", "pf_last",
                                                     "qr_hook", "qr_defer", "qr_invoke", "qr_page_stub",
                                                     "qr_text", "qr_gfx", "qr_state", "qr_msg", "qr_up")},
        "patches": patches,
    }
    (HERE / "patch.json").write_text(json.dumps(spec, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    (REPO / "out" / "perf-fx").mkdir(parents=True, exist_ok=True)
    (REPO / "out" / "perf-fx" / "perf.lst").write_text(dis, encoding="utf-8")
    print(f"patch.json: {len(blob)} B a {CODE_BASE:#x}..{CODE_BASE + len(blob):#x}")


if __name__ == "__main__":
    main()
