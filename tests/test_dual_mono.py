"""Mod dual-mono: blocco originale vs routine con trampolino, eseguiti in Unicorn sulla sezione 3.

Serve il firmware stock (sezione 3): saltato se assente.
"""

import json
import random
import struct
import sys
from pathlib import Path

import pytest

pytest.importorskip("unicorn")
from unicorn import UC_ARCH_M68K, UC_MODE_BIG_ENDIAN, Uc  # noqa: E402
from unicorn.m68k_const import (UC_CPU_M68K_ANY, UC_M68K_REG_A2, UC_M68K_REG_A3,  # noqa: E402
                                UC_M68K_REG_A7, UC_M68K_REG_D4, UC_M68K_REG_SR)

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "tools" / "emu"), str(ROOT / "tools" / "unpack")]
import eft  # noqa: E402
from emac import UnicornEmac  # noqa: E402

STOCK = ROOT / "firmware" / "Syntakt_OS1.41.syx"
pytestmark = pytest.mark.skipif(not STOCK.exists(), reason="firmware stock assente")

SPEC = json.loads((ROOT / "mods" / "dual-mono" / "patch.json").read_text(encoding="utf-8"))
LOAD = 0x4000_0400
BLOCK, AFTER = 0x4009_0872, 0x4009_08FC
PANLAW = 0x400A_171A
FLAG = 0x8000_3146
PARAMS, HW, STACK = 0x5000_0000, 0x5000_2000, 0x5001_0000
MIX3 = 0x41B9_F7F0
STEREO_LAYOUT = [126, 0, 0, 0, 129, 130, 128, 132]
MONO_LAYOUT = [126, 125, 0, 0, 129, 130, 0, 132]     # IN R = alias 125 reso alias di BAL
DESC = 0x4022D59C                                       # descrittori: record da 52 B, indice = id logico
NAMES = {i: DESC + 52 * i + 48 for i in (125, 126, 127, 128)}
ORIG_NAMES = {125: 0x4024F8A7, 126: 0x40253B6E, 127: 0x40266015, 128: 0x40265CC9}
LONG = {i: DESC + 52 * i + 40 for i in (125, 126)}
ORIG_LONG = {125: 0x40253B4D, 126: 0x40253B60}          # "Input Level", "In Left/Right"
SWITCHES = (0x4000C8B0, 0x4000C9A4)                     # get/set del valore per id logico 125..132
# istruzioni EMAC del codice originale eseguito (blocco, legge di bilanciamento, seno): da GNU objdump
ORIG_EMAC = [0x40090880, 0x40090884, 0x40090892, 0x40090896, 0x400908AA, 0x400908AE, 0x400908B8,
             0x400908BC, 0x400908CA, 0x400908CE, 0x400908D2, 0x400908D4,
             0x400A174E, 0x400A1752, 0x400A16CC, 0x400A16D0, 0x400A16D4, 0x400A16D8]


@pytest.fixture(scope="module")
def sec3():
    return eft.unpack(STOCK, ROOT / "unpacked" / STOCK.stem, ids=[3])[3].read_bytes()


class Machine:
    def __init__(self, sec3: bytes, patched: bool, macsr: int):
        uc = self.uc = Uc(UC_ARCH_M68K, UC_MODE_BIG_ENDIAN, cpu=UC_CPU_M68K_ANY)
        uc.mem_map(0x4000_0000, 0x0040_0000)
        uc.mem_write(LOAD, sec3)
        uc.mem_map(0x41B9_F000, 0x1000)                       # pagina MIX3 (BSS)
        uc.mem_write(MIX3, struct.pack(">8i", *STEREO_LAYOUT))
        uc.mem_map(0x8000_0000, 0x1_0000)                     # SRAM (flag dual mono)
        uc.mem_map(0x5000_0000, 0x2_0000)                     # parametri, hw, stack
        sites = list(ORIG_EMAC)
        if patched:
            for p in SPEC["patches"]:
                uc.mem_write(int(p["addr"], 16), bytes.fromhex(p["hex"]))
            sites += [int(a, 16) for a in SPEC["emac_sites"]]
        self.emac = UnicornEmac(uc, sites)
        self.emac.state.load_macsr(macsr)

    def run(self, level, pan, x, prepost, mono):
        uc = self.uc
        p = bytearray(0x800)
        struct.pack_into(">H", p, 0x70A, level)
        struct.pack_into(">H", p, 0x70E, pan)
        struct.pack_into(">H", p, 0x740, x)
        struct.pack_into(">H", p, 0x71A, prepost)
        uc.mem_write(PARAMS, bytes(p))
        uc.mem_write(HW, b"\xAA" * 0x40)
        uc.mem_write(FLAG, bytes([0 if mono else 1]))       # 0 = mono (verificato sulla macchina)
        uc.reg_write(UC_M68K_REG_SR, 0x2700)
        uc.reg_write(UC_M68K_REG_A7, STACK)
        uc.reg_write(UC_M68K_REG_A2, PARAMS)
        uc.reg_write(UC_M68K_REG_A3, HW)
        uc.reg_write(UC_M68K_REG_D4, PANLAW)
        uc.emu_start(BLOCK, AFTER, count=100_000)
        assert self.emac.error is None, self.emac.error
        hw = bytes(uc.mem_read(HW, 0x40))
        return struct.unpack_from(">H", hw, 8)[0], struct.unpack_from(">H", hw, 0x12)[0], hw

    def layout(self):
        return list(struct.unpack(">8i", self.uc.mem_read(MIX3, 32)))

    def u32(self, addr):
        return struct.unpack(">I", self.uc.mem_read(addr, 4))[0]

    def name_ptr(self, idx):
        return struct.unpack(">I", self.uc.mem_read(NAMES[idx], 4))[0]


def cases(n, seed):
    rnd = random.Random(seed)
    edge = [0, 0x100, 0x3F00, 0x4000, 0x7E00, 0x7F00]
    for _ in range(n):
        yield (rnd.choice(edge + [rnd.randrange(0, 0x7F01)]), rnd.choice(edge + [rnd.randrange(0, 0x7F01)]),
               rnd.randrange(0, 0x7F01), rnd.choice([0, 1]))


def test_original_descriptor_fields_are_as_assumed(sec3):
    u = lambda a: struct.unpack_from(">I", sec3, a - LOAD)[0]                       # noqa: E731
    # alias 125: stesso gruppo/id interno di IN LR, nessun CC/NRPN, nessuna posizione di salvataggio
    assert [u(DESC + 52 * 125 + 4 * k) for k in (0, 1, 6, 7, 8)] == [0x34, 0x23, 0xFFFFFFFF, 0xFFFFFFFF, 0]
    assert [u(DESC + 52 * 128 + 4 * k) for k in (0, 1)] == [0x34, 0x25]               # BAL
    assert {i: u(LONG[i]) for i in LONG} == ORIG_LONG
    for tab in SWITCHES:                    # voci 125,126 -> campo di IN LR; 127,128 -> campo di BAL
        assert struct.unpack_from(">4h", sec3, tab - LOAD) == (0x10, 0x10, 0x22, 0x22)


def test_alias_125_becomes_bal_alias(sec3):
    patched = bytearray(sec3)
    for p in SPEC["patches"]:
        a = int(p["addr"], 16) - LOAD
        patched[a:a + p["len"]] = bytes.fromhex(p["hex"])
    rec = lambda b, i: struct.unpack_from(">13I", b, DESC + 52 * i - LOAD)            # noqa: E731
    assert rec(patched, 125)[1] == rec(patched, 128)[1] == 0x25
    assert rec(patched, 126) == rec(sec3, 126) and rec(patched, 128) == rec(sec3, 128)
    for tab in SWITCHES:
        assert struct.unpack_from(">8h", patched, tab - LOAD)[:4] == (0x22, 0x10, 0x22, 0x22)
        assert patched[tab - LOAD + 2:tab - LOAD + 16] == sec3[tab - LOAD + 2:tab - LOAD + 16]


@pytest.mark.parametrize("macsr", [0x00, 0x20, 0x40, 0x60, 0xA0])
def test_stereo_is_bit_identical_to_original(sec3, macsr):
    orig, mod = Machine(sec3, False, macsr), Machine(sec3, True, macsr)
    for level, pan, x, prepost in cases(60, macsr):
        lo, ro, hwo = orig.run(level, pan, x, prepost, mono=False)
        lm, rm, hwm = mod.run(level, pan, x, prepost, mono=False)
        assert (lm, rm) == (lo, ro), (hex(level), hex(pan), hex(x), prepost)
        assert hwm == hwo                       # nient'altro toccato nella struttura hardware


@pytest.mark.parametrize("macsr", [0x20, 0xA0])
def test_mono_left_from_inlr_right_from_bal(sec3, macsr):
    orig, mod = Machine(sec3, False, macsr), Machine(sec3, True, macsr)
    for level, bal, x, prepost in cases(40, 100 + macsr):
        expect_l, _, _ = orig.run(level, 0x4000, x, prepost, mono=False)
        _, expect_r, _ = orig.run(bal, 0x4000, x, prepost, mono=False)
        lm, rm, _ = mod.run(level, bal, x, prepost, mono=True)
        assert (lm, rm) == (expect_l, expect_r), (hex(level), hex(bal), hex(x), prepost)


def test_mono_left_and_right_are_independent(sec3):
    mod = Machine(sec3, True, 0xA0)
    l1, r1, _ = mod.run(0x7F00, 0x0000, 0x4000, 0, mono=True)   # L al massimo, R a zero
    l2, r2, _ = mod.run(0x0000, 0x7F00, 0x4000, 0, mono=True)   # L a zero, R al massimo
    assert l1 == r2 and r1 == l2 and l1 != r1


def test_ui_switches_layout_and_names_and_back(sec3):
    mod = Machine(sec3, True, 0xA0)
    mod.run(0x4000, 0x4000, 0x4000, 0, mono=True)
    assert mod.layout() == MONO_LAYOUT
    assert bytes(mod.uc.mem_read(mod.name_ptr(126), 5)) == b"IN L\x00"
    assert bytes(mod.uc.mem_read(mod.name_ptr(125), 5)) == b"IN R\x00"
    assert mod.name_ptr(127) == ORIG_NAMES[127] and mod.name_ptr(128) == ORIG_NAMES[128]
    assert bytes(mod.uc.mem_read(mod.u32(LONG[126]), 11)) == b"Input Left" + bytes(1)
    assert bytes(mod.uc.mem_read(mod.u32(LONG[125]), 12)) == b"Input Right" + bytes(1)
    mod.run(0x4000, 0x4000, 0x4000, 0, mono=False)
    assert mod.layout() == STEREO_LAYOUT
    assert {i: mod.name_ptr(i) for i in NAMES} == ORIG_NAMES
    assert {i: mod.u32(LONG[i]) for i in LONG} == ORIG_LONG


def test_ui_untouched_if_page_is_not_the_expected_one(sec3):
    mod = Machine(sec3, True, 0xA0)
    weird = [1, 2, 3, 4, 5, 6, 7, 8]
    mod.uc.mem_write(MIX3, struct.pack(">8i", *weird))
    mod.run(0x4000, 0x4000, 0x4000, 0, mono=True)
    assert mod.layout() == weird
    assert {i: mod.name_ptr(i) for i in NAMES} == ORIG_NAMES
    assert {i: mod.u32(LONG[i]) for i in LONG} == ORIG_LONG
