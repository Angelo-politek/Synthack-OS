"""lfo3 (mods/lfo3): il terzo LFO di Synfact sulla 1.42.

- Nucleo (synfact/render.s, copia in SRAM): stesso risultato bit per bit dell'LFO1 nativo (0x4011942A) sulle stesse
  parole, per forme d'onda, modi, moltiplicatori, fade, fase di partenza, trig e casuale (stesso generatore).
- Nell'interrupt: senza destinazioni LFO3 non costa nulla (sfcore rigioca lo stock); con una destinazione modula la
  parola di lavoro della traccia prima di LFO1/LFO2.
- SRAM: nucleo e banco nelle code del registro, il resto della SRAM come prima.
"""

import json
import random
import struct
import sys
from pathlib import Path

import pytest

pytest.importorskip("unicorn")

ROOT = Path(__file__).resolve().parents[1]
SY = ROOT / "firmware" / "Syntakt_OS1.42.syx"
pytestmark = pytest.mark.skipif(not SY.exists(), reason="OS stock assente")
sys.path[:0] = [str(ROOT / "tools" / "emu"), str(ROOT / "tools" / "build"), str(ROOT / "tools" / "unpack")]

SPEC = json.loads((ROOT / "mods" / "lfo3" / "patch.json").read_text(encoding="utf-8"))
SYM = {k: int(v, 16) for k, v in SPEC["symbols"].items()}
SF = {k: int(v, 16) for k, v in json.loads((ROOT / "mods" / "sfcore" / "patch.json").read_text(
    encoding="utf-8"))["symbols"].items()}
CODE, BANK = 0x8000_7340, 0x8000_F870
NATIVE_LFO = 0x4011_942A
NATIVE_STATE = 0x444D_B72C                      # 13 tracce x 80 B: LFO1 (40 B), poi LFO2
NATIVE_RNG = 0x402D_736C
WORKING = 0x5000_0000                           # proiezione di lavoro finta: 0x1C B d'intestazione + 13 x 142 B
TRACK = lambda t: WORKING + 0x1C + 0x8E * t     # noqa: E731
DEFAULT = (0x7000, 0x300, 0x4000, 0x7F00, 0, 0, 0, 0x4000)
TEMPO = 0x3840 * 4                              # come dall'OS a 120 BPM (0x402D7360)


class Bench:
    """Un emulatore con l'EMAC (tools/emu/isr.py): chiamate dirette al nucleo nativo e a quello di LFO3."""

    def __init__(self, mods):
        import isr
        self.m = isr.Isr(mods)
        self.ui, self.uc = self.m.ui, self.m.uc
        self.uc.mem_map(WORKING, 0x1_0000)
        self.m.emac.state.macsr = 0x20                          # frazionario con segno, come nell'interrupt

    def call(self, fn, args):
        import isr
        self.m.st, self.m.stack, self.m.pending = isr.Stats(), [], None
        self.uc.ctl_flush_tb()
        try:
            self.ui.call(fn, args)
            return self.m.st.n
        finally:
            self.m.st = None

    def words(self, a, n):
        return list(struct.unpack(f">{n}h", self.uc.mem_read(a, 2 * n)))

    def put16(self, a, *v):
        self.uc.mem_write(a, struct.pack(f">{len(v)}H", *[x & 0xFFFF for x in v]))


@pytest.fixture(scope="module")
def benches():
    native, lfo3 = Bench([]), Bench(["lfo3"])
    assert lfo3.ui.long(SF["sfcore_status"] + 4 * 3) == 1      # legato da sfcore (posto 3)
    assert lfo3.ui.long(SYM["lfo3_in_sram"]) == 1
    return native, lfo3


def working(rnd, t, lfo1):
    """Parole di lavoro: casuali (0..0x7F00), LFO1 della traccia t = lfo1, LFO2 di tutte senza effetto."""
    w = bytearray(0x1C + 0x8E * 13)
    for i in range(0x1C // 2, len(w) // 2):
        struct.pack_into(">H", w, 2 * i, rnd.randrange(0, 0x7F01))
    for k in range(13):
        base = 0x1C + 0x8E * k
        for j, v in enumerate(DEFAULT):
            struct.pack_into(">H", w, base + 2 * (1 + j), v)            # LFO1: id interni 1..8
            struct.pack_into(">H", w, base + 2 * (9 + j), v)            # LFO2: 9..16
    for j, v in enumerate(lfo1):
        struct.pack_into(">H", w, 0x1C + 0x8E * t + 2 * (1 + j), v)
    return bytes(w)


CASES = [
    # SPD, MULT, FADE, DEST (slot<<8), WAVE, SPH, MODE, DEP
    (0x7000, 0x300, 0x4000, 0x2200, 0, 0, 0, 0x7000),           # TRI, libero
    (0x5000, 0x500, 0x4000, 0x1200, 1, 0x2000, 1, 0x1000),      # SINE, TRG, fase di partenza
    (0x7FFE, 0x1000, 0x4000, 0x3000, 2, 0x4000, 2, 0x7FFE),     # SQR, HLD, moltiplicatore fisso
    (0x2000, 0x0B00, 0x6000, 0x1500, 3, 0, 3, 0x6000),          # SAW, ONE, fade out
    (0x6000, 0x0300, 0x2000, 0x0500, 4, 0x7F00, 4, 0x2000),     # EXP, HLF, fade in
    (0x7000, 0x1700, 0x4000, 0x4600, 5, 0x1000, 0, 0x5000),     # RMP, MULT massimo, ultimo slot
    (0x4800, 0x0200, 0x4000, 0x1A00, 6, 0x3000, 1, 0x7000),     # RND (stesso generatore), TRG
    (0x0000, 0x0000, 0x0000, 0x1100, 0, 0, 0, 0x0000),          # velocita' negativa, profondita' negativa
]


@pytest.mark.parametrize("case", range(len(CASES)))
def test_kernel_matches_native_lfo1(benches, case):
    """Stesse parole d'ingresso, stato iniziale e generatore: stato, uscita e parola modulata identici a ogni blocco.
    I trig arrivano come dall'interrupt (un bit per traccia)."""
    native, lfo3 = benches
    rnd = random.Random(case)
    p = CASES[case]
    t = case % 13
    native.uc.mem_write(NATIVE_STATE, bytes(13 * 80))
    for k in range(13):
        native.uc.mem_write(NATIVE_STATE + 80 * k + 16, struct.pack(">I", 0x3FFF_FFFF))
        native.uc.mem_write(NATIVE_STATE + 80 * k + 56, struct.pack(">I", 0x3FFF_FFFF))
    rng = (0x1234_5678, 0x9ABC_DEF0)
    native.uc.mem_write(NATIVE_RNG, struct.pack(">2I", *rng))
    state = bytearray(13 * 40)
    for k in range(13):
        struct.pack_into(">I", state, 40 * k + 16, 0x3FFF_FFFF)
    lfo3.uc.mem_write(BANK, bytes(state) + struct.pack(">2I", *rng))
    params = bytearray()
    for k in range(13):
        params += struct.pack(">8H", *(p if k == t else DEFAULT))
    lfo3.uc.mem_write(BANK + 13 * 40 + 8, bytes(params))
    for block in range(48):
        w = working(rnd, t, p)
        trigs = (1 << t) if block % 7 == 3 else 0
        native.uc.mem_write(WORKING, w)
        lfo3.uc.mem_write(WORKING, w)
        native.call(NATIVE_LFO, [WORKING, TEMPO, trigs])
        lfo3.call(CODE, [WORKING, TEMPO, trigs, BANK + 13 * 40 + 8, BANK, BANK + 13 * 40])
        a = bytes(native.uc.mem_read(NATIVE_STATE + 80 * t, 40))
        b = bytes(lfo3.uc.mem_read(BANK + 40 * t, 40))
        assert a == b, (block, a.hex(), b.hex())
        slot = p[3] >> 8
        assert native.words(TRACK(t) + 2 * slot, 1) == lfo3.words(TRACK(t) + 2 * slot, 1), block
        if p[4] == 6:
            assert native.uc.mem_read(NATIVE_RNG, 8) == lfo3.uc.mem_read(BANK + 13 * 40, 8)


def test_sram_layout_and_build():
    """Nucleo e banco nelle code del registro (SRAM): il nucleo intero sta prima delle destinazioni di
    modulation-skip, il banco prima del suo stato."""
    import registry as R
    n = SYM["lfo3_render_end"] - SYM["lfo3_render"]
    tail = [(a, b) for a, b, who, _ in R.SRAM if who == "lfo3"]
    assert any(a <= CODE and CODE + n <= b for a, b in tail), n
    assert any(a <= BANK and BANK + 13 * 40 + 8 + 2 * 13 * 16 <= b for a, b in tail)


# ------------------------------------------------------------------ interrupt audio
def run(mods, uses=(), setup=None, blocks=4):
    import isr
    m = isr.Isr(mods, uses=uses)
    if setup:
        setup(m)
    m.scene("max")
    st = m.run()
    m.fast(blocks)
    return m, st


def test_unused_costs_nothing():
    """Senza destinazioni l'interesse per l'operazione LFO resta spento: stesse istruzioni di sfcore da solo con
    l'adattatore dell'LFO (un tst.b), e solo quello: gli altri adattatori nativi non ci sono."""
    _, a = run(["sfcore", "xparams", "idspace"], uses=["sfcore:lfo"])
    m, b = run(["lfo3"])
    assert m.ui.long(SYM["lfo3_active"]) == 0
    print("istruzioni:", a.n, b.n)
    assert b.n == a.n
    _, s = run(["xparams", "idspace"])                           # lfo3 le richiede: confronto senza il loro costo
    assert b.n - s.n <= 4, (s.n, b.n)


def test_destination_modulates_before_native_lfos():
    """DEST della traccia 3 sul volume (slot 0x30), profondita' piena: la parola di lavoro e' quella del
    blocco piu' la modulazione di LFO3 (stato +28), poi le LFO native. Costo misurato."""
    def setup(m):                                   # parametri: indici 0x3e..0x45 della traccia (xparams)
        m.uc.mem_write(0x8000_21B0 + 28 + 142 * 3 + 2 * 0x3E,
                       struct.pack(">8H", 0x7000, 0x300, 0x4000, 0x3000, 1, 0, 0, 0x7F00))
        m.ui.call(SYM["lfo3_update"])
    _, a = run(["sfcore", "xparams", "idspace"], uses=["sfcore:lfo"])
    m, b = run(["lfo3"], setup=setup)
    assert m.ui.long(SYM["lfo3_active"]) == 1 << 3
    delta = struct.unpack(">i", m.uc.mem_read(BANK + 40 * 3 + 28, 4))[0]
    assert delta != 0
    print("istruzioni con un LFO3 attivo:", b.n - a.n)
    assert b.n - a.n < 2600


# ------------------------------------------------------------------ pagina (idspace) e DEST
def test_page_three_of_the_lfo_tab():
    """Scheda LFO: pagine {4, 5, 38}; la 38 mostra SPD..DEP di LFO3 (id 530..537, indici 0x3e..0x45 del suono)."""
    import screens
    import idspace_layout as I
    screens.TABS.setdefault("LFO", 280)
    ui = screens.UI(["lfo3"])
    t = ui.tab("LFO")
    assert [ui.long(x) for x in range(ui.long(t + 124), ui.long(t + 128), 4)] == [4, 5, 38]
    ui.page(t, 2)
    ids = [ui.param(t, e) for e in "ABCDEFGH"]
    assert ids == list(range(530, 538))
    names = [bytes(ui.uc.mem_read(ui.long(I.TABLE + 52 * i + 48), 5)).split(b"\0")[0] for i in ids]
    assert names == [b"SPD", b"MULT", b"FADE", b"DEST", b"WAVE", b"SPH", b"MODE", b"DEP"]
    assert [struct.unpack(">I", ui.uc.mem_read(I.TABLE + 52 * i + 4, 4))[0] for i in ids] == list(range(0x3E, 0x46))
    assert sum(bin(b).count("1") for b in ui.draw(t)) > 500
    before = ui.raw(t, "A")
    ui.turn(t, "A", +5)
    assert ui.raw(t, "A") != before


def test_dest_helpers_and_fx_track_page():
    import screens
    import idspace_layout as I
    from unicorn.m68k_const import UC_M68K_REG_D0, UC_M68K_REG_D1
    ui = screens.UI(["lfo3"])
    stub = 0x4FE0_5000                                          # jsr lfo3_dest_d0 ; seq d1 ; rts
    ui.uc.mem_write(stub, bytes.fromhex("4eb9") + struct.pack(">I", SYM["lfo3_dest_d0"]) + bytes.fromhex("57c14e75"))
    for pid, z in ((89, 1), (99, 1), (533, 1), (90, 0), (532, 0)):
        ui.uc.reg_write(UC_M68K_REG_D0, pid)
        ui.uc.reg_write(UC_M68K_REG_D1, 0)
        ui.call(stub)
        assert (ui.uc.reg_read(UC_M68K_REG_D1) & 0xFF == 0xFF) == bool(z), pid
    slots = lambda: struct.unpack(">8I", ui.uc.mem_read(I.page(38) + 8, 32))     # noqa: E731
    ui.call(SYM["lfo3_page_slots"])
    assert slots() == tuple(range(530, 538))                    # traccia attiva 0


def test_paste_page_between_the_lfo_pages():
    """Incolla pagina (0x4001F55E): l'OS accetta LFO1 <-> LFO2 spostando gli id di 10; con LFO3 (pagina 38) rifiutava
    (sulla macchina: paste page non funziona col terzo LFO). Ora LFO1/LFO2 <-> LFO3, stessa manopola; un'altra pagina
    resta rifiutata."""
    import screens
    screens.TABS.setdefault("LFO", 280)
    ui = screens.UI(["lfo3"])
    t = ui.tab("LFO")
    model = ui.long(t + 104)
    COPY, PASTE = 0x4001_F466, 0x4001_F55E

    def vals(page):
        ui.page(t, page)
        return [ui.raw(t, e) >> 8 for e in "ABCDEFGH"]
    ui.page(t, 0)
    ui.set(t, "A", 40)
    ui.set(t, "H", 90)
    one = vals(0)
    assert ui.call(COPY, [model, 4], count=400_000_000) & 0xFF == 1
    assert ui.call(PASTE, [model, 38, 1], count=400_000_000) & 0xFF == 1 and vals(2) == one      # LFO1 -> LFO3
    assert ui.call(PASTE, [model, 5, 1], count=400_000_000) & 0xFF == 1 and vals(1) == one       # LFO1 -> LFO2, come l'OS
    ui.page(t, 2)
    ui.set(t, "A", 33)
    ui.set(t, "F", 64)
    three = vals(2)
    assert ui.call(COPY, [model, 38], count=400_000_000) & 0xFF == 1
    for page, index in ((0, 4), (1, 5)):                                                         # LFO3 -> LFO1, LFO2
        assert ui.call(PASTE, [model, index, 1], count=400_000_000) & 0xFF == 1 and vals(page) == three
    ui.page(t, 2)
    ui.set(t, "A", 1)
    assert ui.call(PASTE, [model, 38, 1], count=400_000_000) & 0xFF == 1 and vals(2) == three    # LFO3 -> LFO3
    f = ui.tab("FLTR")
    assert ui.call(COPY, [ui.long(f + 104), ui.long(ui.long(f + 124))], count=400_000_000) & 0xFF == 1
    assert ui.call(PASTE, [model, 38, 1], count=400_000_000) & 0xFF == 0 and vals(2) == three    # FLTR su LFO3: no
