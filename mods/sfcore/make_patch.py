"""Genera mods/sfcore/patch.json: il sottoinsieme del core di Synfact (bus degli eventi, transazioni native, host API)
per i port di Synfact sulla 1.42 (README.md).

    python mods/sfcore/make_patch.py          # richiede gcc m68k in WSL (CONTRIBUTING.md)

Gli adattatori audio, dei file e nativi hanno un "service": la build li installa solo se una mod li usa
("uses": ["sfcore:native"], tools/build/build.py). Quelli dell'interfaccia (tick, draw, key, enc) sempre.

SPDX-License-Identifier: GPL-2.0-or-later
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
import modarea_layout  # noqa: E402
import idspace_layout as IDS  # noqa: E402
import registry  # noqa: E402

LOAD = 0x4000_0400
TABLE = modarea_layout.RAM + registry.SFCORE_TABLE
OFFSET, END = next((a, b) for a, b, who, _ in registry.MODAREA if who == "sfcore" and a != registry.SFCORE_TABLE)
CODE_BASE = modarea_layout.RAM + OFFSET
SLOT = next(s for s, who in registry.BOOT_SLOTS.items() if who == "sfcore")
TOOLS = "~/tools/m68k/root"
CFLAGS = (f"-DIDS_CODE={IDS.CODE:#x}u " "-mcpu=54418 -Os -ffreestanding -fno-builtin -nostdlib -fno-pic -fno-common -fno-jump-tables "
          "-fno-tree-loop-distribute-patterns -Iinclude -Wall -Wextra -Wno-unused-parameter")
NOP = b"\x4e\x71"
UI, RENDER, MIX, FS, NATIVE, PAGES = (None, "sfcore:render_in", "sfcore:main_mix", "sfcore:fs", "sfcore:native",
                                      "sfcore:pages")
# un servizio per operazione dove una mod ne usa una sola: lfo3 vuole l'operazione LFO (interrupt) e il setter del
# Sound (interfaccia), non gli altri 11 adattatori (~900 cicli a blocco anche senza iscritti)
LFO, SOUND_SET = "sfcore:lfo", "sfcore:sound_set"
# (indirizzo 1.42, byte stock, istruzione, simbolo, servizio, descrizione); Synfact: mods/core-st/mod.json (1.41)
SITES = [
    (0x4000_A220, "4eb94010095c", "jsr", "core_tick", UI, "ev_tick: controllo del ridisegno a 30 Hz"),
    (0x4000_A286, "4eb940100992", "jsr", "core_draw", UI, "ev_draw: sopra ogni schermata composta"),
    (0x4000_839E, "4feffff048d70c0c", "jmp", "core_key", UI, "ev_key: ingresso del dispatcher dei tasti (dopo perf-fx)"),
    (0x4000_B468, "4eb9400083f0", "jsr", "core_enc", UI, "ev_enc: dispatcher degli encoder"),
    (0x400A_38D6, "203c7fffffff", "jmp", "core_render_in", RENDER, "ev_render_in: interrupt audio, dopo il prologo"),
    (0x4008_FB86, "487980003950", "jsr", "core_main_mix", MIX, "ev_main_mix: bus del master (dopo fx3)"),
    (0x400B_620C, "266e000c280e", "jmp", "core_fs_write", FS, "ev_fs_write: Data RPC, dopo il prologo (dopo long-samples)"),
    (0x4010_BA9E, "4eb94019c5ce", "jsr", "core_fs_written", FS, "ev_fs_written: DataWriteClose completato"),
    (0x4008_B8FA, "4fefffc848d77cfc", "jmp", "core_native_trig", NATIVE, "TRIG"),
    (0x4008_D03C, "4eb94011a80c", "jsr", "core_native_enqueue", NATIVE, "ENQUEUE"),
    (0x400A_7A44, "4feffff448d70c04", "jmp", "core_native_header_load", NATIVE, "HEADER_LOAD"),
    (0x400B_3746, "206f00044a88", "jmp", "core_native_header_reset", NATIVE, "HEADER_RESET"),
    (0x400A_4B56, "49f9800046884285", "jmp", "core_native_publish", NATIVE, "PUBLISH"),
    (0x4011_A8F8, "2479444df4344a8a", "jmp", "core_native_immediate", NATIVE, "IMMEDIATE"),
    (0x400A_4C46, "7119e1883140003e", "jmp", "core_native_type", NATIVE, "TYPE"),
    (0x400A_4D0E, "712b0da07225b280", "jmp", "core_native_src_type", NATIVE, "TYPE (sorgente)"),
    (0x4001_3304, "4e56ffd848d704fc", "jmp", "core_native_sound_set", SOUND_SET, "SOUND_ALLOWED e parametri del provider"),
    (0x4002_559C, "246f002c242f0030", "jmp", "core_native_machine_select", NATIVE, "MACHINE_ALLOWED (dopo sampler)"),
    (0x4009_7B74, "4fefffc448d77cfc", "jmp", "core_native_modulation", NATIVE, "MODULATION"),
    (0x4011_942A, "4fefffc048d77cfc", "jmp", "core_native_lfo", LFO, "LFO"),
    (0x400A_42B6, "202a00247201", "jmp", "core_native_note_accept", NATIVE, "NOTE_ACCEPT"),
    # pagine e contesti di vista (Synfact machine-pages.s, machine-ui.s, view-draw.s): solo interfaccia
    (0x4003_7D9E, "2f027008206f0008", "jmp", "core_page_nav", PAGES, "PAGE_NAV: id del controllo per manopola"),
    (0x4003_85DC, "2f0a70ff2f02246f000c", "jmp", "core_page_385dc", PAGES, "azione di pagina: GUARD, BEGIN/END"),
    (0x4003_8642, "4feffff470ff48d7040c", "jmp", "core_page_38642", PAGES, "azione di pagina: GUARD, BEGIN/END"),
    (0x4003_A244, "4fefffb048d77cfc", "jmp", "core_page_3a244", PAGES, "pagina: PAGE_SYNC"),
    (0x4003_B1F0, "4e56fff070ff2f0a", "jmp", "core_page_3b1f0", PAGES, "azione di pagina: GUARD, BEGIN/END"),
    (0x4003_B29E, "4e56fff070ff2f0a", "jmp", "core_page_3b29e", PAGES, "azione di pagina: GUARD, BEGIN/END"),
    (0x4003_B3B8, "4e56fff070ff2f0a", "jmp", "core_page_3b3b8", PAGES, "azione di pagina: GUARD, BEGIN/END"),
    (0x4003_BC74, "4e56ffa848d73cfc", "jmp", "core_page_key", PAGES, "tasti della ParameterView: KEY prima e dopo"),
    (0x4010_09F4, "2f0c4e952653", "jmp", "core_view_draw", PAGES, "DRAW nel contesto della vista"),
    (0x4003_B8C6, "206800bc4e90", "jsr", "core_editor_resolve", PAGES, "encoder: PAGE_GUARD e ENC nel contesto"),
]
# simboli di long-samples (stesso codice di Synfact): storage, HZFS, CRC. Usati solo se la sua intestazione c'e'.
LS = {"ls_header_at": "ls_header", "ls_native_io": "core_hzfs_native_io", "ls_hz_open": "core_hzfs_open",
      "ls_hz_close": "core_hzfs_close", "ls_crc_update": "core_crc_update"}


def sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def wsl(cmd: str) -> str:
    r = subprocess.run(["wsl.exe", "-e", "bash", "-lc", cmd], capture_output=True, text=True)
    if r.returncode:
        raise SystemExit(f"comando WSL fallito:\n{cmd}\n{r.stdout}{r.stderr}")
    return r.stdout + r.stderr


def long_samples() -> dict[str, int]:
    sym = json.loads((REPO / "mods" / "long-samples" / "patch.json").read_text(encoding="utf-8"))["symbols"]
    return {ours: int(sym[theirs], 16) for ours, theirs in LS.items()}


def build_blob():
    with tempfile.TemporaryDirectory(prefix="sfcore-") as tmp:
        tmp = Path(tmp)
        shutil.copytree(HERE / "include", tmp / "include")
        for f in ("sfcore.c", "adapters.S"):
            shutil.copy(HERE / f, tmp / f)
        w = eft.to_wsl_path(tmp)
        env = f"R={TOOLS}; export LD_LIBRARY_PATH=$R/usr/lib/x86_64-linux-gnu; cd {w}; "
        gcc = "$R/usr/bin/m68k-linux-gnu-gcc-13 -B$R/usr/libexec/gcc/m68k-linux-gnu/13/ -B$R/usr/bin/m68k-linux-gnu-"
        warn = wsl(env + f"{gcc} {CFLAGS} -c sfcore.c -o c.o")
        if "warning" in warn:
            raise SystemExit(warn)
        wsl(env + "$R/usr/bin/m68k-linux-gnu-as -mcpu=54418 adapters.S -o a.o")
        defs = {"sfcore_modules": TABLE, **long_samples()}
        ld_defs = " ".join(f"--defsym={k}={v:#x}" for k, v in defs.items())
        wsl(env + f"$R/usr/bin/m68k-linux-gnu-ld -N -Ttext={CODE_BASE:#x} -e sfcore_boot {ld_defs} -o s.elf a.o c.o")
        undef = wsl(env + "$R/usr/bin/m68k-linux-gnu-nm -u s.elf").strip()
        if undef:
            raise SystemExit(f"simboli esterni non permessi (libgcc?): {undef}")
        wsl(env + "$R/usr/bin/m68k-linux-gnu-objcopy -O binary -j .text -j .rodata -j .data s.elf s.bin")
        syms = {}
        for line in wsl(env + "$R/usr/bin/m68k-linux-gnu-nm s.elf").splitlines():
            parts = line.split()
            if len(parts) == 3:
                syms[parts[2]] = int(parts[0], 16)
        return (tmp / "s.bin").read_bytes(), syms


def main() -> None:
    stock = REPO / "firmware" / "Syntakt_OS1.42.syx"
    sec3 = eft.unpack(stock, REPO / "unpacked" / stock.stem, ids=[3])[3].read_bytes()
    blob, syms = build_blob()
    end = max(syms.get("_end", 0), CODE_BASE + len(blob))
    if end > modarea_layout.RAM + END:
        raise SystemExit(f"non ci sta: fine a {end:#x}, spazio fino a {modarea_layout.RAM + END:#x}")
    patches = [{"section": 3, "addr": f"{modarea_layout.IMG + OFFSET:#010X}", "len": len(blob), "append": True,
                "hex": blob.hex(), "ram": f"{CODE_BASE:#010x}", "what": "(area mod) bus, adattatori, host API"},
               {"section": 3, "addr": f"{modarea_layout.boot_slot(SLOT):#010X}", "len": 4, "append": True,
                "hex": struct.pack(">I", syms["sfcore_boot"]).hex(),
                "ram": f"{modarea_layout.RAM + modarea_layout.BOOT_LIST + 4 * SLOT:#010x}",
                "what": f"lista di avvio dell'area mod, posto {SLOT}: sfcore_boot"}]
    for addr, orig, op, sym, service, what in SITES:
        n = len(orig) // 2
        old = sec3[addr - LOAD:addr - LOAD + n]
        if old.hex() != orig:
            raise SystemExit(f"{addr:#x}: byte inattesi {old.hex()}")
        new = struct.pack(">HI", 0x4EF9 if op == "jmp" else 0x4EB9, syms[sym])
        new += NOP * ((n - len(new)) // 2)
        p = {"section": 3, "addr": f"{addr:#010X}", "len": n, "expect_sha256": sha(old), "hex": new.hex(), "what": what}
        if service:
            p["service"] = service
        patches.append(p)
    spec = {
        "name": "sfcore", "os": "1.42", "requires": ["modarea"],
        "description": "Sottoinsieme del core di Synfact per i suoi moduli: tabella dei moduli, eventi (tick, draw, "
                       "key, enc, render_in, main_mix, fs_write, fs_written), transazioni native, host API 12.",
        "license": "GPL-2.0-or-later", "credits": "Synfact (GSM1980), elekloader (irpina)",
        "generated_by": "mods/sfcore/make_patch.py",
        "layout": {"table": f"{TABLE:#010x}", "slots": registry.SFCORE_N},
        "symbols": {k: f"{v:#010x}" for k, v in sorted(syms.items())
                    if k.startswith(("sfcore_", "ev_", "core_")) and v >= CODE_BASE},
        "patches": patches,
    }
    (HERE / "patch.json").write_text(json.dumps(spec, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"patch.json: {len(blob)} B a {CODE_BASE:#x}, fine con .bss {end:#x}")


if __name__ == "__main__":
    main()
