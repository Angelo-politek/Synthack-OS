"""Genera mods/syn-pages/patch.json: pagine SYN proprie per una machine (vista SRC), sull'OS 1.42.

    python mods/syn-pages/make_patch.py       # richiede gcc m68k in WSL (CONTRIBUTING.md)

synpages.c nell'area mod a synpages_layout.OFF; la tabella delle machine (synpages_layout.TABLE) e' il primo
oggetto del blob. Slot della vtable di SourcePageView: 47 (manopola -> descrittore), 19 (titolo), 4 (disegno).
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
import synpages_layout as SP  # noqa: E402

LOAD = 0x4000_0400
TOOLS = "~/tools/m68k/root"
CFLAGS = "-mcpu=54418 -O2 -ffreestanding -fno-builtin -fno-common -Wall -Wextra -fomit-frame-pointer"
SRC_VPTR = 0x401C_A37C                  # vtable di SourcePageView
SLOTS = {47: ("sp_record", 0x4004_4C54, "manopola -> descrittore, pagine della machine"),
         19: ("sp_title", 0x4004_4894, "titolo della pagina (std::string)"),
         4: ("sp_draw", 0x4003_0B84, "disegno: pagina stock, poi quello della machine")}
LDS = """ENTRY(sp_machines)
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
    with tempfile.TemporaryDirectory(prefix="syn-pages-") as tmp:
        tmp = Path(tmp)
        for f in ("synpages.c", "synpages.h"):
            shutil.copy(HERE / f, tmp / f)
        (tmp / "blob.ld").write_text(LDS.format(base=base), encoding="ascii")
        w = eft.to_wsl_path(tmp)
        env = f"R={TOOLS}; export LD_LIBRARY_PATH=$R/usr/lib/x86_64-linux-gnu; cd {w}; "
        gcc = "$R/usr/bin/m68k-linux-gnu-gcc-13 -B$R/usr/libexec/gcc/m68k-linux-gnu/13/ -B$R/usr/bin/m68k-linux-gnu-"
        out = wsl(env + f"{gcc} {CFLAGS} -nostdlib -Wl,--no-warn-rwx-segments,--build-id=none -T blob.ld "
                        f"-o b.elf synpages.c")
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

    blob, s = compile_blob(SP.TABLE)
    if s["sp_machines"] != SP.TABLE:
        raise SystemExit(f"tabella a {s['sp_machines']:#x}, attesa a {SP.TABLE:#x}")
    room = next(b for a, b, who, _ in registry.MODAREA if who == "syn-pages")
    if s["__bss_end"] > M.RAM + room:
        raise SystemExit(f"{s['__bss_end'] - SP.TABLE} B con il BSS, oltre lo spazio registrato")

    p = [{"section": 3, "addr": f"{M.IMG + SP.OFF:#010X}", "len": len(blob), "append": True, "hex": blob.hex(),
          "ram": f"{SP.TABLE:#010x}", "what": "(area mod) synpages.c: tabella delle machine, vista SRC"}]
    for slot, (sym, was, what) in sorted(SLOTS.items()):
        a = SRC_VPTR + 4 * slot
        old = sec3[a - LOAD:a - LOAD + 4]
        if old != long(was):
            raise SystemExit(f"slot {slot}: {old.hex()}, atteso {was:#x}")
        p.append({"section": 3, "addr": f"{a:#010X}", "len": 4, "expect_sha256": sha(old),
                  "hex": long(s[sym]).hex(), "what": f"SourcePageView slot {slot}: {what}"})
    spec = {
        "name": "syn-pages", "os": "1.42", "requires": ["modarea"],
        "description": "Pagine SYN proprie per una machine: la vista SRC chiede alla machine registrata quante "
                       "pagine ha, il descrittore di ogni manopola, il titolo e cosa disegnare.",
        "generated_by": "mods/syn-pages/make_patch.py",
        "symbols": {k: f"{v:#010x}" for k, v in sorted(s.items()) if k.startswith("sp_")},
        "patches": p,
    }
    (HERE / "patch.json").write_text(json.dumps(spec, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"{len(blob)} B (+BSS {s['__bss_end'] - s['__blob_end']}) a {SP.TABLE:#x}")


if __name__ == "__main__":
    main()
