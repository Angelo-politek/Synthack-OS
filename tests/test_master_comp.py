"""Mod master-comp (solo branch locale dt-compressor): routine ColdFire vs modello Compact.

Esegue sull'OS Syntakt patchato il tratto 0x4009053E..0x40090562 (trampolino + comp_hook) a
ogni "blocco", con segnali finti sugli ADC 6/7, e confronta i CV del master con il modello.
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
                                UC_M68K_REG_D0, UC_M68K_REG_D1, UC_M68K_REG_D3, UC_M68K_REG_SR)

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
HW, STACK = 0x5000_2000, 0x5001_0000
FX_SLOTS = 0x41B9_F950
IDS = {"THR": 144, "ATK": 72, "REL": 91, "MUP": 101, "RAT": 127}
GET, SET, KIT = 0x4000_D94A, 0x4000_DA32, 0x4000_D870
REGS = [getattr(__import__("unicorn.m68k_const", fromlist=["x"]), f"UC_M68K_REG_{r}")
        for r in ("D0", "D2", "D4", "D5", "D6", "D7", "A0", "A1", "A2", "A4", "A5")]


@pytest.fixture(scope="module")
def setup():
    from model import Compact, Preset, Tables
    spec = json.loads(SPEC_F.read_text(encoding="utf-8"))
    sec3 = eft.unpack(SY, ROOT / "unpacked" / SY.stem, ids=[3])[3].read_bytes()
    dt = Tables(eft.unpack(DT, ROOT / "unpacked" / "DT1.54", ids=[3])[3])
    params = [int(x, 16) for x in spec["params"]]
    return spec, sec3, (lambda: Compact(Preset(dt, params)))


class Machine:
    def __init__(self, spec, sec3):
        uc = self.uc = Uc(UC_ARCH_M68K, UC_MODE_BIG_ENDIAN, cpu=UC_CPU_M68K_ANY)
        uc.mem_map(0x4000_0000, 0x0040_0000)
        uc.mem_write(LOAD, sec3)
        uc.mem_map(0x4600_0000, 0x1_0000)                      # area mod (dopo la rilocazione)
        for p in spec["patches"]:
            dst = int(p["ram"], 16) if p.get("append") else int(p["addr"], 16)
            uc.mem_write(dst, bytes.fromhex(p["hex"]))
        uc.mem_map(0x8000_0000, 0x1_0000)
        uc.mem_map(0x5000_0000, 0x2_0000)
        uc.mem_map(0x41B9_F000, 0x1000)                         # pagina FX Drive (BSS)
        uc.mem_write(FX_SLOTS, struct.pack(">8i", 0, 0, 0, 0, 0, 0, 0, 150))
        self.emac = UnicornEmac(uc, [int(a, 16) for a in spec["emac_sites"]])

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


def test_matches_compact_model_bit_exact(setup):
    spec, sec3, mk_model = setup
    m, model = Machine(spec, sec3), mk_model()
    rnd = random.Random(7)
    for left, right in signal(rnd, 400):
        cv_l, cv_r = rnd.randrange(0, 70000), rnd.randrange(0, 70000)
        got = m.block(left, right, cv_l, cv_r)
        g = model.block(left, right)
        assert got == (expected(g, cv_l), expected(g, cv_r))


def test_silence_gives_makeup_only(setup):
    spec, sec3, mk_model = setup
    m, model = Machine(spec, sec3), mk_model()
    zeros = [0] * 32
    for _ in range(50):
        got = m.block(zeros, zeros, 30000, 30000)
        g = model.block(zeros, zeros)
    mup_db = int(spec["params"][3], 16) / 0x7F00 * 24
    assert abs(20 * math.log10(got[0] / 30000) - mup_db) < 0.1
    assert got[0] == got[1] == expected(g, 30000)


def test_loud_signal_reduces_cv(setup):
    spec, sec3, mk_model = setup
    m = Machine(spec, sec3)
    loud = [int(0.9 * 2**31 * math.sin(2 * math.pi * 200 * i / 48000)) for i in range(32)]
    quiet = m.block([0] * 32, [0] * 32, 30000, 30000)[0]
    for _ in range(200):
        got = m.block(loud, loud, 30000, 30000)[0]
    assert got < quiet / 2                    # piu' di 6 dB di riduzione su un segnale a -1 dBFS


# ----------------------------------------------------------------------------- interfaccia (v0.3)
def call(m, fn, args, stop):
    """Chiama fn(args...) con un indirizzo di ritorno fittizio; si ferma a 'stop' (ritorno o ripresa)."""
    uc = m.uc
    uc.mem_write(0x5000_8000, b"Nu")
    sp = STACK - 4 * (len(args) + 1)
    uc.mem_write(sp, struct.pack(f">{len(args) + 1}I", 0x5000_8000, *[a & 0xFFFFFFFF for a in args]))
    uc.reg_write(UC_M68K_REG_SR, 0x2700)
    uc.reg_write(UC_M68K_REG_A7, sp)
    uc.emu_start(fn, stop, count=10_000)
    return uc.reg_read(UC_M68K_REG_D0) & 0xFFFFFFFF


def test_ui_get_set_and_clamp(setup):
    spec, sec3, _ = setup
    m = Machine(spec, sec3)
    params = [int(x, 16) for x in spec["params"]]
    for (name, i), default in zip(IDS.items(), params):
        assert call(m, GET, [0x5000_0000, i], 0x5000_8000) == default            # preset
        assert call(m, KIT, [0x5000_0000, i], 0x5000_8000) == 1                  # "di kit"
    call(m, SET, [0x5000_0000, IDS["THR"], 0x1234, 1], 0x5000_8000)
    assert call(m, GET, [0x5000_0000, IDS["THR"]], 0x5000_8000) == 0x1234
    call(m, SET, [0x5000_0000, IDS["RAT"], 0x7F00, 1], 0x5000_8000)             # oltre il massimo
    assert call(m, GET, [0x5000_0000, IDS["RAT"]], 0x5000_8000) == 0x0700
    call(m, SET, [0x5000_0000, IDS["MUP"], -5, 1], 0x5000_8000)                 # sotto lo zero
    assert call(m, GET, [0x5000_0000, IDS["MUP"]], 0x5000_8000) == 0


@pytest.mark.parametrize("fn,resume", [(KIT, 0x4000_D878), (GET, 0x4000_D950), (SET, 0x4000_DA3A)])
def test_other_ids_resume_original_code_identically(setup, fn, resume):
    """Per un id non nostro lo stato alla ripresa e' lo stesso dell'OS originale."""
    from unicorn.m68k_const import UC_M68K_REG_D1, UC_M68K_REG_D2
    spec, sec3, _ = setup
    states = []
    for patched in (False, True):
        m = Machine(spec if patched else {"patches": [], "emac_sites": []}, sec3)
        uc = m.uc
        uc.reg_write(UC_M68K_REG_D2, 0x2222_2222)
        uc.reg_write(UC_M68K_REG_D3, 0x3333_3333)
        call(m, fn, [0x5000_0100, 126, 0x4000, 1], resume)
        sp = uc.reg_read(UC_M68K_REG_A7)
        states.append((sp, bytes(uc.mem_read(sp, 32)), uc.reg_read(UC_M68K_REG_D1), uc.reg_read(UC_M68K_REG_D2),
                       uc.reg_read(UC_M68K_REG_D3)))
    assert states[0] == states[1]


def test_constants_follow_parameters(setup):
    from model import Preset, Tables
    spec, sec3, _ = setup
    dt = Tables(eft.unpack(DT, ROOT / "unpacked" / "DT1.54", ids=[3])[3])
    m = Machine(spec, sec3)
    rnd = random.Random(11)
    kc = int(spec["symbols"]["k_const"], 16)
    for _ in range(20):
        v = {k: rnd.randrange(0, 0x80) << 8 for k in IDS}
        v["RAT"] = rnd.randrange(0, 8) << 8
        for k, i in IDS.items():
            call(m, SET, [0x5000_0000, i, v[k], 1], 0x5000_8000)
        m.block([0] * 32, [0] * 32, 1000, 1000)
        got = struct.unpack(">8i", m.uc.mem_read(kc, 32))
        pr = Preset(dt, [v["THR"], v["ATK"], v["REL"], v["MUP"], v["RAT"], 0, 0, 0x7F00])
        one = (1 << 31) - 1
        assert got[1:] == (pr.thr, pr.slope, one - pr.rel, pr.rel, one - pr.att, pr.att, pr.mk)


def test_fx_page_gets_the_five_knobs_only_if_original(setup):
    spec, sec3, _ = setup
    m = Machine(spec, sec3)
    m.block([0] * 32, [0] * 32, 1000, 1000)
    assert list(struct.unpack(">8i", m.uc.mem_read(FX_SLOTS, 32))) == [144, 72, 91, 101, 127, 0, 0, 150]
    m2 = Machine(spec, sec3)
    weird = [1, 2, 3, 4, 5, 6, 7, 8]
    m2.uc.mem_write(FX_SLOTS, struct.pack(">8i", *weird))
    m2.block([0] * 32, [0] * 32, 1000, 1000)
    assert list(struct.unpack(">8i", m2.uc.mem_read(FX_SLOTS, 32))) == weird
