"""Mod kitstore: parole delle mod salvate con il kit, con le funzioni vere dell'OS.

Scrittura (0x400A6E6E) e lettura (0x400A6E02) di un blocco per traccia del kit girano nell'emulatore con
e senza i nostri agganci: file e blocco riletto identici a quelli dell'OS stock, tranne le parole 41..43
(RAM +82..+87) che vanno nei byte riservati +150..+155 e tornano indietro.
"""

import json
import random
import struct
import sys
from pathlib import Path

import pytest

pytest.importorskip("unicorn")
from unicorn import UC_ARCH_M68K, UC_MODE_BIG_ENDIAN, Uc  # noqa: E402
from unicorn.m68k_const import UC_CPU_M68K_ANY, UC_M68K_REG_A7, UC_M68K_REG_D0, UC_M68K_REG_SR  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "tools" / "build"), str(ROOT / "tools" / "unpack")]
import eft  # noqa: E402
import kitstore_layout as L  # noqa: E402

SY = ROOT / "firmware" / "Syntakt_OS1.41.syx"
SPEC_F = ROOT / "mods" / "kitstore" / "patch.json"
pytestmark = pytest.mark.skipif(not (SY.exists() and SPEC_F.exists()), reason="OS o patch assenti")

LOAD, STACK, RET = 0x4000_0400, 0x5000_F000, 0x5000_FF00
WRITE, READ = 0x400A_6E6E, 0x400A_6E02
RAM_A, RAM_B, FILE = 0x5001_0000, 0x5001_1000, 0x5001_2000
OURS = slice(82, 88)                                      # parole 41..43 del blocco in RAM


class Machine:
    def __init__(self, hooked):
        sec3 = eft.unpack(SY, ROOT / "unpacked" / SY.stem, ids=[3])[3].read_bytes()
        spec = json.loads(SPEC_F.read_text(encoding="utf-8"))
        uc = self.uc = Uc(UC_ARCH_M68K, UC_MODE_BIG_ENDIAN, cpu=UC_CPU_M68K_ANY)
        uc.mem_map(0x4000_0000, 0x0040_0000)
        uc.mem_write(LOAD, sec3)
        uc.mem_map(0x444E_0000, 0x2_0000)
        uc.mem_map(0x5000_0000, 0x4_0000)
        if hooked:
            for p in spec["patches"]:
                uc.mem_write(int(p["ram"], 16) if p.get("append") else int(p["addr"], 16),
                             bytes.fromhex(p["hex"]))
        uc.mem_write(RET, b"\x4e\x75")

    def call(self, fn, *args):
        uc = self.uc
        sp = STACK - 4 * (len(args) + 1)
        uc.mem_write(sp, struct.pack(f">{len(args) + 1}I", RET, *args))
        uc.reg_write(UC_M68K_REG_SR, 0x2700)
        uc.reg_write(UC_M68K_REG_A7, sp)
        uc.emu_start(fn, RET, count=1_000_000)
        assert uc.reg_read(UC_M68K_REG_A7) == sp + 4
        return uc.reg_read(UC_M68K_REG_D0) & 0xFF

    def write(self, block):
        self.uc.mem_write(RAM_A, block)
        self.uc.mem_write(FILE, b"\xEE" * 160)
        assert self.call(WRITE, FILE, RAM_A) == 1
        return bytes(self.uc.mem_read(FILE, 156))

    def read(self, f, before=b"\x55" * 148):
        self.uc.mem_write(FILE, f)
        self.uc.mem_write(RAM_B, before)
        assert self.call(READ, RAM_B, FILE) == 1
        return bytes(self.uc.mem_read(RAM_B, 148))


def block(seed):
    rnd = random.Random(seed)
    words = [rnd.randrange(0x80) << 8 for _ in range(71)]     # valori dei parametri in scala
    return struct.pack(">71H", *words) + bytes(6)


def test_layout():
    assert L.word(0, 0) == 0xE5C + 82 and L.word(11, 2) == 0xE5C + 148 * 11 + 86


@pytest.mark.parametrize("seed", [1, 2, 3])
def test_round_trip_keeps_our_words_and_the_os_fields(seed):
    stock, ours = Machine(False), Machine(True)
    b = block(seed)
    f_stock, f_ours = stock.write(b), ours.write(b)
    assert f_stock[150:156] == bytes(6)                       # riservati: l'OS li azzera
    assert f_ours[:150] == f_stock[:150] and f_ours[150:156] == b[OURS]
    r_stock, r_ours = stock.read(f_ours), ours.read(f_ours)
    assert r_ours[:82] == r_stock[:82] and r_ours[88:] == r_stock[88:]
    assert r_ours[OURS] == b[OURS]


def test_kit_saved_without_our_words_loads_zeros():
    stock, ours = Machine(False), Machine(True)
    f = stock.write(block(5))                                 # salvato da OS stock / versioni precedenti
    assert ours.read(f)[OURS] == bytes(6)


def test_failures_pass_through():
    ours = Machine(True)
    assert ours.call(WRITE, 0, RAM_A) == 0
    ours.uc.mem_write(FILE, struct.pack(">I", 3))             # tipo di blocco sbagliato: rifiutato
    ours.uc.mem_write(RAM_B, b"\x55" * 148)
    assert ours.call(READ, RAM_B, FILE) == 0
    assert bytes(ours.uc.mem_read(RAM_B, 148)) == b"\x55" * 148
