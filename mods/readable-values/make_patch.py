"""Mod readable-values: costruisce patch.json da rv.c.

- compila rv.c per ColdFire (gcc m68k, -mcpu=54418) e lo collega nell'area mod a 0x46002000;
- per ogni id gestito, l'operando del `pea <prototipo>` (campo +20) nell'inizializzatore degli
  oggetti per-parametro passa dal formattatore numerico dell'OS (0x41B9DFB0) a rv_proto.

    python mods/readable-values/make_patch.py
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
MODAREA_RAM, MODAREA_IMG, MODAREA_SIZE = 0x4600_0000, 0x4034_8000, 0x8000
CODE_BASE = MODAREA_RAM + 0x2000        # dopo master-comp (offset 0..0x1FFF)
CODE_END = MODAREA_RAM + 0x4000
# formattatori dell'OS (prototipi in BSS)
P_PLAIN, P_NUM, P_PAN, P_TIME, P_HOLD, P_SEND = 0x41B9_DFD0, 0x41B9_DFB0, 0x41B9_DF10, 0x41B9_DDB0, 0x41B9_DDC0, 0x41B9_DF30
# id logico -> (indirizzo dell'operando del prototipo (+20) nell'inizializzatore 0x401885D2.., prototipo atteso)
PROTO_OPERANDS = {
    10: (0x4018_A1FE, P_PLAIN),   # LEV di traccia
    58: (0x4018_AE88, P_NUM),     # filtro: FREQ (move.l)
    63: (0x4018_B08C, P_PLAIN),   # filtro: DEL
    64: (0x4018_B0DC, P_PLAIN),   # filtro: ATK
    65: (0x4018_B130, P_TIME),    # filtro: DEC (move.l)
    66: (0x4018_B180, P_PLAIN),   # filtro: SUS
    67: (0x4018_B1D0, P_TIME),    # filtro: REL
    70: (0x4018_B2C8, P_PLAIN),   # filtro base-width: BASE
    71: (0x4018_B318, P_PLAIN),   # filtro base-width: WDTH
    73: (0x4018_B3BC, P_PLAIN),   # ampiezza: ATK (move.l)
    74: (0x4018_B40C, P_HOLD),    # ampiezza: HOLD
    75: (0x4018_B45C, P_TIME),    # ampiezza: DEC
    76: (0x4018_B4AC, P_PLAIN),   # ampiezza: SUS
    77: (0x4018_B500, P_TIME),    # ampiezza: REL (move.l)
    78: (0x4018_B566, P_SEND),    # mandata DEL
    79: (0x4018_B5B6, P_SEND),    # mandata REV
    81: (0x4018_B64E, P_NUM),     # VOL
    110: (0x4018_BF56, P_NUM),    # delay HPF (move.l)
    111: (0x4018_BFA8, P_NUM),    # delay LPF
    112: (0x4018_BFFA, P_NUM),    # delay -> reverb
    113: (0x4018_C04C, P_NUM),    # delay mix (alias)
    114: (0x4018_C0A2, P_NUM),    # delay mix (move.l)
    116: (0x4018_C146, P_NUM),    # reverb pre-delay
    118: (0x4018_C1EE, P_NUM),    # reverb: FREQ dello shelving (move.l)
    119: (0x4018_C240, P_NUM),    # reverb: GAIN dello shelving
    120: (0x4018_C292, P_NUM),    # reverb HPF
    121: (0x4018_C2E4, P_NUM),    # reverb LPF
    122: (0x4018_C33A, P_NUM),    # reverb mix (alias, move.l)
    123: (0x4018_C38C, P_NUM),    # reverb mix
    125: (0x4018_C430, P_NUM),    # IN (alias; IN R in dual mono)
    126: (0x4018_C47A, P_NUM),    # IN LR
    129: (0x4018_C558, P_NUM),    # ingresso esterno: mandata DEL
    130: (0x4018_C5A2, P_NUM),    # ingresso esterno: mandata REV
    133: (0x4018_C696, P_NUM),    # FX track: FREQ (filtro analogico)
    140: (0x4018_C906, P_PLAIN),  # FX track: SUS del filtro
    145: (0x4018_CA9E, P_PLAIN),  # FX track: ATK (move.l)
    146: (0x4018_CAEE, P_HOLD),   # FX track: HOLD
    147: (0x4018_CB3E, P_TIME),   # FX track: DEC
    148: (0x4018_CB8E, P_PLAIN),  # FX track: SUS
    149: (0x4018_CBEC, P_PLAIN),  # FX track: REL (move.l)
    151: (0x4018_CCDE, P_SEND),   # FX track: mandata DEL
    152: (0x4018_CD30, P_SEND),   # FX track: mandata REV
    154: (0x4018_CDD0, P_NUM),    # FX track: VOL (move.l)
}

TOOLS = "~/tools/m68k/root"
CFLAGS = "-mcpu=54418 -O2 -ffreestanding -fno-builtin -nostdlib -fno-pic -fno-common -Wall -Wextra"


def sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def wsl(cmd: str) -> str:
    r = subprocess.run(["wsl.exe", "-e", "bash", "-lc", cmd], capture_output=True, text=True)
    if r.returncode:
        raise SystemExit(f"comando WSL fallito:\n{cmd}\n{r.stderr}")
    return r.stdout + r.stderr


def build_blob() -> tuple[bytes, dict[str, int], str]:
    with tempfile.TemporaryDirectory(prefix="rv-") as tmp:
        tmp = Path(tmp)
        shutil.copy(HERE / "rv.c", tmp / "rv.c")
        w = eft.to_wsl_path(tmp)
        env = f"R={TOOLS}; export LD_LIBRARY_PATH=$R/usr/lib/x86_64-linux-gnu; cd {w}; "
        gcc = "$R/usr/bin/m68k-linux-gnu-gcc-13 -B$R/usr/libexec/gcc/m68k-linux-gnu/13/ -B$R/usr/bin/m68k-linux-gnu-"
        warn = wsl(env + f"{gcc} {CFLAGS} -c rv.c -o rv.o")
        if "warning" in warn:
            raise SystemExit(warn)
        wsl(env + f"$R/usr/bin/m68k-linux-gnu-ld -N -Ttext={CODE_BASE:#x} -e rv_invoke -o rv.elf rv.o")
        undef = wsl(env + "$R/usr/bin/m68k-linux-gnu-nm -u rv.elf").strip()
        if undef:
            raise SystemExit(f"simboli esterni non permessi (libgcc?): {undef}")
        heads = wsl(env + "$R/usr/bin/m68k-linux-gnu-objdump -h rv.elf")
        for name, size in re.findall(r"^\s*\d+\s+(\.\S+)\s+([0-9a-f]+)", heads, re.M):
            if name in (".bss", ".sbss") and int(size, 16):
                raise SystemExit("rv.c non deve avere variabili in .bss (l'area mod e' copiata, non azzerata)")
        wsl(env + "$R/usr/bin/m68k-linux-gnu-objcopy -O binary -j .text -j .rodata -j .data rv.elf rv.bin")
        syms = {}
        for line in wsl(env + "$R/usr/bin/m68k-linux-gnu-nm rv.elf").splitlines():
            parts = line.split()
            if len(parts) == 3:
                syms[parts[2]] = int(parts[0], 16)
        dis = wsl(env + "$R/usr/bin/m68k-linux-gnu-objdump -d -m m68k:isa-c:emac rv.elf")
        blob = (tmp / "rv.bin").read_bytes()
    return blob, syms, dis


def main() -> None:
    stock = REPO / "firmware" / "Syntakt_OS1.41.syx"
    sec3 = eft.unpack(stock, REPO / "unpacked" / stock.stem, ids=[3])[3].read_bytes()
    blob, syms, dis = build_blob()
    if CODE_BASE + len(blob) > CODE_END:
        raise SystemExit(f"non ci sta: {len(blob)} B (spazio {CODE_END - CODE_BASE})")
    if re.search(r"\b(mac|msac|movclr)\w*\b|%acc|%macsr", dis):
        raise SystemExit("rv.c non deve usare l'EMAC (stato condiviso con l'audio)")

    patches = [{"section": 3, "addr": f"{MODAREA_IMG + CODE_BASE - MODAREA_RAM:#010X}", "len": len(blob),
                "append": True, "hex": blob.hex(), "ram": f"{CODE_BASE:#010x}",
                "what": "(area mod) formattatori con unita' reali (rv.c)"}]
    for pid, (addr, proto) in sorted(PROTO_OPERANDS.items()):
        old = sec3[addr - LOAD:addr - LOAD + 4]
        if struct.unpack(">I", old)[0] != proto:
            raise SystemExit(f"id {pid}: a {addr:#x} non c'e' il prototipo atteso {proto:#x}")
        patches.append({"section": 3, "addr": f"{addr:#010X}", "len": 4, "expect_sha256": sha(old),
                        "hex": struct.pack(">I", syms["rv_proto"]).hex(),
                        "what": f"id {pid} +20: formattatore {proto:#x} -> rv_proto"})
    spec = {
        "name": "readable-values", "os": "1.41", "requires": ["modarea"],
        "description": "Valori in unita' reali (Hz, dB, ms, %) calcolati dagli stessi dati che usa il DSP: "
                       "delay e reverb, livelli e mandate, inviluppi delle tracce digitali.",
        "generated_by": "mods/readable-values/make_patch.py",
        "ids": sorted(PROTO_OPERANDS),
        "symbols": {k: f"{syms[k]:#010x}" for k in ("rv_invoke", "rv_mgr", "rv_proto")},
        "patches": patches,
    }
    (HERE / "patch.json").write_text(json.dumps(spec, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    (REPO / "out" / "readable-values").mkdir(parents=True, exist_ok=True)
    (REPO / "out" / "readable-values" / "rv.lst").write_text(dis, encoding="utf-8")
    print(f"patch.json: {len(blob)} B a {CODE_BASE:#x}..{CODE_BASE + len(blob):#x}; {len(PROTO_OPERANDS)} id")


if __name__ == "__main__":
    main()
