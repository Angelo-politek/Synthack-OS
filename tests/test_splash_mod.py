"""Mod splash: esegue splash_draw (codice ColdFire assemblato) in Unicorn e controlla il framebuffer.

Non serve il firmware: patch.json contiene solo byte nostri (codice, logo, voci di animazione).
"""

import json
import struct
import sys
from pathlib import Path

import pytest

pytest.importorskip("unicorn")
from unicorn import UC_ARCH_M68K, UC_MODE_BIG_ENDIAN, Uc  # noqa: E402
from unicorn.m68k_const import UC_CPU_M68K_ANY, UC_M68K_REG_A7, UC_M68K_REG_SR  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools" / "splash"))
import render  # noqa: E402

SPEC = json.loads((ROOT / "mods" / "splash" / "patch.json").read_text(encoding="utf-8"))
BLOB = SPEC["patches"][0]
BASE = int(BLOB["addr"], 16)
DATA = bytes.fromhex(BLOB["hex"])
CODE_LEN = 28                                     # splash_draw: 28 byte, poi il logo
LOGO = DATA[CODE_LEN:CODE_LEN + 1024]

RAM, BM, FB, RET = 0x5000_0000, 0x5000_0000, 0x5000_1000, 0x5000_0F00


def run_splash_draw(frame=0, total=120) -> bytes:
    uc = Uc(UC_ARCH_M68K, UC_MODE_BIG_ENDIAN, cpu=UC_CPU_M68K_ANY)
    uc.mem_map(BASE & ~0xFFF, 0x2000)
    uc.mem_write(BASE, DATA)
    uc.mem_map(RAM, 0x20000)
    uc.mem_write(FB, b"\x55" * 1024)              # framebuffer "sporco": deve essere sovrascritto
    uc.mem_write(BM + 16, struct.pack(">I", FB))  # Bitmap: puntatore ai dati a +16
    sp = RAM + 0x10000 - 16
    uc.mem_write(sp, struct.pack(">IIII", RET, frame, total, BM))   # ritorno, arg1, arg2, arg3
    uc.reg_write(UC_M68K_REG_SR, 0x2700)          # PRIMA SR (supervisore), poi A7: cambiando
    uc.reg_write(UC_M68K_REG_A7, sp)              # modo la CPU scambia lo stack pointer
    uc.emu_start(BASE, RET, count=100_000)
    return bytes(uc.mem_read(FB, 1024))


def test_splash_draw_copies_the_logo_into_the_framebuffer():
    assert run_splash_draw() == LOGO


def test_logo_matches_the_rendered_design():
    expected = render.compose(render.figlet("SyntHack", "smslant"), 3, 6, "v0.1")
    assert render.Bitmap.from_bytes_syntakt(LOGO).px == expected.px


def test_new_animation_entries_keep_original_and_add_splash():
    entries = [int(p["hex"], 16) for p in SPEC["patches"][1:]]
    assert len(entries) == 5
    for e in entries:
        o = e - BASE
        func, frames, sfunc, sframes, end0, end1 = struct.unpack_from(">IIIIII", DATA, o)
        assert 0x4000_0400 <= func < 0x4033_9000 and frames > 0      # animazione originale
        assert (sfunc, sframes) == (BASE, 120)                      # poi il nostro splash
        assert (end0, end1) == (0, 0)                               # fine elenco


def test_fits_in_the_free_region():
    assert 0x4033_8740 <= BASE and BASE + len(DATA) <= 0x4033_9000
