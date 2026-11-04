"""Mod fastmix: routine dell'interrupt audio dell'OS riscritte, stesso risultato bit per bit.

Somme dei bus (0x4008EF8C 10 canali, 0x4008F024 9, 0x4008F0B6 8): la routine dell'OS e quella della mod
girano con gli stessi dati (guadagni nulli, pochi, tutti, in rampa; acc0 di partenza non nullo;
saturazione) in due emulatori, uno stock e uno con la patch. Devono restare uguali bus scritto (e la memoria
intorno), guadagni riscritti, accumulatori, MACSR (modo), registri salvati e pila. Poi il costo.
"""

import json
import random
import struct
import sys
from pathlib import Path

import pytest

pytest.importorskip("unicorn")
from unicorn import UC_ARCH_M68K, UC_HOOK_CODE, UC_MODE_BIG_ENDIAN, Uc  # noqa: E402
from unicorn.m68k_const import (UC_CPU_M68K_ANY, UC_M68K_REG_A2, UC_M68K_REG_A3, UC_M68K_REG_A4,  # noqa: E402
                                UC_M68K_REG_A5, UC_M68K_REG_A6, UC_M68K_REG_A7, UC_M68K_REG_D2, UC_M68K_REG_D3,
                                UC_M68K_REG_D4, UC_M68K_REG_D5, UC_M68K_REG_D6, UC_M68K_REG_D7, UC_M68K_REG_SR)

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "tools" / "build"), str(ROOT / "tools" / "unpack"), str(ROOT / "tools" / "emu")]
import eft  # noqa: E402
import modarea_layout  # noqa: E402
from emac import UnicornEmac  # noqa: E402

SY = ROOT / "firmware" / "Syntakt_OS1.42.syx"
SPEC = ROOT / "mods" / "fastmix" / "patch.json"
pytestmark = pytest.mark.skipif(not (SY.exists() and SPEC.exists()), reason="OS o patch assenti")

LOAD, STACK, RET = 0x4000_0400, 0x5000_8000, 0x5000_F000
SRC, DST, GAINS, INCS = 0x8000_3D50, 0x8000_DAD0, 0x8000_E188, 0x5000_4000
SUMS = {10: 0x4008_EF8C, 9: 0x4008_F024, 8: 0x4008_F0B6}
# istruzioni EMAC delle tre routine dell'OS (msac con load della catena e movclr finale)
OS_EMAC = ([0x4008_EFA6 + 6 * i for i in range(9)] + [0x4008_EFDC, 0x4008_F006]
           + [0x4008_F044 + 6 * i for i in range(8)] + [0x4008_F074, 0x4008_F09A]
           + [0x4008_F0D6 + 6 * i for i in range(7)] + [0x4008_F100, 0x4008_F122]
           + [0x4009_7A00, 0x4009_7A04, 0x4009_7A0A, 0x4009_7A10, 0x4009_7A14, 0x4009_7A18])
SMOOTH, X, S, OUT, NW = 0x4009_79CA, 0x8000_21B0, 0x8000_E9B0, 0x8000_6348, 938
SAVED = (UC_M68K_REG_D2, UC_M68K_REG_D3, UC_M68K_REG_D4, UC_M68K_REG_D5, UC_M68K_REG_D6, UC_M68K_REG_D7,
         UC_M68K_REG_A2, UC_M68K_REG_A3, UC_M68K_REG_A4, UC_M68K_REG_A5, UC_M68K_REG_A6)


def s32(v):
    v &= 0xFFFF_FFFF
    return v - (1 << 32) if v & 0x8000_0000 else v


class Machine:
    def __init__(self, sec3, patched):
        self.spec = json.loads(SPEC.read_text(encoding="utf-8"))
        uc = self.uc = Uc(UC_ARCH_M68K, UC_MODE_BIG_ENDIAN, cpu=UC_CPU_M68K_ANY)
        uc.mem_map(0x4000_0000, 0x0040_0000)
        uc.mem_write(LOAD, sec3)
        uc.mem_map(0x444E_0000, 0x2_0000)                       # area mod
        uc.mem_map(0x5000_0000, 0x1_0000)
        uc.mem_map(0x8000_0000, 0x1_0000)
        sites = list(OS_EMAC)
        if patched:
            for p in self.spec["patches"]:
                uc.mem_write(int(p["ram"], 16) if p.get("append") else int(p["addr"], 16), bytes.fromhex(p["hex"]))
            # smussamento: non piu' agganciato nella build (make_patch.SMOOTH_HOOK), qui si prova ancora fm_smooth
            fm = int(self.spec["symbols"]["fm_smooth"], 16)
            uc.mem_write(0x4009_79D6, struct.pack(">HIHIH", 0x4EB9, fm, 0x4EF9, 0x4009_7A2A, 0x4E71))
            sites += [int(a, 16) for a in self.spec["emac_sites"]]
        uc.mem_write(RET, b"\x4e\x75")
        self.emac = UnicornEmac(uc, sites)

    def call(self, fn, args, regs):
        uc = self.uc
        sp = STACK - 4 * (len(args) + 1)
        uc.mem_write(sp, struct.pack(f">{len(args) + 1}I", RET, *[a & 0xFFFF_FFFF for a in args]))
        for r, v in regs.items():
            uc.reg_write(r, v)
        uc.reg_write(UC_M68K_REG_SR, 0x2700)
        uc.reg_write(UC_M68K_REG_A7, sp)
        uc.emu_start(fn, RET, count=200_000)
        assert self.emac.error is None
        assert uc.reg_read(UC_M68K_REG_A7) == sp + 4

    def counted(self, fn, args, regs):
        n = [0]
        self.uc.ctl_flush_tb()
        h = self.uc.hook_add(UC_HOOK_CODE, lambda *a: n.__setitem__(0, n[0] + 1))
        self.call(fn, args, regs)
        self.uc.hook_del(h)
        return n[0] - 1                                         # il rts di ritorno


@pytest.fixture(scope="module")
def pair():
    sec3 = eft.unpack(SY, ROOT / "unpacked" / SY.stem, ids=[3])[3].read_bytes()
    return Machine(sec3, False), Machine(sec3, True)


def state(m):
    uc, e = m.uc, m.emac.state
    return {"mem": bytes(uc.mem_read(0x8000_0000, 0x1_0000)), "incs": bytes(uc.mem_read(INCS, 64)),
            "acc": list(e.acc), "mode": e.macsr & 0xF0, "regs": [uc.reg_read(r) for r in SAVED]}


def run_both(pair, n, gains, incs, src, acc0=0, macsr=0xA0, count=False):
    out = []
    regs = {r: 0x1111_0000 + i for i, r in enumerate(SAVED)}
    for m in pair:
        uc = m.uc
        uc.mem_write(0x8000_0000, bytes(0x1_0000))
        uc.mem_write(SRC, struct.pack(f">{len(src)}I", *[v & 0xFFFF_FFFF for v in src]))
        uc.mem_write(DST - 8, b"\x5a" * 0x110)
        uc.mem_write(GAINS, struct.pack(f">{n}I", *[g & 0xFFFF_FFFF for g in gains]))
        uc.mem_write(INCS, struct.pack(f">{n}I", *[i & 0xFFFF_FFFF for i in incs]))
        m.emac.state.acc[:] = [acc0, 0x123, -0x456, 0x789]
        m.emac.state.macsr = macsr
        args = [DST, SRC, GAINS, INCS]
        cost = m.counted(SUMS[n], args, regs) if count else m.call(SUMS[n], args, regs)
        out.append((state(m), cost))
    return out


def signal(rnd, n, loud=False):
    lim = 2 ** 31 if loud else 2 ** 28
    return [rnd.randrange(-lim, lim) for _ in range(32 * (n + 1))]


def pick(rnd, n, k):
    on = set(rnd.sample(range(n), k))
    return [rnd.choice([rnd.randrange(1, 2 ** 31), -rnd.randrange(1, 2 ** 31), 0x7FFF_FFFF, 1])
            if c in on else 0 for c in range(n)]


@pytest.mark.parametrize("n", [10, 9, 8])
@pytest.mark.parametrize("k", list(range(0, 11)))
def test_steady_gains_same_as_os(pair, n, k):
    if k > n:
        pytest.skip()
    rnd = random.Random(n * 100 + k)
    for trial in range(3):
        gains = pick(rnd, n, k)
        src = signal(rnd, n, loud=trial == 2)
        (a, _), (b, _) = run_both(pair, n, gains, [0] * n, src, acc0=[0, 0x1234_5678 << 8, -5][trial])
        assert a == b, (n, k, trial)


@pytest.mark.parametrize("n", [10, 9, 8])
def test_ramping_gains_run_the_os_routine(pair, n):
    rnd = random.Random(n)
    for k in (0, 1, 3, n):
        gains = pick(rnd, n, k)
        incs = [0] * n
        incs[rnd.randrange(n)] = rnd.randrange(-2 ** 20, 2 ** 20)
        (a, _), (b, _) = run_both(pair, n, gains, incs, signal(rnd, n))
        assert a == b, (n, k)


@pytest.mark.parametrize("macsr", [0x20, 0x80, 0xA0, 0xB0])
def test_any_emac_mode(pair, macsr):
    rnd = random.Random(macsr)
    for k in (0, 2, 7, 10):
        (a, _), (b, _) = run_both(pair, 10, pick(rnd, 10, k), [0] * 10, signal(rnd, 10, loud=True), macsr=macsr)
        assert a == b, (macsr, k)


# istruzioni per chiamata, guadagni fermi (stock -> mod): tetti
CEIL = {(10, 0): 80, (10, 2): 300, (10, 5): 410, (10, 10): 515, (9, 9): 480, (8, 8): 440, (8, 1): 250}


def test_cost(pair):
    rnd = random.Random(7)
    got = {}
    for (n, k), ceil in CEIL.items():
        (_, os_cost), (_, cost) = run_both(pair, n, pick(rnd, n, k), [0] * n, signal(rnd, n), count=True)
        got[(n, k)] = (os_cost, cost)
        assert cost <= ceil, (n, k, cost)
        assert cost < os_cost
    print("istruzioni per chiamata (OS, fastmix):", got)
    # in rampa: la routine dell'OS e la scansione
    incs = [1] * 10
    (_, os_cost), (_, cost) = run_both(pair, 10, pick(rnd, 10, 10), incs, signal(rnd, 10), count=True)
    assert cost - os_cost <= 20, (os_cost, cost)


def test_patched_bytes():
    spec = json.loads(SPEC.read_text(encoding="utf-8"))
    sym = {k: int(v, 16) for k, v in spec["symbols"].items()}
    hooks = {int(p["addr"], 16): bytes.fromhex(p["hex"]) for p in spec["patches"] if not p.get("append")}
    want = {a: struct.pack(">HIH", 0x4EF9, sym[f"fm_sum{n}"], 0x4E71) for n, a in SUMS.items()}
    assert hooks == want                                        # smussamento non agganciato (2026-11-04)
    code = [p for p in spec["patches"] if p.get("append")]
    assert len(code) == 1 and int(code[0]["ram"], 16) == modarea_layout.RAM + 0xF000
    assert int(code[0]["addr"], 16) == modarea_layout.IMG + 0xF000
    assert sym["fm_sm_x"] + 58 * 32 <= modarea_layout.RAM + modarea_layout.SIZE      # .bss nell'area


# ---- smussamento dei parametri (0x400979CA)

def words(m, a, n):
    return list(struct.unpack(f">{n}h", m.uc.mem_read(a, 2 * n)))


def smooth_state(m):
    uc, e = m.uc, m.emac.state
    return {"out": bytes(uc.mem_read(OUT - 8, 469 * 4 + 16)), "s": bytes(uc.mem_read(S, NW * 4)),
            "copy": bytes(uc.mem_read(0x8000_6A9C, 0x64C)), "acc": list(e.acc), "regs": [uc.reg_read(r) for r in SAVED]}


class Smooth:
    """Le due macchine con la stessa copia dei parametri, chiamate blocco per blocco."""

    def __init__(self, pair, rnd):
        self.pair, self.rnd = pair, rnd
        x = [rnd.randrange(-0x8000, 0x8000) for _ in range(NW + 806)]
        s = [rnd.randrange(-2 ** 31, 2 ** 31) for _ in range(NW)]
        for m in pair:
            m.uc.mem_write(0x8000_0000, bytes(0x1_0000))
            m.uc.mem_write(X, struct.pack(f">{len(x)}h", *x))
            m.uc.mem_write(S, struct.pack(f">{NW}I", *[v & 0xFFFF_FFFF for v in s]))
            m.emac.state.acc[:] = [0, 0, 0x55, 0x66]
            m.emac.state.macsr = 0x20                           # come all'ingresso dell'interrupt
        self.x = x

    def both(self, fn):
        for m in self.pair:
            fn(m)

    def set_x(self, i, v):
        self.x[i] = v
        self.both(lambda m: m.uc.mem_write(X + 2 * i, struct.pack(">h", v)))

    def block(self, count=False, scribble=True):
        """Un blocco; poi, come l'OS (LFO, tracce), scritture sull'uscita che il blocco dopo deve cancellare."""
        regs = {r: 0x2222_0000 + i for i, r in enumerate(SAVED)}
        regs[UC_M68K_REG_A3] = 0x1234_5678
        got, costs = [], []
        for m in self.pair:
            costs.append(m.counted(SMOOTH, [X], regs) if count else m.call(SMOOTH, [X], regs))
            got.append(smooth_state(m))
        assert got[0] == got[1]
        if scribble:
            spots = [(self.rnd.randrange(469), self.rnd.randrange(2 ** 32)) for _ in range(20)]
            self.both(lambda m: [m.uc.mem_write(OUT + 4 * j, struct.pack(">I", v)) for j, v in spots])
        return costs


def test_smoothing_from_random_state_same_as_os(pair):
    sm = Smooth(pair, random.Random(1))
    for _ in range(10):
        sm.block()


def settled(pair, seed, moving=10):
    """Stato al punto fisso (x << 16 o pochi bit sotto) e qualche parola ancora in moto."""
    sm = Smooth(pair, random.Random(seed))
    s = [((v << 16) - sm.rnd.choice([0, 0, 0, 1, 7, 33])) & 0xFFFF_FFFF for v in sm.x[:NW]]
    for i in sm.rnd.sample(range(NW), moving):
        s[i] = (s[i] + sm.rnd.randrange(-50_000, 50_000)) & 0xFFFF_FFFF
    sm.both(lambda m: m.uc.mem_write(S, struct.pack(f">{NW}I", *s)))
    return sm


def test_settled_blocks_same_as_os(pair):
    sm = settled(pair, 2)
    for k in range(40):
        if k in (12, 25):                                       # parametri cambiati (manopole, p-lock)
            for _ in range(5):
                sm.set_x(sm.rnd.randrange(NW + 806), sm.rnd.randrange(-0x8000, 0x8000))
        sm.block()


def test_writers_of_the_state_same_as_os(pair):
    """Come le funzioni dell'OS che scrivono s: x e s insieme (s = x << 16), anche senza cambiare x."""
    sm = settled(pair, 3)
    for k in range(30):
        if k % 5 == 4:
            i = sm.rnd.randrange(NW)
            v = sm.x[i] if k % 10 == 4 else sm.rnd.randrange(-0x8000, 0x8000)
            sm.set_x(i, v)
            sm.both(lambda m: m.uc.mem_write(S + 4 * i, struct.pack(">I", (v << 16) & 0xFFFF_FFFF)))
        sm.block()


def test_accumulators_and_emac_mode_same_as_os(pair):
    sm = settled(pair, 4)
    for k in range(30):
        if k == 10:
            sm.both(lambda m: m.emac.state.acc.__setitem__(0, 0x1234_5678 << 8))
        if k == 14:
            sm.both(lambda m: m.emac.state.acc.__setitem__(1, -77))
        if k == 18:
            sm.both(lambda m: setattr(m.emac.state, "macsr", 0x30))    # arrotondamento
        if k == 24:
            sm.both(lambda m: setattr(m.emac.state, "macsr", 0x20))
        sm.block()


def test_smoothing_cost(pair):
    sm = settled(pair, 5, moving=0)
    for _ in range(17):
        sm.block()
    os_cost, cost = sm.block(count=True)
    print("smussamento a regime, istruzioni (OS, fastmix):", os_cost, cost)
    assert cost <= 2600 and os_cost > 7000                      # 795 sono il resto della funzione (copia, tracce)
    for i in range(0, NW, 16):                                  # tutto in moto: al massimo come l'OS + 10 %
        sm.set_x(i, sm.x[i] ^ 0x100)
    os_cost, cost = sm.block(count=True)
    print("tutti i blocchi cambiati:", os_cost, cost)
    assert cost <= os_cost * 1.1
    os_cost, cost = sm.block(count=True)                        # poi in moto verso il nuovo valore
    print("in moto:", os_cost, cost)
    assert cost <= os_cost * 1.03
