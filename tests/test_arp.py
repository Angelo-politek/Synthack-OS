"""arp (mods/arp): l'arpeggiatore di Synfact (arp-st) sulla 1.42, sopra sfcore.

- Sorgenti: quelli di Synfact con gli indirizzi tradotti; modifiche marcate, nessun indirizzo 1.41 rimasto.
- Selettore: confronto con quello originale della Digitone 1.44 (test_st_arp_selector_emu di Synfact), doppio TRIG
  e orologio.
- Lock: MODE/SPEED/RANGE/LEN in un lock nativo sull'indice 0x46, con le funzioni di lock dell'OS; lettura dagli
  oggetti lock degli eventi; posto per una corsia nuova.
- Impostazioni per traccia nel projstore: default a zero, andata e ritorno.
- Interrupt audio: a riposo quasi nulla.
"""

import hashlib
import itertools
import json
import random
import struct
import sys
from pathlib import Path

import pytest

pytest.importorskip("unicorn")

ROOT = Path(__file__).resolve().parents[1]
SY = ROOT / "firmware" / "Syntakt_OS1.42.syx"
DN = ROOT / "unpacked" / "Digitone_OS1.44" / "section_3_MAIN_OS.bin"
sys.path[:0] = [str(ROOT / "tools" / "emu"), str(ROOT / "tools" / "build"), str(ROOT / "tools" / "unpack")]
MOD = ROOT / "mods" / "arp"
SPEC = json.loads((MOD / "patch.json").read_text(encoding="utf-8"))
SYM = {k: int(v, 16) for k, v in SPEC["symbols"].items()}

APP, PATTERN, LOCK_MODEL = 0x4016_E9C8, 0x4001_9000, 0x4001_6062     # 1.41 0x4016E804, uguali, uguali
LOCK_GET = 0x4001_722A
WORK = 0x4FE1_0000
LEN_TABLE = list(range(31)) + list(range(32, 63, 2)) + [66, 70, 74, 78, 86, 94, 102, 110, 127]
DEFAULT = dict(mode=0, speed=9, range=1, len=30, length=15, enabled=0xFFFF, offsets=[0] * 16)


def needs_os():
    return pytest.mark.skipif(not SY.exists(), reason="OS stock assente")


# ------------------------------------------------------------------ sorgenti e patch (senza emulazione)
def test_sources_are_ported_and_marked():
    text = "".join(f.read_text(encoding="utf-8") for f in sorted((MOD / "synfact").glob("*.[ch]")))
    for tag in ("0x41525031u", "0x43464731u"):                         # 'ARP1', 'CFG1': etichette, non indirizzi
        assert tag in text
    for old in ("0x43bd7430", "0x43bd743c", "0x401c97fc", "0x4011a722", "0x4016e804", "0x4553f6e0"):
        assert old not in text.lower()
    assert "lfo3_pattern_get(" not in text and "arp_sound_" not in text and "->machine_telemetry" not in text
    assert text.count("SyntHack") >= 6
    origin = (MOD / "synfact" / "ORIGIN").read_text(encoding="utf-8")
    assert "1a6d0c74469db4c30423be29c90e0b07ba7f8003" in origin and "GPL-2.0-or-later" in origin
    assert not (MOD / "synfact" / "persist.c").exists()


def test_patch_is_current_and_registered():
    import modarea_layout as MA
    import projstore_layout as PS
    import registry
    for name, h in SPEC["sources_sha256"].items():
        assert hashlib.sha256((MOD / name).read_bytes().replace(b"\r\n", b"\n")).hexdigest() == h, name
    assert set(SPEC["uses"]) == {"sfcore:native", "sfcore:pages", "sfcore:render_in"}
    assert {"sfcore", "projstore", "xparams"} <= set(SPEC["requires"])
    assert registry.SFCORE_SLOTS[4] == "arp" and PS.PARTS["arp"] == (132, 288)
    blob, slot = SPEC["patches"]
    base = int(blob["ram"], 16)
    lo, hi = next((a, b) for a, b, who, w in registry.MODAREA if who == "arp" and "BSS" not in w)
    assert base == MA.RAM + lo and base + blob["len"] <= MA.RAM + hi
    assert struct.unpack(">I", bytes.fromhex(slot["hex"]))[0] == SYM["arp_module"]
    assert not any(p for p in SPEC["patches"] if not p.get("append"))      # nessun sito proprio


@needs_os()
def test_build_with_every_mod(tmp_path):
    import bootcheck
    import build
    mods = ["splash", "modarea", "vparams", "kitstore", "projstore", "fastmix", "dual-mono", "master-comp",
            "readable-values", "perf-fx", "fx3", "modarea7", "syn-pages", "xparams", "sy-fm4", "sampler",
            "long-samples", "sfcore", "modulation-skip", "idspace", "lfo3", "recorder", "poly", "arp"]
    m = build.build(SY, [ROOT / "mods" / n for n in mods], tmp_path / "x.syx", log=lambda *_: None)
    print("margine:", m["boot_margin"])
    assert "arp" in m["mods"] and m["boot_margin"] >= bootcheck.MIN_MARGIN


# ------------------------------------------------------------------ selettore (Digitone 1.44 come oracolo)
class Lab:
    """Come test_st_arp_selector_emu di Synfact: la routine originale della Digitone e la nostra, stesso emulatore."""
    ENTRY = 0x4009_7E46
    STATE, MASKS, NODES, HEADS, TAILS = 0x413915F4, 0x41391694, 0x413916D4, 0x413926E4, 0x413926D4
    OWN, SETTINGS, SOUND, SP, RET = 0x49000000, 0x49010000, 0x49020000, 0x4DFFF000, 0x4DFF0000

    def __init__(self):
        from unicorn import UC_ARCH_M68K, UC_HOOK_CODE, UC_MODE_BIG_ENDIAN, Uc
        from unicorn import m68k_const as K
        self.K = K
        u = self.u = Uc(UC_ARCH_M68K, UC_MODE_BIG_ENDIAN, cpu=K.UC_CPU_M68K_ANY)   # CFV4E di unicorn: niente ff1
        blob = SPEC["patches"][0]
        base = int(blob["ram"], 16)
        page = base & ~0xFFF
        for a, n in ((0x40000000, 0x300000), (0x41390000, 0x10000), (page, 0x10000), (self.OWN, 0x40000),
                     (0x4DFF0000, 0x10000)):
            u.mem_map(a, n)
        u.mem_write(0x40000400, DN.read_bytes()[:0x300000 - 0x400])
        u.mem_write(base, bytes.fromhex(blob["hex"]))
        u.mem_write(self.RET, b"\x4e\x71")
        self.count = 0
        u.hook_add(UC_HOOK_CODE, self._trace)
        self.saved = [K.UC_M68K_REG_D2, K.UC_M68K_REG_D3, K.UC_M68K_REG_D4, K.UC_M68K_REG_D5, K.UC_M68K_REG_D6,
                      K.UC_M68K_REG_D7, K.UC_M68K_REG_A2, K.UC_M68K_REG_A3, K.UC_M68K_REG_A4, K.UC_M68K_REG_A5,
                      K.UC_M68K_REG_A6]

    def _trace(self, *_):
        self.count += 1

    def w(self, a, n):
        self.u.mem_write(a, struct.pack(">I", n & 0xFFFFFFFF))

    def read(self, a, n):
        return bytes(self.u.mem_read(a, n))

    def call(self, fn, *args):
        K, u = self.K, self.u
        for i, r in enumerate(self.saved):
            u.reg_write(r, 0x13570000 + i * 256)
        before = [u.reg_read(r) for r in self.saved]
        u.reg_write(K.UC_M68K_REG_SR, 0x2000)
        u.reg_write(K.UC_M68K_REG_A7, self.SP)
        u.mem_write(self.SP, struct.pack(f">{1 + len(args)}I", self.RET, *[a & 0xFFFFFFFF for a in args]))
        self.count = 0
        u.emu_start(SYM.get(fn, fn) if isinstance(fn, str) else fn, self.RET, count=30000)
        assert u.reg_read(K.UC_M68K_REG_PC) == self.RET, fn
        assert u.reg_read(K.UC_M68K_REG_A7) == self.SP + 4
        assert [u.reg_read(r) for r in self.saved] == before, fn
        v = u.reg_read(K.UC_M68K_REG_D0)
        return v if v < 0x80000000 else v - 0x100000000

    def fixture(self, track, mode, notes, octaves, mask, length, offsets):
        self.u.mem_write(0x41390000, bytes(0x10000))
        self.u.mem_write(self.SOUND, bytes(0x200))
        state = self.STATE + 40 * track
        for off in (0, 12, 16):
            self.w(state + off, 0xFFFFFFFF)
        self.w(state + 24, 1)
        self.w(state + 32, self.SOUND)
        self.u.mem_write(self.SOUND + 0x10F, bytes([mode, 0, octaves, 0, length]))
        self.u.mem_write(self.SOUND + 0x114, struct.pack(">H", mask))
        self.u.mem_write(self.SOUND + 0x116, bytes(x & 255 for x in offsets))
        nodes = [self.NODES + track * 1024 + note * 8 for note in notes]
        for i, (note, node) in enumerate(zip(notes, nodes)):
            self.w(node, nodes[i - 1] if i else 0)
            self.w(node + 4, nodes[i + 1] if i + 1 < len(nodes) else 0)
            a = self.MASKS + track * 16 + (note // 32) * 4
            self.w(a, int.from_bytes(self.read(a, 4), "big") | 1 << (note & 31))
        self.w(self.HEADS + track * 4, nodes[0] if nodes else 0)
        self.w(self.TAILS + track * 4, nodes[-1] if nodes else 0)
        own = self.OWN + 180 * (track + 8)
        self.call("arp_reset", own, 1)
        for note in notes:
            assert self.call("arp_hold", own, note) == 1
        self.u.mem_write(self.SETTINGS, struct.pack(">5BxH16b", mode, 0, octaves, 0, length, mask, *offsets))
        return own


@pytest.mark.skipif(not DN.exists() or hashlib.sha256(DN.read_bytes()).hexdigest() !=
                    "fce648a97c6c5d93b961732e8f8db6b02e0820c6d344c7e2131fa05a4b3168e4", reason="Digitone 1.44 assente")
def test_selector_matches_digitone_1_44():
    lab = Lab()
    rng = random.Random(29012026)
    sets = [[], [60], [60, 64, 67], [67, 60, 64], [0, 31, 32, 63, 64, 95, 96, 127], list(range(128))]
    calls = 0
    for c, (mode, which, octaves, mask, length) in enumerate(
            itertools.product(range(5), range(len(sets)), [0, 3], [0, 0xFFFF, 0xA55A], [0, 15])):
        notes = sets[which]
        offsets = [rng.randrange(-24, 25) for _ in range(16)]
        track = c % 4
        own = lab.fixture(track, mode, notes, octaves, mask, length, offsets)
        for step in range(32):
            expected = lab.call(Lab.ENTRY, track, 1)
            actual = lab.call("arp_next", own, Lab.SETTINGS, 1)
            assert actual == expected, (mode, notes, octaves, mask, length, step)
            calls += 1
        assert lab.call(Lab.ENTRY, track, 2) == lab.call("arp_next", own, Lab.SETTINGS, 2) == -2
    # controllo negativo: un ordine diverso deve dare un'altra nota
    own = lab.fixture(0, 1, [67, 60, 64], 0, 0xFFFF, 15, [0] * 16)
    lab.u.mem_write(Lab.SETTINGS, bytes([2]))
    assert lab.call(Lab.ENTRY, 0, 1) != lab.call("arp_next", own, Lab.SETTINGS, 1)
    print("chiamate confrontate:", calls)
    assert calls == 360 * 32


@pytest.mark.skipif(not DN.exists(), reason="Digitone 1.44 assente")
def test_double_trig_and_clock():
    lab = Lab()
    s = Lab.OWN

    def clear():
        lab.u.mem_write(s, bytes(20))

    def key(flags, now, t=0, main=1, k=0x13):
        return lab.call("arp_trig_tap", s, k, flags, t, now, main)
    clear(); assert key(1, 0) == 0; assert key(16, 1) == 0; assert key(1, 525) == 2; assert key(16, 526) == 1  # noqa: E702
    clear(); assert key(1, 0) == 0; assert key(9, 300) == 0; assert key(16, 400) == 0; assert key(1, 526) == 0  # noqa: E702
    clear(); key(1, 0); key(16, 1); assert key(1, 10, t=1) == 0                     # noqa: E702
    clear(); key(1, 0); key(16, 1); assert key(1, 10, main=0) == 0                  # noqa: E702
    clear(); key(1, 0, t=11); key(16, 1, t=11); assert key(1, 300, t=11) == 2       # noqa: E702
    clear(); assert key(1, 0, t=12) == 0; key(16, 1, t=12); assert key(1, 300, t=12) == 0  # noqa: E702
    # doppio tocco segnato dall'OS (bit 1, 0x400F9820): apre anche oltre la finestra, non sulla FX track o fuori
    # dalla schermata principale (sulla macchina il doppio TRIG rapido arrivava con il bit 1 e passava all'OS)
    clear(); key(1, 0); key(16, 1); assert key(3, 10) == 2; assert key(18, 11) == 1  # noqa: E702
    clear(); assert key(3, 5000, t=3) == 2                                           # noqa: E702
    clear(); assert key(3, 0, t=12) == 0; clear(); assert key(3, 0, main=0) == 0     # noqa: E702
    state, due = Lab.OWN + 0x31000, Lab.SETTINGS + 0x300
    den = [1, 2, 3, 4, 5, 6, 8, 10, 12, 16, 20, 24, 32, 40, 48, 64, 80, 96]
    for speed, d in enumerate(den):
        for tempo in (3600, 14400, 36000):
            step, period = 2 * tempo, 86400000 // d
            assert lab.call("arp_clock_arm", state, 0, speed, 1) == 1
            for n in range(d):
                tick = n * period
                begin = tick // step * step
                assert lab.call("arp_clock_poll", state, begin, begin + step, 1, due) == 1
                assert int.from_bytes(lab.read(due, 4), "big") == tick


# ------------------------------------------------------------------ OS avviato
def boot(mods=("arp",)):
    import screens
    u = screens.UI(list(mods))
    u.call(u.sym["sfcore_bind"])
    u.sym.update(SYM)
    return u


def lock_model(u):
    app = u.call(APP)
    pattern = u.call(PATTERN, [app])
    model = u.call(LOCK_MODEL, [pattern])
    assert model
    return model


def signed(v):
    return v - (1 << 32) if v & 0x8000_0000 else v


@needs_os()
def test_binding_and_interest():
    u = boot()
    st = struct.unpack(">8I", u.uc.mem_read(u.sym["sfcore_status"], 32))
    assert st[4] == 1 and sum(st) == 1
    interest = bytes(u.uc.mem_read(u.sym["core_native_interest"], 22))
    assert [i for i, b in enumerate(interest) if b] == [2, 5, 6, 20]      # IMMEDIATE, HEADER_LOAD/RESET, NOTE_ACCEPT


@needs_os()
def test_len_steps():
    u = boot()
    step = u.sym["arp_len_step"]
    assert [u.call(step, [n, 1]) for n in LEN_TABLE] == LEN_TABLE[1:] + [127]
    assert [u.call(step, [n, signed(-1) & 0xFFFFFFFF]) for n in LEN_TABLE] == [0] + LEN_TABLE[:-1]
    assert u.call(step, [33, 1]) == 34 and u.call(step, [33, -1 & 0xFFFFFFFF]) == 32 and u.call(step, [120, 1]) == 127
    assert u.call(step, [30, 100]) == 127 and u.call(step, [30, -100]) == 0


@needs_os()
def test_packed_locks_with_the_os_lock_functions():
    u = boot()
    model = lock_model(u)
    get, put = u.sym["arp_lock_get"], u.sym["arp_lock_set"]
    native = lambda t, s: signed(u.call(LOCK_GET, [model, t, s, 0x46]))    # noqa: E731
    assert [signed(u.call(get, [model, 3, 5, f])) for f in range(4)] == [-1] * 4
    assert u.call(put, [model, 3, 5, 1, 12]) == 1                          # SPEED 1/32
    assert [signed(u.call(get, [model, 3, 5, f])) for f in range(4)] == [-1, 12, -1, -1]
    assert 0 <= native(3, 5) < 0x8000 and native(3, 6) == -1 and native(2, 5) == -1
    assert u.call(put, [model, 3, 5, 3, 33]) == 1                          # LEN 33: il valore della tabella sotto
    assert u.call(put, [model, 3, 5, 0, 4]) == 1 and u.call(put, [model, 3, 5, 2, 3]) == 1
    assert [signed(u.call(get, [model, 3, 5, f])) for f in range(4)] == [4, 12, 3, 32]
    assert u.call(put, [model, 3, 5, 0, 5]) == 0 and u.call(put, [model, 3, 5, 2, 4]) == 0   # fuori scala
    rnd = random.Random(3)
    for _ in range(150):                                                   # ogni campo, con e senza lock
        want = [rnd.choice([-1, rnd.randrange(5)]), rnd.choice([-1, rnd.randrange(18)]),
                rnd.choice([-1, rnd.randrange(4)]), rnd.choice([-1, rnd.choice(LEN_TABLE)])]
        step = rnd.randrange(64)
        for f, v in enumerate(want):
            u.call(put, [model, 7, step, f, v & 0xFFFFFFFF])
        assert [signed(u.call(get, [model, 7, step, f])) for f in range(4)] == want
        assert (native(7, step) >= 0) == any(v >= 0 for v in want) and native(7, step) < 0x8000
    for f in range(4):                                                     # tutti tolti: nessun lock
        u.call(put, [model, 3, 5, f, 0xFFFFFFFF])
    assert native(3, 5) == -1


@needs_os()
def test_a_new_lane_needs_room():
    u = boot()
    model = lock_model(u)
    put = u.sym["arp_lock_set"]
    matrix = u.call(u.long(u.long(model) + 40), [model])
    flags = lambda t: matrix + t * 0x2447 + 0x2400                         # noqa: E731
    used = sum(u.uc.mem_read(flags(t), 71).count(0) ^ 71 for t in range(13))
    assert used == 0
    for i in range(79):                                                    # 79 corsie di altri parametri
        u.uc.mem_write(flags(i // 40) + i % 40, b"\x01")
    assert u.call(put, [model, 2, 0, 1, 3]) == 0
    u.uc.mem_write(flags(1) + 38, b"\x00")
    assert u.call(put, [model, 2, 0, 1, 3]) == 1
    u.uc.mem_write(flags(1) + 38, b"\x01")                                 # di nuovo pieno: la corsia c'e' gia'
    assert u.call(put, [model, 2, 9, 0, 1]) == 1


@needs_os()
def test_locks_from_the_event_lock_object():
    u = boot()
    model = lock_model(u)
    u.call(u.sym["arp_lock_set"], [model, 0, 0, 1, 17])
    u.call(u.sym["arp_lock_set"], [model, 0, 0, 3, 127])
    packed = signed(u.call(LOCK_GET, [model, 0, 0, 0x46]))
    obj, out = 0x47FF_0000, WORK + 0x200                                  # gli oggetti lock stanno sotto 0x48000000
    ext = u.sym["synfact_extra_locks"]

    def lock_object(pairs):
        u.uc.mem_write(obj, bytes(0x100))
        u.put(obj + 8, ">I", len(pairs))
        for i, (lix, v) in enumerate(pairs):
            u.put(obj + 20 + 8 * i, ">HHI", lix, v, 0)
    lock_object([(0x12, 100), (0x46, packed), (0x20, 5)])
    assert u.call(ext, [0, obj, out]) == 0b1010
    assert struct.unpack(">4H", u.uc.mem_read(out, 8))[1::2] == (17, 127)
    assert u.call(ext, [12, obj, out]) == 0                                # traccia FX: niente ARP
    lock_object([(0x12, 100)])
    assert u.call(ext, [0, obj, out]) == 0
    lock_object([(0x46, 0x8000)])
    assert u.call(ext, [0, obj, out]) == 0
    assert u.call(ext, [0, 0, out]) == 0


@needs_os()
def test_settings_per_track_saved_with_the_project():
    import projstore_layout as PS
    u = boot()
    data = PS.DATA + PS.PARTS["arp"][0]
    rd, st = u.sym["arp_track_read"], u.sym["arp_track_store"]

    def read(t):
        u.call(rd, [t, WORK])
        m, sp, rg, ln, lg, en, *ofs = struct.unpack(">5BxH16b", u.uc.mem_read(WORK, 24))
        return dict(mode=m, speed=sp, range=rg, len=ln, length=lg, enabled=en, offsets=ofs)
    assert bytes(u.uc.mem_read(data, 288)) == bytes(288)
    assert all(read(t) == DEFAULT for t in range(12))                      # zeri del progetto = default
    want = dict(mode=2, speed=17, range=3, len=94, length=7, enabled=0x1234, offsets=list(range(-8, 8)))
    u.uc.mem_write(WORK + 0x100, struct.pack(">5BxH16b", 2, 17, 3, 94, 7, 0x1234, *range(-8, 8)))
    assert u.call(st, [5, WORK + 0x100]) == 1
    assert read(5) == want and read(4) == DEFAULT and read(6) == DEFAULT
    assert bytes(u.uc.mem_read(data + 24 * 5 + 24, 24)) == bytes(24)
    u.uc.mem_write(WORK + 0x100, struct.pack(">5BxH16b", 5, 0, 0, 0, 0, 0, *[0] * 16))
    assert u.call(st, [5, WORK + 0x100]) == 0 and read(5) == want         # non valido: rifiutato
    u.uc.mem_write(data + 24 * 9, b"\xFF" * 24)                            # byte rovinati: default
    assert read(9) == DEFAULT


# ------------------------------------------------------------------ interrupt audio
@needs_os()
def test_idle_costs_almost_nothing():
    import isr

    def run(mods, uses=()):
        m = isr.Isr(mods, uses=uses)
        m.ui.call(m.ui.sym["sfcore_bind"])
        m.scene("max")
        m.run()
        m.fast(4)
        return m, m.run().n
    s, a = run(["sfcore", "projstore", "xparams"], sorted(SPEC["uses"]))
    m, b = run(["arp"])
    print("istruzioni per blocco:", a, b)
    assert bytes(s.uc.mem_read(0x8000_0000, 0x1_0000)) == bytes(m.uc.mem_read(0x8000_0000, 0x1_0000))
    assert b - a <= 40


# ------------------------------------------------------------------ generatore: NOTE_ACCEPT e render_in
POOL = 0x444D_F440                     # testa della lista libera degli eventi nativi (test_poly)
PLAYING, KIT_PTR, TIME, TEMPO = 0x43BD_83BC, 0x43BD_843C, 0x8000_46EC, 0x402D_7360
NOTE_ACCEPT = 20
STUB = WORK + 0xF00                    # coda: annota l'evento e risponde 1


def running(u, tracks, mode=2, speed=9, notes=(60,)):
    """ARP acceso sulle tracce (impostazioni nel projstore), radici accettate a tempo 0, coda finta."""
    for t in tracks:
        u.uc.mem_write(WORK + 0x100, struct.pack(">5BxH16b", mode, speed, 1, 30, 15, 0xFFFF, *[0] * 16))
        assert u.call(u.sym["arp_track_store"], [t, WORK + 0x100]) == 1
    base = WORK + 0x4000                                   # 600 eventi da 80 B, il successivo a +76
    for i in range(600):
        u.uc.mem_write(base + 80 * i, bytes(76) + struct.pack(">I", base + 80 * (i + 1) if i < 599 else 0))
    u.put(POOL, ">I", base)
    u.uc.mem_write(STUB, bytes.fromhex("7001" "4e75"))      # moveq #1,d0 ; rts
    api = u.sym["arp_native_api"]
    u.put(api + 12, ">I", STUB)
    u.put(PLAYING, ">I", 1)
    u.put(TEMPO, ">I", 14400)
    u.put(TIME, ">I", 0)
    assert u.long(KIT_PTR)
    for t in tracks:
        e = WORK + 0x200
        u.uc.mem_write(e, struct.pack(">20I", 1, 1, t, 1, 0, 0, notes[0], 0, 0, 0x10201, 0, 0, 0, *[0] * 7))
        u.put(WORK + 0x300, ">4I", e, 0, 0, 28800)
        u.put(WORK + 0x310, ">I", 0)
        assert u.call(u.sym["arp_native"], [NOTE_ACCEPT, WORK + 0x300, WORK + 0x310]) == 1, t
        assert u.long(WORK + 0x310) == 1                       # la radice e' dell'ARP
    return u


RT = 628                                # sizeof(struct arp_runtime): selector 180, clock 20, ..., live_sound 0x123
EMITTED, DROPPED, QUEUED_NOTE = 220, 224, 264


def count_instructions(u, fn, args=()):
    from unicorn import UC_HOOK_CODE
    n = [0]
    h = u.uc.hook_add(UC_HOOK_CODE, lambda *_: n.__setitem__(0, n[0] + 1))
    u.call(fn, args)
    u.uc.hook_del(h)
    return n[0]


@needs_os()
def test_note_accept_starts_and_render_in_plays_the_arp():
    u = running(boot(), [0])
    assert u.long(u.sym["arp_running"]) == 1
    assert u.sym["arp_voice"] + 12 * RT <= max(v for v in u.sym.values() if v > u.sym["arp_voice"])
    assert u.long(u.sym["arp_voice"] + EMITTED) == 1           # la prima nota subito
    for k in range(1, 800):                                    # 800 blocchi a 120 BPM: 1/16 = 187,5 blocchi
        u.put(TIME, ">I", 28800 * k)
        u.call(u.sym["arp_frame"])
    emitted = u.long(u.sym["arp_voice"] + EMITTED)
    assert emitted == 1 + 800 * 28800 // 5_400_000 == 5, emitted
    assert u.long(u.sym["arp_voice"] + DROPPED) == 0           # nessuna persa
    notes = struct.unpack(">5I", u.uc.mem_read(u.sym["arp_voice"] + QUEUED_NOTE, 20))
    assert notes == (60, 72, 60, 72, 60)                       # UP su due ottave (RANGE 2)
    assert u.long(u.sym["arp_blocks"]) == 799
    u.put(PLAYING, ">I", 0)                                    # STOP: l'arp si ferma
    u.call(u.sym["arp_frame"])
    assert u.long(u.sym["arp_running"]) == 0


@needs_os()
def test_cost_of_twelve_running_arps():
    """render_in con 12 arp in corsa: istruzioni per blocco senza nota e nel blocco di una nota (1/16 a 120 BPM)."""
    u = running(boot(), range(12))
    assert u.long(u.sym["arp_running"]) == 0xFFF
    quiet, beat = [], []
    for k in range(1, 400):
        u.put(TIME, ">I", 28800 * k)
        before = u.long(u.sym["arp_voice"] + EMITTED)
        n = count_instructions(u, u.sym["arp_frame"])
        (beat if u.long(u.sym["arp_voice"] + EMITTED) != before else quiet).append(n)
    print("istruzioni per blocco, 12 arp: senza nota", max(quiet), "con nota", max(beat), "media",
          sum(quiet + beat) // len(quiet + beat))
    # tra due passi solo i controlli rapidi (Synfact ricalcolava la velocita' a ogni blocco: media 908)
    assert len(beat) == 2 and sum(quiet + beat) // len(quiet + beat) <= 12 * 60 and max(beat) <= 12 * 150
