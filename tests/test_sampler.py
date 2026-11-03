"""SAMPLER (mods/sampler): le machine a campioni della Digitakt riscritte, al posto di SP TWINSHOT.

- Riferimento: le funzioni della Digitakt 1.54 (firmware/Digitakt_OS1.54.syx, solo in locale) eseguite
  nell'emulatore accanto alle nostre (il blob della CPU #2 della build), con gli stessi ingressi:
  posizioni di ONESHOT, REPITCH, SLICE, WERP; ricerca dello zero-crossing; griglia dei 256 punti;
  interpolazione (con la tabella della Digitakt al posto della nostra: aritmetica identica).
- La nostra tabella: stessa risposta in frequenza della Digitakt entro 0.2 dB fino a 0.5 fs.
- CPU #2 (build vera, avvio a freddo della sezione 7 compressa): il campione suona, TUNE, REV, STRT/LEN,
  loop, SLICE; le altre machine non cambiano; costo per blocco.
- CPU #1: descrittori, testi dei valori, tempo nella RAM condivisa.
"""

import json
import math
import random
import struct
import sys
from pathlib import Path

import pytest

pytest.importorskip("unicorn")

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "tests"), str(ROOT / "tools" / "emu"), str(ROOT / "tools" / "build"),
                str(ROOT / "tools" / "unpack"), str(ROOT / "mods" / "sampler" / "engine")]
import build  # noqa: E402
import eft  # noqa: E402

STOCK = ROOT / "firmware" / "Syntakt_OS1.42.syx"
DT = ROOT / "firmware" / "Digitakt_OS1.54.syx"
pytestmark = pytest.mark.skipif(not STOCK.exists(), reason="firmware stock assente")
need_dt = pytest.mark.skipif(not DT.exists(), reason="Digitakt 1.54 assente (riferimento solo locale)")
SPEC = json.loads((ROOT / "mods" / "sampler" / "patch.json").read_text(encoding="utf-8"))
SYM = {k: int(v, 16) for k, v in SPEC["symbols"].items()}
LOAD = 0x4000_0400
BLOB7 = next(p for p in SPEC["patches"] if p["section"] == 7 and p.get("append"))
STACK, RET = 0x4FF0_8000, 0x4FF0_F000

# Digitakt 1.54, sezione 3
DT_ONESHOT, DT_REPITCH, DT_SLICE, DT_WERP = 0x4007_4C9C, 0x4007_4D72, 0x4007_4DF2, 0x4007_4EBE
DT_ZERO_CROSS, DT_REGISTER = 0x4007_62EE, 0x4007_63B4
DT_GRIDS = 0x402F_A380                   # 256 posizioni per slot
DT_VOICE_SLOT = 0x8000_EE20              # slot della voce, 94 B per voce
DT_TABLE_IMG, DT_TABLE_RAM = 0x4025_A350, 0x8000_C000
DT_INTERP, DT_INTERP_END = 0x4007_5EA2, 0x4007_5F00


class Cpu:
    """Unicorn con la sezione 3 della Digitakt e il nostro blob della CPU #2, chiamate a funzione C."""

    def __init__(self, dt3: bytes):
        from unicorn import UC_ARCH_M68K, UC_MODE_BIG_ENDIAN, Uc
        from unicorn.m68k_const import UC_CPU_M68K_ANY
        import emac
        uc = Uc(UC_ARCH_M68K, UC_MODE_BIG_ENDIAN)
        uc.ctl_set_cpu_model(UC_CPU_M68K_ANY)
        uc.mem_map(0x4000_0000, 0x0800_0000)
        uc.mem_map(0x4FF0_0000, 0x0001_0000)
        uc.mem_map(0x8000_0000, 0x0001_0000)
        uc.mem_write(LOAD, dt3)
        uc.mem_write(int(BLOB7["ram"], 16), bytes.fromhex(BLOB7["hex"]))
        sites = json.loads((ROOT / "tools" / "emu" / "emac_sites_dt154.json").read_text())
        self.emac = emac.UnicornEmac(uc, sites["sites"])
        self.uc = uc

    def call(self, fn: int, *args: int, sr: int = 0x2700) -> tuple[int, int]:
        from unicorn.m68k_const import UC_M68K_REG_A7, UC_M68K_REG_D0, UC_M68K_REG_D1, UC_M68K_REG_SR
        uc = self.uc
        sp = STACK - 4 * (len(args) + 1)
        uc.mem_write(sp, struct.pack(f">{len(args) + 1}I", RET, *[a & 0xFFFF_FFFF for a in args]))
        self.emac.state.load_macsr(0xA0)          # come nel render della Digitakt: frazionario, saturato
        for n in range(4):
            self.emac.state.clear_acc(n)
        uc.reg_write(UC_M68K_REG_SR, sr)          # prima di A7: SR sceglie la pila
        uc.reg_write(UC_M68K_REG_A7, sp)
        uc.emu_start(fn, RET, count=50_000_000)
        s = lambda v: v - (1 << 32) if v & 0x8000_0000 else v       # noqa: E731
        return s(uc.reg_read(UC_M68K_REG_D0)), s(uc.reg_read(UC_M68K_REG_D1))

    def w32(self, a: int, *v: int) -> None:
        self.uc.mem_write(a, struct.pack(f">{len(v)}i", *v))

    def r32(self, a: int, n: int = 1) -> list[int]:
        return list(struct.unpack(f">{n}i", self.uc.mem_read(a, 4 * n)))


@pytest.fixture(scope="module")
def dt3():
    if not DT.exists():
        pytest.skip("Digitakt 1.54 assente")
    return eft.unpack(DT, ROOT / "unpacked" / DT.stem, ids=[3])[3].read_bytes()


@pytest.fixture(scope="module")
def cpu(dt3):
    return Cpu(dt3)


PAR, PAR_OURS = 0x4600_0000, 0x4600_0100
OUT_A = 0x4600_0200
GRID = 0x4600_1000                       # sm_grid_t: data, len, pt[256], done[256]


def put_par(cpu, words):
    blob = struct.pack(">8h", *words)
    cpu.uc.mem_write(PAR, blob)
    cpu.uc.mem_write(PAR_OURS, blob)


def ours(cpu, fn, *args):
    cpu.call(SYM[fn], *args, OUT_A, OUT_A + 4)
    return tuple(cpu.r32(OUT_A, 2))


def random_par(rng, play=None):
    w = [rng.randrange(-0x800, 0x8000) for _ in range(8)]
    w[1] = (rng.randrange(0, 4) if play is None else play) << 8 | rng.randrange(256)
    return w


@need_dt
def test_positions_oneshot_repitch_as_digitakt(cpu):
    rng = random.Random(1)
    for n in range(400):
        w = random_par(rng)
        if n % 3 == 0:
            w[6] = 0
        put_par(cpu, w)
        length = rng.choice([1, 2, 100, 4800, 48000, 0x7FFFF, rng.randrange(1, 0x80000)])
        first = rng.randrange(2)
        assert cpu.call(DT_ONESHOT, PAR, length, first) == ours(cpu, "sm_pos_oneshot", PAR_OURS, length, first), w
        assert cpu.call(DT_REPITCH, PAR, length) == ours(cpu, "sm_pos_repitch", PAR_OURS, length), w


@need_dt
def test_positions_slice_werp_as_digitakt(cpu):
    rng = random.Random(2)
    slot = 5
    pts = sorted(rng.randrange(0, 0x7FFFF) for _ in range(256))
    pts[0] = 0
    cpu.w32(DT_GRIDS + 1024 * slot, *pts)
    cpu.w32(GRID, 0, 0x7FFFF, *pts)
    for n in range(400):
        w = random_par(rng)
        w[3] = slot << 8 | rng.randrange(256)
        w[4] = rng.randrange(0, 0x4100) if n % 2 else rng.randrange(-0x400, 0x7F00)
        w[6] = rng.randrange(0, 0x800)
        put_par(cpu, w)
        length = rng.randrange(1, 0x80000)
        note = rng.randrange(0, 128) << 16 | rng.randrange(0x10000)
        track = rng.randrange(8)
        cpu.uc.mem_write(DT_VOICE_SLOT + 94 * track, bytes([slot]))
        assert cpu.call(DT_SLICE, PAR, note, length, track) == \
            ours(cpu, "sm_pos_slice", PAR_OURS, note, length, GRID), w
        phase = rng.randrange(0, 0x7FC0_0000)
        assert cpu.call(DT_WERP, PAR, phase, length) == ours(cpu, "sm_pos_werp", PAR_OURS, phase, length, GRID), w
    # nessun campione: tutto il campione
    cpu.uc.mem_write(DT_VOICE_SLOT, bytes([200]))
    assert cpu.call(DT_SLICE, PAR, 60 << 16, 1000, 0) == ours(cpu, "sm_pos_slice", PAR_OURS, 60 << 16, 1000, 0)


def make_signal(rng, n):
    """Audio di prova: toni e rumore con tratti di silenzio e di continua (zero-crossing rari)."""
    out, ph = [], 0.0
    for i in range(n):
        f = 0.002 + 0.03 * (math.sin(i / 3000) ** 2)
        ph += f
        v = 9000 * math.sin(2 * math.pi * ph) + rng.randrange(-300, 300)
        if (i // 2000) % 7 == 3:
            v = 0
        elif (i // 2500) % 9 == 5:
            v = 1200 + rng.randrange(0, 50)
        out.append(max(-32768, min(32767, int(v))))
    return out


@need_dt
def test_zero_crossing_and_grid_as_digitakt(cpu):
    rng = random.Random(3)
    for length in (5, 700, 20000, 150001):
        data = make_signal(rng, length + 1)
        ptr = 0x4500_0000
        cpu.uc.mem_write(ptr, struct.pack(f">{len(data)}h", *data))
        end = ptr + 2 * length
        for _ in range(60):
            idx = rng.randrange(0, length + 2)
            d = rng.choice([-1, 1])
            md = rng.randrange(0, 2000)
            assert cpu.call(DT_ZERO_CROSS, ptr, end, idx, d, md)[0] == \
                cpu.call(SYM["sm_zero_cross"], ptr, end, idx, d, md)[0]
        slot = 9
        cpu.call(DT_REGISTER, slot, ptr, 2 * length, 48000)
        ref = cpu.r32(DT_GRIDS + 1024 * slot, 256)
        got = [cpu.call(SYM["sm_grid_point"], ptr, length, k)[0] for k in range(256)]
        assert got == ref, length


def interp_ref(cpu, table_img: bytes, win: list[int], frac: int, rate: int) -> list[int]:
    """Il ciclo d'interpolazione della Digitakt eseguito da solo, con i registri che si aspetta."""
    from unicorn.m68k_const import (UC_M68K_REG_A0, UC_M68K_REG_A1, UC_M68K_REG_A7, UC_M68K_REG_D0,
                                    UC_M68K_REG_D1, UC_M68K_REG_D2, UC_M68K_REG_D3, UC_M68K_REG_SR)
    uc = cpu.uc
    uc.mem_write(DT_TABLE_RAM, table_img)
    w = 0x4500_8000
    uc.mem_write(w, struct.pack(f">{len(win)}h", *win))
    sp = STACK - 0x100
    uc.mem_write(sp + 88, struct.pack(">I", w))
    uc.mem_write(sp + 96, struct.pack(">I", (rate << 4) & 0xFFFF_FFFF))
    out = 0x8000_ECC0
    for reg, v in ((UC_M68K_REG_SR, 0x2700), (UC_M68K_REG_A7, sp), (UC_M68K_REG_A0, DT_TABLE_RAM),
                   (UC_M68K_REG_A1, out), (UC_M68K_REG_D0, 24), (UC_M68K_REG_D1, 28), (UC_M68K_REG_D2, frac),
                   (UC_M68K_REG_D3, (rate >> 28) & 0xFFFF_FFFF)):
        uc.reg_write(reg, v)
    cpu.emac.state.load_macsr(0xA0)
    uc.emu_start(DT_INTERP, DT_INTERP_END, count=100_000)
    return list(struct.unpack(">64i", uc.mem_read(out, 256)))


@need_dt
def test_interpolation_as_digitakt(cpu, dt3):
    table = dt3[DT_TABLE_IMG - LOAD:DT_TABLE_IMG - LOAD + 3072]
    tab_ours = 0x4600_4000
    cpu.uc.mem_write(tab_ours, table)
    rng = random.Random(4)
    for _ in range(40):
        win = [rng.randrange(-32768, 32768) for _ in range(160)]
        frac = rng.randrange(0, 1 << 32)
        rate = rng.randrange(1, 0x2300_0000)
        ref = interp_ref(cpu, table, win, frac, rate)
        w = 0x4500_9000
        cpu.uc.mem_write(w, struct.pack(f">{len(win)}h", *win))
        cpu.w32(OUT_A, frac - (1 << 32) if frac >= 1 << 31 else frac, 0)
        cpu.call(SYM["sm_interp"], w, OUT_A, OUT_A + 4, rate, OUT_A + 16, 64, tab_ours)
        assert cpu.r32(OUT_A + 16, 64) == ref


def response_db(table, freqs):
    """Risposta del prototipo (256 x 6 punti) in dB, normalizzata alla continua."""
    import numpy as np
    v = np.zeros(1536)
    for p in range(256):
        for k in range(6):
            v[256 * k + 255 - p] = table[k // 2][p][k % 2]
    nfft = 1 << 16
    h = np.abs(np.fft.rfft(v, nfft))
    return [20 * math.log10(max(h[int(f / 256 * nfft)] / h[0], 1e-9)) for f in freqs]


@need_dt
def test_our_table_has_the_digitakt_response(dt3):
    pytest.importorskip("numpy")
    import gen_table
    raw = struct.unpack(">1536h", dt3[DT_TABLE_IMG - LOAD:DT_TABLE_IMG - LOAD + 3072])
    theirs = [[[raw[r * 512 + 2 * p], raw[r * 512 + 2 * p + 1]] for p in range(256)] for r in range(3)]
    freqs = [0.05 * i for i in range(1, 12)]
    a, b = response_db(gen_table.table(), freqs), response_db(theirs, freqs)
    assert max(abs(x - y) for x, y in zip(a, b)) < 0.2
    stop = [0.75, 1.0, 1.25]
    assert all(x < -55 for x in response_db(gen_table.table(), stop))


def test_table_file_is_generated():
    import gen_table
    src = (ROOT / "mods" / "sampler" / "engine" / "interp_table.c").read_text()
    nums = [int(x) for x in src.split("sm_interp_table[3][256][2] = {", 1)[1].split("};", 1)[0]
            .replace("{", " ").replace("}", " ").replace(",", " ").split()]
    t = gen_table.table()
    assert nums == [t[r][p][i] for r in range(3) for p in range(256) for i in range(2)]


# ---- CPU #2: la build vera, sezione 7 compressa, avvio a freddo

SAMPLE_PTR, SAMPLE_TABLE = 0x4500_0000, 0x4404_F754
SR = 48000


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    t = tmp_path_factory.mktemp("sampler")
    out = t / "o.syx"
    build.build(STOCK, [ROOT / "mods" / "sampler"], out, log=lambda *_: None)
    f = eft.unpack(out, t / "u", ids=[3, 7])
    return f[3].read_bytes(), f[7].read_bytes()


def load_sample(e, data, slot=0):
    e.uc.mem_write(SAMPLE_PTR + 0x10_0000 * slot, struct.pack(f">{len(data)}h", *data))
    e.uc.mem_write(SAMPLE_TABLE + 8 * slot, struct.pack(">II", len(data), SAMPLE_PTR + 0x10_0000 * slot))


@pytest.fixture(scope="module")
def engines(built):
    import engine as eng
    e = eng.Engine(image=built[1])
    e.boot(cold=True)
    ref = eng.Engine()
    ref.boot()
    return e, ref


def frame(words, machine=44, note=60, typ=0):
    """words: indici 0x12..0x19 (TUNE PLAY BR SAMP, i tre del tipo, LEV); typ: TYPE, nella parola 0x1A (OVER)."""
    import cli
    p = cli.make_params(machine, note)
    for k, w in enumerate(words):                      # indici 0x12.. dalla parola 1 del blocco della traccia
        struct.pack_into(">h", p, 2 + 2 * k, w)
    struct.pack_into(">h", p, 2 + 2 * (0x1A - 0x12), typ)
    return p


def raw(e, words, typ=0):
    """Le parole della machine come impostate (xparams, 0x640: 20 B a voce dall'indice 0x11): il frame le porta
    smussate, il motore prende da qui le scelte (PLAY, SAMP, i tre del tipo, il tipo)."""
    e.uc.mem_write(0x640, struct.pack(">10h", 44, *(list(words) + [0] * 8)[:8], typ))


def play(e, words, blocks=24, **kw):
    p, out = frame(words, **kw), []
    raw(e, words, kw.get("typ", 0))
    for b in range(blocks):
        q = bytearray(p)
        if b in (0, 2):
            q[0x180] = 1                                # trig (il primo carica la machine)
        out += e.render_block(bytes(q))[0]
    return out


def sine(n, f=1000.0, amp=16000):
    return [int(amp * math.sin(2 * math.pi * f * i / SR)) for i in range(n)]


def freq(x):
    zc = sum(1 for i in range(1, len(x)) if (x[i - 1] < 0) != (x[i] < 0))
    return zc / 2 / (len(x) / SR)


def peak(x):
    return max(abs(v) for v in x)


ONESHOT = [0x4000, 0x300, 0, 0, 0, 0x7800, 0, 0x6400]  # TUNE PLAY BR SAMP STRT LEN LOOP LEV (100)
TAIL = 32 * 8                                          # dopo l'attacco dell'inviluppo


def test_plays_at_the_level_of_sp_twinshot(engines):
    e, ref = engines
    data = sine(48000)
    load_sample(e, data)
    load_sample(ref, data)
    out = play(e, ONESHOT)
    tw = play(ref, [0x4000, 0x4000, 0x4000, 0, 0x4000, 0x4000, 0x7F00, 0x7F00])  # SMP1 = slot 0, MIX tutto A
    ratio = peak(out[TAIL:]) / peak(tw[TAIL:])
    assert abs(20 * math.log10(ratio)) < 0.3
    assert abs(freq(out[TAIL:]) - 1000) < 40


def test_tune_reverse_start_length_loop(engines):
    e, _ = engines
    load_sample(e, sine(24000, 500))
    up = play(e, [0x4C00] + ONESHOT[1:])               # TUNE +12
    assert abs(freq(up[TAIL:]) - 1000) < 40
    n = 24000                                          # glissando: 300 Hz -> 3.3 kHz
    load_sample(e, [int(12000 * math.sin(2 * math.pi * (300 + 1500 * i / n) * i / SR)) for i in range(n)])
    base = play(e, ONESHOT)
    rev = play(e, [0x4000, 0x000] + ONESHOT[2:])       # REV: dalla fine (frequenza alta)
    assert freq(rev[TAIL:TAIL + 1024]) > 2 * freq(base[TAIL:TAIL + 1024])
    late = play(e, ONESHOT[:4] + [0x3C00, 0x7800] + ONESHOT[6:])   # STRT 60: dalla meta'
    assert freq(late[TAIL:TAIL + 1024]) > 1.5 * freq(base[TAIL:TAIL + 1024])
    short = play(e, ONESHOT[:5] + [0x0200] + ONESHOT[6:], blocks=60)   # LEN 2/120 = 400 campioni
    assert peak(short[-512:]) == 0 and peak(short[TAIL:TAIL + 256]) > 0
    looped = play(e, [0x4000, 0x200, 0, 0, 0, 0x0200, 0, 0x6400], blocks=60)   # FWD.L: continua
    assert peak(looped[-512:]) > 0


def test_slice_and_repitch(engines):
    e, _ = engines
    n = 48000
    data = [int(12000 * math.sin(2 * math.pi * f * i / SR)) for f in (500, 1000, 2000, 4000) for i in range(n // 4)]
    load_sample(e, data)
    for sel, f in ((1, 500), (2, 1000), (4, 4000)):    # GRID 0 = 4 slice
        out = play(e, [0x4000, 0x300, 0, 0, sel << 8, 0, 0, 0x6400], blocks=40, typ=0x300)
        assert abs(freq(out[TAIL:TAIL + 2048]) - f) < f * 0.08, sel
    # SLICE NOTE: la nota sceglie la slice ((nota - 12) & 3 con 4 slice: C4 = 1, E4 = 1, D#4 = 4) e non traspone,
    # come la Digitakt (0x4007576A: nota 60 per l'intonazione)
    for note, f in ((60, 500), (61, 1000), (63, 4000), (64, 500)):
        out = play(e, [0x4000, 0x300, 0, 0, 0, 0, 0, 0x6400], blocks=40, typ=0x300, note=note)
        assert abs(freq(out[TAIL:TAIL + 2048]) - f) < f * 0.08, note
    load_sample(e, sine(48000))                      # 1 s a 120 BPM, BARS 0 = 1 battuta (2 s): meta' velocita'
    out = play(e, [0x4000, 0x300, 0, 0, 0, 0x7800, 0x000, 0x6400], blocks=40, typ=0x200)
    assert abs(freq(out[TAIL:]) - 500) < 30
    out = play(e, [0x4000, 0x300, 0, 0, 0, 0x7800, 0x100, 0x6400], blocks=40, typ=0x200)    # BARS 1 = 2 battute
    assert abs(freq(out[TAIL:]) - 250) < 25
    # TUNE +12 e la nota non traspongono, come la Digitakt (0x400756C0)
    out = play(e, [0x4C00, 0x300, 0, 0, 0, 0x7800, 0x000, 0x6400], blocks=40, typ=0x200, note=67)
    assert abs(freq(out[TAIL:]) - 500) < 30


def test_choices_are_the_values_as_set(engines):
    """Il frame porta i parametri della machine smussati dalla CPU #1 (0x400979CA: qualche percento a blocco verso
    il valore nuovo): al trig dopo un p-lock o un cambio il valore sarebbe ancora quello vecchio. Le scelte vengono
    da xparams (0x640), come impostate: frame con SLICE 1, impostato SLICE 4 -> suona la slice 4."""
    e, _ = engines
    n = 48000
    load_sample(e, [int(12000 * math.sin(2 * math.pi * f * i / SR)) for f in (500, 1000, 2000, 4000) for i in range(n // 4)])
    p, out = frame([0x4000, 0x300, 0, 0, 1 << 8, 0, 0, 0x6400], typ=0x300), []
    raw(e, [0x4000, 0x300, 0, 0, 4 << 8, 0, 0, 0x6400], 0x300)
    for b in range(40):
        q = bytearray(p)
        if b in (0, 2):
            q[0x180] = 1
        out += e.render_block(bytes(q))[0]
    assert abs(freq(out[TAIL:TAIL + 2048]) - 4000) < 320


def xpar(e, v):
    """Manopola H della 2/2 (indice 0x36): sy-fm4 la copia nella RAM condivisa a 0x700, 16 byte a voce."""
    e.uc.mem_write(0x700, struct.pack(">h", v << 8))


def test_knob_h_per_machine(engines):
    """XFAD, RAND, KEY, ORDR: 0 lascia la machine come la Digitakt."""
    e, _ = engines
    try:
        n = 48000                                       # 4 slice: 500, 1000, 2000, 4000 Hz
        load_sample(e, [int(12000 * math.sin(2 * math.pi * f * i / SR)) for f in (500, 1000, 2000, 4000)
                        for i in range(n // 4)])
        # SLICE ORDR NEXT: a ogni trig la slice successiva, da SLICE 2
        xpar(e, 1)
        p = frame([0x4000, 0x300, 0, 0, 2 << 8, 0, 0, 0x6400], typ=0x300)
        raw(e, [0x4000, 0x300, 0, 0, 2 << 8, 0, 0, 0x6400], 0x300)
        got = []
        for trig in range(4):
            out = []
            for b in range(40):
                q = bytearray(p)
                if b in ((0, 2) if trig == 0 else (0,)):
                    q[0x180] = 1
                out += e.render_block(bytes(q))[0]
            got.append(freq(out[TAIL:TAIL + 512]))
        assert [round(f / 500) for f in got] == [4, 8, 1, 2], got            # 2 trig al primo giro: 3, 4, 1, 2
        # REPITCH KEY ON: nota +12 = un'ottava sopra; OFF (0) come la Digitakt
        load_sample(e, sine(48000))
        xpar(e, 1)
        up = play(e, [0x4000, 0x300, 0, 0, 0, 0x7800, 0, 0x6400], blocks=40, typ=0x200, note=72)
        xpar(e, 0)
        flat = play(e, [0x4000, 0x300, 0, 0, 0, 0x7800, 0, 0x6400], blocks=40, typ=0x200, note=72)
        assert abs(freq(up[TAIL:]) - 1000) < 60 and abs(freq(flat[TAIL:]) - 500) < 30
        # ONESHOT XFAD: loop su 2000 campioni di un seno a 1001 Hz (fase sbagliata alla giunzione)
        load_sample(e, sine(8000, 1001.0))
        words = [0x4000, 0x200, 0, 0, 0, 0x2000, 0x1001, 0x6400]           # FWD.L, LEN 32, LOOP 16
        hard = play(e, words, blocks=120)
        xpar(e, 127)
        soft = play(e, words, blocks=120)
        jump = lambda x: max(abs(x[i] - x[i - 1]) for i in range(TAIL * 4, len(x)))   # noqa: E731
        assert jump(soft) < 0.8 * jump(hard)
        # WERP RAND: 127 cambia la sequenza dei segmenti, 0 no
        load_sample(e, [int(12000 * math.sin(2 * math.pi * (200 + 3000 * i / 96000) * i / SR)) for i in range(96000)])
        xpar(e, 0)
        w0 = play(e, [0x4000, 0x300, 0, 0, 0x000, 0x300, 0x000, 0x6400], blocks=200, typ=0x100)
        w0b = play(e, [0x4000, 0x300, 0, 0, 0x000, 0x300, 0x000, 0x6400], blocks=200, typ=0x100)
        xpar(e, 127)
        w1 = play(e, [0x4000, 0x300, 0, 0, 0x000, 0x300, 0x000, 0x6400], blocks=200, typ=0x100)
        assert w0[TAIL:] == w0b[TAIL:] and w1[TAIL:] != w0[TAIL:] and peak(w1) > 0   # dopo il trig
    finally:
        xpar(e, 0)


def test_type_word_does_not_reach_the_overdrive(built):
    """TYPE viaggia nella parola 0x1A, quella che l'overdrive comune (0x4000112C) legge dopo i motori: il prep la
    legge e la azzera. Con SLICE (0x300) la parola e' 0 quando gira l'overdrive."""
    import engine as eng
    from unicorn import UC_HOOK_CODE
    from unicorn.m68k_const import UC_M68K_REG_A7
    e = eng.Engine(image=built[1])
    e.boot(cold=True)
    load_sample(e, sine(48000))
    seen = []

    def at_over(uc, _a, _s, _d):
        params[0] and seen.append(struct.unpack(">h", uc.mem_read(params[0] + 2 * 0x1A, 2))[0])
    params = [0]

    def at_prep(uc, _a, _s, _d):
        params[0] = struct.unpack(">I", uc.mem_read(uc.reg_read(UC_M68K_REG_A7) + 12, 4))[0]
    e.uc.hook_add(UC_HOOK_CODE, at_prep, begin=SYM["syn_smp_prep"], end=SYM["syn_smp_prep"])
    e.uc.hook_add(UC_HOOK_CODE, at_over, begin=0x4000_112C, end=0x4000_112C)
    out = play(e, [0x4000, 0x300, 0, 0, 0x100, 0, 0, 0x6400], blocks=8, typ=0x300)
    assert peak(out) > 0 and seen and set(seen[2:]) == {0}


def test_lev_scales_the_level(engines):
    e, _ = engines
    load_sample(e, sine(48000))
    full = play(e, ONESHOT)
    half = play(e, ONESHOT[:7] + [0x3200])
    assert abs(20 * math.log10(peak(half[TAIL:]) / peak(full[TAIL:])) + 6.02) < 0.2
    assert peak(play(e, ONESHOT[:7] + [0])[TAIL:]) == 0


def test_waveform_for_the_main_cpu(built):
    """La CPU #1 chiede il profilo di uno slot a 0x5B0 (slot + 1); la CPU #2 lo calcola a colonne durante i
    prep: 112 picchi 0..127 a 0x5C0, pronti quando 0x5B6 = 112 (0x5B4 = slot + 1)."""
    import engine as eng
    e = eng.Engine(image=built[1])
    e.boot(cold=True)
    data = [int(16000 * (i / 48000)) * (1 if i % 2 else -1) for i in range(48000)]   # rampa: picchi crescenti
    load_sample(e, data, slot=2)
    load_sample(e, sine(4800), slot=0)
    e.uc.mem_write(0x5B0, struct.pack(">H", 3))
    play(e, ONESHOT, blocks=80)
    slot, done = struct.unpack(">HH", e.uc.mem_read(0x5B4, 4))
    assert (slot, done) == (3, 112)
    w = list(e.uc.mem_read(0x5C0, 112))
    assert w == sorted(w) and w[0] < 5 and w[-1] >= 60
    load_sample(e, sine(9600), slot=2)                 # sample nuovo nello stesso slot: si ricomincia
    play(e, ONESHOT, blocks=80)
    w = list(e.uc.mem_read(0x5C0, 112))
    assert min(w) >= 60                                # 16000 >> 8: picchi uguali dall'inizio


def test_other_machines_unchanged(built):
    import engine as eng
    for m in (0, 4, 37):                                   # motori nuovi: lo stato delle voci non passa da un test all'altro
        e = eng.Engine(image=built[1])
        e.boot(cold=True)
        ref = eng.Engine()
        ref.boot()
        assert play(e, [0x4000] * 8, machine=m, blocks=12) == play(ref, [0x4000] * 8, machine=m, blocks=12), m


def test_werp_plays_segments(engines):
    e, _ = engines
    load_sample(e, sine(96000, 700))
    out = play(e, [0x4000, 0x300, 0, 0, 0x100, 0x300, 0x200, 0x6400], blocks=40, typ=0x100)   # SEG 1/16, 4 bars
    assert peak(out[TAIL:]) > 0
    assert abs(freq(out[TAIL:]) - 700) < 60               # tono invariato: si allunga il tempo, non l'altezza


# ---- CPU #1: interfaccia (emulatore dell'OS principale)

@pytest.fixture(scope="module")
def ui():
    import screens

    def setup(u):
        obj = u.call(0x4000_F04C, [u.project + 304, 0])          # suono della traccia 1
        u.call(0x4002_5594, [obj, 44, 0, 1], count=400_000_000)  # machine 44
    return screens.UI(["sampler"], setup=setup)


OBJS, DESC = 0x41BA_0A24, 0x4022_D83C


def text(u, i, v):
    buf = 0x4FE0_3000
    u.uc.mem_write(buf, bytes(32))
    u.call(u.sym["sm_invoke"], [OBJS + 84 * i + 20, v, buf])
    return bytes(u.uc.mem_read(buf, 16)).split(b"\0")[0].decode()


def short(u, i):
    a = struct.unpack(">I", u.uc.mem_read(DESC + 52 * i + 48, 4))[0]
    return bytes(u.uc.mem_read(a, 8)).split(b"\0")[0].decode()


def test_page_names_and_values(ui):
    tab = ui.tab("SRC")
    ids = [ui.param(tab, e) for e in "ABCDEFGH"]
    lix = [struct.unpack(">I", ui.uc.mem_read(DESC + 52 * i + 4, 4))[0] for i in ids]
    assert lix == list(range(0x12, 0x1A))                        # A..H = indici 0x12..0x19 (il tipo in 0x1A, dal menu)
    assert [short(ui, i) for i in ids[:4]] + [short(ui, ids[7])] == ["TUNE", "PLAY", "BR", "SAMP", "LEV"]
    for i in ids[1:]:                                            # TUNE tiene formattatore e grafica dell'OS
        f = struct.unpack(">8I", ui.uc.mem_read(OBJS + 84 * i + 20, 32))
        assert f[2:4] == (ui.sym["sm_mgr"], ui.sym["sm_invoke"]) and f[6:] == (ui.sym["sm_mgr"], ui.sym["sm_gfx"])
    assert [text(ui, ids[1], v << 8) for v in range(4)] == ["REV", "REV.L", "FWD.L", "FWD"]
    assert text(ui, ids[3], 0) == "1" and text(ui, ids[3], 0x3F00) == "64"
    assert text(ui, ids[7], 100 << 8) == "100"                   # LEV
    seq = 0x8000_21B0 + 2 * (0xE + 0x1A)                         # TYPE della traccia 1 nei valori del sequencer
    expect = {0: ["STRT", "LEN", "LOOP"], 1: ["SEG", "MODE", "BARS"], 2: ["STRT", "LEN", "BARS"],
              3: ["SLICE", "LEN", "GRID"]}
    for t, names in expect.items():
        ui.put(seq, ">h", t << 8)
        text(ui, ids[1], 0)
        assert [short(ui, i) for i in ids[4:7]] == names
    ui.put(seq, ">h", 3 << 8)
    assert [text(ui, ids[6], v << 8) for v in range(5)] == ["4", "8", "16", "32", "64"]
    assert text(ui, ids[4], 0) == "NOTE"                          # testi della Digitakt
    ui.put(seq, ">h", 1 << 8)
    assert [text(ui, ids[4], v << 8) for v in range(3)] == ["1/32", "1/16", "1/8"]
    assert [text(ui, ids[6], v << 8) for v in range(4)] == ["1", "2", "4", "8"]


def test_tempo_to_shared_ram(ui):
    ui.call(ui.sym["sm_block"], [0])
    tempo = struct.unpack(">I", ui.uc.mem_read(0x402D_7360, 4))[0]
    assert tempo == 120 * 120                                    # progetto nuovo: 120 BPM
    assert struct.unpack(">I", ui.uc.mem_read(0x1000_07F0, 4))[0] == tempo


def test_main_cpu_cost_per_block(ui):
    """sm_block a ogni blocco: il tempo nella RAM condivisa, poi la chiamata originale."""
    import budget
    from unicorn import UC_HOOK_CODE
    n = [0]
    h = ui.uc.hook_add(UC_HOOK_CODE, lambda *a: n.__setitem__(0, n[0] + 1))
    ui.call(0x4009_5608, [0])
    orig, n[0] = n[0], 0
    ui.call(ui.sym["sm_block"], [0])
    ui.uc.hook_del(h)
    assert n[0] - orig <= budget.AUDIO_CPU["sampler"], n[0] - orig


def test_syn_pages():
    """Pagine SYN da syn-pages (vista SRC, machine del suono = 44). 1/2: la pagina della Digitakt, H = LEV
    (indice 0x19). 2/2: niente manopole sotto la forma d'onda, i tre del tipo, H = il parametro della machine
    (indice 0x36: XFAD, RAND, KEY, ORDR); il tipo si sceglie dal menu delle machine. Titoli col nome della machine della Digitakt. La 2/2 chiede alla CPU #2 il profilo dello slot della traccia e lo disegna quando e' pronto;
    sm_block chiede un ridisegno quando ne arriva dell'altro."""
    from syn_view import SynView
    v = SynView(["sampler"], machine=44)
    ui = v.ui
    lix = lambda: struct.unpack(">I", ui.uc.mem_read(DESC + 52 * 503 + 4, 4))[0]   # noqa: E731
    assert v.knobs() == [497, 498, 499, 504, 501, 502, 500, 503, 10] and v.pages() == 2
    assert lix() == 0x19 and short(ui, 503) == "LEV" and v.title() == b"SAMPLE 1/2"
    v.set_value(0, 0x15, 5 << 8)                                   # SAMP 6
    v.page(1)
    assert v.knobs() == [0, 0, 0, 0, 501, 502, 500, 503, 10]
    assert lix() == 0x36 and short(ui, 503) == "XFAD" and v.title() == b"SAMPLE 2/2"   # H: il parametro della machine
    for t, name, texts in ((1, "RAND", {0: "0", 127: "127"}), (2, "KEY", {0: "OFF", 1: "ON"}),
                           (3, "ORDR", {0: "SLICE", 1: "NEXT", 2: "RAND"})):
        v.set_value(0, 0x1A, t << 8)
        v.record(7)
        assert short(ui, 503) == name and lix() == 0x36
        assert {k: text(ui, 503, k << 8) for k in texts} == texts
    assert v.title() == b"SLICE 2/2"
    v.set_value(0, 0x1A, 0)
    v.record(7)
    waiting = v.frame()
    assert struct.unpack(">H", ui.uc.mem_read(0x1000_05B0, 2))[0] == 6
    ui.put(0x1000_05B4, ">HH", 6, 112)
    ui.uc.mem_write(0x1000_05C0, bytes(range(0, 112)))
    drawn = v.frame()
    assert drawn != waiting
    rows = screens_pixels(drawn)
    assert sum(rows[y][x] for y in range(13, 37) for x in range(16, 128)) > 400     # la forma d'onda
    assert not any(rows[y][x] for y in range(13) for x in range(16, 128))         # sopra: il valore girato
    v.page(0)
    v.record(0)
    assert lix() == 0x19
    ui.put(0x444E_2334, ">I", 0x4FE0_4000)                         # ViewController finto: flag a +96
    ui.uc.mem_write(0x4FE0_4000 + 96, b"\0")
    ui.put(0x1000_05B6, ">H", 50)
    ui.call(ui.sym["sm_block"], [0])
    assert ui.uc.mem_read(0x4FE0_4000 + 96, 1) == b"\x01"


def test_machine_menu():
    """Menu delle machine: ONESHOT, WERP, REPITCH, SLICE (valori 45..48) al posto della machine 44 nell'elenco delle
    tracce digitali (0x400264B6), nella categoria della 44; la scelta (0x40025594) imposta la machine 44, il tipo
    nella parola 0x1A e i valori di partenza di E F G del tipo; da un'altra machine anche TUNE PLAY BR LEV (SAMP
    resta). Cursore del menu e manopola della machine vedono il valore del tipo della traccia."""
    import screens
    from unicorn.m68k_const import UC_M68K_REG_A0, UC_M68K_REG_A2
    u = screens.UI(["sampler"])
    out = 0x4FE0_3000
    u.uc.mem_write(out, bytes(12))
    u.uc.reg_write(UC_M68K_REG_A0, out)
    u.call(0x4002_64B6, [0])                                      # traccia 1, digitale
    ids = [u.long(a) for a in range(u.long(out), u.long(out + 4), 4)]
    assert 44 not in ids and ids[ids.index(45):ids.index(45) + 4] == [45, 46, 47, 48]
    name = lambda i: bytes(u.uc.mem_read(u.call(u.sym["sm_menu_name"], [i]), 12)).split(b"\0")[0]   # noqa: E731
    assert [name(i) for i in (45, 46, 47, 48)] == [b"ONESHOT", b"WERP", b"REPITCH", b"SLICE"]
    assert name(0) == b"BD MODERN"
    assert u.long(0x4002_F3E8) == u.sym["sm_menu_name"]           # anche il nome mostrato dopo YES (0x4002F346)
    assert [u.call(0x4002_EEB4, [i]) for i in (44, 45, 48, 0, 99)] == [11, 11, 11, 1, 0]
    out8 = 0x4FE0_3100
    u.uc.mem_write(out8, bytes(12))
    u.uc.reg_write(UC_M68K_REG_A0, out8)
    u.call(0x4002_64B6, [8])                                      # traccia 9, analogica: niente sampler
    assert not {44, 45, 46, 47, 48} & {u.long(a) for a in range(u.long(out8), u.long(out8 + 4), 4)}
    src = u.tab("SRC")
    trk = u.call(0x4001_FF74, [u.long(src + 116)])
    snd = u.call(0x4000_F04C, [u.long(src + 120), trk])
    data = u.call(u.long(u.long(snd) + 40), [snd])
    w = lambda: list(struct.unpack(">9H", u.uc.mem_read(data + 20 + 2 * 0x12, 18)))   # noqa: E731
    u.put(data + 20 + 2 * 0x15, ">H", 7 << 8)                     # SAMP 8: resta
    u.put(0x8000_21B0 + 2 * (0xE + 0x47 * trk + 0x15), ">H", 7 << 8)
    assert u.call(0x4002_5594, [snd, 48, trk, 0]) & 0xFF
    assert u.uc.mem_read(data + 162, 1)[0] == 44
    live = 0x8000_21B0 + 2 * (0xE + 0x47 * trk + 0x12)             # i valori vivi = i dati del suono da +20
    assert bytes(u.uc.mem_read(live, 18)) == bytes(u.uc.mem_read(data + 20 + 2 * 0x12, 18))
    assert w() == [0x4000, 0x300, 0, 0x700, 0, 0, 0, 0x6400, 0x300]       # SLICE: NOTE, LEN 1, GRID 4
    u.put(data + 20 + 2 * 0x12, ">H", 0x4C00)                     # TUNE +12: resta passando a WERP
    assert u.call(0x4002_5594, [snd, 46, trk, 0]) & 0xFF
    assert w() == [0x4C00, 0x300, 0, 0x700, 0x100, 0x300, 0x200, 0x6400, 0x100]   # SEG 1/16, MODE FWD, BARS 4
    assert u.call(0x4002_5594, [snd, 45, trk, 0]) & 0xFF
    assert w()[4:7] == [0, 0x7800, 0]                              # ONESHOT: STRT 0, LEN 120, LOOP OFF
    seq = 0x8000_21B0 + 2 * (0xE + 0x1A)
    u.put(seq, ">h", 2 << 8)                                       # la traccia attiva e' REPITCH
    u.uc.reg_write(UC_M68K_REG_A2, out)
    u.put(out + 460, ">I", 44)
    assert u.call(u.sym["sm_menu_cursor"]) == 47
    u.put(out + 460, ">I", 3)
    assert u.call(u.sym["sm_menu_cursor"]) == 3
    # 0x4002F2AE riporta il menu sulla machine del suono, e confronta con quella d'apertura (+436): valori del menu,
    # o il menu chiede "Confirm? Y/N" scorrendo le voci del sampler
    from unicorn.m68k_const import UC_M68K_REG_A6, UC_M68K_REG_D1, UC_M68K_REG_D2
    u.put(out + 12, ">I", 44)
    u.uc.reg_write(UC_M68K_REG_A6, out)
    u.uc.reg_write(UC_M68K_REG_D1, 49)
    assert u.call(u.sym["sm_menu_set"]) == 47
    assert u.uc.reg_read(UC_M68K_REG_D2) == 47 and u.uc.reg_read(UC_M68K_REG_D1) == 49
    u.put(out + 12, ">I", 0x1234)
    u.uc.reg_write(UC_M68K_REG_D2, 44)
    u.call(u.sym["sm_menu_opened"])
    assert u.long(out + 436) == 47 and u.long(out + 432) == 0x1234
    # i valori vivi della traccia seguono subito; la stessa machine di nuovo tiene i suoi valori
    assert u.call(0x4002_5594, [snd, 48, trk, 0]) & 0xFF
    assert struct.unpack(">h", u.uc.mem_read(seq, 2))[0] == 3 << 8
    u.put(data + 20 + 2 * 0x17, ">H", 5 << 8)                     # LEN 6 slice
    assert u.call(0x4002_5594, [snd, 48, trk, 0]) & 0xFF
    assert w()[5] == 5 << 8


def screens_pixels(frame):
    import screens
    return screens.pixels(frame)
