"""Genera mods/sy-fm4/patch.json: la machine SY FM4 di Rxuting (MIT, Rxuting/sy-fm4 a596b63) sull'OS 1.42.

    python mods/sy-fm4/make_patch.py         # richiede gcc m68k in WSL (CONTRIBUTING.md)

- CPU #1 (engine/main/main_fm4.c): area mod a +OFF_MAIN; fm4m_boot nella lista di avvio dell'area mod;
  pagina SYN 2/2 sui descrittori 254..261; salvataggio di suoni e p-lock; pagina 2/2 verso la RAM condivisa.
- CPU #2 (engine/syn, engine/fm4*.c): area motori di modarea7 a +OFF_ENGINE; motore 4 (SY TONE) -> SY FM4.

Ogni sito della sezione 3 e' quello del patcher originale per la 1.40A: rimettendo gli indirizzi della 1.40A al
posto di quelli della 1.42 i byte hanno la stessa impronta (tests/test_sy_fm4.py). La sezione 7 e' identica.
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
OFF_MAIN = 0x8180                       # area mod (registry.py)
OFF_ENGINE = 0x0000                     # area motori di modarea7 (registry.py)
BOOT_SLOT = next(n for n, who in registry.BOOT_SLOTS.items() if who == "sy-fm4")
TOOLS = "~/tools/m68k/root"
CFLAGS = "-mcpu=54418 -O2 -ffreestanding -fno-builtin -fno-common -Wall -Wextra -fomit-frame-pointer"

# sezione 3 (OS 1.42)
SRC_VPTR = 0x401C_A37C                  # vtable di SourcePageView: slot 47 (manopola -> descrittore), 19 (titolo)
SLOT_RECORD, RECORD_WAS = 47, 0x4004_4C54
SLOT_TITLE, TITLE_WAS = 19, 0x4004_4894
DESC = 0x4022_D83C                      # descrittori, 52 B per id
PAGE2_IDS = range(254, 262)             # "CC1..CC8 Value" delle tracce MIDI della Digitakt: nessuna pagina sulla Syntakt
LIX2PHYS, PHYS2LIX = 0x4023_4344, 0x4023_441C
SAVE_LEA, SAVE_BOUND = 0x400A_7436, 0x400A_7452
LOAD_LOOP = 0x400A_706A                 # 34 B: ciclo degli slot del deserializzatore
LOCK_W_A, LOCK_W_B, LOCK_R_BOUND = 0x400A_81CA, 0x400A_8336, 0x400A_803E
PHYS_TO_LIX, DMA_WAIT, INDEX_DONE = 0x400A_6D32, 0x400A_20AE, 0x400A_61B0
NAME, SHORT = 0x4025_38C7, 0x4025_38CF
# sezione 7 (identica in 1.40A, 1.41, 1.42)
RENDER_TABLE, PREP_TABLE, ENGINE = 0x4001_48F0, 0x4001_4920, 4

MAIN_SRC = ["main/main_fm4.c"]
SYN_SRC = ["syn/entries.c", "syn/fm4_syn.c", "syn/fm4_syn_tables.c", "fm4.c", "fm4_tables.c"]
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
    with tempfile.TemporaryDirectory(prefix="sy-fm4-") as tmp:
        tmp = Path(tmp)
        shutil.copytree(HERE / "engine", tmp / "engine")
        (tmp / "blob.ld").write_text(LDS.format(entry=entry, base=base), encoding="ascii")
        w = eft.to_wsl_path(tmp)
        env = f"R={TOOLS}; export LD_LIBRARY_PATH=$R/usr/lib/x86_64-linux-gnu; cd {w}; "
        gcc = "$R/usr/bin/m68k-linux-gnu-gcc-13 -B$R/usr/libexec/gcc/m68k-linux-gnu/13/ -B$R/usr/bin/m68k-linux-gnu-"
        srcs = " ".join(f"engine/{s}" for s in sources)
        out = wsl(env + f"{gcc} {CFLAGS} -Iengine -nostdlib -Wl,--no-warn-rwx-segments,--build-id=none -T blob.ld -o b.elf {srcs} -lgcc")
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
    blob3, s3 = compile_blob(MAIN_SRC, main_ram, "fm4m_entries")
    room = next(b for a, b, who, _ in registry.MODAREA if who == "sy-fm4" and a == OFF_MAIN)
    if s3["__bss_end"] > M.RAM + room:
        raise SystemExit(f"CPU #1: {s3['__bss_end'] - main_ram} B con il BSS, oltre lo spazio registrato")
    blob7, s7 = compile_blob(SYN_SRC, E.RAM + OFF_ENGINE, "fm4_entries")
    room7 = next(b for a, b, who, _ in registry.ENGINE if who == "sy-fm4")
    if s7["__bss_end"] > E.RAM + room7:
        raise SystemExit(f"CPU #2: {s7['__bss_end'] - E.RAM - OFF_ENGINE} B con il BSS, oltre lo spazio registrato")

    def fixed(sec: bytes, section: int, addr: int, new: bytes, what: str, expect: bytes | None = None) -> dict:
        old = sec[addr - LOAD:addr - LOAD + len(new)]
        if expect is not None and old != expect:
            raise SystemExit(f"{addr:#x}: byte inattesi {old.hex()} (attesi {expect.hex()})")
        return {"section": section, "addr": f"{addr:#010X}", "len": len(new), "expect_sha256": sha(old),
                "hex": new.hex(), "what": what}

    p = [{"section": 3, "addr": f"{M.IMG + OFF_MAIN:#010X}", "len": len(blob3), "append": True, "hex": blob3.hex(),
          "ram": f"{main_ram:#010x}", "what": "(area mod) main_fm4.c: pagina 2/2, salvataggio, RAM condivisa"},
         {"section": 3, "addr": f"{M.boot_slot(BOOT_SLOT):#010X}", "len": 4, "append": True,
          "hex": long(s3["fm4m_boot"]).hex(), "ram": f"{M.RAM + M.BOOT_LIST + 4 * BOOT_SLOT:#010x}",
          "what": "(area mod) lista di avvio: fm4m_boot (tabelle degli slot e delle lane)"}]
    entries = struct.unpack_from(">2I", blob3, 0)
    p.append(fixed(sec3, 3, SRC_VPTR + 4 * SLOT_RECORD, long(entries[0]), "SourcePageView slot 47: pagina SYN 2/2",
                   long(RECORD_WAS)))
    p.append(fixed(sec3, 3, SRC_VPTR + 4 * SLOT_TITLE, long(entries[1]), "SourcePageView slot 19: titolo 1/2, 2/2",
                   long(TITLE_WAS)))
    recs = s3["fm4m_records"] - main_ram
    for k, i in enumerate(PAGE2_IDS):
        row = DESC + 52 * i
        group, iid = struct.unpack_from(">ii", sec3, row - LOAD)
        if (group, iid) != (0x39, 0x19 + k):
            raise SystemExit(f"descrittore {i}: non e' il 'CC{k + 1} Value' delle tracce MIDI ({group:#x}, {iid:#x})")
        rec = blob3[recs + 52 * k:recs + 52 * (k + 1)]
        if struct.unpack_from(">I", rec, 32)[0] != i:
            raise SystemExit(f"record {k}: id {struct.unpack_from('>I', rec, 32)[0]}, atteso {i}")
        p.append(fixed(sec3, 3, row, rec, f"descrittore {i}: SY FM4 pagina 2/2"))
    p += [
        fixed(sec3, 3, SAVE_LEA, b"\x41\xf9" + long(s3["fm4m_sound_l2p"]), "salvataggio del suono: tabella degli slot",
              b"\x41\xf9" + long(LIX2PHYS)),
        fixed(sec3, 3, SAVE_BOUND, b"\x72\x7c", "salvataggio del suono: fino all'indice 0x3d", b"\x72\x6c"),
        fixed(sec3, 3, LOAD_LOOP, b"\x4e\xb9" + long(s3["fm4m_load_shim"]) + b"\x43\xf9" + long(s3["fm4m_sound_p2l"])
              + b"\x4e\x71" * 11, "caricamento del suono: fm4m_load_shim (default di 2/2 per i suoni stock)"),
        fixed(sec3, 3, LOCK_W_A, b"\x4b\xf9" + long(s3["fm4m_lane_of_lix"]), "p-lock, scrittura A: lane di 2/2",
              b"\x4b\xf9" + long(LIX2PHYS)),
        fixed(sec3, 3, LOCK_W_B, b"\x45\xf9" + long(s3["fm4m_lane_of_lix"]), "p-lock, scrittura B: lane di 2/2",
              b"\x45\xf9" + long(LIX2PHYS)),
        fixed(sec3, 3, LOCK_R_BOUND, b"\x7a\x57", "p-lock, lettura: lane fino a 0x57", b"\x7a\x46"),
        fixed(sec3, 3, PHYS_TO_LIX, b"\x4e\xf9" + long(s3["fm4m_phys_to_lix"]), "slot/lane -> indice logico"),
        fixed(sec3, 3, DMA_WAIT, b"\x4e\xf9" + long(s3["fm4m_dma_wait"]), "attesa eDMA 47: pagina 2/2 nella RAM condivisa"),
        fixed(sec3, 3, INDEX_DONE, b"\x4e\xb9" + long(s3["fm4m_index_done"]), "tabelle degli indici: default di 2/2"),
        fixed(sec3, 3, NAME, b"SY FM4\x00\x00", "nome della machine 4", b"SY TONE\x00"),
        fixed(sec3, 3, SHORT, b"SYF4\x00", "sigla della machine 4", b"SYTN\x00"),
    ]
    prep, render = struct.unpack_from(">2I", blob7, 0)
    p += [
        fixed(sec7, 7, PREP_TABLE + 4 * ENGINE, long(prep), "motore 4: prep di SY FM4", long(u32(sec7, PREP_TABLE + 16))),
        fixed(sec7, 7, RENDER_TABLE + 4 * ENGINE, long(render), "motore 4: render di SY FM4",
              long(u32(sec7, RENDER_TABLE + 16))),
        {"section": 7, "addr": f"{E.IMG + OFF_ENGINE:#010X}", "len": len(blob7), "append": True, "hex": blob7.hex(),
         "ram": f"{E.RAM + OFF_ENGINE:#010x}", "what": "(area motori) SY FM4 sulla CPU #2"},
    ]
    spec = {
        "name": "sy-fm4", "os": "1.42", "requires": ["modarea", "modarea7"],
        "description": "SY FM4 (Rxuting, MIT): SY TONE diventa una machine FM a 4 operatori. ALGO 0 = SY TONE, "
                       "ALGO 1-11 algoritmi FM; seconda pagina SYN (ALGO, RAT3, LEV3, DEC3, DET, RAT4, LEV4, DEC4), "
                       "salvata con il suono e con i p-lock.",
        "generated_by": "mods/sy-fm4/make_patch.py",
        "upstream": "https://github.com/Rxuting/sy-fm4/tree/a596b6393fc43582fd3ae0234ac04e198b779edb",
        "symbols": {k: f"{v:#010x}" for k, v in sorted(s3.items()) if k.startswith("fm4m_")}
        | {k: f"{v:#010x}" for k, v in sorted(s7.items()) if k.startswith(("syn_fm4", "fm4_entries"))},
        "patches": p,
    }
    (HERE / "patch.json").write_text(json.dumps(spec, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"CPU #1: {len(blob3)} B (+BSS {s3['__bss_end'] - s3['__blob_end']}) a {main_ram:#x}; "
          f"CPU #2: {len(blob7)} B (+BSS {s7['__bss_end'] - s7['__blob_end']}) a {E.RAM + OFF_ENGINE:#x}")


if __name__ == "__main__":
    main()
