"""Mod projstore: i byte delle mod salvati con il progetto, con le funzioni vere dell'OS.

Scrittura (0x400A90BC) e lettura (0x400A8478) delle impostazioni del progetto girano nell'emulatore con e
senza i nostri agganci: il blocco nel file e le impostazioni rilette devono essere identici a quelli
dell'OS stock, tranne i nostri byte nell'area riservata; i byte delle mod devono tornare uguali.
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

SY = ROOT / "firmware" / "Syntakt_OS1.41.syx"
SPEC_F = ROOT / "mods" / "projstore" / "patch.json"
pytestmark = pytest.mark.skipif(not (SY.exists() and SPEC_F.exists()), reason="OS o patch assenti")

LOAD, STACK, RET = 0x4000_0400, 0x5000_F000, 0x5000_FF00
WRITE, READ = 0x400A_90BC, 0x400A_8478
SET_A, SET_B, FILE = 0x5001_0000, 0x5002_0000, 0x5003_0000   # impostazioni (RAM), blocco nel file
RESERVED = (0x227, 0x400)


class Machine:
    def __init__(self, hooked):
        sec3 = eft.unpack(SY, ROOT / "unpacked" / SY.stem, ids=[3])[3].read_bytes()
        self.spec = json.loads(SPEC_F.read_text(encoding="utf-8"))
        self.data = int(self.spec["layout"]["data"], 16)
        self.size = self.spec["layout"]["size"]
        uc = self.uc = Uc(UC_ARCH_M68K, UC_MODE_BIG_ENDIAN, cpu=UC_CPU_M68K_ANY)
        uc.mem_map(0x4000_0000, 0x0040_0000)
        uc.mem_write(LOAD, sec3)
        uc.mem_map(0x444E_0000, 0x2_0000)
        uc.mem_map(0x5000_0000, 0x4_0000)
        if hooked:
            for p in self.spec["patches"]:
                uc.mem_write(int(p["ram"], 16) if p.get("append") else int(p["addr"], 16),
                             bytes.fromhex(p["hex"]))
        uc.mem_write(RET, b"\x4e\x75")

    def call(self, fn, *args):
        uc = self.uc
        sp = STACK - 4 * (len(args) + 1)
        uc.mem_write(sp, struct.pack(f">{len(args) + 1}I", RET, *args))
        uc.reg_write(UC_M68K_REG_SR, 0x2700)
        uc.reg_write(UC_M68K_REG_A7, sp)
        uc.emu_start(fn, RET, count=2_000_000)
        assert uc.reg_read(UC_M68K_REG_A7) == sp + 4                     # rts al chiamante
        return uc.reg_read(UC_M68K_REG_D0) & 0xFF


def settings(seed):
    rnd = random.Random(seed)
    return bytes(rnd.randrange(4) for _ in range(0x400))       # valori piccoli: campi in scala


def write(m, s):
    m.uc.mem_write(SET_A, s)
    m.uc.mem_write(FILE, b"\xEE" * 0x400)
    assert m.call(WRITE, FILE, SET_A, 0) == 1
    return bytes(m.uc.mem_read(FILE, 0x400))


def read(m, block):
    m.uc.mem_write(FILE, block)
    m.uc.mem_write(SET_B, bytes(0x400))
    assert m.call(READ, SET_B, FILE) == 1
    return bytes(m.uc.mem_read(SET_B, 0x400))


@pytest.mark.parametrize("seed", [1, 2, 3])
def test_round_trip_keeps_our_bytes_and_the_os_fields(seed):
    stock, ours = Machine(False), Machine(True)
    s = settings(seed)
    mine = bytes(random.Random(seed + 10).randrange(256) for _ in range(ours.size))
    ours.uc.mem_write(ours.data, mine)
    f_stock, f_ours = write(stock, s), write(ours, s)
    lo, hi = 0x228, 0x22C + ours.size
    assert f_ours[:lo] == f_stock[:lo] and f_ours[hi:] == f_stock[hi:]     # il resto come l'OS
    assert f_stock[RESERVED[0]:RESERVED[1]] == bytes(RESERVED[1] - RESERVED[0])
    assert f_ours[lo:lo + 4] == bytes([0x53, 0x48, 1, ours.size // 4]) and f_ours[lo + 4:hi] == mine
    ours.uc.mem_write(ours.data, b"\x77" * ours.size)
    assert read(ours, f_ours) == read(stock, f_ours)                       # impostazioni come l'OS
    assert bytes(ours.uc.mem_read(ours.data, ours.size)) == mine


def test_project_without_our_bytes_loads_zeros():
    stock, ours = Machine(False), Machine(True)
    f = write(stock, settings(5))                                          # salvato da OS stock / v0.8
    ours.uc.mem_write(ours.data, b"\x77" * ours.size)
    assert read(ours, f) == read(stock, f)
    assert bytes(ours.uc.mem_read(ours.data, ours.size)) == bytes(ours.size)


def test_failures_pass_through():
    ours = Machine(True)
    ours.uc.mem_write(ours.data, b"\x77" * ours.size)
    assert ours.call(WRITE, 0, SET_A, 0) == 0
    ours.uc.mem_write(FILE, struct.pack(">I", 3))                         # versione diversa: rifiutato
    assert ours.call(READ, SET_B, FILE) == 0
    assert bytes(ours.uc.mem_read(ours.data, ours.size)) == b"\x77" * ours.size
