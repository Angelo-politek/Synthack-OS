"""Mod fx3 (terza mandata, chorus), eseguita nell'emulatore con la routine delle mandate dell'OS.

- trampolino del ciclo per traccia: bersagli della mandata come l'OS per DEL/REV ((v/32768)^2 per livello,
  media dei lati), mute, istruzioni EMAC sostituite rieseguite, registri intatti;
- fx3_block: bus 3 = routine delle mandate dell'OS sui buffer delle tracce; chorus come ritardo puro;
  a riposo senza mandate; costo per blocco limitato (prove di regressione sul numero di istruzioni);
- fx3_out: ritorno sul bus diretto con il segno dell'OS; pagina, parametri, testi.
"""

import json
import struct
import sys
from pathlib import Path

import pytest

pytest.importorskip("unicorn")
from unicorn import UC_ARCH_M68K, UC_HOOK_CODE, UC_MODE_BIG_ENDIAN, Uc  # noqa: E402
from unicorn.m68k_const import (UC_CPU_M68K_ANY, UC_M68K_REG_A0, UC_M68K_REG_A1, UC_M68K_REG_A3,  # noqa: E402
                                UC_M68K_REG_A6, UC_M68K_REG_A7, UC_M68K_REG_D0, UC_M68K_REG_D1,
                                UC_M68K_REG_D2, UC_M68K_REG_D3, UC_M68K_REG_D7, UC_M68K_REG_SR)

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "tools" / "unpack"), str(ROOT / "tools" / "emu")]
import eft  # noqa: E402
from emac import UnicornEmac  # noqa: E402

SY = ROOT / "firmware" / "Syntakt_OS1.41.syx"
MODS = [ROOT / "mods" / m / "patch.json" for m in ("vparams", "fx3")]
pytestmark = pytest.mark.skipif(not (SY.exists() and all(p.exists() for p in MODS)), reason="OS o patch assenti")

LOAD, STACK, RET, UI = 0x4000_0400, 0x5000_8000, 0x5000_F000, 0x5000_0C00
FRAME, TRK = 0x5000_4000, 0x5000_5000
SUM8_EMAC = [0x4008_F05E, 0x4008_F064, 0x4008_F06A, 0x4008_F070, 0x4008_F076, 0x4008_F07C, 0x4008_F082,
             0x4008_F088, 0x4008_F0AA,                                  # 8 canali
             0x4008_F15A, 0x4008_F160, 0x4008_F166, 0x4008_F16C, 0x4008_F17E]   # 4 canali
SRC_DIG, SRC_ANA, OUT_A, OUT_B = 0x8000_3D50, 0x8000_3950, 0x8000_DAD0, 0x8000_DFD0
GET, SET, KIT = 0x4000_D94A, 0x4000_DA32, 0x4000_D870
IDS = {"TYPE": 246, "SPD": 247, "DEP": 248, "TIME": 250, "FDBK": 251, "WID": 252, "DSND": 249, "VOL": 253}
DELAY, DLY_IN = 0x4009_6890, 0x8000_DBD0


def s32(v):
    v &= 0xFFFF_FFFF
    return v - (1 << 32) if v & 0x8000_0000 else v


@pytest.fixture()
def m():
    return Machine()


class Machine:
    def __init__(self):
        sec3 = eft.unpack(SY, ROOT / "unpacked" / SY.stem, ids=[3])[3].read_bytes()
        self.spec = json.loads(MODS[1].read_text(encoding="utf-8"))
        self.sym = {k: int(v, 16) for k, v in self.spec["symbols"].items()}
        uc = self.uc = Uc(UC_ARCH_M68K, UC_MODE_BIG_ENDIAN, cpu=UC_CPU_M68K_ANY)
        uc.mem_map(0x4000_0000, 0x0040_0000)
        uc.mem_write(LOAD, sec3)
        uc.mem_map(0x41B9_0000, 0x2_0000)
        uc.mem_map(0x444E_0000, 0x1_0000)
        uc.mem_map(0x4600_0000, 0x1_0000)
        uc.mem_map(0x5000_0000, 0x1_0000)
        uc.mem_map(0x8000_0000, 0x1_0000)
        for f in MODS:
            for p in json.loads(f.read_text(encoding="utf-8"))["patches"]:
                uc.mem_write(int(p["ram"], 16) if p.get("append") else int(p["addr"], 16), bytes.fromhex(p["hex"]))
        uc.mem_write(RET, b"\x4e\x75")
        uc.mem_write(0x444E_1334, struct.pack(">I", UI))
        self.emac = UnicornEmac(uc, SUM8_EMAC + [int(a, 16) for a in self.spec["emac_sites"]])

    def call(self, fn, args=(), regs=None):
        uc = self.uc
        sp = STACK - 4 * (len(args) + 1)
        uc.mem_write(sp, struct.pack(f">{len(args) + 1}I", RET, *[a & 0xFFFFFFFF for a in args]))
        for r, v in (regs or {}).items():
            uc.reg_write(r, v & 0xFFFFFFFF)
        uc.reg_write(UC_M68K_REG_SR, 0x2700)
        uc.reg_write(UC_M68K_REG_A7, sp)
        uc.emu_start(fn, RET, count=2_000_000)
        assert self.emac.error is None
        return uc.reg_read(UC_M68K_REG_D0) & 0xFFFFFFFF

    def longs(self, a, n):
        return [s32(v) for v in struct.unpack(f">{n}I", self.uc.mem_read(a, 4 * n))]

    def put(self, a, vals):
        self.uc.mem_write(a, struct.pack(f">{len(vals)}I", *[v & 0xFFFFFFFF for v in vals]))

    def param(self, name, v):
        self.call(SET, [0x5000_0000, IDS[name], v << 8, 1])


def frac(a, b):
    return ((a >> 16) * (b >> 16)) << 1


def track(m, t, gl, gr, v, mute=0):
    """Il trampolino come nel ciclo per traccia dell'OS: d0/d1 guadagni, d3 traccia, a3 struttura, fp quadro."""
    m.put(FRAME - 508, [mute])
    m.uc.mem_write(TRK + 106, struct.pack(">h", v))
    m.emac.state.acc[0] = m.emac.state.acc[1] = 0
    regs = {UC_M68K_REG_D0: gl, UC_M68K_REG_D1: gr, UC_M68K_REG_D2: 0x1234, UC_M68K_REG_D3: t,
            UC_M68K_REG_D7: s32(-2 * 0x7F00 * 0x7F00), UC_M68K_REG_A0: 0xA0, UC_M68K_REG_A1: 0xA1,
            UC_M68K_REG_A3: TRK, UC_M68K_REG_A6: FRAME}
    m.call(m.sym["fx3_trk_hook"], regs=regs)
    for r, val in regs.items():
        assert m.uc.reg_read(r) & 0xFFFFFFFF == val & 0xFFFFFFFF            # registri dell'OS intatti
    assert m.uc.reg_read(UC_M68K_REG_A7) == STACK
    assert m.emac.state.acc[0] != 0 and m.emac.state.acc[1] != 0           # msac sostituite rieseguite
    return m.longs(m.sym["fx3_tgt"], 16)


@pytest.mark.parametrize("t, v", [(0, 0x7F00), (3, 0x4000), (9, 0x2000), (11, 0), (5, -3)])
def test_track_targets_like_os_sends(m, t, v):
    gl, gr = 0x6000_0000, 0x2000_0000
    tgt = track(m, t, gl, gr, v)
    g = 2 * v * v if v > 0 else 0
    assert tgt[t] == frac((gl >> 1) + (gr >> 1), g)
    assert abs(tgt[t] / 2 ** 31 - (gl + gr) / 2 ** 32 * (max(v, 0) / 32768) ** 2) < 1e-3


def test_muted_track_sends_nothing(m):
    assert track(m, 2, 0x6000_0000, 0x6000_0000, 0x7F00)[2] != 0
    assert track(m, 2, 0x6000_0000, 0x6000_0000, 0x7F00, mute=1 << 2)[2] == 0


def test_fx_track_and_beyond_ignored(m):
    assert track(m, 12, 0x6000_0000, 0x6000_0000, 0x7F00) == [0] * 16


def run_block(m):
    """Come l'OS: jsr fx3_del_hook al posto del delay (qui un rts), argomenti intatti."""
    m.uc.mem_write(DELAY, b"\x4e\x75")
    m.call(m.sym["fx3_del_hook"], [0x1111, 0x2222, 0x3333])
    assert m.uc.reg_read(UC_M68K_REG_A7) == STACK - 16 + 4


def gains(m, g):
    m.put(m.sym["fx3_tgt"], g + [0] * (16 - len(g)))
    m.put(m.sym["fx3_cur"], g + [0] * (16 - len(g)))         # nessuna rampa


@pytest.mark.parametrize("dig_on, ana_on", [(True, True), (True, False), (False, True)])
def test_bus_is_the_os_send_sum(m, dig_on, ana_on):
    dig = [((k * 7919 + n * 104729) % 65536 - 32768) << 12 for k in range(8) for n in range(32)]
    ana = [((k * 31337 + n * 7) % 65536 - 32768) << 12 for k in range(8) for n in range(32)]
    m.put(SRC_DIG, dig)
    m.put(SRC_ANA, ana)
    g = [0x1000_0000 * (k + 1) // 2 if (k < 8 and dig_on) or (k >= 8 and ana_on) else 0 for k in range(12)]
    gains(m, g)
    run_block(m)
    bus = m.longs(m.sym["fx3_bus"], 32)
    for n in range(32):
        want = -sum(g[k] * dig[32 * k + n] for k in range(8)) * 2 - sum(g[8 + k] * ana[32 * k + n] for k in range(4)) * 2
        assert abs(bus[n] - want / 2 ** 32) < 64, n


def test_gain_follows_target_smoothly_and_lands_exactly(m):
    m.put(m.sym["fx3_tgt"], [0x4000_0000] + [0] * 15)
    seen = []
    for _ in range(80):                                          # ~58 blocchi (40 ms) per arrivare
        run_block(m)
        seen.append(m.longs(m.sym["fx3_cur"], 1)[0])
    assert seen[0] == 0x4000_0000 >> 2                           # 1/4 a blocco
    assert all(a < b for a, b in zip(seen, seen[1:])) or seen[-1] == 0x4000_0000
    assert seen[-1] == 0x4000_0000


def settle(m, **params):
    """Parametri e due blocchi muti con mandata attiva: LFO e posizioni di lettura a regime."""
    for k, v in params.items():
        m.param(k, v)
    gains(m, [0x7FFF_FFFF])
    m.put(SRC_DIG, [0] * 256)
    run_block(m)
    run_block(m)


def impulse(m):
    sig = [0] * 256
    sig[5] = 0x1234 << 16
    m.put(SRC_DIG, sig)
    run_block(m)
    bus5 = m.longs(m.sym["fx3_bus"], 32)[5]
    m.put(SRC_DIG, [0] * 256)
    return bus5


def test_chorus_without_depth_is_a_pure_delay(m):
    settle(m, DEP=0, TIME=0, FDBK=0, VOL=127)                  # 1 ms = 48 campioni
    bus5 = impulse(m)
    run_block(m)
    wet = m.longs(m.sym["fx3_wet"], 64)
    y = bus5 >> 16
    assert wet[2 * (5 + 48 - 32)] == y != 0
    assert wet[2 * (5 + 48 - 32) + 1] == wet[2 * (5 + 48 - 32)]
    assert sum(1 for v in wet if v) == 2


def test_idle_without_sends_and_after_tail(m):
    settle(m, DEP=0, TIME=0, FDBK=0)
    assert m.longs(m.sym["fx3_idle"], 1) == [0]
    gains(m, [0])
    for _ in range(4096 // 32 + 2):
        run_block(m)
    assert m.longs(m.sym["fx3_idle"], 1) == [1]
    m.put(OUT_A, [5] * 64)
    m.call(m.sym["fx3_out"])
    assert m.longs(OUT_A, 64) == [5] * 64                       # a riposo non tocca le uscite


def count(m, fn):
    n = [0]
    m.uc.ctl_flush_tb()                                        # i blocchi gia' tradotti non vedrebbero il gancio
    h = m.uc.hook_add(UC_HOOK_CODE, lambda *a: n.__setitem__(0, n[0] + 1))
    fn()
    m.uc.hook_del(h)
    return n[0]


def test_cost_per_block(m):
    """Regressione sul carico: istruzioni per blocco (32 campioni, 1500 blocchi al secondo)."""
    for _ in range(4096 // 32 + 2):
        run_block(m)
    assert count(m, lambda: run_block(m)) < 250                 # a riposo
    assert count(m, lambda: m.call(m.sym["fx3_out"])) < 20
    gains(m, [0x4000_0000] * 12)
    m.param("DSND", 64)
    active = count(m, lambda: run_block(m)) + count(m, lambda: m.call(m.sym["fx3_out"]))
    assert active < 5000, active                               # 4600 nel caso peggiore (era 13 000)


def test_return_added_with_os_sign(m):
    wet = [(n - 32) * 1000 for n in range(64)]                  # scala 16 bit
    m.put(m.sym["fx3_wet"], wet)
    m.put(m.sym["fx3_idle"], [0])
    m.param("VOL", 127)
    m.put(OUT_A, [1000] * 64)
    m.put(OUT_B, [-1000] * 64)
    m.call(m.sym["fx3_out"])
    assert m.longs(OUT_A, 64) == [1000 - 2 * w * 32767 for w in wet]
    assert m.longs(OUT_B, 64) == [-1000] * 64                  # bus del blocco FX analogico: non toccato
    m.put(OUT_A, [0x7FFF_0000] * 64)
    m.call(m.sym["fx3_out"])
    assert m.longs(OUT_A, 64)[0] == 0x7FFF_FFFF                   # saturazione come l'OS
    m.param("VOL", 0)
    m.put(OUT_A, [1000] * 64)
    m.call(m.sym["fx3_out"])
    assert m.longs(OUT_A, 64) == [1000] * 64


def test_mix_hook_replays_pushes(m):
    uc = m.uc
    uc.mem_write(0x5000_E000, b"\x4e\x71" * 2 + b"\x4e\x75")   # nop ; nop ; rts (dopo il trampolino)
    sp = STACK - 4
    uc.mem_write(sp, struct.pack(">I", 0x5000_E000))
    uc.reg_write(UC_M68K_REG_SR, 0x2700)
    uc.reg_write(UC_M68K_REG_A7, sp)
    uc.reg_write(UC_M68K_REG_A6, FRAME)
    hit = []

    def at(uc_, addr, size, _):
        if addr == 0x5000_E000:
            hit.append(uc_.reg_read(UC_M68K_REG_A7))
            uc_.emu_stop()
    h = uc.hook_add(UC_HOOK_CODE, at)
    uc.emu_start(m.sym["fx3_mix_hook"], 0, count=200_000)
    uc.hook_del(h)
    assert hit == [STACK - 8]
    assert struct.unpack(">II", uc.mem_read(STACK - 8, 8)) == (0x8000_E0F0, FRAME - 296)


def test_page_slots_and_reverb_tab(m):
    m.call(m.sym["fx3_page_stub"])
    assert m.longs(0x41B9_F81C, 9) == [246, 247, 248, 250, 251, 252, 249, 253, 0]
    m.call(m.sym["fx3_amp_stub"])
    assert m.longs(0x41B9_F674, 1) == [72] and m.longs(0x41B9_F6A0, 1) == [72]
    assert m.longs(m.sym["fx3_reverb_pages"], 2) == [21, 25]


def test_parameters_through_vparams(m):
    for name, pid in IDS.items():
        assert m.call(KIT, [0x5000_0000, pid]) == 1
    assert m.call(GET, [0x5000_0000, IDS["VOL"]]) == 100 << 8
    m.param("SPD", 90)
    assert m.call(GET, [0x5000_0000, IDS["SPD"]]) == 90 << 8
    m.param("TYPE", 3)                                          # un solo tipo per ora
    assert m.call(GET, [0x5000_0000, IDS["TYPE"]]) == 0
    m.call(SET, [0x5000_0000, IDS["WID"], 0x9000, 1])
    assert m.call(GET, [0x5000_0000, IDS["WID"]]) == 127 << 8


@pytest.mark.parametrize("fn, v, text", [("fx3_fmt_type", 0, "CHOR"), ("fx3_fmt_spd", 0, "0.05Hz"),
                                         ("fx3_fmt_spd", 127, "10.0"), ("fx3_fmt_del", 0, "1.0ms"),
                                         ("fx3_fmt_del", 127, "30ms"), ("fx3_fmt_dep", 0, "0.00ms"),
                                         ("fx3_fmt_dep", 127, "8.0ms")])
def test_texts(m, fn, v, text):
    buf = 0x5000_3000
    m.call(m.sym[fn], [0, v << 8, buf])
    raw = bytes(m.uc.mem_read(buf, 12))
    assert raw[:raw.index(0)].decode() == text


def test_patched_bytes():
    want = {0x4008_F3A0: "ae000900ae810900", 0x4008_FB04: "486efed848798000e0f0",
            0x4019_4E2A: "42b941b9f83c", 0x4019_4A50: "42b941b9f6a0", 0x4003_588C: "7201",
            0x4003_5890: "203c401c7fa8", 0x4019_49EA: "42b941b9f674", 0x4004_2CE0: "4fefffa048d77cfc",
            0x4008_F828: "4eb940096890", 0x4004_1E84: "605c"}
    sec3 = eft.unpack(SY, ROOT / "unpacked" / SY.stem, ids=[3])[3].read_bytes()
    for a, orig in want.items():
        assert sec3[a - LOAD:a - LOAD + len(orig) // 2].hex() == orig


def stub_calls(m, addr, nargs, fn, args):
    """Esegue fn con un rts al posto della routine dell'OS a addr; ritorna gli argomenti di ogni chiamata."""
    m.uc.mem_write(addr, b"\x4e\x75")
    got = []

    def at(uc, a, size, _):
        sp = uc.reg_read(UC_M68K_REG_A7)
        got.append([s32(v) for v in struct.unpack(f">{nargs}I", uc.mem_read(sp + 4, 4 * nargs))])
    h = m.uc.hook_add(UC_HOOK_CODE, at, begin=addr, end=addr)
    m.call(fn, args)
    m.uc.hook_del(h)
    return got


def image(m, a):
    w, h, stride, data, mask = struct.unpack(">5I", m.uc.mem_read(a + 4, 20))
    rows = struct.unpack(f">{h}I", m.uc.mem_read(data, 4 * h))
    return w, h, stride, rows, mask


def test_sends_use_the_delay_send_graphic():
    spec = json.loads(MODS[1].read_text(encoding="utf-8"))
    fixes = {int(p["addr"], 16): p["hex"] for p in spec["patches"] if not p.get("append")}
    for g36, s68 in ((0x4018_B37A, 0x4018_B396), (0x4018_F356, 0x4018_F372)):   # SND3 (72), DEL (249)
        assert fixes[g36] == "41b9dbd0" and fixes[s68] == "41b9d5d0"             # come la mandata DEL (78)


def test_type_drawn_as_text(m):
    calls = stub_calls(m, 0x400F_8C18, 9, m.sym["fx3_type_gfx"], [0, 0, 0x5000_5000, 30, 40])
    c = calls[0]
    text = lambda a: bytes(m.uc.mem_read(a, 8)).split(b"\0")[0].decode()
    assert c[:6] == [0x5000_5000, 0x402A_91C0, 38, 45, 1, 0]
    assert (text(c[6]), text(c[7]), text(c[8])) == ("XXXX", "%s", "CHOR")


@pytest.mark.parametrize("page, target", [(25, 0x4003_A244), (21, 0x4004_2CE8), (20, 0x4004_2CE8)])
def test_draw_hook_routes_only_our_page(m, page, target):
    obj, vec = 0x5000_6000, 0x5000_6100
    m.put(vec, [21, page])
    m.put(obj + 124, [vec])
    m.put(obj + 144, [1])
    uc = m.uc
    sp = STACK - 12
    uc.mem_write(sp, struct.pack(">3I", RET, obj, 0x5000_5000))
    uc.reg_write(UC_M68K_REG_SR, 0x2700)
    uc.reg_write(UC_M68K_REG_A7, sp)
    hit = []

    def at(uc_, a, size, _):
        if a in (0x4003_A244, 0x4004_2CE8):
            hit.append((a, uc_.reg_read(UC_M68K_REG_A7)))
            uc_.emu_stop()
    h = uc.hook_add(UC_HOOK_CODE, at)
    uc.emu_start(m.sym["fx3_draw_hook"], 0, count=1000)
    uc.hook_del(h)
    assert hit[0][0] == target
    assert hit[0][1] == (sp if target == 0x4003_A244 else sp - 96)


@pytest.mark.parametrize("fn, v, text", [("fx3_fmt_fdbk", 0, "0%"), ("fx3_fmt_fdbk", 127, "90%"),
                                         ("fx3_fmt_wid", 64, "91deg"), ("fx3_fmt_wid", 127, "180deg"),
                                         ("fx3_fmt_vol", 0, "-inf"), ("fx3_fmt_vol", 127, "0.0dB"),
                                         ("fx3_fmt_vol", 100, "-4.2dB")])
def test_more_texts(m, fn, v, text):
    buf = 0x5000_3000
    m.call(m.sym[fn], [0, v << 8, buf])
    raw = bytes(m.uc.mem_read(buf, 12))
    assert raw[:raw.index(0)].decode() == text


def test_object_fields_like_del():
    spec = json.loads(MODS[1].read_text(encoding="utf-8"))
    fixes = {int(p["addr"], 16): p["hex"] for p in spec["patches"] if not p.get("append")}
    for a in (0x4018_F234, 0x4018_F290, 0x4018_F2E2, 0x4018_F476):
        assert fixes[a] == "2f03"                              # prototipo d3, come 250 (DEL)
    for a in (0x4018_F23C, 0x4018_F292, 0x4018_F47E):
        assert fixes[a][2:] == "00"                            # tipo 0
    assert fixes[0x4018_F2EA] == "42b941ba4b84"


def test_send_to_delay_adds_scaled_chorus(m):
    settle(m, DEP=0, TIME=0, FDBK=0, VOL=127, DSND=127)
    impulse(m)
    m.put(DLY_IN, [7] * 64)
    run_block(m)
    wet = m.longs(m.sym["fx3_wet"], 64)                        # DEL = 127: guadagno 32767
    assert any(wet)
    assert m.longs(DLY_IN, 64) == [7 + 2 * w * 32767 for w in wet]
    m.param("DSND", 0)
    m.put(DLY_IN, [7] * 64)
    run_block(m)
    assert m.longs(DLY_IN, 64) == [7] * 64


@pytest.mark.parametrize("start", [20, -12, 63, -63])
def test_ramp_does_not_stick_near_zero(m, start):
    """(t - c) >> 5 si fermava a pochi punti da zero: FX3 restava attivo (e pesante) fino al riavvio."""
    m.put(m.sym["fx3_tgt"], [0] * 16)
    m.put(m.sym["fx3_cur"], [start] + [0] * 15)
    run_block(m)
    assert m.longs(m.sym["fx3_cur"], 1) == [0]


def test_back_to_idle_after_heavy_use(m):
    settle(m, FDBK=127, DEP=127, TIME=127)
    sig = [((n * 7919) % 65536 - 32768) << 15 for n in range(256)]
    m.put(SRC_DIG, sig)
    gains(m, [0x7FFF_FFFF] * 8)
    for _ in range(50):
        run_block(m)
    m.put(m.sym["fx3_tgt"], [0] * 16)                           # SND3 a zero, tracce ancora in play
    blocks = 0
    while m.longs(m.sym["fx3_idle"], 1) != [1]:
        run_block(m)
        blocks += 1
        assert blocks < 3000, "FX3 non torna a riposo"           # 2 secondi
    assert m.longs(m.sym["fx3_cur"], 16) == [0] * 16


@pytest.mark.parametrize("fb", [0, 90])
def test_send_to_delay_in_every_loop_variant(m, fb):
    settle(m, DEP=40, TIME=20, FDBK=fb, VOL=0, DSND=100)       # VOL 0: la mandata al delay basta
    impulse(m)
    seen = False
    for _ in range(8):                                          # TIME 20: ~136 campioni
        m.put(DLY_IN, [5] * 64)
        run_block(m)
        wet = m.longs(m.sym["fx3_wet"], 64)
        ds = round(32767 * (100 / 127) ** 2)
        assert m.longs(DLY_IN, 64) == [5 + 2 * w * ds for w in wet]
        seen |= any(wet)
    assert seen


def test_nothing_runs_when_nobody_listens(m):
    settle(m, VOL=0, DSND=0)
    m.put(DLY_IN, [5] * 64)
    run_block(m)
    assert m.longs(m.sym["fx3_idle"], 1) == [1]
    assert m.longs(DLY_IN, 64) == [5] * 64
    assert count(m, lambda: run_block(m)) < 250
