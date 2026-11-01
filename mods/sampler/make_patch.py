"""Genera mods/sampler/patch.json: SAMPLER, le machine a campioni della Digitakt (ONESHOT, WERP, REPITCH,
SLICE) al posto di SP TWINSHOT, sull'OS 1.42.

    python mods/sampler/make_patch.py         # richiede gcc m68k in WSL (CONTRIBUTING.md)

- CPU #2 (engine/): area motori di modarea7 a +OFF_ENGINE; motore 11 (SP TWINSHOT) -> SAMPLER.
- CPU #1 (main/smp_main.c): area mod a +OFF_MAIN; descrittori 497..504 riscritti (pagina della Digitakt,
  manopola G sull'indice 0x18, H = tipo di machine), testi dei valori, tempo nella RAM condivisa.
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
import engine_layout as E  # noqa: E402
import modarea_layout as M  # noqa: E402
import registry  # noqa: E402

LOAD = 0x4000_0400
OFF_MAIN = next(a for a, b, who, _ in registry.MODAREA if who == "sampler")
OFF_ENGINE = next(a for a, b, who, _ in registry.ENGINE if who == "sampler")
TOOLS = "~/tools/m68k/root"
CFLAGS = ("-mcpu=54418 -O2 -ffreestanding -fno-builtin -fno-common -Wall -Wextra -fomit-frame-pointer "
          "--param=min-pagesize=0")             # la RAM condivisa della CPU #2 parte da 0

# sezione 3 (OS 1.42)
DESC = 0x4022_D83C                      # descrittori, 52 B per id
IDS = range(497, 505)                   # SP TWINSHOT: TUN1 SMP1 FLT1 MIX TUN2 SMP2 OVER DEC1 (knobs A B C G E F H D)
STOCK_LIX = (0x12, 0x13, 0x14, 0x15, 0x16, 0x17, 0x1A, 0x19)
# formattatore (+20) nell'inizializzatore degli oggetti per-parametro: indirizzo dell'operando, prototipo stock.
# TUNE (497) tiene il suo (semitoni con segno).
PROTO_OPERANDS = {498: (0x4019_4264, 0x41B9_ECE0), 499: (0x4019_42BA, 0x41B9_EF70), 500: (0x4019_430C, 0x41B9_EF70),
                  501: (0x4019_4360, 0x41B9_EF90), 502: (0x4019_43AA, 0x41B9_ECE0), 503: (0x4019_43FC, 0x41B9_EFD0),
                  504: (0x4019_4444, 0x41B9_EDB0)}
NAME, SHORT = 0x4025_3AFB, 0x4025_3B07
BLOCK_CALL = 0x400A_4E78                # jsr 0x40095608 nell'interrupt audio: una volta per blocco
BLOCK_WAS = 0x4009_5608
# sezione 7 (identica in 1.40A, 1.41, 1.42)
RENDER_TABLE, PREP_TABLE, ENGINE = 0x4001_48F0, 0x4001_4920, 11

MAIN_SRC = ["main/smp_main.c"]
SYN_SRC = ["engine/entries.c", "engine/syn.c", "engine/pos.c", "engine/interp.c", "engine/interp_table.c"]
LDS = """ENTRY({entry})
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


def compile_blob(sources: list[str], base: int, entry: str) -> tuple[bytes, dict[str, int]]:
    with tempfile.TemporaryDirectory(prefix="sampler-") as tmp:
        tmp = Path(tmp)
        shutil.copytree(HERE / "engine", tmp / "engine")
        shutil.copytree(HERE / "main", tmp / "main")
        (tmp / "blob.ld").write_text(LDS.format(entry=entry, base=base), encoding="ascii")
        w = eft.to_wsl_path(tmp)
        env = f"R={TOOLS}; export LD_LIBRARY_PATH=$R/usr/lib/x86_64-linux-gnu; cd {w}; "
        gcc = "$R/usr/bin/m68k-linux-gnu-gcc-13 -B$R/usr/libexec/gcc/m68k-linux-gnu/13/ -B$R/usr/bin/m68k-linux-gnu-"
        srcs = " ".join(sources)
        out = wsl(env + f"{gcc} {CFLAGS} -Iengine -nostdlib -Wl,--no-warn-rwx-segments,--build-id=none -T blob.ld "
                        f"-o b.elf {srcs}")      # niente libgcc: e' codice 68020
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
    files = eft.unpack(stock, REPO / "unpacked" / stock.stem, ids=[3, 7])
    sec3, sec7 = files[3].read_bytes(), files[7].read_bytes()
    u32 = lambda s, a: struct.unpack_from(">I", s, a - LOAD)[0]          # noqa: E731
    long = lambda v: struct.pack(">I", v)                                 # noqa: E731

    main_ram = M.RAM + OFF_MAIN
    blob3, s3 = compile_blob(MAIN_SRC, main_ram, "sm_entries")
    room = next(b for a, b, who, _ in registry.MODAREA if who == "sampler")
    if s3["__bss_end"] > M.RAM + room:
        raise SystemExit(f"CPU #1: {s3['__bss_end'] - main_ram} B con il BSS, oltre lo spazio registrato")
    blob7, s7 = compile_blob(SYN_SRC, E.RAM + OFF_ENGINE, "smp_entries")
    room7 = next(b for a, b, who, _ in registry.ENGINE if who == "sampler")
    if s7["__bss_end"] > E.RAM + room7:
        raise SystemExit(f"CPU #2: {s7['__bss_end'] - E.RAM - OFF_ENGINE} B con il BSS, oltre lo spazio registrato")

    def fixed(sec: bytes, section: int, addr: int, new: bytes, what: str, expect: bytes | None = None) -> dict:
        old = sec[addr - LOAD:addr - LOAD + len(new)]
        if expect is not None and old != expect:
            raise SystemExit(f"{addr:#x}: byte inattesi {old.hex()} (attesi {expect.hex()})")
        return {"section": section, "addr": f"{addr:#010X}", "len": len(new), "expect_sha256": sha(old),
                "hex": new.hex(), "what": what}

    p = [{"section": 3, "addr": f"{M.IMG + OFF_MAIN:#010X}", "len": len(blob3), "append": True, "hex": blob3.hex(),
          "ram": f"{main_ram:#010x}", "what": "(area mod) smp_main.c: testi dei valori, nomi per tipo, tempo"}]
    proto, block, rows = struct.unpack_from(">3I", blob3, 0)
    for k, i in enumerate(IDS):
        row = DESC + 52 * i
        st = struct.unpack_from(">10I", sec3, row - LOAD)
        if (st[0], st[1]) != (44, STOCK_LIX[k]):
            raise SystemExit(f"descrittore {i}: non e' SP TWINSHOT ({st[0]}, {st[1]:#x})")
        ours = bytearray(blob3[rows - main_ram + 52 * k:rows - main_ram + 52 * (k + 1)])
        struct.pack_into(">3I", ours, 24, st[6], st[7], st[8])           # CC, NRPN e numero di SP TWINSHOT
        p.append(fixed(sec3, 3, row, bytes(ours), f"descrittore {i}: SAMPLER"))
    for i, (addr, was) in PROTO_OPERANDS.items():
        p.append(fixed(sec3, 3, addr, long(proto), f"formattatore dell'id {i}: sm_proto", long(was)))
    p += [
        fixed(sec3, 3, NAME, b"SAMPLER\x00\x00\x00\x00\x00", "nome della machine 44", b"SP TWINSHOT\x00"),
        fixed(sec3, 3, SHORT, b"SMPL\x00", "sigla della machine 44", b"SPTS\x00"),
        fixed(sec3, 3, BLOCK_CALL, b"\x4e\xb9" + long(block), "interrupt audio: sm_block (tempo nella RAM condivisa)",
              b"\x4e\xb9" + long(BLOCK_WAS)),
    ]
    prep, render = struct.unpack_from(">2I", blob7, 0)
    p += [
        fixed(sec7, 7, PREP_TABLE + 4 * ENGINE, long(prep), "motore 11: prep del SAMPLER",
              long(u32(sec7, PREP_TABLE + 4 * ENGINE))),
        fixed(sec7, 7, RENDER_TABLE + 4 * ENGINE, long(render), "motore 11: render del SAMPLER",
              long(u32(sec7, RENDER_TABLE + 4 * ENGINE))),
        {"section": 7, "addr": f"{E.IMG + OFF_ENGINE:#010X}", "len": len(blob7), "append": True, "hex": blob7.hex(),
         "ram": f"{E.RAM + OFF_ENGINE:#010x}", "what": "(area motori) SAMPLER sulla CPU #2"},
    ]
    spec = {
        "name": "sampler", "os": "1.42", "requires": ["modarea", "modarea7"],
        "description": "SAMPLER al posto di SP TWINSHOT: le machine a campioni della Digitakt (ONESHOT, WERP, "
                       "REPITCH, SLICE), riscritte. Pagina SYN TUNE PLAY BR SAMP / tre parametri del tipo / TYPE.",
        "generated_by": "mods/sampler/make_patch.py",
        "symbols": {k: f"{v:#010x}" for k, v in sorted(s3.items()) if k.startswith("sm_")}
        | {k: f"{v:#010x}" for k, v in sorted(s7.items()) if k.startswith(("syn_smp", "smp_", "sm_"))},
        "patches": p,
    }
    (HERE / "patch.json").write_text(json.dumps(spec, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"CPU #1: {len(blob3)} B (+BSS {s3['__bss_end'] - s3['__blob_end']}) a {main_ram:#x}; "
          f"CPU #2: {len(blob7)} B (+BSS {s7['__bss_end'] - s7['__blob_end']}) a {E.RAM + OFF_ENGINE:#x}")


if __name__ == "__main__":
    main()
