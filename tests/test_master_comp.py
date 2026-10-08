"""Mod master-comp (solo branch locale dt-compressor): routine ColdFire vs modello, interfaccia, salvataggio.

Esegue sull'OS Syntakt patchato il tratto 0x4009053E..0x40090562 (trampolino + comp_hook) a ogni
"blocco", con segnali finti sugli ADC 6/7, e le funzioni centrali dei parametri agganciate.
Serve l'OS Syntakt 1.41 e l'OS Digitakt 1.54 (per le costanti): saltato se mancano.
"""

import json
import math
import random
import struct
import sys
from pathlib import Path

import pytest

pytest.importorskip("unicorn")
from unicorn import UC_ARCH_M68K, UC_MODE_BIG_ENDIAN, Uc  # noqa: E402
from unicorn.m68k_const import (UC_CPU_M68K_ANY, UC_M68K_REG_A3, UC_M68K_REG_A7,  # noqa: E402
                                UC_M68K_REG_D0, UC_M68K_REG_D1, UC_M68K_REG_D2, UC_M68K_REG_D3,
                                UC_M68K_REG_SR)

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "tools" / "emu"), str(ROOT / "tools" / "unpack"), str(ROOT / "mods" / "dt-comp")]
import eft  # noqa: E402
from emac import UnicornEmac  # noqa: E402

SY = ROOT / "firmware" / "Syntakt_OS1.41.syx"
DT = ROOT / "firmware" / "Digitakt_OS1.54.syx"
SPEC_F = ROOT / "mods" / "master-comp" / "patch.json"
pytestmark = pytest.mark.skipif(not (SY.exists() and DT.exists() and SPEC_F.exists()),
                                reason="OS Syntakt/Digitakt o patch assenti")

LOAD = 0x4000_0400
HOOK, AFTER = 0x4009_053E, 0x4009_0562
ADC_L, ADC_R = 0x8000_3C50, 0x8000_3CD0
HW, STACK, RET = 0x5000_2000, 0x5001_0000, 0x5000_8000
FX_SLOTS = 0x41B9_F950
KIT_PTR, KIT, KIT_OFF = 0x8000_30BC, 0x5000_4000, 82
GLOB_STORE, GLOBAL_FLAGS = 0x41B9_D3BC, 0x43BD_E444
IDS = {"THR": 144, "ATK": 72, "REL": 91, "MUP": 101, "RAT": 127, "GR": 59}
GET, SET, KIT_FN = 0x4000_D94A, 0x4000_DA32, 0x4000_D870
REGS = [getattr(__import__("unicorn.m68k_const", fromlist=["x"]), f"UC_M68K_REG_{r}")
        for r in ("D0", "D2", "D4", "D5", "D6", "D7", "A0", "A1", "A2", "A4", "A5")]


@pytest.fixture(scope="module")
def setup():
    from model import Tables
    spec = json.loads(SPEC_F.read_text(encoding="utf-8"))
    sec3 = eft.unpack(SY, ROOT / "unpacked" / SY.stem, ids=[3])[3].read_bytes()
    dt = Tables(eft.unpack(DT, ROOT / "unpacked" / "DT1.54", ids=[3])[3])
    return spec, sec3, dt


class Machine:
    def __init__(self, spec, sec3, kit=True):
        uc = self.uc = Uc(UC_ARCH_M68K, UC_MODE_BIG_ENDIAN, cpu=UC_CPU_M68K_ANY)
        uc.mem_map(0x4000_0000, 0x0040_0000)
        uc.mem_write(LOAD, sec3)
        uc.mem_map(0x4600_0000, 0x1_0000)                      # area mod (dopo la rilocazione)
        for p in spec["patches"]:
            dst = int(p["ram"], 16) if p.get("append") else int(p["addr"], 16)
            uc.mem_write(dst, bytes.fromhex(p["hex"]))
        uc.mem_map(0x8000_0000, 0x1_0000)
        uc.mem_map(0x5000_0000, 0x2_0000)
        uc.mem_map(0x41B9_D000, 0x3000)                        # contenitore globale + pagine (BSS)
        uc.mem_map(0x43BD_E000, 0x1000)                        # bit global
        uc.mem_write(FX_SLOTS, struct.pack(">8i", 0, 0, 0, 0, 0, 0, 0, 150))
        uc.mem_write(KIT_PTR, struct.pack(">I", KIT if kit else 0))
        uc.mem_write(RET, b"\x4e\x75")
        self.emac = UnicornEmac(uc, [int(a, 16) for a in spec.get("emac_sites", [])])

    def block(self, left, right, cv_l, cv_r, macsr=0x20):
        uc = self.uc
        uc.mem_write(ADC_L, struct.pack(">32i", *left))
        uc.mem_write(ADC_R, struct.pack(">32i", *right))
        uc.mem_write(HW, bytes(128))
        self.emac.state.load_macsr(macsr)
        uc.reg_write(UC_M68K_REG_SR, 0x2700)
        uc.reg_write(UC_M68K_REG_A7, STACK)
        uc.reg_write(UC_M68K_REG_A3, HW)
        uc.reg_write(UC_M68K_REG_D1, cv_l)
        uc.reg_write(UC_M68K_REG_D3, cv_r)
        marks = [0x1111_0000 + i for i in range(len(REGS))]
        for r, v in zip(REGS, marks):
            uc.reg_write(r, v)
        uc.emu_start(HOOK, AFTER, count=200_000)
        assert self.emac.error is None, self.emac.error
        assert [uc.reg_read(r) & 0xFFFFFFFF for r in REGS] == marks       # registri preservati
        assert uc.reg_read(UC_M68K_REG_A7) == STACK
        assert self.emac.state.macsr == macsr                              # MACSR ripristinato
        assert self.emac.state.acc[0] == 0                                 # accumulatore pulito
        return struct.unpack_from(">2H", uc.mem_read(HW + 70, 4))

    def call(self, fn, args, stop=RET):
        uc = self.uc
        sp = STACK - 4 * (len(args) + 1)
        uc.mem_write(sp, struct.pack(f">{len(args) + 1}I", RET, *[a & 0xFFFFFFFF for a in args]))
        uc.reg_write(UC_M68K_REG_SR, 0x2700)
        uc.reg_write(UC_M68K_REG_A7, sp)
        uc.emu_start(fn, stop, count=10_000)
        assert self.emac.error is None, self.emac.error
        return uc.reg_read(UC_M68K_REG_D0) & 0xFFFFFFFF

    def get(self, name):
        return self.call(GET, [0x5000_0000, IDS[name]])

    def set(self, name, value):
        self.call(SET, [0x5000_0000, IDS[name], value, 1])

    def words(self, addr):
        return struct.unpack(">I", self.uc.mem_read(addr, 4))[0]


def preset_of(spec):
    v = [int(x, 16) for x in spec["params"]]
    return {"THR": v[0], "ATK": v[1], "REL": v[2], "MUP": v[3], "RAT": v[4] << 8}


def model(dt, p):
    from model import Compact, Preset
    rat_dt = ((p["RAT"] >> 8) - 1) << 8              # RAT 1..8 -> indice 0..7 della Digitakt
    return Compact(Preset(dt, [p["THR"], p["ATK"], p["REL"], p["MUP"], rat_dt, 0, 0, 0x7F00]))


def signal(rnd, n_blocks):
    ph = 0
    for _ in range(n_blocks):
        amp = 10 ** (rnd.uniform(-70, 0) / 20)
        f = rnd.choice([55, 220, 1000, 5000])
        left = [int(amp * 0.999 * 2**31 * math.sin(2 * math.pi * f * (ph + i) / 48000)) for i in range(32)]
        right = [int(v * rnd.uniform(-1, 1)) for v in left]
        ph += 32
        yield left, right


def expected(g, cv):
    cv = min(cv, 65535)
    return min(65535, (cv * g) >> 12)


# ----------------------------------------------------------------------------- default e spento
def test_new_kit_reads_preset_and_compressor_is_off(setup):
    spec, sec3, _ = setup
    m = Machine(spec, sec3)
    p = preset_of(spec)
    for k in ("THR", "ATK", "REL", "MUP"):
        assert m.get(k) == p[k]                     # due parole a zero = preset
    assert m.get("RAT") == 0                         # ... con compressore spento
    loud = [int(0.9 * 2**31 * math.sin(2 * math.pi * 200 * i / 48000)) for i in range(32)]
    for _ in range(20):
        assert m.block(loud, loud, 30000, 70000) == (30000, 65535)   # CV originali (limitati)
    assert m.get("GR") == 0


# ----------------------------------------------------------------------------- compressore acceso
def test_matches_compact_model_bit_exact(setup):
    spec, sec3, dt = setup
    m = Machine(spec, sec3)
    p = preset_of(spec)
    m.set("RAT", p["RAT"])
    mod = model(dt, p)
    rnd = random.Random(7)
    for left, right in signal(rnd, 300):
        cv_l, cv_r = rnd.randrange(0, 70000), rnd.randrange(0, 70000)
        got = m.block(left, right, cv_l, cv_r)
        g = mod.block(left, right)
        assert got == (expected(g, cv_l), expected(g, cv_r))


def test_parameters_change_the_compressor_like_the_model(setup):
    spec, sec3, dt = setup
    rnd = random.Random(11)
    for _ in range(6):
        p = {k: rnd.randrange(0, 0x80) << 8 for k in ("THR", "ATK", "REL", "MUP")}
        p["RAT"] = rnd.randrange(1, 9) << 8
        m = Machine(spec, sec3)
        for k, v in p.items():
            m.set(k, v)
            assert m.get(k) == v
        mod = model(dt, p)
        for left, right in signal(rnd, 40):
            got = m.block(left, right, 40000, 40000)
            assert got == (expected(mod.block(left, right), 40000),) * 2


def test_loud_signal_reduces_cv_and_meter_shows_it(setup):
    spec, sec3, _ = setup
    m = Machine(spec, sec3)
    m.set("RAT", 8 << 8)                             # 20:1
    loud = [int(0.9 * 2**31 * math.sin(2 * math.pi * 200 * i / 48000)) for i in range(32)]
    quiet = m.block([0] * 32, [0] * 32, 30000, 30000)[0]
    for _ in range(200):
        got = m.block(loud, loud, 30000, 30000)[0]
    assert got < quiet / 2
    gr = m.get("GR")
    assert 0x1000 < gr <= 0x7F00                     # riduzione di qualche dB visibile
    m.set("GR", 0)                                   # sola lettura: ignorato
    assert m.get("GR") == gr


# ----------------------------------------------------------------------------- salvataggio
def test_values_live_in_the_pattern_kit_words(setup):
    spec, sec3, _ = setup
    m = Machine(spec, sec3)
    k_def = int(spec["k_def"], 16)
    m.set("THR", 0x1200)
    m.set("RAT", 0x300)
    raw = m.words(KIT + KIT_OFF) ^ k_def
    assert (raw >> 25) & 0x7F == 0x12 and raw & 0xF == 3
    assert m.words(GLOB_STORE) == 0                  # il globale non e' toccato
    m.uc.mem_write(KIT + KIT_OFF, bytes(4))          # altro kit (parole a zero) -> preset, spento
    assert m.get("THR") == preset_of(spec)["THR"] and m.get("RAT") == 0


def test_syn_global_uses_the_global_words(setup):
    spec, sec3, _ = setup
    m = Machine(spec, sec3)
    m.set("MUP", 0x7F00)
    m.uc.mem_write(GLOBAL_FLAGS, struct.pack(">I", 4))          # SYN global
    assert m.get("MUP") == preset_of(spec)["MUP"]                # globale ancora a zero = preset
    m.set("MUP", 0x0500)
    assert m.get("MUP") == 0x0500
    m.uc.mem_write(GLOBAL_FLAGS, struct.pack(">I", 0))
    assert m.get("MUP") == 0x7F00                                # il kit ha il suo valore
    assert m.words(GLOB_STORE) != 0


def test_no_kit_yet_uses_ram_fallback(setup):
    spec, sec3, _ = setup
    m = Machine(spec, sec3, kit=False)
    m.set("REL", 0x3300)
    assert m.get("REL") == 0x3300


def test_set_clamps_to_range(setup):
    spec, sec3, _ = setup
    m = Machine(spec, sec3)
    m.set("RAT", 0x7F00)
    assert m.get("RAT") == 0x0800
    m.set("ATK", -5)
    assert m.get("ATK") == 0
    m.set("THR", 0x7FFF)
    assert m.get("THR") == 0x7F00


# ----------------------------------------------------------------------------- integrazione OS
def test_our_ids_are_kit_params(setup):
    spec, sec3, _ = setup
    m = Machine(spec, sec3)
    for i in IDS.values():
        assert m.call(KIT_FN, [0x5000_0000, i]) == 1


@pytest.mark.parametrize("fn,resume", [(KIT_FN, 0x4000_D878), (GET, 0x4000_D950), (SET, 0x4000_DA3A)])
def test_other_ids_resume_original_code_identically(setup, fn, resume):
    """Per un id non nostro lo stato alla ripresa e' lo stesso dell'OS originale."""
    spec, sec3, _ = setup
    states = []
    for patched in (False, True):
        m = Machine(spec if patched else {"patches": [], "emac_sites": []}, sec3)
        uc = m.uc
        uc.reg_write(UC_M68K_REG_D2, 0x2222_2222)
        uc.reg_write(UC_M68K_REG_D3, 0x3333_3333)
        m.call(fn, [0x5000_0100, 126, 0x4000, 1], resume)
        sp = uc.reg_read(UC_M68K_REG_A7)
        states.append((sp, bytes(uc.mem_read(sp, 32)), uc.reg_read(UC_M68K_REG_D1), uc.reg_read(UC_M68K_REG_D2),
                       uc.reg_read(UC_M68K_REG_D3)))
    assert states[0] == states[1]


def test_fx_page_gets_the_knobs_only_if_original(setup):
    spec, sec3, _ = setup
    m = Machine(spec, sec3)
    m.block([0] * 32, [0] * 32, 1000, 1000)
    assert list(struct.unpack(">8i", m.uc.mem_read(FX_SLOTS, 32))) == [144, 72, 91, 101, 127, 59, 0, 150]
    m2 = Machine(spec, sec3)
    weird = [1, 2, 3, 4, 5, 6, 7, 8]
    m2.uc.mem_write(FX_SLOTS, struct.pack(">8i", *weird))
    m2.block([0] * 32, [0] * 32, 1000, 1000)
    assert list(struct.unpack(">8i", m2.uc.mem_read(FX_SLOTS, 32))) == weird
