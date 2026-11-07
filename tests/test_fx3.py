"""Mod fx3 (terza mandata, chorus), eseguita nell'emulatore con la routine delle mandate dell'OS.

- trampolino del ciclo per traccia: bersagli della mandata come l'OS per DEL/REV ((v/32768)^2 per livello,
  media dei lati, a meta' per la somma delle coppie), mute, istruzioni EMAC sostituite rieseguite, registri
  intatti;
- fx3_run (somme del master): bus 3 a 24 kHz = media delle coppie di campioni pesata come le mandate
  dell'OS; chorus come ritardo puro; ritorno sul bus diretto con il segno dell'OS, riportato a 48 kHz per
  interpolazione lineare; a riposo senza mandate, senza ascoltatori o con ingressi muti; costo per blocco
  limitato (prove di regressione sul numero di istruzioni);
- fx3_dsnd (prima del delay): uscita del blocco precedente nel bus del delay; pagina, parametri, testi.
"""

import json
import random
import struct
import sys
from pathlib import Path

import pytest

pytest.importorskip("unicorn")
from unicorn import UC_ARCH_M68K, UC_HOOK_CODE, UC_MODE_BIG_ENDIAN, Uc  # noqa: E402
from unicorn.m68k_const import (UC_CPU_M68K_ANY, UC_M68K_REG_A0, UC_M68K_REG_A1, UC_M68K_REG_A2, UC_M68K_REG_A3,  # noqa: E402
                                UC_M68K_REG_A6, UC_M68K_REG_A7, UC_M68K_REG_D0, UC_M68K_REG_D1,
                                UC_M68K_REG_D2, UC_M68K_REG_D3, UC_M68K_REG_D7, UC_M68K_REG_SR)

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "tools" / "build"), str(ROOT / "tools" / "unpack"), str(ROOT / "tools" / "emu")]
import eft  # noqa: E402
import modarea_layout  # noqa: E402
from emac import UnicornEmac  # noqa: E402

MA = modarea_layout.RAM                                    # area mod (mods/modarea)
MA_PAGE, MA_MAP = 0x444E_1000, 0x9_0000                     # area mod e radice dell'interfaccia (0x444E2334)
assert MA_PAGE <= MA and MA + modarea_layout.SIZE <= MA_PAGE + MA_MAP

SY = ROOT / "firmware" / "Syntakt_OS1.42.syx"
MODS = [ROOT / "mods" / m / "patch.json" for m in ("vparams", "fx3", "idspace")]
pytestmark = pytest.mark.skipif(not (SY.exists() and all(p.exists() for p in MODS)), reason="OS o patch assenti")

LOAD, STACK, RET, UI = 0x4000_0400, 0x5000_8000, 0x5000_F000, 0x5000_0C00
FRAME, TRK = 0x5000_4000, 0x5000_5000
SRC_DIG, SRC_ANA, OUT_A, OUT_B = 0x8000_3D50, 0x8000_3950, 0x8000_DAD0, 0x8000_DFD0
GET, SET, KIT = 0x4000_D94A, 0x4000_DA32, 0x4000_D870
IDS = {"TYPE": 505, "SPD": 506, "DEP": 507, "TIME": 509, "FDBK": 510, "WID": 511, "DSND": 508, "RSND": 512}   # idspace
DELAY, REVERB, DLY_IN = 0x4009_6908, 0x4009_6EB4, 0x8000_DBD0


def s32(v):
    v &= 0xFFFF_FFFF
    return v - (1 << 32) if v & 0x8000_0000 else v


@pytest.fixture()
def m():
    return Machine()


class Machine:
    def __init__(self, spec=None):
        sec3 = eft.unpack(SY, ROOT / "unpacked" / SY.stem, ids=[3])[3].read_bytes()
        self.spec = spec or json.loads(MODS[1].read_text(encoding="utf-8"))
        self.sym = {k: int(v, 16) for k, v in self.spec["symbols"].items()}
        uc = self.uc = Uc(UC_ARCH_M68K, UC_MODE_BIG_ENDIAN, cpu=UC_CPU_M68K_ANY)
        uc.mem_map(0x4000_0000, 0x0040_0000)
        uc.mem_write(LOAD, sec3)
        uc.mem_map(0x41B9_1000, 0x2_0000)
        uc.mem_map(MA_PAGE, MA_MAP)
        uc.mem_map(0x5000_0000, 0x1_0000)
        uc.mem_map(0x8000_0000, 0x1_0000)
        ids = json.loads(MODS[2].read_text(encoding="utf-8"))
        for patches in (json.loads(MODS[0].read_text(encoding="utf-8"))["patches"], self.spec["patches"],
                        ids["patches"]):
            for p in patches:
                uc.mem_write(int(p["ram"], 16) if p.get("append") else int(p["addr"], 16), bytes.fromhex(p["hex"]))
        uc.mem_write(RET, b"\x4e\x75")
        uc.mem_write(0x444E_2334, struct.pack(">I", UI))
        self.emac = UnicornEmac(uc, [int(a, 16) for a in self.spec["emac_sites"]])
        self.call(int(ids["symbols"]["ids_boot"], 16))           # descrittori nella copia di idspace (avvio)

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

    ids = None

    def param(self, name, v):
        self.call(SET, [0x5000_0000, (self.ids or IDS)[name], v << 8, 1])


def wet16(m):
    """Uscita dell'effetto: 32 valori a 16 bit, L/R alternati (scala 16 bit, 24 kHz)."""
    return list(struct.unpack(">32h", m.uc.mem_read(m.sym["fx3_wet"], 64)))


def put_wet(m, vals):
    m.uc.mem_write(m.sym["fx3_wet"], struct.pack(">32h", *vals))


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
    assert tgt[t] == frac((gl >> 1) + (gr >> 1), g) >> 1
    assert abs(tgt[t] / 2 ** 30 - (gl + gr) / 2 ** 32 * (max(v, 0) / 32768) ** 2) < 1e-3
    assert (m.longs(m.sym["fx3_moving"], 1)[0] != 0) == (v > 0)  # bersaglio cambiato: rampa


def test_muted_track_sends_nothing(m):
    assert track(m, 2, 0x6000_0000, 0x6000_0000, 0x7F00)[2] != 0
    assert track(m, 2, 0x6000_0000, 0x6000_0000, 0x7F00, mute=1 << 2)[2] == 0


def test_fx_track_and_beyond_ignored(m):
    assert track(m, 12, 0x6000_0000, 0x6000_0000, 0x7F00) == [0] * 16


def run_block(m):
    """Come l'OS: jsr fx3_del_hook al posto del delay (qui un rts), argomenti intatti; poi il trampolino
    delle somme del master (ritorna con le due pea sostituite in pila)."""
    m.uc.mem_write(DELAY, b"\x4e\x75")
    m.call(m.sym["fx3_del_hook"], [0x1111, 0x2222, 0x3333])
    assert m.uc.reg_read(UC_M68K_REG_A7) == STACK - 16 + 4
    m.uc.reg_write(UC_M68K_REG_A6, FRAME)
    m.call(m.sym["fx3_mix_hook"])
    assert m.uc.reg_read(UC_M68K_REG_A7) == STACK - 8
    assert m.emac.state.acc[0] == 0                             # le somme dell'OS partono da acc0 = 0


def sat(v):
    return max(-2 ** 31, min(2 ** 31 - 1, v))


def ret_ref(wet, gain, a, h):
    """fx3_ret: a -= 2 * wet * guadagno a 48 kHz; dispari = campione del chorus, pari = media col precedente."""
    a, h = list(a), list(h)
    for n in range(16):
        for c in (0, 1):
            x = wet[2 * n + c] * gain
            a[4 * n + c] = sat(a[4 * n + c] - (h[c] + x))
            a[4 * n + 2 + c] = sat(a[4 * n + 2 + c] - 2 * x)
            h[c] = x
    return a, h


def gains(m, g):
    m.put(m.sym["fx3_tgt"], g + [0] * (16 - len(g)))
    m.put(m.sym["fx3_cur"], g + [0] * (16 - len(g)))         # nessuna rampa
    m.put(m.sym["fx3_moving"], [1])                            # come il ciclo per traccia


@pytest.mark.parametrize("on", [range(12), range(8), range(8, 12), [3], [10], [0, 11], [6, 7], [2, 5, 9]])
def test_bus_is_the_os_send_sum(m, on):
    """Tutte, digitali, analogiche (un passaggio con 12/8/4 canali) e una o due tracce (un passaggio ciascuna)."""
    dig = [((k * 7919 + n * 104729) % 65536 - 32768) << 12 for k in range(8) for n in range(32)]
    ana = [((k * 31337 + n * 7) % 65536 - 32768) << 12 for k in range(4) for n in range(32)]
    m.put(SRC_DIG, dig)
    m.put(SRC_ANA, ana)
    m.put(SRC_ANA + 512, [0x7FFF_FFFF] * 8)                   # oltre i canali: non deve entrare
    m.put(m.sym["fx3_bus"], [12345] * 16)
    g = [0x0800_0000 * (k + 1) if k in on else 0 for k in range(12)]
    gains(m, g)
    run_block(m)
    bus = m.longs(m.sym["fx3_bus"], 16)
    pair = lambda x, k, n: x[32 * k + 2 * n] + x[32 * k + 2 * n + 1]
    for n in range(16):
        want = (-sum(g[k] * pair(dig, k, n) for k in range(8)) * 2
                - sum(g[8 + k] * pair(ana, k, n) for k in range(4)) * 2)
        assert abs(bus[n] - want / 2 ** 32) < 64, n


def test_gain_follows_target_smoothly_and_lands_exactly(m):
    m.put(m.sym["fx3_tgt"], [0x4000_0000] + [0] * 15)
    m.put(m.sym["fx3_moving"], [1])
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
    gains(m, [0x4000_0000])                                    # guadagno 1 (meta')
    m.put(SRC_DIG, [0] * 256)
    run_block(m)
    if m.longs(m.sym["fx3_clr"], 1)[0]:                        # nuovo tipo: linea svuotata in CLR_N blocchi,
        while m.longs(m.sym["fx3_clr"], 1)[0]:                 # effetto fermo; poi due blocchi con l'effetto
            run_block(m)
        run_block(m)
    run_block(m)


def impulse(m):
    sig = [0] * 256
    sig[10] = 0x1234 << 16                                      # coppia 5 a 24 kHz
    m.put(SRC_DIG, sig)
    run_block(m)
    bus5 = m.longs(m.sym["fx3_bus"], 16)[5]
    m.put(SRC_DIG, [0] * 256)
    return bus5


def test_chorus_without_depth_is_a_pure_delay(m):
    settle(m, DEP=0, TIME=0, FDBK=0)                  # 1 ms = 24 campioni a 24 kHz
    bus5 = impulse(m)
    m.put(OUT_A, [0] * 64)
    run_block(m)
    wet = wet16(m)
    y = bus5 >> 16
    k = 5 + 24 - 16
    assert wet[2 * k] == y != 0
    assert wet[2 * k + 1] == wet[2 * k]
    assert sum(1 for v in wet if v) == 2
    x = y * 32767                                               # ritorno a 48 kHz, interpolato
    out = m.longs(OUT_A, 64)
    assert out[4 * k:4 * k + 8] == [-x, -x, -2 * x, -2 * x, -x, -x, 0, 0]
    assert sum(1 for v in out if v) == 6


def test_idle_without_sends_and_after_tail(m):
    settle(m, DEP=0, TIME=0, FDBK=0)
    assert m.longs(m.sym["fx3_idle"], 1) == [0]
    gains(m, [0])
    for _ in range(1024 // 16 + 2):
        run_block(m)
    assert m.longs(m.sym["fx3_idle"], 1) == [1]
    m.put(OUT_A, [5] * 64)
    m.put(DLY_IN, [5] * 64)
    run_block(m)
    assert m.longs(OUT_A, 64) == [5] * 64                       # a riposo non tocca le uscite
    assert m.longs(DLY_IN, 64) == [5] * 64


def count(m, fn):
    n = [0]
    m.uc.ctl_flush_tb()                                        # i blocchi gia' tradotti non vedrebbero il gancio
    h = m.uc.hook_add(UC_HOOK_CODE, lambda *a: n.__setitem__(0, n[0] + 1))
    fn()
    m.uc.hook_del(h)
    return n[0]


def loud(m):
    m.put(SRC_DIG, [((n * 7919) % 65536 - 32768) << 14 for n in range(256)])
    m.put(SRC_ANA, [((n * 7907) % 65536 - 32768) << 14 for n in range(256)])


def os_bus_loop(m):
    """Istruzioni del ciclo stock che fx3_del_hook / fx3_rev_hook sostituiscono (0x4008F852, 0x4008F98A)."""
    if not hasattr(m, "bus_loop"):
        sec3 = eft.unpack(SY, ROOT / "unpacked" / SY.stem, ids=[3])[3].read_bytes()
        stock = 0x5000_E100
        m.uc.mem_write(stock, sec3[0x4008_F852 - LOAD:0x4008_F852 - LOAD + 0x30] + b"\x4e\x75")
        m.bus_loop = count(m, lambda: m.call(stock)) - 1
    return m.bus_loop


def block_cost(m):
    """Istruzioni in piu' di un blocco nei due trampolini (le chiamate dei test hanno un rts in piu' ciascuna),
    meno il ciclo dell'OS che fx3_del_hook sostituisce."""
    base = os_bus_loop(m)
    return count(m, lambda: run_block(m)) - 3 - base


def test_cost_per_block(m):
    """Regressione sul carico: istruzioni per blocco (32 campioni, 1500 blocchi al secondo). L'OS usa gia'
    quasi tutta la CPU: ogni istruzione qui toglie tempo all'interfaccia."""
    for _ in range(1024 // 16 + 2):
        run_block(m)
    rest = block_cost(m)
    assert rest < 120, rest                                     # nessuna mandata
    loud(m)
    gains(m, [0x4000_0000])                                    # una traccia, senza retroazione ne' DEL
    run_block(m)                                               # a regime (il primo blocco fa la rampa)
    one = block_cost(m)
    assert one < 1400, one                                     # era ~3100
    for t, most in ((1, 1600), (2, 1800), (3, 1050)):          # FLNG e PHSR con retroazione (-95/-90 %),
        m.param("TYPE", t)                                     # CRSH neutro (un campione su uno)
        m.param("FDBK", 0)
        for _ in range(CLR_N + 1):                             # linea svuotata in CLR_N blocchi
            run_block(m)
        assert block_cost(m) < most, t
    m.param("TYPE", 0)
    gains(m, [0x4000_0000] * 12)
    m.param("FDBK", 64)
    m.param("DSND", 64)
    for _ in range(CLR_N + 1):
        run_block(m)
    worst = block_cost(m)
    assert worst < 2400, worst                                 # era ~3800


CLR_N = 8                                                       # blocchi di svuotamento della linea (fx3.c)


def test_type_change_spreads_the_line_clear(m):
    """Cambio di TYPE: la linea da 4 KB si svuota in CLR_N blocchi con l'effetto muto. Tutta in un blocco erano
    ~1 000 scritture e 256 righe di cache: quel blocco sforava il tempo dell'interrupt."""
    settle(m, TYPE=0, FDBK=120)
    loud(m)
    gains(m, [0x4000_0000] * 12)
    for _ in range(10):
        run_block(m)
    full = block_cost(m)
    m.param("TYPE", 2)
    costs = [block_cost(m) for _ in range(CLR_N)]
    assert max(costs) < full, (costs, full)                     # mai piu' di un blocco con l'effetto
    line = m.uc.mem_read(MA + 0xE000, 4096)
    assert line == bytes(4096)                                  # linea e copia vuote
    assert wet16(m) == [0] * 32            # muto durante lo svuotamento
    run_block(m)
    assert block_cost(m) < 2400                                 # il phaser riparte


def test_sends_on_but_inputs_silent(m):
    """Sequencer fermo con SND3 alzato: dopo la coda resta solo la somma del bus."""
    settle(m, FDBK=0)
    gains(m, [0x4000_0000] * 8)
    loud(m)
    run_block(m)
    m.put(SRC_DIG, [1 << 16] * 256)                             # fondo sotto la soglia
    m.put(SRC_ANA, [0] * 256)
    for _ in range(1024 // 16 + 40):                           # coda (TIME + DEP) e linea da svuotare
        run_block(m)
    assert m.longs(m.sym["fx3_idle"], 1) == [1]
    m.put(OUT_A, [5] * 64)
    idle = block_cost(m)
    assert idle < 600, idle
    assert m.longs(OUT_A, 64) == [5] * 64
    loud(m)                                                     # riparte subito
    run_block(m)
    assert m.longs(m.sym["fx3_idle"], 1) == [0]


@pytest.mark.parametrize("gain", [0, -32767, -9000, 20000])
def test_bus_loop_replacement_is_the_os_loop_then_the_send(m, gain):
    """fx3_addsat al posto dei cicli dell'OS a 0x4008F852 / 0x4008F98A: stesso risultato del ciclo originale
    (copiato dallo stock) seguito da fx3_ret, saturazioni comprese; con guadagno 0 solo il ciclo."""
    sec3 = eft.unpack(SY, ROOT / "unpacked" / SY.stem, ids=[3])[3].read_bytes()
    for loop in (0x4008_F852, 0x4008_F98A):
        assert m.uc.mem_read(loop, 6) == b"\x4e\xb9" + struct.pack(">I", m.sym["fx3_" + ("del" if loop < 0x4008_F900
                                                                                         else "rev") + "_hook"])
        stock = 0x5000_E100                                     # il ciclo stock, rilocabile, con un rts
        m.uc.mem_write(stock, sec3[loop - LOAD:loop - LOAD + 0x30] + b"\x4e\x75")
        rnd = random.Random(loop + gain)
        big = [2 ** 31 - 1, -2 ** 31, 2 ** 30 + 5, -2 ** 30 - 7]
        bus = [rnd.choice(big) if rnd.random() < 0.2 else rnd.randrange(-2 ** 31, 2 ** 31) for _ in range(64)]
        ana = [rnd.choice(big) if rnd.random() < 0.2 else rnd.randrange(-2 ** 30, 2 ** 30) for _ in range(64)]
        wet = [rnd.randrange(-32768, 32768) for _ in range(32)]
        h0 = [rnd.randrange(-2 ** 28, 2 ** 28), rnd.randrange(-2 ** 28, 2 ** 28)]
        st = 0x5000_3800
        put_wet(m, wet)
        m.put(DLY_IN + 0x300, ana)
        m.put(DLY_IN, bus)
        m.put(st, h0)
        m.call(stock)
        if gain:
            m.call(m.sym["fx3_ret"], [m.sym["fx3_wet"], gain, DLY_IN, st])
        want, hw = m.longs(DLY_IN, 64), m.longs(st, 2)
        m.put(DLY_IN, bus)
        m.put(st, h0)
        m.call(m.sym["fx3_addsat"], [DLY_IN, gain, st])
        assert m.longs(DLY_IN, 64) == want
        assert m.longs(st, 2) == hw
        assert m.longs(DLY_IN + 0x300, 64) == ana


def test_bus_loop_replacement_is_cheaper_than_the_os_loop(m):
    sec3 = eft.unpack(SY, ROOT / "unpacked" / SY.stem, ids=[3])[3].read_bytes()
    stock = 0x5000_E100
    m.uc.mem_write(stock, sec3[0x4008_F852 - LOAD:0x4008_F852 - LOAD + 0x30] + b"\x4e\x75")
    os_loop = count(m, lambda: m.call(stock)) - 1
    ours = count(m, lambda: m.call(m.sym["fx3_addsat"], [DLY_IN, 0, 0x5000_3800])) - 1
    send = count(m, lambda: m.call(m.sym["fx3_addsat"], [DLY_IN, -20000, 0x5000_3800])) - 1
    assert os_loop > 350 and ours < 230 and send < 530, (os_loop, ours, send)   # 386, 218, 512


def test_return_added_with_os_sign(m):
    wet = [(n - 16) * 2000 for n in range(32)]                  # scala 16 bit, 24 kHz
    h0 = [123456, -654321]
    st = 0x5000_3800
    for gain in (32767, -20000, 1):
        put_wet(m, wet)
        m.put(st, h0)
        m.put(OUT_A, [1000] * 64)
        m.call(m.sym["fx3_ret"], [m.sym["fx3_wet"], gain, OUT_A, st])
        want, h = ret_ref(wet, gain, [1000] * 64, h0)
        assert m.longs(OUT_A, 64) == want
        assert m.longs(st, 2) == h
    m.put(st, [0, 0])
    m.put(OUT_A, [0x7FFF_0000] * 64)
    m.call(m.sym["fx3_ret"], [m.sym["fx3_wet"], 32767, OUT_A, st])
    assert m.longs(OUT_A, 64)[2] == 0x7FFF_FFFF                   # saturazione come l'OS


def test_return_only_on_the_direct_bus(m):
    settle(m, DEP=0, TIME=0, FDBK=0)
    m.put(OUT_B, [-1000] * 64)
    impulse(m)
    for _ in range(3):
        run_block(m)
    assert m.longs(OUT_B, 64) == [-1000] * 64                  # bus del blocco FX analogico: non toccato


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
    assert m.longs(0x41BA_081C, 9) == [505, 506, 507, 509, 510, 511, 508, 512, 0]
    m.call(m.sym["fx3_amp_stub"])                               # AMP 1: ... DEL REV SND3 VOL; AMP 2: PAN in E
    assert m.longs(0x41BA_0624, 1) == [72] and m.longs(0x41BA_0650, 1) == [72]
    assert m.longs(0x41BA_0674, 1) == [80] and m.longs(0x41BA_06A0, 1) == [80]
    assert m.longs(m.sym["fx3_reverb_pages"], 2) == [21, 25]


def test_parameters_through_vparams(m):
    for name, pid in IDS.items():
        assert m.call(KIT, [0x5000_0000, pid]) == 1
    assert m.call(GET, [0x5000_0000, IDS["RSND"]]) == 0
    m.param("SPD", 90)
    assert m.call(GET, [0x5000_0000, IDS["SPD"]]) == 90 << 8
    m.param("TYPE", 3)                                          # CHOR FLNG PHSR CRSH
    assert m.call(GET, [0x5000_0000, IDS["TYPE"]]) == 3 << 8
    m.param("TYPE", 9)
    assert m.call(GET, [0x5000_0000, IDS["TYPE"]]) == 3 << 8
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
    want = {0x4008_F418: "ae000900ae810900", 0x4008_FB7C: "486efed848798000e0f0",
            0x4019_4FEE: "42b941ba083c", 0x4019_4C14: "42b941ba06a0", 0x4003_588C: "7201",
            0x4003_5890: "203c401c8248", 0x4019_4BAE: "42b941ba0674", 0x4004_2CE0: "4fefffa048d77cfc",
            0x4008_F8A0: "4eb940096908", 0x4004_1E84: "605c"}
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


def objdefs():
    """Definizioni degli oggetti (idspace): id -> (modello, +20, +36, +68)."""
    import idspace_layout as I
    spec = json.loads(MODS[1].read_text(encoding="utf-8"))
    out = {}
    for p in spec["patches"]:
        if p.get("append") and I.OBJDEF <= int(p["ram"], 16) < I.PAGEDEF:
            out[I.FIRST + (int(p["ram"], 16) - I.OBJDEF) // 16] = struct.unpack(">4I", bytes.fromhex(p["hex"]))
    return out


def test_send_graphics():
    spec = json.loads(MODS[1].read_text(encoding="utf-8"))
    fixes = {int(p["addr"], 16): p["hex"] for p in spec["patches"] if not p.get("append")}
    assert fixes[0x4018_B53E] == "41b9e730" and fixes[0x4018_B55A] == "41b9e5d0"   # SND3 (72): icona MOD + barra
    d = objdefs()
    assert d[508][2:] == (0x41B9_EBD0, 0x41B9_E5D0)                                # DEL: come la mandata DEL
    assert d[512][2] == 0x41B9_EBA0                                                # REV: come la mandata REV (79)


def test_type_drawn_as_text(m):
    calls = stub_calls(m, 0x400F_8DDC, 9, m.sym["fx3_type_gfx"], [0, 0, 0x5000_5000, 30, 40])
    c = calls[0]
    text = lambda a: bytes(m.uc.mem_read(a, 8)).split(b"\0")[0].decode()
    assert c[:6] == [0x5000_5000, 0x402A_9510, 38, 45, 1, 0]
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


def test_object_templates_and_no_patch_on_midi_ids():
    """Ogni id della pagina e della mandata dell'ingresso ha un oggetto di idspace con un modello stock; nessuna
    patch tocca piu' gli oggetti o i descrittori degli id MIDI 246-269."""
    d = objdefs()
    assert sorted(d) == list(range(505, 514))
    assert all(v[0] for v in d.values())
    spec = json.loads(MODS[1].read_text(encoding="utf-8"))
    for p in spec["patches"]:
        a = int(p["addr"], 16)
        assert not 0x4022_D83C + 52 * 246 <= a < 0x4022_D83C + 52 * 270, p["what"]
        assert not 0x4018_F3F0 <= a < 0x4018_FC00, p["what"]


def test_send_to_delay_adds_scaled_chorus(m):
    settle(m, DEP=0, TIME=0, FDBK=0, DSND=127)
    impulse(m)
    run_block(m)
    wet = wet16(m)                        # DEL = 127: guadagno 32767
    assert any(wet)
    m.put(DLY_IN, [7] * 64)
    run_block(m)                                                # nel delay al blocco dopo
    assert m.longs(DLY_IN, 64) == ret_ref(wet, -32767, [7] * 64, [0, 0])[0]
    m.param("DSND", 0)
    m.put(DLY_IN, [7] * 64)
    run_block(m)
    assert m.longs(DLY_IN, 64) == [7] * 64


@pytest.mark.parametrize("fb", [0, 90])
def test_send_to_delay_with_and_without_feedback(m, fb):
    settle(m, DEP=40, TIME=20, FDBK=fb, DSND=100)
    impulse(m)
    ds = round(32767 * (100 / 127) ** 2)
    prev, h, seen = wet16(m), [0, 0], False
    for _ in range(12):                                         # TIME 20: ~68 campioni a 24 kHz
        m.put(DLY_IN, [5] * 64)
        run_block(m)
        want, h = ret_ref(prev, -ds, [5] * 64, h)
        assert m.longs(DLY_IN, 64) == want
        prev = wet16(m)
        seen |= any(prev)
    assert seen


@pytest.mark.parametrize("start", [20, -12, 63, -63])
def test_ramp_does_not_stick_near_zero(m, start):
    """(t - c) >> 5 si fermava a pochi punti da zero: FX3 restava attivo (e pesante) fino al riavvio."""
    m.put(m.sym["fx3_tgt"], [0] * 16)
    m.put(m.sym["fx3_cur"], [start] + [0] * 15)
    m.put(m.sym["fx3_moving"], [1])
    run_block(m)
    assert m.longs(m.sym["fx3_cur"], 1) == [0]


def test_back_to_idle_after_heavy_use(m):
    settle(m, FDBK=127, DEP=127, TIME=127)
    sig = [((n * 7919) % 65536 - 32768) << 15 for n in range(256)]
    m.put(SRC_DIG, sig)
    gains(m, [0x4000_0000] * 8)
    for _ in range(50):
        run_block(m)
    m.put(m.sym["fx3_tgt"], [0] * 16)                           # SND3 a zero, tracce ancora in play
    m.put(m.sym["fx3_moving"], [1])
    blocks = 0
    while m.longs(m.sym["fx3_idle"], 1) != [1]:
        run_block(m)
        blocks += 1
        assert blocks < 3000, "FX3 non torna a riposo"           # 2 secondi
    assert m.longs(m.sym["fx3_cur"], 16) == [0] * 16


def test_reverb_hook_passes_through_when_idle(m):
    """Senza nulla da fare (FX3 a riposo) il trampolino va al riverbero senza toccare il suo bus."""
    m.put(m.sym["fx3_idle"], [1])
    m.put(DLY_IN, [5] * 64)
    m.uc.mem_write(REVERB, b"\x4e\x75")
    m.call(m.sym["fx3_rev_hook"], [0x1111, 0x2222, 0x3333])
    assert m.longs(DLY_IN, 64) == [5] * 64
    assert m.uc.reg_read(UC_M68K_REG_A7) == STACK - 16 + 4


@pytest.mark.parametrize("dep, spd, time", [(127, 127, 127), (127, 127, 0), (60, 90, 30)])
def test_chorus_reads_stay_in_the_line(m, dep, spd, time):
    """Senza maschera per campione le prese devono restare nella linea doppia (4 KB a MA + 0xE000)."""
    from unicorn import UC_HOOK_MEM_READ
    settle(m, DEP=dep, SPD=spd, TIME=time, FDBK=100, WID=127)
    loud(m)
    seen = []
    h = m.uc.hook_add(UC_HOOK_MEM_READ, lambda uc, acc, a, size, v, _: seen.append(a),
                      begin=(MA + 0xD000), end=(MA + 0x1_0000))
    m.uc.ctl_flush_tb()                                         # i blocchi gia' tradotti non vedrebbero il gancio
    for _ in range(400):                                        # piu' di un periodo dell'LFO a 10 Hz
        run_block(m)
    m.uc.hook_del(h)
    line = [a for a in seen if a >= (MA + 0xE000)]
    assert line and min(line) >= (MA + 0xE000) and max(line) < (MA + 0xF000)


def test_track_hook_cheap_when_snd3_is_off(m):
    """Il trampolino gira per ogni traccia a ogni blocco, anche senza FX3: con SND3 a zero esce subito."""
    n = count(m, lambda: track(m, 4, 0x6000_0000, 0x6000_0000, 0))
    assert n <= 11, n
    assert track(m, 4, 0x6000_0000, 0x6000_0000, 0x7F00)[4] != 0
    m.put(m.sym["fx3_moving"], [0])
    assert track(m, 4, 0x6000_0000, 0x6000_0000, 0)[4] == 0  # spenta dopo essere stata accesa: azzerata
    assert m.longs(m.sym["fx3_moving"], 1) != [0]


# ---- v0.8: salvataggio nel kit, tipi, nomi e testi per tipo

KIT_PTR, KIT_A, KIT_B = 0x8000_30BC, 0x5000_A000, 0x5000_A100
WOFF = (0, 52, 112, 140)                                        # id interni 0, 0x1A, 0x38, 0x46
DEFV = (0, 60, 64, 64, 0, 64, 0, 0)


def kit_words(m, base):
    return [struct.unpack(">H", m.uc.mem_read(base + o, 2))[0] for o in WOFF]


def put_kit(m, base, vals):
    m.uc.mem_write(base, bytes(142))
    for j, o in enumerate(WOFF):
        w = (vals[2 * j] ^ DEFV[2 * j]) << 8 | (vals[2 * j + 1] ^ DEFV[2 * j + 1])
        m.uc.mem_write(base + o, struct.pack(">H", w))


def text(m, a, n=24):
    return bytes(m.uc.mem_read(a, n)).split(b"\0")[0].decode()


def test_params_saved_in_the_kit_words(m):
    m.put(KIT_PTR, [KIT_A])
    m.uc.mem_write(KIT_A, bytes(142))
    assert m.call(GET, [0x5000_0000, IDS["DEP"]]) == 64 << 8      # parole a zero = default
    m.param("TYPE", 2)                                           # prima il tipo (riporta SPD..WID al via)
    m.param("SPD", 90)
    m.param("TIME", 3)
    m.param("RSND", 127)
    assert kit_words(m, KIT_A) == [2 << 8 | (90 ^ 60), 3 ^ 64, 64 << 8, 127]   # PHSR: FDBK al centro
    raw = bytes(m.uc.mem_read(KIT_A, 142))
    others = [i for i in range(0, 142, 2) if i not in WOFF and raw[i:i + 2] != b"\0\0"]
    assert others == []                                          # il resto del kit non si tocca


def test_pattern_change_follows_the_kit(m):
    put_kit(m, KIT_A, [0, 10, 20, 30, 40, 50, 60, 70])
    put_kit(m, KIT_B, [2, 11, 21, 31, 41, 51, 61, 71])
    m.put(KIT_PTR, [KIT_A])
    run_block(m)
    assert list(m.uc.mem_read(m.sym["fx3_p"], 8)) == [0, 10, 20, 30, 40, 50, 60, 70]
    m.put(KIT_PTR, [KIT_B])                                       # altro pattern
    run_block(m)
    assert list(m.uc.mem_read(m.sym["fx3_p"], 8)) == [2, 11, 21, 31, 41, 51, 61, 71]
    assert m.call(GET, [0x5000_0000, IDS["DEP"]]) == 21 << 8
    m.call(m.sym["fx3_fmt_dep"], [0, 21 << 8, 0x5000_3000])     # l'interfaccia ridisegna
    assert text(m, m.sym["fx3_n3_s"]) == "FREQ" and text(m, m.sym["fx3_page_l"]) == "Phaser"
    m.uc.mem_write(KIT_B + 0, struct.pack(">H", 0xFF00))         # valori fuori scala: limitati
    run_block(m)
    assert m.uc.mem_read(m.sym["fx3_p"], 1)[0] == 3


@pytest.mark.parametrize("t, n1, n3, n3l, page", [(0, "SPD", "TIME", "Chorus Delay", "Chorus"),
                                                  (1, "SPD", "TIME", "Flanger Delay", "Flanger"),
                                                  (2, "SPD", "FREQ", "Phaser Frequency", "Phaser"),
                                                  (3, "SRR", "DRV", "Crusher Drive", "Crusher")])
def test_names_follow_the_type(m, t, n1, n3, n3l, page):
    m.param("TYPE", t)
    assert (text(m, m.sym["fx3_n1_s"]), text(m, m.sym["fx3_n3_s"])) == (n1, n3)
    assert (text(m, m.sym["fx3_n3_l"]), text(m, m.sym["fx3_page_l"])) == (n3l, page)


@pytest.mark.parametrize("t, fn, v, want", [
    (1, "fx3_fmt_fdbk", 64, "0%"), (1, "fx3_fmt_fdbk", 127, "+95%"), (1, "fx3_fmt_fdbk", 0, "-95%"),
    (1, "fx3_fmt_del", 0, "0.10ms"), (1, "fx3_fmt_del", 127, "8.0ms"), (1, "fx3_fmt_spd", 127, "5.00Hz"),
    (2, "fx3_fmt_del", 0, "100Hz"), (2, "fx3_fmt_del", 127, "4.0kHz"), (2, "fx3_fmt_dep", 127, "6.0oct"),
    (2, "fx3_fmt_wid", 127, "100%"), (2, "fx3_fmt_fdbk", 127, "+90%"),
    (3, "fx3_fmt_spd", 0, "24kHz"), (3, "fx3_fmt_spd", 127, "750Hz"), (3, "fx3_fmt_dep", 0, "16bit"),
    (3, "fx3_fmt_dep", 127, "1bit"), (3, "fx3_fmt_del", 127, "24.0dB"), (3, "fx3_fmt_fdbk", 50, "-"),
    (0, "fx3_fmt_type", 2, "PHSR"), (0, "fx3_fmt_type", 3, "CRSH")])
def test_texts_per_type(m, t, fn, v, want):
    m.param("TYPE", t)
    buf = 0x5000_3000
    m.call(m.sym[fn], [0, v << 8, buf])
    assert text(m, buf, 12) == want


def s16(v):
    return max(-32768, min(32767, v))


def ph_coef(tim):
    import math
    t = [math.tan(math.pi * 20 * 2 ** (i / 32) / 24000) for i in range(292)]
    tab = [round(4096 * (x - 1) / (x + 1)) for x in t]
    fidx = round(32 * 256 * math.log2(100 * 40 ** (tim / 127) / 20))
    i, f = fidx >> 8, fidx & 0xFF
    return tab[i] + (((tab[i + 1] - tab[i]) * f) >> 8)


def phaser_ref(bus, st, a, fb, w):
    """4 celle allpass: y = a (x - s_k) / 4096 + s_k-1; sinistra (x + y) / 2, destra sinistra - w y."""
    out = []
    for b in bus:
        u = b >> 16
        if fb:
            u = s16(u + ((s32(st[4] * fb) >> 8) >> 7))
        x = u
        for k in range(1, 5):
            y = (s32((x - st[k]) * a) >> 12) + st[k - 1]
            st[k - 1] = x
            x = y
        st[4] = x
        left = s16((x + st[0]) >> 1)
        out += [left, s16(left - (s32(x * w) >> 14))]
    return out


@pytest.mark.parametrize("fdbk", [64, 127, 10])
def test_phaser_matches_the_model(m, fdbk):
    settle(m, TYPE=2, DEP=0, TIME=70, FDBK=fdbk, WID=90)
    x = (fdbk - 64) * 29491
    fb = max(-29491, min(29491, int(x / 63)))                     # come la divisione in C (verso zero)
    w = 16384 * 90 // 127
    st = [0] * 5
    loud(m)
    for _ in range(6):
        run_block(m)
        bus = m.longs(m.sym["fx3_bus"], 16)
        assert wet16(m) == phaser_ref(bus, st, ph_coef(70), fb, w)


def test_crusher_matches_the_model(m):
    spd, dep, tim = 40, 90, 60
    settle(m, TYPE=3, SPD=spd, DEP=dep, TIME=tim)
    n = 1 + (31 * spd + 63) // 127
    sh = (15 * dep + 63) // 127
    g = round(256 * 10 ** (24 * tim / 127 / 20))
    cnt, hold, seen = 32 % n, 0, set()                          # i due blocchi muti di settle
    loud(m)
    for _ in range(4):
        run_block(m)
        want = []
        for b in m.longs(m.sym["fx3_bus"], 16):
            cnt += 1
            if cnt >= n:
                cnt = 0
                hold = s16(((b >> 16) * g) >> 8) & -(1 << sh)
            want += [hold, hold]
        assert wet16(m) == want
        seen |= set(want)
    assert len(seen) > 4


def test_type_change_drops_the_old_tail(m):
    settle(m, TYPE=0, FDBK=120)
    loud(m)
    for _ in range(10):
        run_block(m)
    m.put(SRC_DIG, [0] * 256)
    m.put(SRC_ANA, [0] * 256)
    m.param("TYPE", 1)
    m.param("FDBK", 64)                                         # flanger senza retroazione
    run_block(m)
    run_block(m)
    assert wet16(m) == [0] * 32          # linea svuotata al cambio


@pytest.mark.parametrize("t", [0, 1])
def test_time_jumps_glide_and_reads_stay_in_the_line(m, t):
    from unicorn import UC_HOOK_MEM_READ
    settle(m, TYPE=t, DEP=127, SPD=127, TIME=0, FDBK=110, WID=127)
    loud(m)
    seen = []
    h = m.uc.hook_add(UC_HOOK_MEM_READ, lambda uc, acc, a, size, v, _: seen.append(a),
                      begin=(MA + 0xD000), end=(MA + 0x1_0000))
    m.uc.ctl_flush_tb()                                         # i blocchi gia' tradotti non vedrebbero il gancio
    for k in range(300):                                        # TIME 0 <-> 127 di colpo, ripetutamente
        if k % 40 == 0:
            m.param("TIME", 127 if (k // 40) % 2 == 0 else 0)
        run_block(m)
    m.uc.hook_del(h)
    blob = next(p for p in m.spec["patches"] if p.get("append"))
    end = int(blob["ram"], 16) + blob["len"]                    # fine del codice e dei dati di fx3
    line = [a for a in seen if a >= end and not (MA + 0xDFFC) <= a < (MA + 0xE000)]  # tranne FDBK
    assert line and min(line) >= (MA + 0xE000) and max(line) < (MA + 0xF000)


LOOK = {0: [(0x41B9_E6B0, 0), (0x41B9_E730, 0), (0x41B9_E7D0, 0), (0x41B9_ECD0, 0x41B9_E5E0), (0x41B9_E740, 0x41B9_E660)],
        1: [(0x41B9_E6B0, 0), (0x41B9_E7E0, 0), (0x41B9_E7D0, 0), (0x41B9_EC70, 0x41B9_E660), (0x41B9_E740, 0x41B9_E660)],
        2: [(0x41B9_E6B0, 0), (0x41B9_E7E0, 0), (0x41B9_E760, 0x41B9_E660), (0x41B9_EC70, 0x41B9_E660),
            (0x41B9_E740, 0x41B9_E660)],
        3: [(0x41B9_E780, 0x41B9_E660), (0x41B9_E830, 0), (0x41B9_ECB0, 0x41B9_E670), (0, 0), (0, 0)]}


def obj(i):
    import idspace_layout as I
    return 0x41BA_0A24 + 84 * i if i < I.FIRST else I.OBJ + 84 * (i - I.FIRST)


@pytest.mark.parametrize("t", [0, 1, 2, 3, 0])
def test_icons_and_slots_follow_the_type(m, t):
    ids = json.loads(MODS[2].read_text(encoding="utf-8"))["symbols"]
    m.call(int(ids["ids_obj32"], 16), [505])                    # oggetti di idspace costruiti (prima ricerca)
    protos = {a for row in LOOK.values() for pair in row for a in pair if a}
    for a in protos:                                            # prototipi "costruiti all'avvio": firme
        m.put(a, [a, a + 1, a + 2, a + 3])
    m.call(m.sym["fx3_page_stub"])
    if t == 0:
        m.param("TYPE", 3)                                      # da un altro tipo
    m.param("TYPE", t)
    for i, pid in enumerate((506, 507, 509, 510, 511)):
        g, st = LOOK[t][i]                                      # {0, 0, fx3_mgr, invoker del prototipo}
        mgr = m.sym["fx3_mgr"]
        assert m.longs(obj(pid) + 36, 4) == ([0, 0, mgr, g + 3] if g else [0] * 4), (pid, hex(g))
        assert m.longs(obj(pid) + 68, 4) == ([0, 0, mgr, st + 3] if st else [0] * 4), pid
    want = [505, 506, 507, 509, 0, 0, 508, 512] if t == 3 else [505, 506, 507, 509, 510, 511, 508, 512]
    assert m.longs(0x41BA_081C, 8) == want                      # il crusher lascia vuote FDBK e WID


def test_audio_interrupt_never_rewrites_the_ui(m):
    """Cambio di pattern a un kit con altro tipo: l'interrupt aggiorna i valori, nomi e icone li cambia
    solo l'interfaccia (al primo disegno o lettura)."""
    m.call(m.sym["fx3_fmt_spd"], [0, 0, 0x5000_3000])          # interfaccia: tipo 0 sistemato
    m.put(obj(506) + 36, [0x1111] * 4)
    put_kit(m, KIT_A, [3, 10, 20, 30, 40, 50, 60, 70])
    m.put(KIT_PTR, [KIT_A])
    gains(m, [0x4000_0000])
    run_block(m)
    assert m.uc.mem_read(m.sym["fx3_p"], 1)[0] == 3
    assert m.longs(obj(506) + 36, 4) == [0x1111] * 4             # non toccata dall'interrupt
    assert text(m, m.sym["fx3_n1_s"]) == "SPD"
    m.call(m.sym["fx3_fmt_spd"], [0, 0, 0x5000_3000])
    assert text(m, m.sym["fx3_n1_s"]) == "SRR"
    assert m.longs(0x41BA_081C + 16, 2) == [0, 0]


# ----------------------------------------------------------------------------- kit nel file (FUNC+YES/NO)
KSER, KDES = 0x400A_6E0E, 0x400A_6DA6          # blocco della FX track: kit -> file, file -> kit
FILE, KBLK, KIT2 = 0x5000_6000, 0x5000_6100, 0x5000_6200
FX3_WORDS = (0, 0x1A, 0x38, 0x46)               # parole del kit usate da fx3
LFO_DEST = (4, 12)                              # destinazioni degli LFO: indice convertito con la tabella


def valid(words):
    """Parole del kit con destinazioni LFO valide (0 = nessuna), come le scrive l'OS."""
    return [0 if i in LFO_DEST else w for i, w in enumerate(words)]


def round_trip(m, words, file_fill=0x00):
    """Blocco del kit (71 parole) -> file -> nuovo kit, con le funzioni dell'OS. -> parole rilette."""
    m.uc.mem_write(KBLK, struct.pack(">71H", *words))
    m.uc.mem_write(FILE, bytes([file_fill]) * 160)
    assert m.call(KSER, [FILE, KBLK]) & 0xFF == 1
    m.uc.mem_write(KIT2, b"\xee" * 142)
    assert m.call(KDES, [KIT2, FILE]) & 0xFF == 1
    return list(struct.unpack(">71H", m.uc.mem_read(KIT2, 142)))


def test_stock_kit_file_loses_fx3_words():
    """Senza gli agganci (OS stock): la tabella delle posizioni perde 0x1A e 0x46 e rilegge nella 0 il
    valore della 0x1A. Era FUNC+NO che portava fx3 dal chorus al crusher (issue #4)."""
    m = Machine()
    for addr, orig in ((KSER, "2f0b2f0a246f000c"), (KDES, "4feffff448d71c00")):
        m.uc.mem_write(addr, bytes.fromhex(orig))
    words = valid([0x1000 + i for i in range(71)])
    back = round_trip(m, words)
    assert back[0] == words[0x1A] and back[0x1A] == 0xEEEE and back[0x46] == 0xEEEE
    assert [i for i in range(71) if back[i] != words[i]] == [0, 0x1A, 0x46]


def test_kit_file_keeps_every_word():
    m = Machine()
    rnd = random.Random(4)
    for _ in range(20):
        words = valid([rnd.randrange(0x10000) for _ in range(71)])
        assert round_trip(m, words, file_fill=rnd.randrange(256)) == words
    raw = m.uc.mem_read(FILE + 148, 8)
    assert struct.unpack(">4H", raw) == (0x5349, words[0], words[0x1A], words[0x46])


def test_kit_file_without_marker_gives_fx3_defaults():
    """File scritto dall'OS stock (o da v0.8.0): niente marcatore -> parole di fx3 a zero (= default),
    non il valore spostato dalla 0x1A."""
    m = Machine()
    words = valid([0x2000 + i for i in range(71)])
    m.uc.mem_write(KBLK, struct.pack(">71H", *words))
    m.call(KSER, [FILE, KBLK])
    m.uc.mem_write(FILE + 148, bytes(8))                    # come l'OS stock: byte azzerati
    m.uc.mem_write(KIT2, b"\xee" * 142)
    m.call(KDES, [KIT2, FILE])
    back = struct.unpack(">71H", m.uc.mem_read(KIT2, 142))
    assert back[0] == back[0x1A] == back[0x46] == 0
    assert all(back[i] == words[i] for i in range(71) if i not in (0, 0x1A, 0x46))


def test_kit_hooks_keep_failure_paths():
    m = Machine()
    assert m.call(KSER, [0, KBLK]) & 0xFF == 0
    m.uc.mem_write(FILE, struct.pack(">I", 7))              # tipo di blocco sbagliato: l'OS rifiuta
    assert m.call(KDES, [KIT2, FILE]) & 0xFF == 0


# ----------------------------------------------------------------------------- SND3 dell'ingresso (v0.9)
IN_ID, IN_HOOK_RET = 513, 0x5000_E000
A2 = 0x5000_9000                                    # array dei parametri levigati (a2 nel mix)


def test_input_snd3_through_vparams_in_kit_word_0x37(m):
    kit = 0x5000_6000
    m.uc.mem_write(0x8000_30BC, struct.pack(">I", kit))
    m.uc.mem_write(kit, bytes(142))
    m.uc.mem_write(kit + 110, b"\xAB\x00")                      # byte alto: non nostro
    assert m.call(KIT, [0x5000_0000, IN_ID]) == 1
    assert m.call(GET, [0x5000_0000, IN_ID]) == 0
    m.call(SET, [0x5000_0000, IN_ID, 90 << 8, 1])
    assert m.call(GET, [0x5000_0000, IN_ID]) == 90 << 8
    assert bytes(m.uc.mem_read(kit + 110, 2)) == b"\xAB\x5A"
    m.call(SET, [0x5000_0000, IN_ID, 0x9000, 1])
    assert m.call(GET, [0x5000_0000, IN_ID]) == 127 << 8         # limitato


def in_hook(m, gl, gr, rev=0x1357):
    """Come a 0x4008F53C: in pila l'argomento della legge di bilanciamento, d1/a0 guadagni L/R."""
    m.uc.mem_write(A2 + 1812, struct.pack(">H", rev))
    sp = STACK - 8
    m.uc.mem_write(sp, struct.pack(">II", RET, 0xBA1A))
    regs = {UC_M68K_REG_D0: 0xD0, UC_M68K_REG_D1: gl, UC_M68K_REG_D2: 0xD2, UC_M68K_REG_A0: gr,
            UC_M68K_REG_A1: 0xA1, UC_M68K_REG_A2: A2, UC_M68K_REG_D3: 0xD3}
    for r, v in regs.items():
        m.uc.reg_write(r, v & 0xFFFFFFFF)
    m.uc.reg_write(UC_M68K_REG_SR, 0x2700)
    m.uc.reg_write(UC_M68K_REG_A7, sp)
    m.uc.emu_start(m.sym["fx3_in_hook"], RET, count=10_000)
    assert m.uc.reg_read(UC_M68K_REG_A7) == STACK              # argomento tolto (addq.l #4,sp)
    assert m.uc.reg_read(UC_M68K_REG_D2) & 0xFFFF == rev       # move.w 1812(a2),d2
    for r, v in regs.items():
        if r != UC_M68K_REG_D2:
            assert m.uc.reg_read(r) & 0xFFFFFFFF == v & 0xFFFFFFFF
    return m.longs(m.sym["fx3_tgt"], 16)


@pytest.mark.parametrize("v", [0, 40, 127])
def test_input_targets_like_the_os_input_sends(m, v):
    kit = 0x5000_6000
    m.uc.mem_write(0x8000_30BC, struct.pack(">I", kit))
    m.uc.mem_write(kit, bytes(142))
    m.call(SET, [0x5000_0000, IN_ID, v << 8, 1])
    m.put(m.sym["fx3_moving"], [0])
    gl, gr = s32(-0x5000_0000), s32(-0x2000_0000)               # come escono da msac (negativi)
    tgt = in_hook(m, gl, gr)
    s = (2 * (v << 8) ** 2) >> 16
    sw = lambda x: struct.unpack(">h", struct.pack(">H", ((x >> 1) >> 16) & 0xFFFF))[0]
    assert tgt[12] == (sw(gl) * s if v else 0) and tgt[13] == (sw(gr) * s if v else 0)
    assert tgt[:12] == [0] * 12
    assert (m.longs(m.sym["fx3_moving"], 1)[0] != 0) == (v > 0)


@pytest.mark.parametrize("on", [[12], [13], [12, 13], [3, 12], [0, 5, 9, 12, 13]])
def test_bus_includes_the_input(m, on):
    dig = [((k * 7919 + n * 104729) % 65536 - 32768) << 12 for k in range(8) for n in range(32)]
    ana = [((k * 31337 + n * 7) % 65536 - 32768) << 12 for k in range(6) for n in range(32)]
    m.put(SRC_DIG, dig)
    m.put(SRC_ANA, ana)
    m.put(m.sym["fx3_bus"], [12345] * 16)
    g = [0x0800_0000 * (k + 1) if k in on else 0 for k in range(14)]
    gains(m, g)
    run_block(m)
    bus = m.longs(m.sym["fx3_bus"], 16)
    pair = lambda x, k, n: x[32 * k + 2 * n] + x[32 * k + 2 * n + 1]
    for n in range(16):
        want = (-sum(g[k] * pair(dig, k, n) for k in range(8)) * 2
                - sum(g[8 + k] * pair(ana, k, n) for k in range(6)) * 2)
        assert abs(bus[n] - want / 2 ** 32) < 64, n


# ----------------------------------------------------------------------------- SND3 della FX track
FX_ID = 144


def fx_kit(m, v, route=0):
    """Kit attivo (kitstore, 0x800030B8) con SND3 della FX track = v; kit del pattern col routing di FX3."""
    import kitstore_layout as KS
    ui_kit, kit = 0x5000_A000, 0x5000_6000
    m.uc.mem_write(0x8000_30B8, struct.pack(">I", ui_kit))
    m.uc.mem_write(0x8000_30BC, struct.pack(">I", kit))
    m.uc.mem_write(ui_kit, bytes(0x1000))
    m.uc.mem_write(kit, bytes(142))
    m.uc.mem_write(kit + 110, struct.pack(">H", route << 8))
    m.uc.mem_write(ui_kit + KS.word(*KS.PARTS["fx3"][0]), struct.pack(">H", v))
    return ui_kit + KS.word(*KS.PARTS["fx3"][0])


def test_fx_track_snd3_through_vparams_in_kitstore(m):
    w = fx_kit(m, 0)
    assert m.call(KIT, [0x5000_0000, FX_ID]) == 1
    assert m.call(GET, [0x5000_0000, FX_ID]) == 0
    m.call(SET, [0x5000_0000, FX_ID, 70 << 8, 1])
    assert m.call(GET, [0x5000_0000, FX_ID]) == 70 << 8
    assert struct.unpack(">H", m.uc.mem_read(w, 2))[0] == 70
    m.call(SET, [0x5000_0000, FX_ID, 0x9000, 1])
    assert m.call(GET, [0x5000_0000, FX_ID]) == 127 << 8


@pytest.mark.parametrize("v, route", [(0, 0), (40, 0), (127, 0), (127, 1), (200, 0)])
def test_fx_track_targets_like_the_os_fx_sends(m, v, route):
    """Canali 14/15 = ADC 6/7, guadagno pieno dell'ingresso (-1) per (v/32768)^2; 0 se il ritorno di FX3 va
    nella FX track (anello: l'OS fa lo stesso con DEL e REV della FX track)."""
    fx_kit(m, v, route)
    m.put(m.sym["fx3_moving"], [0])
    tgt = in_hook(m, s32(-0x5000_0000), s32(-0x2000_0000))
    s = (2 * (min(v, 127) << 8) ** 2) >> 16
    want = 0 if route or not v else -0x4000 * s
    assert tgt[14] == tgt[15] == want
    assert (m.longs(m.sym["fx3_moving"], 1)[0] != 0) == (want != 0)


@pytest.mark.parametrize("on", [[14, 15], [3, 14, 15], [12, 14, 15], [12, 13, 14, 15], [0, 5, 9, 12, 13, 14, 15]])
def test_bus_includes_the_fx_track(m, on):
    dig = [((k * 7919 + n * 104729) % 65536 - 32768) << 12 for k in range(8) for n in range(32)]
    ana = [((k * 31337 + n * 7) % 65536 - 32768) << 12 for k in range(8) for n in range(32)]
    m.put(SRC_DIG, dig)
    m.put(SRC_ANA, ana)
    m.put(m.sym["fx3_bus"], [12345] * 16)
    g = [-0x0800_0000 * (k + 1) if k in on else 0 for k in range(16)]
    gains(m, g)
    run_block(m)
    bus = m.longs(m.sym["fx3_bus"], 16)
    pair = lambda x, k, n: x[32 * k + 2 * n] + x[32 * k + 2 * n + 1]
    for n in range(16):
        want = (-sum(g[k] * pair(dig, k, n) for k in range(8)) * 2
                - sum(g[8 + k] * pair(ana, k, n) for k in range(8)) * 2)
        assert abs(bus[n] - want / 2 ** 32) < 64, n


def test_fx_track_amp_pages():
    """G delle pagine AMP 1 della FX track (AHD 17, ADSR 18) = 144 accanto a DEL/REV; PAN (153) in E della pagina 2."""
    m = Machine()
    m.uc.reg_write(UC_M68K_REG_D0, 0x1234)
    m.call(m.sym["fx3_fxamp_stub"])
    assert [struct.unpack(">I", m.uc.mem_read(a, 4))[0] for a in (0x41BA_06D4, 0x41BA_0700, 0x41BA_0724)] == \
        [FX_ID, FX_ID, 153]
    assert m.uc.reg_read(UC_M68K_REG_D0) == 0x1234


def test_input_snd3_on_the_external_mixer_page(m):
    m.uc.mem_write(0x41BA_07F8, struct.pack(">I", 0))
    m.uc.reg_write(UC_M68K_REG_D0, 0x1234)
    m.call(m.sym["fx3_in_page"])
    assert struct.unpack(">I", m.uc.mem_read(0x41BA_07F8, 4))[0] == IN_ID
    assert m.uc.reg_read(UC_M68K_REG_D0) == 0x1234


def test_type_change_resets_the_effect_knobs(m):
    """Cambiare tipo riporta SPD..WID ai valori di partenza del tipo (il crusher neutro); DEL e REV restano.
    Riscrivere lo stesso tipo non tocca nulla."""
    get = lambda k: m.call(GET, [0x5000_0000, IDS[k]]) >> 8
    for k, v in (("SPD", 100), ("DEP", 20), ("TIME", 120), ("FDBK", 90), ("WID", 3), ("DSND", 50), ("RSND", 70)):
        m.param(k, v)
    m.param("TYPE", 0)                                          # stesso tipo: niente reset
    assert [get(k) for k in ("SPD", "DEP", "TIME", "FDBK", "WID")] == [100, 20, 120, 90, 3]
    m.param("TYPE", 3)                                          # crusher: neutro
    assert [get(k) for k in ("SPD", "DEP", "TIME")] == [0, 0, 0]
    assert get("DSND") == 50 and get("RSND") == 70
    m.param("SPD", 30)
    m.param("TYPE", 1)                                          # flanger: retroazione al centro (nessuna)
    assert [get(k) for k in ("SPD", "DEP", "TIME", "FDBK", "WID")] == [60, 64, 64, 64, 64]
    m.param("TYPE", 0)
    assert [get(k) for k in ("SPD", "DEP", "TIME", "FDBK", "WID")] == [60, 64, 64, 0, 64]


def test_send_to_reverb_into_its_input_bus(m):
    """Prima del riverbero (0x4008F9CA) l'effetto del blocco precedente entra nel suo bus d'ingresso, come
    la mandata al delay; il riverbero parte con gli argomenti al loro posto."""
    settle(m, DEP=40, TIME=20, RSND=100)
    impulse(m)
    rs = round(32767 * (100 / 127) ** 2)
    prev, h, seen = wet16(m), [0, 0], False
    m.uc.mem_write(REVERB, b"\x4e\x75")
    for _ in range(12):                                         # ordine dell'OS: riverbero, poi somme
        m.put(DLY_IN, [5] * 64)
        m.call(m.sym["fx3_rev_hook"], [0x1111, 0x2222, 0x3333])
        assert m.uc.reg_read(UC_M68K_REG_A7) == STACK - 16 + 4
        want, h = ret_ref(prev, -rs, [5] * 64, h)
        assert m.longs(DLY_IN, 64) == want
        run_block(m)
        prev = wet16(m)
        seen |= any(prev)
    assert seen


def test_kit_file_from_v081_resets_the_old_vol_byte():
    """Kit salvati con v0.8.1 (marcatore "SH"): il byte basso della parola 0x46 era VOL; ora e' REV e
    riparte da 0, il resto si rilegge."""
    m = Machine()
    words = valid([0x3000 + i for i in range(71)])
    m.uc.mem_write(KBLK, struct.pack(">71H", *words))
    m.call(KSER, [FILE, KBLK])
    m.uc.mem_write(FILE + 148, struct.pack(">H", 0x5348))
    m.uc.mem_write(KIT2, b"\xee" * 142)
    m.call(KDES, [KIT2, FILE])
    back = struct.unpack(">71H", m.uc.mem_read(KIT2, 142))
    assert back[0] == words[0] and back[0x1A] == words[0x1A] and back[0x46] == words[0x46] & 0xFF00


# ----------------------------------------------------------------------------- ROUTING (FUNC+FX), tasto 13
RT_KIT, RT_VIEW, RT_EVENT = 0x5000_6000, 0x5000_6800, 0x5000_6900
IS_PRESS, REFRESH, RT_DONE = 0x400F_9830, 0x400F_FE22, 0x4004_C80A


def route_kit(m, word):
    m.uc.mem_write(0x8000_30BC, struct.pack(">I", RT_KIT))
    m.uc.mem_write(RT_KIT, bytes(142))
    m.uc.mem_write(RT_KIT + 110, struct.pack(">H", word))


def rt_key(m, code, press=True):
    """Come a 0x4004C5E2: d0 = codice del tasto, d2 = evento, a2 = vista. -> (dove continua l'OS, refresh)."""
    uc = m.uc
    uc.mem_write(IS_PRESS, bytes.fromhex("7001" if press else "7000") + b"\x4e\x75")
    uc.mem_write(REFRESH, b"\x4e\x75")
    refresh = []
    h = uc.hook_add(UC_HOOK_CODE, lambda u, a, s, _: refresh.append(
        struct.unpack(">I", u.mem_read(u.reg_read(UC_M68K_REG_A7) + 4, 4))[0]), begin=REFRESH, end=REFRESH)
    stops = (RT_DONE, 0x4004_C5EC, 0x4004_C5FA)
    for r, v in ((UC_M68K_REG_D0, code), (UC_M68K_REG_D2, RT_EVENT), (UC_M68K_REG_A2, RT_VIEW)):
        uc.reg_write(r, v)
    uc.reg_write(UC_M68K_REG_SR, 0x2700)
    uc.reg_write(UC_M68K_REG_A7, STACK)
    where = []

    def at(u, a, s, _):
        if a in stops:
            where.append(a)
            u.emu_stop()
    h2 = uc.hook_add(UC_HOOK_CODE, at)
    uc.emu_start(0x4004_C5E2, 0, count=10_000)
    uc.hook_del(h)
    uc.hook_del(h2)
    assert uc.reg_read(UC_M68K_REG_A7) == STACK and uc.reg_read(UC_M68K_REG_A2) == RT_VIEW
    return where[0], refresh


def test_routing_key_13_toggles_fx3_and_keeps_the_rest(m):
    route_kit(m, 0x005A)                                         # SND3 dell'ingresso = 90
    assert rt_key(m, 36) == (RT_DONE, [RT_VIEW])
    assert bytes(m.uc.mem_read(RT_KIT + 110, 2)) == b"\x01\x5A"
    assert rt_key(m, 36, press=False) == (RT_DONE, [])           # rilascio: niente
    assert rt_key(m, 36) == (RT_DONE, [RT_VIEW])
    assert bytes(m.uc.mem_read(RT_KIT + 110, 2)) == b"\x00\x5A"
    for code in range(24, 36):                                   # tracce: come l'OS
        assert rt_key(m, code) == (0x4004_C5FA, [])
    for code in (37, 38, 39, 40):                                # delay, riverbero, ingresso, oltre
        assert rt_key(m, code) == (0x4004_C5EC, [])
    assert bytes(m.uc.mem_read(RT_KIT + 110, 2)) == b"\x00\x5A"


@pytest.mark.parametrize("word,want", [(0x0000, 0), (0x0100, 1), (0x017F, 1), (0x00FF, 0)])
def test_routing_entry_13_reads_the_flag(m, word, want):
    route_kit(m, word)
    assert m.call(0x4004_BF86, [RT_VIEW, 12]) == want


def test_routing_other_entries_go_to_the_os(m):
    hit = []

    def at(u, a, s, _):
        sp = u.reg_read(UC_M68K_REG_A7)
        hit.append((sp, struct.unpack(">4I", u.mem_read(sp, 16)), u.mem_read(sp + 16, 12)))
        u.emu_stop()
    h = m.uc.hook_add(UC_HOOK_CODE, at, begin=0x4004_BF8E, end=0x4004_BF8E)
    regs = {UC_M68K_REG_D2: 0xD2, UC_M68K_REG_D3: 0xD3, UC_M68K_REG_A2: 0xA2}
    m.call(0x4004_BF86, [RT_VIEW, 3], regs)
    m.uc.hook_del(h)
    sp, saved, args = hit[0]
    assert sp == STACK - 12 - 16 and saved[0] == 0xD2 and saved[1] == 0xD3 and saved[3] == 0xA2
    assert bytes(args) == struct.pack(">III", RET, RT_VIEW, 3)   # 24(sp) = indice, come l'OS


def test_routing_entry_13_drawn_as_fx3(m):
    """Come le tracce (0x4004C1F4): casella (x-4, base-12, x+8, base) e testo in x+2 sulla riga d7,
    con x = a2, base = d3 dalla riga del ciclo (51, poi 23)."""
    m.uc.mem_write(0x400F_8BD0, bytes.fromhex("4e75"))
    for base in (51, 23):
        regs = {UC_M68K_REG_D2: 0xC0, UC_M68K_REG_A2: 70, UC_M68K_REG_D3: base, UC_M68K_REG_D7: base - 8}
        args = [0xC0, 70, base - 6, 74, 1]                       # quello che spinge l'OS (ignorato)
        box = stub_calls_regs(m, 0x400F_7D9A, 6, m.sym["fx3_rt_draw"], args, regs)
        txt = stub_calls_regs(m, 0x400F_8BD0, 6, m.sym["fx3_rt_draw"], args, regs)
        assert box == [[0xC0, 66, base - 12, 78, base, 1]]
        assert txt[0][:5] == [0xC0, 0x443D_B218, 72, base - 8, 2]
        assert text(m, txt[0][5]).startswith("FX3")


def stub_calls_regs(m, addr, nargs, fn, args, regs):
    m.uc.mem_write(addr, bytes.fromhex("4e75"))
    got = []

    def at(uc, a, size, _):
        sp = uc.reg_read(UC_M68K_REG_A7)
        got.append([s32(v) for v in struct.unpack(f">{nargs}I", uc.mem_read(sp + 4, 4 * nargs))])
    h = m.uc.hook_add(UC_HOOK_CODE, at, begin=addr, end=addr)
    m.call(fn, args, regs)
    m.uc.hook_del(h)
    return got


def test_routing_led_of_key_13_enabled():
    spec = json.loads(MODS[1].read_text(encoding="utf-8"))
    fixes = {int(p["addr"], 16): p["hex"] for p in spec["patches"] if not p.get("append")}
    assert fixes[0x4004_C480] == "6712"                          # beq -> d4 = 1, come le voci 14-16
    assert fixes[0x4004_C242][:4] == "4eb9" and fixes[0x4004_C5E2][:4] == "4ef9"


@pytest.mark.parametrize("routed", [0, 1])
def test_return_goes_to_the_fx_track_when_routed(m, routed):
    route_kit(m, routed << 8)
    settle(m, DEP=0, TIME=0, FDBK=0)
    m.put(OUT_A, [-1000] * 64)
    m.put(OUT_B, [-1000] * 64)
    impulse(m)
    seen = {OUT_A: False, OUT_B: False}
    for _ in range(3):
        m.put(OUT_A, [-1000] * 64)
        m.put(OUT_B, [-1000] * 64)
        run_block(m)
        for bus in seen:
            seen[bus] |= m.longs(bus, 64) != [-1000] * 64
    assert seen == {OUT_A: not routed, OUT_B: bool(routed)}


# ----------------------------------------------------------------------------- come la versione in C (2026-11-05)
C_VERSION = ROOT / "tests" / "data" / "fx3_c.json"       # mods/fx3 a fa839e3: fx3_run in C, uscita a 32 bit


def c_version():
    import base64
    import zlib
    doc = json.loads(C_VERSION.read_text(encoding="utf-8"))
    m = Machine(json.loads(zlib.decompress(base64.b64decode(doc["zlib_b64"]))))
    m.ids = {k: v - 259 for k, v in IDS.items()}                # la versione C usa ancora gli id MIDI (246..253)
    return m


def wet_any(m):
    return wet16(m) if "fx3_s" in m.spec["symbols"] else m.longs(m.sym["fx3_wet"], 32)


def one_block(m, st):
    """Un blocco come nell'OS: mandate per traccia e dell'ingresso, DEL/REV nei cicli dei bus, somme del master.
    -> tutto quello che fx3 scrive (bus dell'OS, uscita, stato visibile, linea)."""
    uc = m.uc
    for name, v in st["ui"]:
        m.param(name, v)
    for a, data in st["mem"]:
        uc.mem_write(a, data)
    m.put(FRAME - 508, [st["mute"]])
    for t, (gl, gr, v) in enumerate(st["trk"]):
        uc.mem_write(TRK + 106, struct.pack(">h", v))
        m.emac.state.acc[0] = m.emac.state.acc[1] = 0
        m.call(m.sym["fx3_trk_hook"], regs={UC_M68K_REG_D0: gl, UC_M68K_REG_D1: gr, UC_M68K_REG_D3: t,
                                            UC_M68K_REG_A3: TRK, UC_M68K_REG_A6: FRAME})
    for gl, gr in st["inp"]:
        in_hook(m, gl, gr)
    out = []
    for hook, bus in (("fx3_del_hook", st["dly"]), ("fx3_rev_hook", st["rev"])):
        m.put(DLY_IN, bus)
        m.put(DLY_IN + 0x300, st["ana"])
        m.call(m.sym[hook], [1, 2, 3])
        out.append(m.longs(DLY_IN, 64))
    m.put(SRC_DIG, st["dig"])
    m.put(SRC_ANA, st["src"])
    m.put(OUT_A, st["outa"])
    m.put(OUT_B, st["outb"])
    m.emac.state.acc[0] = 0
    uc.reg_write(UC_M68K_REG_A6, FRAME)
    m.call(m.sym["fx3_mix_hook"])
    return out + [m.longs(OUT_A, 64), m.longs(OUT_B, 64), wet_any(m), m.longs(m.sym["fx3_bus"], 16),
                  m.longs(m.sym["fx3_cur"], 14), m.longs(m.sym["fx3_tgt"], 14), m.longs(m.sym["fx3_idle"], 1),
                  bytes(uc.mem_read(m.sym["fx3_p"], 8)), bytes(uc.mem_read(MA + 0xE000, 4096))]


def scenario(seed, n, steady):
    """Manopole, cambi di pattern e di kit, dual mono, mandate in moto o ferme, silenzi lunghi (riposo)."""
    import dualmono_layout as DML
    rnd = random.Random(seed)
    kits = (0x5000_6000, 0x5000_6200)
    on = rnd.sample(range(13), rnd.choice((1, 2, 5, 13)))
    trk = [[rnd.randrange(-2 ** 31, 2 ** 31), rnd.randrange(-2 ** 31, 2 ** 31),
            rnd.randrange(1, 0x7F01) if t in on else 0] for t in range(13)]
    inp = (rnd.randrange(-2 ** 31, 2 ** 31), rnd.randrange(-2 ** 31, 2 ** 31))
    silent = 0
    for b in range(n):
        st = {"ui": [], "mem": []}
        if b == 0:
            st["mem"].append((0x8000_30BC, bytes(4)))                         # nessun kit: valori in RAM
        if b == 3:
            st["mem"] += [(kits[0], bytes(142)), (kits[1], bytes(142)), (0x8000_30BC, struct.pack(">I", kits[0])),
                          (0x8000_30B8, struct.pack(">I", 0x5000_6400)), (0x5000_6400, bytes(0x400))]
        r = rnd.random()
        if r < 0.05:
            name = rnd.choice(list(IDS))
            st["ui"].append((name, rnd.randrange(0, 5) if name == "TYPE" else rnd.randrange(0, 128)))
        elif b > 3 and r < 0.06:
            st["mem"].append((0x8000_30BC, struct.pack(">I", rnd.choice(kits))))          # altro pattern
        elif b > 3 and r < 0.07:
            st["mem"].append((rnd.choice(kits) + rnd.choice(WOFF), struct.pack(">H", rnd.randrange(65536))))
        elif b > 3 and r < 0.09:
            st["mem"].append((rnd.choice(kits) + 110, struct.pack(">H", rnd.randrange(0x200))))  # ingresso, routing
        elif r < 0.10:
            side = rnd.choice((0, 0, 1, 2, 3))
            st["mem"].append((DML.HDR, struct.pack(">IB", 0x444D_5632 if side else 0, side)))
        elif b > 3 and r < 0.11:
            st["mem"].append((0x5000_6400 + DML.FX3_R, struct.pack(">H", rnd.randrange(300))))
        for g in trk:
            if steady and rnd.random() > 0.01:
                continue
            if rnd.random() < 0.03:
                g[2] = 0 if rnd.random() < 0.5 else rnd.randrange(-100, 0x7F01)
            elif rnd.random() < 0.05:
                g[2] = max(-50, min(0x7F00, g[2] + rnd.randrange(-2000, 2000)))
        st["trk"] = [tuple(g) for g in trk]
        st["mute"] = rnd.randrange(1 << 13) if rnd.random() < 0.05 else 0
        if not steady and rnd.random() < 0.3:
            inp = (rnd.randrange(-2 ** 31, 2 ** 31), rnd.randrange(-2 ** 31, 2 ** 31))
        st["inp"] = [inp] * rnd.choice((1, 1, 2))
        if silent:
            silent -= 1
            amp = 0 if rnd.random() < 0.7 else 1 << 16                      # sotto la soglia
        else:
            silent = rnd.randrange(50, 200) if rnd.random() < 0.01 else 0
            amp = rnd.choice((1 << 20, 1 << 28, 1 << 30, 1 << 31))
        st["dig"] = [rnd.randrange(-amp, amp) if amp > 1 else 0 for _ in range(256)]
        st["src"] = [rnd.randrange(-amp, amp) if amp > 1 else 0 for _ in range(192)]
        big = lambda: rnd.choice((2 ** 31 - 1, -2 ** 31)) if rnd.random() < 0.1 else rnd.randrange(-2 ** 31, 2 ** 31)
        for k in ("dly", "ana", "rev", "outa", "outb"):
            st[k] = [big() for _ in range(64)]
        yield st


@pytest.mark.parametrize("seed, steady", [(1, False), (2, True), (3, True), (4, False)])
def test_same_output_as_the_c_version(seed, steady):
    """Il percorso di ogni blocco in assembly (2026-11-05) contro la versione in C che sostituisce: stessi ingressi,
    stesse uscite bit per bit, blocco per blocco (bus dell'OS, ritorno, mandate DEL/REV, effetto, linea, stato)."""
    old, new = c_version(), Machine()
    names = ("del", "rev", "out", "fx", "wet", "bus", "cur", "tgt", "idle", "p", "line")
    for b, st in enumerate(scenario(seed, 600, steady)):
        for name, x, y in zip(names, one_block(old, st), one_block(new, st)):
            assert x == y, (seed, b, name)


# ----------------------------------------------------------------------------- LFO della FX track sulla pagina FX3
def test_fx_track_lfo_modulates_the_fx3_page():
    """LFO1 della FX track con DEST sullo slot di SPD (0x24): l'incremento del chorus (valore derivato) segue la
    modulazione; tolta la DEST, torna quello della manopola. Gli slot sono parole del kit FX che l'OS non usa."""
    import isr
    m = isr.Isr(["fx3"])
    fx = lambda iid: 0x8000_2874 + 2 * iid                                        # noqa: E731
    inc = lambda: struct.unpack(">I", bytes(m.uc.mem_read(m.sym["fx3_s"] + 232, 4)))[0]   # noqa: E731 (O_INC)
    m.scene("typ")
    base = inc()
    for iid, v in ((1, 0x7F00), (2, 0x0B00), (3, 0x4000), (5, 0), (6, 0), (7, 0), (8, 0x7F00)):
        m.put16(fx(iid), v)
    m.put16(fx(4), 0x2400)                                       # DEST = slot di SPD
    seen = set()
    for _ in range(12):
        m.fast(8)
        seen.add(inc())
    assert len(seen) > 4, seen
    m.put16(fx(4), 0x7F00)                                       # nessuna DEST
    m.fast(4)
    assert inc() == base
    assert m.uc.mem_read(m.sym["fx3_lfo_on"], 1)[0] == 0
