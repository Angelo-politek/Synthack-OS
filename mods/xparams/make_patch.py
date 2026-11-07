"""Genera mods/xparams/patch.json: indici logici 0x36..0x3d di ogni traccia salvati, con i p-lock e verso la CPU #2.

    python mods/xparams/make_patch.py         # richiede gcc m68k in WSL (CONTRIBUTING.md)

xparams.c nell'area mod a xparams_layout.OFF; la sua tabella (xparams_layout.TABLE) e' il primo oggetto del blob;
xp_boot nella lista di avvio. I siti sono quelli del patcher di SY FM4 (Rxuting, MIT), da cui viene il codice:
tests/test_xparams.py ne controlla le impronte riportate alla 1.40A.
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
import modarea_layout as M  # noqa: E402
import registry  # noqa: E402
import xparams_layout as XP  # noqa: E402

LOAD = 0x4000_0400
TOOLS = "~/tools/m68k/root"
CFLAGS = "-mcpu=54418 -Os -ffreestanding -fno-builtin -fno-common -Wall -Wextra -fomit-frame-pointer"
BOOT_SLOT = next(n for n, who in registry.BOOT_SLOTS.items() if who == "xparams")
LIX2PHYS = 0x4023_4344
SAVE_LEA, SAVE_BOUND = 0x400A_7436, 0x400A_7452
LOAD_LOOP = 0x400A_706A                 # 34 B: ciclo degli slot del deserializzatore
LOCK_W_A, LOCK_W_B, LOCK_R_BOUND = 0x400A_81CA, 0x400A_8336, 0x400A_803E
PHYS_TO_LIX, DMA_WAIT = 0x400A_6D32, 0x400A_20AE
LDS = """ENTRY(xp_table)
SECTIONS
{{
    . = {base:#x};
    .text : {{
        KEEP(*(.entries))
        *(.text .text.*)
        *(.rodata .rodata.*)
        . = ALIGN(4);
        *(.data .data.*)
        . = ALIGN(4);
    }}
    __blob_end = .;
    .bss (NOLOAD) : {{
        *(.bss .bss.* COMMON)
        . = ALIGN(4);
    }}
    __bss_end = .;
    /DISCARD/ : {{ *(.comment) *(.note*) *(.eh_frame*) }}
}}
"""


def sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def wsl(cmd: str) -> str:
    r = subprocess.run(["wsl.exe", "-e", "bash", "-lc", cmd], capture_output=True, text=True)
    if r.returncode:
        raise SystemExit(f"comando WSL fallito:\n{cmd}\n{r.stderr}")
    return r.stdout + r.stderr


def compile_blob(base: int) -> tuple[bytes, dict[str, int]]:
    with tempfile.TemporaryDirectory(prefix="xparams-") as tmp:
        tmp = Path(tmp)
        for f in ("xparams.c", "xparams.h"):
            shutil.copy(HERE / f, tmp / f)
        (tmp / "blob.ld").write_text(LDS.format(base=base), encoding="ascii")
        w = eft.to_wsl_path(tmp)
        env = f"R={TOOLS}; export LD_LIBRARY_PATH=$R/usr/lib/x86_64-linux-gnu; cd {w}; "
        gcc = "$R/usr/bin/m68k-linux-gnu-gcc-13 -B$R/usr/libexec/gcc/m68k-linux-gnu/13/ -B$R/usr/bin/m68k-linux-gnu-"
        out = wsl(env + f"{gcc} {CFLAGS} -nostdlib -Wl,--no-warn-rwx-segments,--build-id=none -T blob.ld "
                        f"-o b.elf xparams.c")
        if "warning" in out:
            raise SystemExit(out)
        wsl(env + "$R/usr/bin/m68k-linux-gnu-objcopy -O binary --only-section=.text b.elf b.bin")
        syms = {}
        for line in wsl(env + "$R/usr/bin/m68k-linux-gnu-nm b.elf").splitlines():
            parts = line.split()
            if len(parts) == 3:
                syms[parts[2]] = int(parts[0], 16)
        blob = (tmp / "b.bin").read_bytes()
    if base + len(blob) != syms["__blob_end"]:
        raise SystemExit("il blob non corrisponde alla mappa del linker")
    return blob, syms


def main() -> None:
    stock = REPO / "firmware" / "Syntakt_OS1.42.syx"
    sec3 = eft.unpack(stock, REPO / "unpacked" / stock.stem, ids=[3])[3].read_bytes()
    long = lambda v: struct.pack(">I", v)                                 # noqa: E731

    blob, s = compile_blob(XP.TABLE)
    if s["xp_table"] != XP.TABLE:
        raise SystemExit(f"tabella a {s['xp_table']:#x}, attesa a {XP.TABLE:#x}")
    room = next(b for a, b, who, _ in registry.MODAREA if who == "xparams")
    if s["__bss_end"] > M.RAM + room:
        raise SystemExit(f"{s['__bss_end'] - XP.TABLE} B con il BSS, oltre lo spazio registrato")

    def fixed(addr: int, new: bytes, what: str, expect: bytes | None = None) -> dict:
        old = sec3[addr - LOAD:addr - LOAD + len(new)]
        if expect is not None and old != expect:
            raise SystemExit(f"{addr:#x}: byte inattesi {old.hex()} (attesi {expect.hex()})")
        return {"section": 3, "addr": f"{addr:#010X}", "len": len(new), "expect_sha256": sha(old),
                "hex": new.hex(), "what": what}

    p = [{"section": 3, "addr": f"{M.IMG + XP.OFF:#010X}", "len": len(blob), "append": True, "hex": blob.hex(),
          "ram": f"{XP.TABLE:#010x}", "what": "(area mod) xparams.c: tabelle, caricamento, copia verso la CPU #2"},
         {"section": 3, "addr": f"{M.boot_slot(BOOT_SLOT):#010X}", "len": 4, "append": True,
          "hex": long(s["xp_boot"]).hex(), "ram": f"{M.RAM + M.BOOT_LIST + 4 * BOOT_SLOT:#010x}",
          "what": "(area mod) lista di avvio: xp_boot (tabelle degli slot e delle lane)"},
         fixed(SAVE_LEA, b"\x41\xf9" + long(s["xp_sound_l2p"]), "salvataggio del suono: tabella degli slot",
               b"\x41\xf9" + long(LIX2PHYS)),
         fixed(SAVE_BOUND, bytes.fromhex("0c40008c"), "salvataggio del suono: fino all'indice 0x45 (cmpi.w #0x8c,d0)",
               bytes.fromhex("726cb280")),
         fixed(LOAD_LOOP, b"\x4e\xb9" + long(s["xp_load_shim"]) + b"\x43\xf9" + long(s["xp_sound_p2l"])
               + b"\x4e\x71" * 11, "caricamento del suono: xp_load_shim (valori della machine per i suoni stock)"),
         fixed(LOCK_W_A, b"\x4b\xf9" + long(s["xp_lane_of_lix"]), "p-lock, scrittura A: lane degli indici extra",
               b"\x4b\xf9" + long(LIX2PHYS)),
         fixed(LOCK_W_B, b"\x45\xf9" + long(s["xp_lane_of_lix"]), "p-lock, scrittura B: lane degli indici extra",
               b"\x45\xf9" + long(LIX2PHYS)),
         fixed(LOCK_R_BOUND, bytes.fromhex("7a5f"), "p-lock, lettura: lane fino a 0x5f", bytes.fromhex("7a46")),
         fixed(PHYS_TO_LIX, b"\x4e\xf9" + long(s["xp_phys_to_lix"]), "slot/lane -> indice logico"),
         fixed(DMA_WAIT, b"\x4e\xf9" + long(s["xp_dma_wait"]), "attesa eDMA 47: indici extra nella RAM condivisa")]
    spec = {
        "name": "xparams", "os": "1.42", "requires": ["modarea"],
        "description": "Indici logici 0x36..0x3d di ogni traccia: salvati con il suono, con i p-lock, copiati a ogni "
                       "blocco nella RAM condivisa (0x700) per i motori della CPU #2. Da SY FM4 (Rxuting, MIT).",
        "generated_by": "mods/xparams/make_patch.py",
        "symbols": {k: f"{v:#010x}" for k, v in sorted(s.items()) if k.startswith("xp_")},
        "patches": p,
    }
    (HERE / "patch.json").write_text(json.dumps(spec, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"{len(blob)} B (+BSS {s['__bss_end'] - s['__blob_end']}) a {XP.TABLE:#x}")


if __name__ == "__main__":
    main()
