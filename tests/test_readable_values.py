"""Mod readable-values: i testi corrispondono ai valori che il codice originale usa davvero.

Per ogni parametro: (1) si esegue nell'emulatore il tratto di codice originale che converte il
valore (coefficiente del filtro, campioni di pre-delay, guadagno); (2) si chiama rv_invoke come
farebbe l'OS; (3) il numero stampato deve coincidere con quello esatto, entro l'ultima cifra.
Serve l'OS Syntakt 1.41 (saltato se manca).
"""

import json
import math
import re
import struct
import sys
from pathlib import Path

import pytest

pytest.importorskip("unicorn")
from unicorn import UC_ARCH_M68K, UC_MODE_BIG_ENDIAN, Uc  # noqa: E402
from unicorn.m68k_const import (UC_CPU_M68K_ANY, UC_M68K_REG_A0, UC_M68K_REG_A2, UC_M68K_REG_A3,  # noqa: E402
                                UC_M68K_REG_A6, UC_M68K_REG_A7, UC_M68K_REG_D0, UC_M68K_REG_D1,
                                UC_M68K_REG_D2, UC_M68K_REG_D3, UC_M68K_REG_D4, UC_M68K_REG_D7,
                                UC_M68K_REG_SR)

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "tools" / "emu"), str(ROOT / "tools" / "unpack")]
import eft  # noqa: E402
from emac import UnicornEmac  # noqa: E402

SY = ROOT / "firmware" / "Syntakt_OS1.41.syx"
SPEC_F = ROOT / "mods" / "readable-values" / "patch.json"
pytestmark = pytest.mark.skipif(not (SY.exists() and SPEC_F.exists()), reason="OS Syntakt o patch assenti")

LOAD = 0x4000_0400
OBJS = 0x41B9_FA24
SRAM = 0x8000_21B0
DLY, REV = SRAM + 1766, SRAM + 1786     # blocchi di parametri copiati per il motore
STACK, RET, BUF = 0x5000_8000, 0x5000_F000, 0x5000_C000
POLE = 0x4029_BFFC


@pytest.fixture(scope="module")
def m():
    spec = json.loads(SPEC_F.read_text(encoding="utf-8"))
    sec3 = eft.unpack(SY, ROOT / "unpacked" / SY.stem, ids=[3])[3].read_bytes()
    return Machine(spec, sec3)


class Machine:
    def __init__(self, spec, sec3):
        self.spec, self.sec3 = spec, sec3
        uc = self.uc = Uc(UC_ARCH_M68K, UC_MODE_BIG_ENDIAN, cpu=UC_CPU_M68K_ANY)
        uc.mem_map(0x4000_0000, 0x0040_0000)
        uc.mem_write(LOAD, sec3)
        uc.mem_map(0x41B9_0000, 0x0002_0000)                   # oggetti per-parametro (BSS)
        uc.mem_map(0x4600_0000, 0x1_0000)                      # area mod
        uc.mem_map(0x5000_0000, 0x1_0000)
        uc.mem_map(0x8000_0000, 0x1_0000)                      # SRAM
        uc.mem_map(0x43BD_0000, 0x1_0000)                      # stato degli inviluppi del filtro
        uc.mem_map(0x444E_0000, 0x1_0000)                      # singleton del progetto (*0x444E13F4)
        # finto progetto: selettore a +48 con metodo virtuale +40 che restituisce un oggetto con la
        # traccia attiva a +8 (catena letta da 0x4001FF74)
        S, VT, STUB, OBJ = 0x5000_9000, 0x5000_9800, 0x5000_9900, 0x5000_9A00
        uc.mem_write(0x444E_13F4, struct.pack(">I", S))
        uc.mem_write(S + 48, struct.pack(">I", VT))
        uc.mem_write(VT + 40, struct.pack(">I", STUB))
        uc.mem_write(STUB, bytes.fromhex("203c") + struct.pack(">I", OBJ) + bytes.fromhex("4e75"))
        self.active = OBJ + 8
        for p in spec["patches"]:
            uc.mem_write(int(p["ram"], 16) if p.get("append") else int(p["addr"], 16), bytes.fromhex(p["hex"]))
        uc.mem_write(RET, b"\x4e\x75")
        # istruzioni EMAC dei tratti di codice originale eseguiti dai test
        self.emac = UnicornEmac(uc, [
            0x4009_6EAA, 0x4009_6EAE, 0x4009_6EB2, 0x4009_6EB4,                         # reverb
            0x4009_6606, 0x4009_660A, 0x4009_6610, 0x4009_6614, 0x4009_6618,           # inviluppo filtro
            0x4009_6626, 0x4009_662A,
            0x4008_ED70, 0x4008_ED74, 0x4008_ED80, 0x4008_ED84, 0x4008_ED8E,           # guadagno traccia
            0x4008_ED92, 0x4008_ED98, 0x4008_ED9C, 0x4008_EDA0, 0x4008_EDA4,
            0x4008_EDA6, 0x4008_EDAA, 0x4008_EDB0, 0x4008_EDB4,
            0x4008_F48E, 0x4008_F492, 0x4008_F498, 0x4008_F49C,                         # ingresso esterno
            0x4008_F60E, 0x4008_F612, 0x4008_F61C, 0x4008_F620, 0x4008_F626, 0x4008_F62A,  # FX track
        ])
        self.emac.state.load_macsr(0xA0)
        self.sym = {k: int(v, 16) for k, v in spec["symbols"].items()}

    def run(self, start, stop, regs):
        uc = self.uc
        uc.reg_write(UC_M68K_REG_SR, 0x2700)
        uc.reg_write(UC_M68K_REG_A7, STACK)
        for r, v in regs.items():
            uc.reg_write(r, v & 0xFFFFFFFF)
        uc.emu_start(start, stop, count=10_000)
        assert self.emac.error is None, self.emac.error

    def call(self, fn, args, count=100_000):
        uc = self.uc
        sp = STACK - 4 * (len(args) + 1)
        uc.mem_write(sp, struct.pack(f">{len(args) + 1}I", RET, *[a & 0xFFFFFFFF for a in args]))
        uc.reg_write(UC_M68K_REG_SR, 0x2700)
        uc.reg_write(UC_M68K_REG_A7, sp)
        uc.emu_start(fn, RET, count=count)
        assert self.emac.error is None, self.emac.error
        return uc.reg_read(UC_M68K_REG_D0) & 0xFFFFFFFF

    def track(self, pid, t):
        """Traccia attiva t (pid ignorato: tutti i parametri di traccia usano la traccia attiva)."""
        self.uc.mem_write(self.active, struct.pack(">i", t))

    def word(self, addr, v):
        self.uc.mem_write(addr, struct.pack(">h", v))

    def long(self, addr):
        return struct.unpack(">i", self.uc.mem_read(addr, 4))[0]

    def text(self, fn, value):
        """Come l'OS: invoker(funzione, valore, buffer)."""
        uc = self.uc
        uc.mem_write(BUF, b"\xEE" * 16)
        sp = STACK - 16
        uc.mem_write(sp, struct.pack(">4I", RET, fn, value & 0xFFFFFFFF, BUF))
        uc.reg_write(UC_M68K_REG_SR, 0x2700)
        uc.reg_write(UC_M68K_REG_A7, sp)
        uc.emu_start(self.sym["rv_invoke"], RET, count=200_000)
        raw = bytes(uc.mem_read(BUF, 16))
        return raw[:raw.index(0)].decode()

    def fmt(self, pid, value):
        return self.text(OBJS + 84 * pid + 20, value)


# ----------------------------------------------------------------------------- riferimenti esatti
FS = 48000


def lpf_hz(p):
    x = (1 - p) / (2 * math.sqrt(p)) if p > 0 else 2
    return FS / 2 if x >= 1 else math.asin(x) * FS / math.pi


def hpf_hz(p):
    x = (1 - p) / math.sqrt(2 * (1 + p * p))
    return math.asin(min(1.0, x)) * FS / math.pi


UNITS = {"Hz": 1, "k": 1000, "dB": 1, "ms": 1}


def parse(t):
    """'1.01k' -> (1010, 10): valore e passo dell'ultima cifra."""
    mm = re.fullmatch(r"(-?)(\d+)(?:\.(\d+))?(Hz|k|dB|ms)", t)
    assert mm, t
    dec = mm[3] or ""
    scale = UNITS[mm[4]]
    v = (int(mm[2]) + (int(dec) / 10 ** len(dec) if dec else 0)) * scale
    return (-v if mm[1] else v), scale / 10 ** len(dec)


def close(t, exact, rel=0.002):
    v, step = parse(t)
    return abs(v - exact) <= step / 2 + rel * abs(exact) + 1e-9


def values():
    return list(range(0, 0x7F01, 0x100)) + [0x1234, 0x7EFF, 0x40C0]


# ----------------------------------------------------------------------------- delay e reverb: filtri
def test_delay_filters_match_original_coefficients(m):
    for hp in (0, 0x1000, 0x4000, 0x7F00):
        for lp in values()[::4]:
            m.word(DLY + 8, hp)
            m.word(DLY + 10, lp)
            m.run(0x4009_68C4, 0x4009_6928, {UC_M68K_REG_A6: DLY})
            p_hp, p_lp = m.long(0x8000_D910) / 2**31, m.long(0x8000_D914) / 2**31
            assert close(m.fmt(110, hp), hpf_hz(p_hp)), (hp, m.fmt(110, hp), hpf_hz(p_hp))
            assert close(m.fmt(111, lp), lpf_hz(p_lp)), (hp, lp, m.fmt(111, lp), lpf_hz(p_lp))


def test_reverb_filters_and_predelay_match_original(m):
    for hp in (0, 0x2000, 0x7F00):
        for v in values()[::3]:
            m.word(REV + 0, v)            # PRE
            m.word(REV + 8, hp)           # HPF
            m.word(REV + 10, v)           # LPF
            m.run(0x4009_6E48, 0x4009_6EE2, {UC_M68K_REG_A0: REV})
            p_hp, p_lp = m.long(0x8000_C530) / 2**31, m.long(0x8000_C534) / 2**31
            pre = m.long(0x8000_C63C)
            assert close(m.fmt(120, hp), hpf_hz(p_hp)), (hp, m.fmt(120, hp))
            assert close(m.fmt(121, v), lpf_hz(p_lp)), (hp, v, m.fmt(121, v), lpf_hz(p_lp))
            assert close(m.fmt(116, v), pre / 48), (v, m.fmt(116, v), pre / 48)


# ----------------------------------------------------------------------------- livelli
def test_mix_levels_match_original_gain(m):
    for v in values():
        m.word(SRAM + 1780, v)            # delay VOL
        m.word(SRAM + 1798, v)            # reverb VOL
        m.uc.reg_write(UC_M68K_REG_A2, SRAM)
        m.uc.reg_write(UC_M68K_REG_D4, 0)
        m.uc.reg_write(UC_M68K_REG_SR, 0x2700)
        m.uc.reg_write(UC_M68K_REG_A7, STACK)
        m.uc.emu_start(0x4008_F96A, 0x4008_F996, count=100)
        g_dly = -struct.unpack(">i", struct.pack(">I", m.uc.reg_read(UC_M68K_REG_D1) & 0xFFFFFFFF))[0] / 2**31
        g_rev = -struct.unpack(">i", struct.pack(">I", m.uc.reg_read(UC_M68K_REG_D0) & 0xFFFFFFFF))[0] / 2**31
        for pid, g in ((114, g_dly), (123, g_rev), (122, g_rev)):     # 113 e' RPT (beat-repeat)
            t = m.fmt(pid, v)
            if g == 0:
                assert t == "-inf"
            else:
                assert close(t, 20 * math.log10(g), rel=0), (pid, v, t, 20 * math.log10(g))


def test_delay_to_reverb_send_matches_original_gain(m):
    for v in values():
        m.word(SRAM + 1778, v)
        m.uc.reg_write(UC_M68K_REG_A2, SRAM)
        m.uc.reg_write(UC_M68K_REG_SR, 0x2700)
        m.uc.reg_write(UC_M68K_REG_A7, STACK)
        m.uc.emu_start(0x4008_F85A, 0x4008_F868, count=100)
        g = -struct.unpack(">i", struct.pack(">I", m.uc.reg_read(UC_M68K_REG_D0) & 0xFFFFFFFF))[0] / 2**31
        t = m.fmt(112, v)
        assert t == "-inf" if g == 0 else close(t, 20 * math.log10(g), rel=0), (v, t)


# ----------------------------------------------------------------------------- forma dei testi
def test_texts_are_short_and_monotonic(m):
    for pid in (110, 111, 112, 114, 116, 120, 121, 123):
        m.word(DLY + 8, 0)
        m.word(REV + 8, 0)
        prev = None
        for v in range(0, 0x7F01, 0x100):
            t = m.fmt(pid, v)
            assert 1 <= len(t) <= 6, (pid, v, t)
            n = -1e9 if t == "-inf" else parse(t)[0]
            assert prev is None or n >= prev, (pid, v, t)
            prev = n


def test_examples(m):
    m.word(DLY + 8, 0)
    assert m.fmt(110, 0) == "5.0Hz"
    assert m.fmt(114, 0x4000) == "-12dB" and m.fmt(114, 0) == "-inf" and m.fmt(114, 0x7F00) == "-0.1dB"
    assert m.fmt(116, 0) == "0.8ms" and m.fmt(116, 0x7F00) == "337ms"
    assert m.fmt(111, 0x7F00) == "24.0k"


def test_unknown_function_prints_plain_number(m):
    assert m.text(0x5000_1000, 0x4000) == "64"
    assert m.text(OBJS + 84 * 110 + 21, 0x4000) == "64"   # non allineato a un oggetto


def test_os_init_copy_installs_our_formatter(m):
    """La copia dell'inizializzatore (0x401882BE) con rv_proto: gestore ed esecutore nostri."""
    dst = OBJS + 84 * 110 + 20
    m.uc.mem_write(dst, b"\xAA" * 16)
    sp = STACK - 12
    m.uc.mem_write(sp, struct.pack(">3I", RET, dst, m.sym["rv_proto"]))
    m.uc.reg_write(UC_M68K_REG_SR, 0x2700)
    m.uc.reg_write(UC_M68K_REG_A7, sp)
    m.uc.emu_start(0x4018_82BE, RET, count=1000)
    mgr, inv = struct.unpack(">II", m.uc.mem_read(dst + 8, 8))
    assert (mgr, inv) == (m.sym["rv_mgr"], m.sym["rv_invoke"])


def test_patched_operands_point_to_our_prototype(m):
    ops = [p for p in m.spec["patches"] if not p.get("append") and p["len"] == 4]
    assert len(ops) == len(m.spec["ids"])
    protos = {0x41B9DFD0, 0x41B9DFB0, 0x41B9DDB0, 0x41B9DDC0, 0x41B9DF30}   # formattatori dell'OS
    for p in ops:
        a = int(p["addr"], 16) - LOAD
        assert struct.unpack(">I", m.sec3[a:a + 4])[0] in protos
        assert int(p["hex"], 16) == m.sym["rv_proto"]


# ----------------------------------------------------------------------------- fase 2: inviluppi
F_STATE, F_VALUE = 0x43BD_C09C, 0x43BD_C0A0       # traccia 0: stato, contatore (+8); valore
FENV = 0x4009_652C                                 # inviluppo del filtro (CPU #1), 8 tracce


def time_close(t, samples, slack):
    """Testo di tempo contro i campioni misurati, con tolleranza di 'slack' campioni."""
    if t == "INF":
        return False
    mm = re.fullmatch(r"(\d+(?:\.\d+)?)(ms|s)", t)
    assert mm, t
    v = float(mm[1]) * (1 if mm[2] == "ms" else 1000)
    step = (10 ** -len(mm[1].split(".")[1]) if "." in mm[1] else 1) * (1 if mm[2] == "ms" else 1000)
    return abs(v - samples / 48) <= step / 2 + slack / 48 + 0.002 * v


def fenv_block(m, trig=0):
    m.call(FENV, [SRAM, trig, 0, 0], count=20_000)


def fenv_set(m, dly=0, atk=0, dec=0, sus=0, rel=0, reset=1):
    for off, v in ((90, dly), (92, atk), (94, dec), (96, sus), (98, rel), (100, reset)):
        m.word(SRAM + off, v)


def fenv_state(m):
    return m.long(F_STATE), m.long(F_VALUE)


@pytest.mark.parametrize("i", [0, 1, 4, 16, 32, 64, 96])
def test_filter_env_delay_and_attack_match_original(m, i):
    m.track(63, 0)
    m.track(64, 0)
    fenv_set(m, dly=i << 8, atk=i << 8, dec=127 << 8)
    fenv_block(m, trig=1)
    n = 0
    while fenv_state(m)[0] == 3:                   # ritardo
        fenv_block(m)
        n += 1
    assert time_close(m.fmt(63, i << 8), n * 32, 32), (i, n, m.fmt(63, i << 8))
    n = 0
    while fenv_state(m)[0] == 2:                   # attacco
        fenv_block(m)
        n += 1
    assert time_close(m.fmt(64, i << 8), n * 32, 32), (i, n, m.fmt(64, i << 8))


@pytest.mark.parametrize("i", [0, 1, 4, 16, 48, 80])
def test_filter_env_decay_to_minus_60db_matches_original(m, i):
    m.track(65, 0)
    m.track(67, 0)
    fenv_set(m, atk=0, dec=i << 8, sus=0)
    fenv_block(m, trig=1)
    while fenv_state(m)[0] == 2:
        fenv_block(m)
    peak = abs(fenv_state(m)[1])
    n = 0
    while abs(fenv_state(m)[1]) > peak / 1000:
        fenv_block(m)
        n += 1
    for pid in (65, 67):                           # REL usa la stessa tabella
        assert time_close(m.fmt(pid, i << 8), n * 32, 32), (pid, i, n, m.fmt(pid, i << 8))


def test_filter_env_127_is_inf_and_analog_filter_env_shows_numbers(m):
    m.track(65, 0)
    assert m.fmt(65, 0x7F00) == "INF"
    for pid in (63, 64, 65, 67):
        m.track(pid, 9)                            # traccia 10: analogica, legge non misurata
        assert m.fmt(pid, 0x4000) == "64"
    m.track(75, -1)
    assert m.fmt(75, 0x4000) == "64"


# misure sulla macchina (traccia 9, tools/measure/analog.py): FREQ -> Hz della risonanza,
# attacco (da -40 a -1 dB, rampa lineare) e tempo a -60 dB
ANALOG_FREQ = {0: 14.56, 64: 583.85, 80: 1445.65, 96: 3660.5, 112: 8961.4}
ANALOG_ATK_MS = {64: 274.4, 96: 862.2, 120: 9631.4}
ANALOG_DEC_MS = {16: 292.9, 32: 1434.6, 64: 7580.6, 96: 19982.1}


def tilde_time(t):
    assert t.startswith("~"), t
    return float(t[1:-2]) if t.endswith("ms") else float(t[1:-1]) * 1000


def test_analog_filter_matches_measurements(m):
    for pid, track in ((58, 9), (133, 12)):
        m.track(0, track)
        for v, f in ANALOG_FREQ.items():
            t = m.fmt(pid, v << 8)
            assert close(t, f, rel=0.02), (pid, v, t, f)
    m.track(0, 9)
    assert m.fmt(70, 0x4000) == "64"               # base-width: niente sulle tracce analogiche


def test_analog_amp_times_match_measurements(m):
    for pid_a, pid_d, track in ((73, 75, 9), (145, 147, 12)):
        m.track(0, track)
        for v, ms in ANALOG_ATK_MS.items():
            assert abs(tilde_time(m.fmt(pid_a, v << 8)) / ms - 1) < 0.03, (pid_a, v, m.fmt(pid_a, v << 8))
        for v, ms in ANALOG_DEC_MS.items():
            for pid in (pid_d, pid_d + 2):         # REL come DEC
                assert abs(tilde_time(m.fmt(pid, v << 8)) / ms - 1) < 0.03, (pid, v, m.fmt(pid, v << 8))
        assert m.fmt(pid_d, 0x7F00) == "INF"
    assert m.fmt(146, 0x7F00) == "INF" and m.fmt(146, 0x4000) == m.fmt(74, 0x4000)
    assert m.fmt(148, 0x4000) == "50%" and m.fmt(140, 0x7F00) == "100%"


def test_hold_and_sustain(m):
    assert m.fmt(74, 0x7F00) == "INF"
    assert m.fmt(74, 0) == "0.0ms"
    assert m.fmt(66, 0x7F00) == "100%" and m.fmt(76, 0) == "0%" and m.fmt(76, 0x4000) == "50%"


def test_amp_tables_are_the_engine_tables(m):
    """Le tabelle d'ampiezza lette dalla CPU #1 sono identiche a quelle del motore (sezione 7)."""
    s7 = eft.unpack(SY, ROOT / "unpacked" / SY.stem, ids=[7])[7].read_bytes()
    for cpu1, cpu2 in ((0x401D_ADDC, 0x4001_4070), (0x401D_A9DC, 0x4001_3C70), (0x401D_ABDC, 0x4001_3E70)):
        assert m.sec3[cpu1 - LOAD:cpu1 - LOAD + 512] == s7[cpu2 - LOAD:cpu2 - LOAD + 512]


class Engine2:
    """Solo la funzione d'inviluppo d'ampiezza della CPU #2 (0x40001476), su un segnale costante."""

    def __init__(self):
        s7 = eft.unpack(SY, ROOT / "unpacked" / SY.stem, ids=[7])[7].read_bytes()
        uc = self.uc = Uc(UC_ARCH_M68K, UC_MODE_BIG_ENDIAN, cpu=UC_CPU_M68K_ANY)
        uc.mem_map(0x4000_0000, 0x0008_0000)
        uc.mem_write(LOAD, s7)
        uc.mem_map(0x5000_0000, 0x1_0000)
        uc.mem_write(RET, b"\x4e\x75")
        sites = json.loads((ROOT / "tools" / "emu" / "emac_sites_os141.json").read_text())["sites"]
        self.emac = UnicornEmac(uc, sites)
        self.emac.state.load_macsr(0xA0)
        self.buf, self.st, self.par = 0x5000_1000, 0x5000_2000, 0x5000_3000

    def setup(self, atk, hold, dec, sus=0, rel=0, mode=0):
        uc = self.uc
        uc.mem_write(self.st, bytes(12))
        uc.mem_write(self.par, bytes(32))
        for off, v in ((2, atk), (4, hold), (6, dec), (8, sus), (10, rel), (22, mode << 8), (24, 0x100)):
            uc.mem_write(self.par + off, struct.pack(">h", v))

    def block(self, trig=0):
        uc = self.uc
        uc.mem_write(self.buf, struct.pack(">32i", *[0x4000_0000] * 32))
        args = [self.buf, self.st, self.par, trig, 0, 0, 0]
        sp = STACK - 4 * (len(args) + 1)
        uc.mem_write(sp, struct.pack(f">{len(args) + 1}I", RET, *args))
        uc.reg_write(UC_M68K_REG_SR, 0x2700)
        uc.reg_write(UC_M68K_REG_A7, sp)
        uc.emu_start(0x4000_1476, RET, count=50_000)
        assert self.emac.error is None, self.emac.error
        return [abs(x) for x in struct.unpack(">32i", uc.mem_read(self.buf, 128))]


@pytest.fixture(scope="module")
def e2():
    return Engine2()


@pytest.mark.parametrize("i", [1, 4, 16, 32, 64])
def test_amp_attack_matches_engine(m, e2, i):
    m.track(73, 0)
    e2.setup(atk=i << 8, hold=0, dec=127 << 8)
    e2.block(trig=1)                               # il trig avvia l'attacco a fine blocco
    out = []
    for _ in range(4000):
        out += e2.block()
        if len(out) > 64 and out[-1] == out[-33]:
            break
    peak = max(out)
    n = next(k for k, x in enumerate(out) if x >= peak)
    assert time_close(m.fmt(73, i << 8), n, 2), (i, n, m.fmt(73, i << 8))


@pytest.mark.parametrize("i", [1, 4, 16, 32])
def test_amp_decay_to_minus_60db_matches_engine(m, e2, i):
    m.track(75, 0)
    m.track(77, 0)
    e2.setup(atk=0, hold=0, dec=i << 8)
    e2.block(trig=1)
    out = e2.block() + e2.block()
    peak = max(out)
    start = out.index(peak)
    while min(out[-32:]) > peak / 1000:
        out += e2.block()
    n = next(k for k in range(start, len(out)) if out[k] <= peak / 1000) - start
    for pid in (75, 77):
        assert time_close(m.fmt(pid, i << 8), n, 4), (pid, i, n, m.fmt(pid, i << 8))


# ----------------------------------------------------------------------------- livelli
def gain_db(g):
    return 20 * math.log10(g)


def s32(x):
    return x - (1 << 32) if x & 0x8000_0000 else x


def test_track_volume_and_level_match_original_gain(m):
    def gain(lev, vol):
        return s32(m.call(0x4008_ED48, [lev, 0x7F00, vol, 0])) / 2**31
    full = gain(0x7F00, 0x7F00)
    for v in values():
        for pid, g in ((81, gain(0x7F00, v)), (10, gain(v, 0x7F00))):
            t = m.fmt(pid, v)
            assert t == "-inf" if g == 0 else close(t, gain_db(g / full), rel=0), (pid, v, t)


def test_track_sends_match_original_gain(m):
    a3 = SRAM
    for v in values():
        m.word(a3 + 118, v)
        m.word(a3 + 120, v)
        m.uc.mem_write(0x5000_7000 - 508, bytes(4))
        regs = {UC_M68K_REG_A3: a3, UC_M68K_REG_D3: 0, UC_M68K_REG_A6: 0x5000_7000}
        m.run(0x4008_F37E, 0x4008_F3A0, regs)
        g = -struct.unpack(">i", struct.pack(">I", m.uc.reg_read(UC_M68K_REG_D7) & 0xFFFFFFFF))[0] / 2**31
        for pid in (78, 79, 151, 152, 129, 130):
            t = m.fmt(pid, v)
            assert t == "-inf" if g == 0 else close(t, gain_db(g), rel=0), (pid, v, t)


def test_external_input_level_matches_original_gain(m):
    m.uc.mem_write(0x8000_3146, b"\x01")             # stereo
    full = None
    for v in [0x7F00] + values():
        m.word(SRAM + 1802, v)
        m.run(0x4008_F480, 0x4008_F4A6, {UC_M68K_REG_A2: SRAM})
        g = s32(m.uc.reg_read(UC_M68K_REG_D2) & 0xFFFFFFFF) / 2**31
        full = full or g
        if v == 0x7F00:
            continue
        for pid in (126, 125):
            t = m.fmt(pid, v)
            assert t == "-inf" if g == 0 else close(t, gain_db(g / full), rel=0), (pid, v, t)


def test_fx_track_volume_matches_original_gain(m):
    m.word(SRAM + 24, 0x7F00)                      # LEV della FX track
    full = None
    for v in [0x7F00] + values():
        m.word(SRAM + 1864, v)
        m.run(0x4008_F5F6, 0x4008_F62C, {UC_M68K_REG_A2: SRAM, UC_M68K_REG_A6: 0x5000_7000})
        g = (s32(m.uc.reg_read(UC_M68K_REG_D2) & 0xFFFFFFFF) / 2**31) ** 2
        full = full or g
        if v == 0x7F00:
            continue
        t = m.fmt(154, v)
        assert t == "-inf" if g == 0 else close(t, gain_db(g / full), rel=0), (v, t)


# ----------------------------------------------------------------------------- traccia attiva
def test_active_track_comes_from_the_os_selector(m):
    m.track(0, 3)
    assert m.fmt(58, 0x4000) == "326Hz"
    m.track(0, 9)                                  # analogica: legge misurata
    assert m.fmt(58, 0x4000) == "577Hz"
    m.track(0, 13)                                 # fuori intervallo: numero
    assert m.fmt(58, 0x4000) == "64"
    m.uc.mem_write(0x444E_13F4, bytes(4))          # progetto non ancora creato
    assert m.fmt(64, 0x4000) == "64"
    m.uc.mem_write(0x444E_13F4, struct.pack(">I", 0x5000_9000))
    m.track(0, 0)


# ----------------------------------------------------------------------------- fase 3: filtri delle tracce digitali
class EngineFilter(Engine2):
    """Filtro multimodo del motore (0x400019D6): coefficienti del biquad per un taglio dato."""

    TRACKS = 0x8000_3C40

    def __init__(self):
        super().__init__()
        uc = self.uc
        uc.mem_map(0x4400_0000, 0x0010_0000)
        uc.mem_map(0x8000_0000, 0x1_0000)
        self.run(0x4000_1860, [])

    def run(self, fn, args):
        uc = self.uc
        sp = STACK - 4 * (len(args) + 1)
        uc.mem_write(sp, struct.pack(f">{len(args) + 1}I", RET, *[a & 0xFFFFFFFF for a in args]))
        uc.reg_write(UC_M68K_REG_SR, 0x2700)
        uc.reg_write(UC_M68K_REG_A7, sp)
        self.emac.state.load_macsr(0xA0)
        uc.emu_start(fn, RET, count=2_000_000)
        assert self.emac.error is None, self.emac.error

    def f0(self, v, reso=0x7F00):
        """Frequenza propria dei poli (Hz) con risonanza alta: angolo dei poli del biquad."""
        tr = self.TRACKS + 82
        self.uc.mem_write(tr, struct.pack(">h", 0))             # TYPE 0
        self.uc.mem_write(tr + 4, struct.pack(">h", reso))      # RESO
        for _ in range(3):
            self.uc.mem_write(0x8000_3840, bytes(128))
            self.run(0x4000_19D6, [tr, 0x8000_3840, v << 16, 0, 0, 0])
        c = [x / 2**31 for x in struct.unpack(">6i", self.uc.mem_read(0x8000_8740, 24))]
        a1, a2 = -(c[1] + c[5]), c[1] * c[5] + c[2] * c[4]
        return math.acos(-a1 / (2 * math.sqrt(a2))) * 48000 / (2 * math.pi)


@pytest.fixture(scope="module")
def ef():
    return EngineFilter()


def test_digital_filter_freq_matches_engine_poles(m, ef):
    m.track(58, 0)
    for v in list(range(0, 0x7F01, 0x400)) + [0x7F00, 0x40C0, 0x1234]:
        f = ef.f0(v)
        t = m.fmt(58, v)
        assert close(t, f, rel=0.004), (v, t, f)


def test_digital_filter_freq_does_not_depend_on_resonance(ef):
    for v in (0x2000, 0x5000, 0x7000):
        a, b = ef.f0(v, 0x4000), ef.f0(v, 0x7F00)
        assert abs(a / b - 1) < 0.003, (v, a, b)


def test_base_width_uses_the_delay_pole_table(m):
    s7 = eft.unpack(SY, ROOT / "unpacked" / SY.stem, ids=[7])[7].read_bytes()
    assert s7[0x4004_0060 - LOAD:0x4004_0060 - LOAD + 4096] == m.sec3[POLE - LOAD:POLE - LOAD + 4096]
    m.track(70, 2)
    m.track(71, 2)
    m.word(SRAM + 142 * 2 + 102, 0x4000)            # BASE della traccia 3 = 64
    assert m.fmt(70, 0x4000) == m.fmt(110, 0x4000)  # come l'HPF del delay
    m.word(DLY + 8, 0x4000)
    assert m.fmt(71, 0x1000) == m.fmt(111, 0x1000)  # WDTH parte da BASE come il LPF da HPF
    m.track(58, 8)
    m.track(70, 8)
    assert m.fmt(58, 0x4000) == "577Hz" and m.fmt(70, 0x4000) == "64"   # traccia 9: analogica


# ----------------------------------------------------------------------------- reverb: shelving
def test_reverb_shelving_matches_original_coefficients(m):
    """y = b0 x + b1 x' - a1 y' con b0 = c + g(1-c), b1 = c - g(1-c), a1 = 2c - 1: shelving bilineare."""
    for v in values()[::2]:
        m.word(REV + 4, v)                 # FREQ
        m.word(REV + 6, v)                 # GAIN
        m.run(0x4009_6E48, 0x4009_6EE2, {UC_M68K_REG_A0: REV})
        b0, b1, a1 = (m.long(a) / 2**31 for a in (0x8000_C5FC, 0x8000_C600, 0x8000_C604))
        c = (a1 + 1) / 2
        g = (b0 - c) / (1 - c)
        assert abs((b1 - (c - g * (1 - c)))) < 1e-6
        fc = 48000 / math.pi * math.atan(c / (1 - c))
        assert close(m.fmt(118, v), fc, rel=0.003), (v, m.fmt(118, v), fc)
        t = m.fmt(119, v)
        assert t == "-inf" if v == 0 else close(t, gain_db(g), rel=0), (v, t, g)
