"""Mod perf-fx: effetti di performance sul sequencer, eseguiti nell'emulatore.

Il tick originale fa avanzare lo step di ogni traccia (step + 1, a capo sulla lunghezza) e poi, alla fine
dell'iterazione, chiama il nostro trampolino (0x4008D152). Qui si simula quell'avanzamento e si esegue il
codice vero della mod. I tasti 13-16 entrano nel nostro trampolino come dal ramo dei tasti 13-16 di
KeyboardView; il modificatore attivo (0x40015AF6) e le impostazioni del progetto (0x40019000) sono
sostituiti da due funzioni minime che leggono un byte di prova. Gli effetti dei tasti sono i valori
M1..M4 di Mod A nel kit attivo (*0x800030B8 + 0x15B6).
"""

import json
import struct
import sys
from pathlib import Path

import pytest

pytest.importorskip("unicorn")
from unicorn import UC_ARCH_M68K, UC_HOOK_CODE, UC_MODE_BIG_ENDIAN, Uc  # noqa: E402
from unicorn.m68k_const import (UC_CPU_M68K_ANY, UC_M68K_REG_A0, UC_M68K_REG_A1, UC_M68K_REG_A2,  # noqa: E402
                                UC_M68K_REG_A3, UC_M68K_REG_A4, UC_M68K_REG_A5, UC_M68K_REG_A6,
                                UC_M68K_REG_A7, UC_M68K_REG_D0, UC_M68K_REG_D1, UC_M68K_REG_D2,
                                UC_M68K_REG_D3, UC_M68K_REG_SR)

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "tools" / "build"), str(ROOT / "tools" / "unpack")]
import eft  # noqa: E402
import modarea_layout  # noqa: E402

MA = modarea_layout.RAM                                    # area mod (mods/modarea)
MA_PAGE, MA_MAP = 0x444E_0000, 0x2_0000
assert MA_PAGE <= MA and MA + modarea_layout.SIZE <= MA_PAGE + MA_MAP

SY = ROOT / "firmware" / "Syntakt_OS1.41.syx"
SPEC_F = ROOT / "mods" / "perf-fx" / "patch.json"
pytestmark = pytest.mark.skipif(not (SY.exists() and SPEC_F.exists()), reason="OS o patch assenti")

LOAD, STACK, RET = 0x4000_0400, 0x5000_8000, 0x5000_F000
PAT, STEPS, EV = 0x5000_1000, 0x5000_0800, 0x5000_2400       # pattern finto, step[13], evento
VIEW, MODE, KIT = 0x5000_2000, 0x5000_2500, 0x5000_4000     # vista finta, modificatore attivo, kit
HANDLED, NATIVE, LOWER = 0x4002_E954, 0x4002_EA9A, 0x4002_EBA6  # uscite del ramo dei tasti 13-16
DISPATCH, PROJ, MOD_MODE, DRAW = 0x4000_839E, 0x4001_9000, 0x4001_5AF6, 0x400F_8C18
KIT_PTR, KIT_MODA = 0x8000_30B8, 0x15B6
FX = {"--": 0, "1/16": 1, "1/8": 2, "3/16": 3, "1/4": 4, "1/2": 5, "1BAR": 6,
      "R1/8": 7, "R1/4": 8, "R1/2": 9, "RBAR": 10, "HALF": 11}
MOD_A, RETRIG = 2, 0


@pytest.fixture()
def m():
    return Machine()


class Machine:
    def __init__(self):
        sec3 = eft.unpack(SY, ROOT / "unpacked" / SY.stem, ids=[3])[3].read_bytes()
        self.spec = json.loads(SPEC_F.read_text(encoding="utf-8"))
        self.sym = {k: int(v, 16) for k, v in self.spec["symbols"].items()}
        uc = self.uc = Uc(UC_ARCH_M68K, UC_MODE_BIG_ENDIAN, cpu=UC_CPU_M68K_ANY)
        uc.mem_map(0x4000_0000, 0x0040_0000)
        uc.mem_write(LOAD, sec3)
        uc.mem_map(0x41B9_0000, 0x2_0000)
        uc.mem_map(MA_PAGE, MA_MAP)
        uc.mem_map(0x5000_0000, 0x4_0000)
        uc.mem_map(0x8000_0000, 0x1_0000)
        for p in self.spec["patches"]:
            uc.mem_write(int(p["ram"], 16) if p.get("append") else int(p["addr"], 16), bytes.fromhex(p["hex"]))
        uc.mem_write(RET, b"\x4e\x75")
        uc.mem_write(PAT + 136057, b"\x00")                      # lunghezza unica del pattern
        self.length(16)
        # 0x40019000 -> move.l #VIEW,d0 ; rts ; 0x40015AF6 -> moveq #0,d0 ; move.b MODE,d0 ; rts
        uc.mem_write(PROJ, struct.pack(">HIH", 0x203C, VIEW, 0x4E75))
        uc.mem_write(MOD_MODE, struct.pack(">HHIH", 0x7000, 0x1039, MODE, 0x4E75))
        uc.mem_write(DRAW, b"\x4e\x75")
        self.mode(MOD_A)
        uc.mem_write(KIT_PTR, struct.pack(">I", KIT))
        self.keys("1/16", "1/8", "R1/4", "HALF")

    def mode(self, v):
        self.uc.mem_write(MODE, bytes([v]))

    def keys(self, *names):
        """M1..M4 di Mod A nel kit attivo."""
        self.uc.mem_write(KIT + KIT_MODA, struct.pack(">4h", *[FX[n] if isinstance(n, str) else n for n in names]))

    def length(self, n):
        self.uc.mem_write(PAT + 136052, struct.pack(">h", n))

    def call(self, fn, args):
        uc = self.uc
        sp = STACK - 4 * (len(args) + 1)
        uc.mem_write(sp, struct.pack(f">{len(args) + 1}I", RET, *[a & 0xFFFFFFFF for a in args]))
        uc.reg_write(UC_M68K_REG_SR, 0x2700)
        uc.reg_write(UC_M68K_REG_A7, sp)
        uc.emu_start(fn, RET, count=100_000)
        return uc.reg_read(UC_M68K_REG_D0) & 0xFFFFFFFF

    def event(self, code, flags):
        self.uc.mem_write(EV + 12, struct.pack(">II", code, flags))

    def key(self, n, down):
        """Tasto di trig n (1..16) nel ramo dei tasti 13-16 di KeyboardView, come a 0x4002EA92.
        Ritorna (dove esce, d0, sp): HANDLED, NATIVE (tasti 13-16) o LOWER (tasti 1-12)."""
        uc = self.uc
        code = 23 + n
        self.event(code, 1 if down else 0)
        regs = {UC_M68K_REG_D0: code, UC_M68K_REG_D2: EV, UC_M68K_REG_A2: VIEW, UC_M68K_REG_D3: 0x33,
                UC_M68K_REG_A3: 0xA3, UC_M68K_REG_A5: 0xA5, UC_M68K_REG_A0: 0xA0, UC_M68K_REG_A1: 0xA1}
        for r, v in regs.items():
            uc.reg_write(r, v)
        uc.reg_write(UC_M68K_REG_SR, 0x2700)
        uc.reg_write(UC_M68K_REG_A7, STACK)
        hit = []

        def at(uc_, addr, size, _):
            if addr in (HANDLED, NATIVE, LOWER):
                hit.append(addr)
                uc_.emu_stop()
        h = uc.hook_add(UC_HOOK_CODE, at)
        uc.emu_start(self.sym["pf_kbd_hook"], 0, count=100_000)
        uc.hook_del(h)
        assert hit
        for r in (UC_M68K_REG_D2, UC_M68K_REG_A2, UC_M68K_REG_D3, UC_M68K_REG_A3, UC_M68K_REG_A5,
                  UC_M68K_REG_A0, UC_M68K_REG_A1):
            assert uc.reg_read(r) == regs[r]                    # registri dell'OS intatti
        return hit[0], uc.reg_read(UC_M68K_REG_D0), uc.reg_read(UC_M68K_REG_A7)

    def dispatch(self, n, down):
        self.event(23 + n, 1 if down else 0)
        uc = self.uc
        sp = STACK - 12
        uc.mem_write(sp, struct.pack(">3I", RET, 0x5000_0000, EV))
        uc.reg_write(UC_M68K_REG_SR, 0x2700)
        uc.reg_write(UC_M68K_REG_A7, sp)
        hit = []

        def at(uc_, addr, size, _):
            if addr == DISPATCH:
                hit.append(uc_.reg_read(UC_M68K_REG_A7))
                uc_.emu_stop()
        h = uc.hook_add(UC_HOOK_CODE, at)
        uc.emu_start(self.sym["pf_ev_hook"], 0, count=100_000)
        uc.hook_del(h)
        assert hit == [sp]                                      # al dispatcher con lo stack d'ingresso

    def held(self):
        return self.uc.mem_read(self.sym["pf_held"], 1)[0]

    def hook(self, t):
        """Fine dell'iterazione della traccia t nel tick, come a 0x4008D152 (d2 gia' incrementato)."""
        uc = self.uc
        regs = {UC_M68K_REG_D2: t + 1, UC_M68K_REG_A2: PAT, UC_M68K_REG_A3: PAT + 1177 * t,
                UC_M68K_REG_A4: STEPS + t, UC_M68K_REG_D3: 100, UC_M68K_REG_A6: 200, UC_M68K_REG_A5: 300,
                UC_M68K_REG_D0: 0xD0, UC_M68K_REG_D1: 0xD1, UC_M68K_REG_A0: 0xA0, UC_M68K_REG_A1: 0xA1}
        for r, v in regs.items():
            uc.reg_write(r, v)
        uc.mem_write(STACK - 4, struct.pack(">I", RET))
        uc.reg_write(UC_M68K_REG_SR, 0x2700)
        uc.reg_write(UC_M68K_REG_A7, STACK - 4)
        uc.emu_start(self.sym["pf_step_hook"], RET, count=100_000)
        for r, v in ((UC_M68K_REG_D3, 101), (UC_M68K_REG_A6, 201), (UC_M68K_REG_A5, 301),
                     (UC_M68K_REG_D0, 0xD0), (UC_M68K_REG_D1, 0xD1), (UC_M68K_REG_A0, 0xA0),
                     (UC_M68K_REG_A1, 0xA1), (UC_M68K_REG_D2, t + 1), (UC_M68K_REG_A4, STEPS + t)):
            assert uc.reg_read(r) & 0xFFFFFFFF == v                 # istruzioni sostituite e registri
        assert uc.reg_read(UC_M68K_REG_A7) == STACK

    def step(self, t):
        return self.uc.mem_read(STEPS + t, 1)[0]

    def advance(self, t, n):
        """Come il tick originale: step + 1, a capo sulla lunghezza, poi il nostro aggancio."""
        cur = (self.step(t) + 1) % n
        self.uc.mem_write(STEPS + t, bytes([cur]))
        self.hook(t)
        return self.step(t)


def play(m, t, n, events, steps=16):
    """Sequenza degli step suonati; events = {indice: azione(m) prima dell'avanzamento}."""
    m.uc.mem_write(STEPS + t, bytes([0]))
    m.hook(t)
    out = [m.step(t)]
    for i in range(1, steps):
        if i in events:
            events[i](m)
            m.hook(t)                                  # un tick senza avanzamento
        out.append(m.advance(t, n))
    return out


def hold(n):
    return lambda m: m.key(n, True)


def release(n):
    return lambda m: m.key(n, False)


def test_repeat_loops_the_slice_and_resumes_in_time(m):
    m.keys("1/8", "1/16", "--", "--")
    seq = play(m, 0, 16, {6: hold(13), 10: release(13)})  # premuto dopo lo step 5, rilasciato dopo 4 step
    assert seq == [0, 1, 2, 3, 4, 5, 4, 5, 4, 5, 10, 11, 12, 13, 14, 15]


@pytest.mark.parametrize("name, L", [("1/16", 1), ("3/16", 3), ("1/4", 4), ("1/2", 8), ("1BAR", 16)])
def test_every_repeat_length(m, name, L):
    m.keys("--", name, "--", "--")
    seq = play(m, 1, 16, {6: hold(14)})
    anchor = 5 - 5 % L
    assert seq[6:] == [anchor + (5 - anchor + 1 + i) % L for i in range(10)]


@pytest.mark.parametrize("name, L", [("R1/8", 2), ("R1/4", 4), ("R1/2", 8), ("RBAR", 16)])
def test_reverse_plays_the_slice_backwards(m, name, L):
    m.keys("--", "--", name, "--")
    seq = play(m, 2, 16, {6: hold(15)})
    anchor = 5 - 5 % L
    assert seq[6:] == [anchor + L - 1 - (5 - anchor + 1 + i) % L for i in range(10)]


def test_half_speed_plays_each_step_twice(m):
    m.keys("--", "--", "--", "HALF")
    seq = play(m, 3, 16, {6: hold(16)}, steps=20)
    # dopo lo step 5: 5 (ancora), poi 6 6 7 7 0 0 1 1 ... nel segmento 0..7
    assert seq[6:] == [5, 6, 6, 7, 7, 0, 0, 1, 1, 2, 2, 3, 3, 4]


def test_release_resumes_where_the_pattern_would_be(m):
    m.keys("R1/4", "--", "--", "--")
    seq = play(m, 4, 16, {6: hold(13), 11: release(13)})
    assert seq[11:] == [11, 12, 13, 14, 15]


def test_short_track_wraps_on_its_length(m):
    m.length(6)
    m.keys("1/2", "HALF", "R1/2", "--")
    for k in (13, 14, 15):
        m.key(k, False)
        seq = play(m, 5, 6, {4: hold(k)})              # segmenti di 8 su una traccia di 6: dentro 0..5
        assert all(s < 6 for s in seq)
        m.key(k, False)


def test_nothing_without_press(m):
    assert play(m, 6, 16, {}) == list(range(16))


def test_second_key_switches_effect_from_real_position(m):
    m.keys("1/8", "1/16", "--", "--")
    seq = play(m, 7, 16, {6: hold(13), 9: hold(14), 12: release(14)})
    # 1/8: 4 5 4 | 1/16: lo step reale appena suonato e' 8 -> 8 8 8 | rilascio: 1/8 dal reale 11
    assert seq == [0, 1, 2, 3, 4, 5, 4, 5, 4, 8, 8, 8, 10, 11, 10, 11]


def test_key_set_to_off_does_nothing(m):
    m.keys("--", "--", "--", "--")
    assert play(m, 8, 16, {6: hold(13)}) == list(range(16))


def test_out_of_range_kit_values_use_the_defaults(m):
    m.keys(127, -1, 12, 64)                            # kit da v0.8 o stock: valori di Mod A qualunque
    seq = play(m, 9, 16, {6: hold(13)})                # tasto 13 -> 1/16
    assert seq[6:] == [5] * 10


def test_no_kit_uses_the_defaults(m):
    m.uc.mem_write(KIT_PTR, bytes(4))
    seq = play(m, 10, 16, {6: hold(14)})               # tasto 14 -> 1/8
    assert seq[6:10] == [4, 5, 4, 5]


def test_release_after_mode_change_still_stops(m):
    m.keys("1/8", "--", "--", "--")

    def leave(m):
        m.mode(RETRIG)                                 # FUNC+13: il ramo resta all'OS...
        m.dispatch(13, False)                          # ...ma il rilascio passa dal dispatcher
    seq = play(m, 11, 16, {6: hold(13), 10: leave})
    assert seq == [0, 1, 2, 3, 4, 5, 4, 5, 4, 5, 10, 11, 12, 13, 14, 15]


def test_keys_13_to_16_are_ours_in_mod_a(m):
    for i, n in enumerate((13, 14, 15, 16)):
        where, _, sp = m.key(n, True)
        assert where == HANDLED and sp == STACK and m.held() == (1 << (i + 1)) - 1
    for i, n in enumerate((13, 14, 15, 16)):
        assert m.key(n, False)[0] == HANDLED
    assert m.held() == 0


@pytest.mark.parametrize("mode", [0, 1, 3])
@pytest.mark.parametrize("n", [13, 14, 15, 16])
def test_native_modifiers_in_other_modes(m, mode, n):
    m.mode(mode)
    where, d0, sp = m.key(n, True)
    assert (where, d0, sp) == (NATIVE, 23 + n, STACK)  # stesso stato del codice originale
    assert m.held() == 0


def test_lower_keys_untouched(m):
    where, d0, sp = m.key(5, True)
    assert (where, d0, sp) == (LOWER, 28, STACK)
    assert m.held() == 0


def test_dispatcher_hook_passes_through(m):
    m.key(14, True)
    m.dispatch(3, False)                               # rilascio di un altro tasto: nessun effetto
    assert m.held() == 2
    m.dispatch(14, True)                               # pressione: nessun effetto
    assert m.held() == 2
    m.dispatch(14, False)
    assert m.held() == 0


def test_slot_graphic_draws_the_effect(m):
    got = []

    def at(uc, addr, size, _):
        sp = uc.reg_read(UC_M68K_REG_A7)
        args = struct.unpack(">9I", uc.mem_read(sp + 4, 36))
        cstr = lambda a: bytes(uc.mem_read(a, 8)).split(b"\0")[0].decode()
        got.append((args[0], args[1], args[2], args[3], args[4], args[5],
                    cstr(args[6]), cstr(args[7]), cstr(args[8])))
    h = m.uc.hook_add(UC_HOOK_CODE, at, begin=DRAW, end=DRAW)
    m.call(m.sym["pf_gfx"], [0, 0x800, 0x5000_5000, 30, 40])
    m.uc.hook_del(h)
    assert got == [(0x5000_5000, 0x402A_91C0, 38, 45, 1, 0, "XXXX", "%s", "R1/4")]


def test_texts(m):
    buf = 0x5000_3000
    out = []
    for pos in range(12):
        m.call(m.sym["pf_invoke"], [0, pos << 8, buf])
        raw = bytes(m.uc.mem_read(buf, 8))
        out.append(raw[:raw.index(0)].decode())
    assert out == list(FX)


def test_mod_a_page_and_objects_at_boot(m):
    page = 0x41B9_F9DC
    m.uc.mem_write(page, struct.pack(">7I", 9, 47, 48, 49, 50, 51, 46))
    for pid in range(48, 52):
        m.uc.mem_write(0x41B9_FA24 + 84 * pid, struct.pack(">I", 1))
    m.call(m.sym["pf_page_stub"], [])
    assert struct.unpack(">7I", m.uc.mem_read(page, 28)) == (0, 0, 48, 49, 50, 51, 46)  # +40 (TRIG) resta
    for pid in range(48, 52):
        assert struct.unpack(">I", m.uc.mem_read(0x41B9_FA24 + 84 * pid, 4))[0] == 0


def test_descriptors_of_m1_to_m4(m):
    for n, pid in enumerate(range(48, 52)):
        d = 0x4022_D59C + 52 * pid
        mn, mx, df = struct.unpack(">3i", m.uc.mem_read(d + 8, 12))
        assert (mn, mx, df) == (0, 11 << 8, (1, 2, 8, 11)[n] << 8)
        name = struct.unpack(">I", m.uc.mem_read(d + 40, 4))[0]
        assert bytes(m.uc.mem_read(name, 10)).split(b"\0")[0] == f"Perf FX {n + 1}".encode()


def test_patched_bytes(m):
    want = {0x4008_D152: "5283528e528d", 0x4002_EA92: "7223b2806c00010e", 0x4000_B420: "4eb94000839e",
            0x4019_5294: "42b941b9f9dc", 0x4019_5202: "4024f87b", 0x4019_5236: "40251b59",
            0x4004_0B68: "4024e83b"}
    sec3 = eft.unpack(SY, ROOT / "unpacked" / SY.stem, ids=[3])[3].read_bytes()
    for a, orig in want.items():
        assert sec3[a - LOAD:a - LOAD + len(orig) // 2].hex() == orig
