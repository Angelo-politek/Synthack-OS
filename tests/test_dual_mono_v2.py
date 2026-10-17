"""Dual mono v2: IN L e IN R con mandate proprie, eseguiti in Unicorn sulla sezione 3 con le patch.

Il blocco originale delle mandate dell'ingresso (0x4008F478..0x4008F604, legge di bilanciamento
0x400A171A ed EMAC compresi) gira come nell'OS. Riferimento: lo stesso blocco senza dual-mono, in mono,
con bilanciamento al centro, una volta con livello e mandate di IN L (canale 12) e una con quelli di IN R
(canale 13). In stereo il blocco dev'essere identico all'originale.
"""

import json
import random
import struct
import sys
from pathlib import Path

import pytest

pytest.importorskip("unicorn")
from unicorn import UC_ARCH_M68K, UC_HOOK_CODE, UC_MODE_BIG_ENDIAN, Uc  # noqa: E402
from unicorn.m68k_const import (UC_CPU_M68K_ANY, UC_M68K_REG_A0, UC_M68K_REG_A1, UC_M68K_REG_A2,  # noqa: E402
                                UC_M68K_REG_A6, UC_M68K_REG_A7, UC_M68K_REG_D0, UC_M68K_REG_D1,
                                UC_M68K_REG_D4, UC_M68K_REG_SR)

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "tools" / "emu"), str(ROOT / "tools" / "unpack"), str(ROOT / "tools" / "build")]
import dualmono_layout as DL  # noqa: E402
import eft  # noqa: E402
from emac import UnicornEmac  # noqa: E402

SY = ROOT / "firmware" / "Syntakt_OS1.41.syx"
pytestmark = pytest.mark.skipif(not SY.exists(), reason="firmware stock assente")

LOAD, START, END = 0x4000_0400, 0x4008_F478, 0x4008_F604     # fino al passo FX R del canale 13 (F600)
STACK, RET, FRAME, A2 = 0x5000_8000, 0x5000_F000, 0x5000_4000, 0x5000_9000
FLAG, UI_KIT_PTR, FX_KIT_PTR, UI = 0x8000_3146, 0x8000_30B8, 0x8000_30BC, 0x5000_0C00
UI_KIT, FX_KIT = 0x5001_0000, 0x5000_6000
SITES = [0x4008F48E, 0x4008F492, 0x4008F498, 0x4008F49C, 0x4008F4B8, 0x4008F4BC, 0x4008F4C0, 0x4008F4C2,
         0x4008F4E0, 0x4008F4E4, 0x4008F4E8, 0x4008F4EA, 0x4008F4F8, 0x4008F4FC, 0x4008F500, 0x4008F502,
         0x400A174E, 0x400A1752, 0x400A16CC, 0x400A16D0, 0x400A16D4, 0x400A16D8]
CH12 = (-408, -376, -344, -312, -280, -248)    # passi: delay L/R, reverb L/R, FX L/R del canale 12
CH13 = (-404, -372, -340, -308, -276, -244)
CURRENT = [0x8000_6250, 0x8000_6254, 0x8000_6270, 0x8000_6274, 0x8000_6290, 0x8000_6294, 0x8000_62B0,
           0x8000_62B4, 0x8000_E0E0, 0x8000_E0E4, 0x8000_E100, 0x8000_E104]
IN_LR, BAL, DEL, REV, ROUTE = 1802, 1806, 1808, 1812, 1818
VIEW, PAGES = 0x5000_3000, 0x5000_3100


def spec(name):
    return json.loads((ROOT / "mods" / name / "patch.json").read_text(encoding="utf-8"))


class Machine:
    def __init__(self, mods):
        sec3 = eft.unpack(SY, ROOT / "unpacked" / SY.stem, ids=[3])[3].read_bytes()
        uc = self.uc = Uc(UC_ARCH_M68K, UC_MODE_BIG_ENDIAN, cpu=UC_CPU_M68K_ANY)
        uc.mem_map(0x4000_0000, 0x0040_0000)
        uc.mem_write(LOAD, sec3)
        uc.mem_map(0x41B9_0000, 0x2_0000)
        uc.mem_map(0x444E_0000, 0x2_0000)
        uc.mem_map(0x5000_0000, 0x2_0000)
        uc.mem_map(0x8000_0000, 0x1_0000)
        self.sym = {}
        for name in mods:
            sp = spec(name)
            self.sym.update({k: int(v, 16) for k, v in sp.get("symbols", {}).items()})
            for p in sp["patches"]:
                uc.mem_write(int(p["ram"], 16) if p.get("append") else int(p["addr"], 16), bytes.fromhex(p["hex"]))
        uc.mem_write(RET, b"\x4e\x75")
        uc.mem_write(0x444E_1334, struct.pack(">I", UI))
        uc.mem_write(UI_KIT_PTR, struct.pack(">I", UI_KIT))
        uc.mem_write(FX_KIT_PTR, struct.pack(">I", FX_KIT))
        self.emac = UnicornEmac(uc, SITES)
        self.emac.state.macsr = 0xA0                       # come nel mix (fx3_mix_hook lo riscrive uguale)

    def w16(self, a, v):
        self.uc.mem_write(a, struct.pack(">H", v & 0xFFFF))

    def r16(self, a):
        return struct.unpack(">H", self.uc.mem_read(a, 2))[0]

    def longs(self, a, n):
        return list(struct.unpack(f">{n}i", self.uc.mem_read(a, 4 * n)))

    def block(self, mono, inlr, bal, dl, rv, route=0, cur=None):
        """Il blocco delle mandate dell'ingresso: -> {offset nel frame: passo}."""
        uc = self.uc
        uc.mem_write(FLAG, bytes([0 if mono else 1]))
        for off, v in ((IN_LR, inlr), (BAL, bal), (DEL, dl), (REV, rv), (ROUTE, route)):
            self.w16(A2 + off, v)
        for i, a in enumerate(CURRENT):
            uc.mem_write(a, struct.pack(">i", (cur or [0] * 12)[i]))
        uc.mem_write(FRAME - 0x200, bytes(0x200))
        uc.reg_write(UC_M68K_REG_A2, A2)
        uc.reg_write(UC_M68K_REG_A6, FRAME)
        uc.reg_write(UC_M68K_REG_D4, 0xD4)
        uc.reg_write(UC_M68K_REG_SR, 0x2700)
        uc.reg_write(UC_M68K_REG_A7, STACK)
        uc.emu_start(START, END, count=2_000_000)
        assert self.emac.error is None
        assert uc.reg_read(UC_M68K_REG_A7) == STACK and uc.reg_read(UC_M68K_REG_A2) == A2
        assert uc.reg_read(UC_M68K_REG_D4) == 0xD4
        return {o: v for o, v in zip(range(-408, -240, 4), self.longs(FRAME - 408, 42))}

    def call(self, fn, args=(), regs=None):
        uc = self.uc
        sp = STACK - 4 * (len(args) + 1)
        uc.mem_write(sp, struct.pack(f">{len(args) + 1}I", RET, *[a & 0xFFFFFFFF for a in args]))
        for r, v in (regs or {}).items():
            uc.reg_write(r, v & 0xFFFFFFFF)
        uc.reg_write(UC_M68K_REG_SR, 0x2700)
        uc.reg_write(UC_M68K_REG_A7, sp)
        uc.emu_start(fn, RET, count=200_000)
        return uc.reg_read(UC_M68K_REG_D0) & 0xFFFFFFFF


@pytest.fixture(scope="module")
def stock():
    return Machine(["vparams", "fx3"])


@pytest.fixture()
def mod():
    return Machine(["vparams", "kitstore", "fx3", "dual-mono"])


def r_words(m, dr, rr, fr):
    for off, v in ((DL.DEL_R, dr), (DL.REV_R, rr), (DL.FX3_R, fr)):
        m.w16(UI_KIT + off, v)


CASES = [(0x7F00, 0x7F00, 0x7F00, 0x7F00, 127, 127), (0x4000, 0x2000, 0x6000, 0x1000, 30, 100),
         (0x7F00, 0, 0x5000, 0x5000, 0, 64), (0, 0x6A00, 0, 0x7F00, 127, 0)]


@pytest.mark.parametrize("lv_l,lv_r,dl,rv,dr,rr", CASES)
@pytest.mark.parametrize("route", [0, 1])
def test_mono_each_side_like_the_os_with_its_own_sends(stock, mod, lv_l, lv_r, dl, rv, dr, rr, route):
    rnd = random.Random(lv_l + 3 * dr + route)
    cur = [rnd.randrange(-0x4000_0000, 0x4000_0000) for _ in range(12)]
    ref_l = stock.block(True, lv_l, 0x4000, dl, rv, route, cur)
    ref_r = stock.block(True, lv_r, 0x4000, dr << 8, rr << 8, route, cur)
    r_words(mod, dr, rr, 0)
    got = mod.block(True, lv_l, lv_r, dl, rv, route, cur)            # BAL = IN R (v1)
    assert [got[o] for o in CH12] == [ref_l[o] for o in CH12]
    assert [got[o] for o in CH13] == [ref_r[o] for o in CH13]
    for off, v in ((IN_LR, lv_l), (BAL, lv_r), (DEL, dl), (REV, rv)):
        assert mod.r16(A2 + off) == v                                    # parametri ripristinati
    assert mod.uc.mem_read(DL.HDR + 4, 1)[0] == 0


@pytest.mark.parametrize("args", [(0x7F00, 0x4000, 0x7F00, 0x3000, 1), (0x2000, 0x0100, 0x5000, 0x7F00, 0),
                                  (0x6000, 0x7F00, 0, 0x4000, 1)])
def test_stereo_identical_to_stock(stock, mod, args):
    cur = list(range(0x1000, 0x1000 + 12 * 0x111, 0x111))
    r_words(mod, 127, 127, 127)
    assert mod.block(False, *args[:4], args[4], cur) == stock.block(False, *args[:4], args[4], cur)


def test_input_fx3_per_side(stock, mod):
    """FX3 dell'ingresso: canale 12 con livello e mandata di IN L, canale 13 con quelli di IN R."""
    for m, fx_l in ((stock, 90), (mod, 90)):
        m.w16(FX_KIT + 2 * 0x37, fx_l)
        m.uc.mem_write(m.sym["fx3_tgt"], bytes(64))
    stock.block(True, 0x6000, 0x4000, 0, 0)
    t12 = stock.longs(stock.sym["fx3_tgt"] + 48, 1)[0]
    stock.w16(FX_KIT + 2 * 0x37, 40)                                     # FX3 R = 40 come riferimento
    stock.block(True, 0x3000, 0x4000, 0, 0)
    t13 = stock.longs(stock.sym["fx3_tgt"] + 52, 1)[0]
    r_words(mod, 0, 0, 40)
    mod.block(True, 0x6000, 0x3000, 0, 0)
    assert mod.longs(mod.sym["fx3_tgt"] + 48, 2) == [t12, t13] and t12 and t13


# ----------------------------------------------------------------------------- interfaccia
def view(m, idx, mono):
    m.uc.mem_write(PAGES, struct.pack(">4i", 22, 23, 24, 27))
    m.uc.mem_write(VIEW + 0x7C, struct.pack(">3I", PAGES, PAGES + 16, PAGES + 16))
    m.uc.mem_write(VIEW + 0x90, struct.pack(">i", idx))
    m.uc.mem_write(FLAG, bytes([0 if mono else 1]))


def pages(m):
    b, e = struct.unpack(">2I", m.uc.mem_read(VIEW + 0x7C, 8))
    return (e - b) // 4, struct.unpack(">i", m.uc.mem_read(VIEW + 0x90, 4))[0]


def test_mixer_view_captured_and_sized_at_boot(mod):
    view(mod, 0, False)
    mod.uc.mem_write(0x4004_4626, b"\x4e\x75")                         # costruttore dell'OS: qui un rts
    mod.call(mod.sym["dm_mixer_ctor"], [VIEW, 0x5000_3200, 0x17, 1])
    assert struct.unpack(">I", mod.uc.mem_read(mod.sym["dm_view"], 4))[0] == VIEW
    assert pages(mod) == (3, 0)


@pytest.mark.parametrize("mono,idx,want", [(True, 1, (4, 1)), (False, 1, (3, 1)), (False, 3, (3, 2)),
                                           (True, 3, (4, 3))])
def test_setting_change_resizes_the_tab(mod, mono, idx, want):
    view(mod, idx, not mono)
    mod.uc.mem_write(mod.sym["dm_view"], struct.pack(">I", VIEW))
    mod.call(mod.sym["dm_flag_hook"], regs={UC_M68K_REG_D0: 0 if mono else 1, UC_M68K_REG_A1: 0xA1})
    assert mod.uc.mem_read(FLAG, 1)[0] == (0 if mono else 1)
    assert pages(mod) == want
    assert mod.uc.reg_read(UC_M68K_REG_A1) == 0xA1


@pytest.mark.parametrize("idx,mono,want", [(3, True, 1), (2, True, 0), (3, False, 0)])
def test_page_r(mod, idx, mono, want):
    view(mod, idx, mono)
    mod.uc.mem_write(mod.sym["dm_view"], struct.pack(">I", VIEW))
    assert mod.call(mod.sym["dm_page_r"]) == want


def test_r_page_reads_and_writes_the_r_sends(mod):
    view(mod, 3, True)
    mod.uc.mem_write(mod.sym["dm_view"], struct.pack(">I", VIEW))
    r_words(mod, 11, 22, 33)
    get, put = 0x4000_D94A, 0x4000_DA32                                # vparams
    assert mod.call(get, [0x5000_0000, 129]) == 11 << 8
    assert mod.call(get, [0x5000_0000, 130]) == 22 << 8
    assert mod.call(get, [0x5000_0000, 269]) == 33 << 8                 # fx3
    mod.call(put, [0x5000_0000, 129, 100 << 8, 1])
    mod.call(put, [0x5000_0000, 130, 0x9000, 1])
    mod.call(put, [0x5000_0000, 269, 5 << 8, 1])
    assert [mod.r16(UI_KIT + o) for o in (DL.DEL_R, DL.REV_R, DL.FX3_R)] == [100, 127, 5]
    assert mod.uc.mem_read(UI + 96, 1)[0] == 1


@pytest.mark.parametrize("fn,id_,orig", [(0x4000_D94A, 129, 0x4000_D950), (0x4000_DA32, 130, 0x4000_DA3A)])
def test_l_page_goes_to_the_os(mod, fn, id_, orig):
    """Fuori dalla pagina IN R: il codice originale, con lo stack del ripiego di vparams."""
    view(mod, 2, True)
    mod.uc.mem_write(mod.sym["dm_view"], struct.pack(">I", VIEW))
    hit = []

    def at(uc, a, s, _):
        hit.append((uc.reg_read(UC_M68K_REG_D1), struct.unpack(">4I", uc.mem_read(uc.reg_read(UC_M68K_REG_A7), 16))))
        uc.emu_stop()
    h = mod.uc.hook_add(UC_HOOK_CODE, at, begin=orig, end=orig)
    mod.call(fn, [0x5000_0000, id_, 0x1234, 1])
    mod.uc.hook_del(h)
    d1, st = hit[0]
    if orig == 0x4000_D950:                                             # push d2 ; d1 = 8(sp) = oggetto
        assert d1 == 0x5000_0000 and st[2:] == (0x5000_0000, id_)
    else:                                                               # push d3, d2 ; d1 = 12(sp)
        assert d1 == 0x5000_0000 and st[3] == 0x5000_0000


def test_fx3_l_page_unchanged(mod):
    view(mod, 2, True)
    mod.uc.mem_write(mod.sym["dm_view"], struct.pack(">I", VIEW))
    mod.w16(FX_KIT + 2 * 0x37, 0x0150)
    assert mod.call(0x4000_D94A, [0x5000_0000, 269]) == 0x50 << 8
    mod.call(0x4000_DA32, [0x5000_0000, 269, 7 << 8, 1])
    assert mod.r16(FX_KIT + 2 * 0x37) == 0x0107


def test_r_page_slots_at_boot(mod):
    mod.uc.mem_write(0x41B9_F7F8, struct.pack(">I", 269))
    mod.uc.mem_write(0x41B9_F874, struct.pack(">9I", *range(246, 255)))
    mod.call(mod.sym["dm_page_stub"])
    assert list(struct.unpack(">9I", mod.uc.mem_read(0x41B9_F874, 36))) == [125, 0, 269, 0, 129, 130, 0, 0, 0]


def test_header_and_patched_bytes():
    sp = spec("dual-mono")
    sym = {k: int(v, 16) for k, v in sp["symbols"].items()}
    assert sym["dm_hdr"] == DL.HDR and sym["dm_side"] == DL.HDR + 4
    blob = next(p for p in sp["patches"] if p.get("ram") == f"{DL.HDR:#010x}")
    assert bytes.fromhex(blob["hex"])[:4] == DL.MAGIC.to_bytes(4, "big")
    assert int.from_bytes(bytes.fromhex(blob["hex"])[8:12], "big") == sym["dm_page_r"]
    want = {0x4008_F478: "4a3980003146", 0x4008_F5F2: "7f6a0746736a0018", 0x4003_5914: "4eb940044626",
            0x400A_3404: "13c080003146", 0x4019_4F1A: "42b941b9f894", 0x4003_58EE: "401c7f9c",
            0x4019_4E4A: "40251b0c", 0x4019_4EB0: "40251b10", 0x4003_58E8: "7203"}
    sec3 = eft.unpack(SY, ROOT / "unpacked" / SY.stem, ids=[3])[3].read_bytes()
    for a, orig in want.items():
        assert sec3[a - LOAD:a - LOAD + len(orig) // 2].hex() == orig
    assert set(sp["requires"]) == {"modarea", "vparams", "kitstore"}
