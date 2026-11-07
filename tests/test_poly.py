"""POLY (mods/poly): port di poly-st di Synfact sulla 1.42, sopra sfcore. Port dei test di Synfact
(test_st_poly_play_emu, _keyboard_emu, _publication_emu, _cost_emu) sull'OS vero avviato nell'emulatore.

- Sorgenti: quelli di Synfact con gli indirizzi tradotti; nessun indirizzo 1.41 rimasto.
- Pagina TRIG 3 (POLY, VOICES, PLAY, NOTE, NOT2-4) solo sulle tracce digitali; record nel pattern con CRC.
- Schiave: TRACK IN / SLAVE MODE, encoder e cambio di machine bloccati; Sound del master copiato (machine,
  parole di xparams: SY FM4 pagine 2/3, SAMPLER), anche dopo una modifica del master.
- Tastiera/MIDI: una voce per tasto, rotazione, furto della piu' vecchia, rilascio alla voce giusta. Accordi
  dai trig (NOT2..NOT4).
- Pubblicazione M.LFO: byte per byte contro un oracolo, ogni topologia digitale e ogni scelta di PLAY.
- Interrupt audio: POLY spento = stessa uscita, poche istruzioni; costo dei gruppi.
- PatternSettings 0x21..0x27: l'OS stock non li legge ne' scrive (solo le copie dell'intestazione).
"""

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
sys.path[:0] = [str(ROOT / "tools" / "emu"), str(ROOT / "tools" / "build"), str(ROOT / "tools" / "unpack")]
MOD = ROOT / "mods" / "poly"
SPEC = json.loads((MOD / "patch.json").read_text(encoding="utf-8"))
SYM = {k: int(v, 16) for k, v in SPEC["symbols"].items()}

SEQ_PTR, KIT_PTR = 0x43BD_8430, 0x43BD_843C          # 1.41 0x43BD7430 / 0x43BD743C
RECORD = 0x21381                                     # PatternSettings 0x21..0x27 nella copia del sequencer
IMMEDIATE = 0x4011_A8E6                              # coda immediata nativa (1.41 0x4011A722)
LIVE_CREATE, LIVE_CREATED = 0x4011_9848, 0x4011_98EC  # costruttore delle note da tastiera/MIDI (1.41 0x40119684)
KEY_PRESS, KEY_RELEASE = 0x4002_ED0A, 0x4002_D602    # ritorni dei chiamanti della tastiera (origine della nota)
EVENT_FREE = 0x4011_A6BC
WORK = 0x4FE1_0000                                   # buffer dei test (impalcatura dell'emulatore)
CMD = 0x4FE1_2000
ROW = 0x8E
POLY, SYNC, CFG2 = 0x504F4C59, 0x53594E43, 0x43464732


def needs_os():
    return pytest.mark.skipif(not SY.exists(), reason="OS stock assente")


# ------------------------------------------------------------------ sorgenti e patch (senza emulazione)
def test_sources_are_ported_and_marked():
    text = "".join(f.read_text(encoding="utf-8") for f in sorted((MOD / "synfact").glob("*.[cs]")))
    assert "0x40338600u" not in text and "0x40339740u" in text           # limite del codice, a mano
    for tag in ("0x434f5059u", "0x43464731u", "0x43464732u", "0x414e4c47u"):   # etichette ASCII, non indirizzi
        assert tag in text
    for old in ("0x43bd7430", "0x43bd743c", "0x401c97fc", "0x4011a722", "0x40115f78"):   # indirizzi 1.41
        assert old not in text.lower()
    assert text.count("SyntHack:") >= 10
    origin = (MOD / "synfact" / "ORIGIN").read_text(encoding="utf-8")
    assert "1a6d0c74469db4c30423be29c90e0b07ba7f8003" in origin and "GPL-2.0-or-later" in origin


def test_patch_is_current_and_registered():
    import hashlib
    import registry
    for name, h in SPEC["sources_sha256"].items():
        assert hashlib.sha256((MOD / name).read_bytes().replace(b"\r\n", b"\n")).hexdigest() == h, name
    assert SPEC["requires"] == ["modarea", "sfcore", "idspace"]          # pagina 3 dal gancio di idspace (0x4007BA48)
    assert set(SPEC["uses"]) == {"sfcore:native", "sfcore:pages", "sfcore:render_in"}
    assert registry.SFCORE_SLOTS[5] == "poly"
    blob, slot = SPEC["patches"]
    base = int(blob["ram"], 16)
    lo, hi = next((a, b) for a, b, who, _ in registry.MODAREA if who == "poly")
    import modarea_layout as MA
    assert base == MA.RAM + lo and base + blob["len"] <= MA.RAM + hi
    assert int(slot["ram"], 16) == MA.RAM + registry.SFCORE_TABLE + 4 * 5
    assert struct.unpack(">I", bytes.fromhex(slot["hex"]))[0] == SYM["poly_module"]
    assert not any(p for p in SPEC["patches"] if not p.get("append"))      # nessun sito proprio: tutto da sfcore


@needs_os()
def test_build_with_every_mod(tmp_path):
    import bootcheck
    import build
    mods = ["splash", "modarea", "vparams", "kitstore", "projstore", "fastmix", "dual-mono", "master-comp",
            "readable-values", "perf-fx", "fx3", "modarea7", "syn-pages", "xparams", "sy-fm4", "sampler",
            "long-samples", "sfcore", "modulation-skip", "poly"]
    m = build.build(SY, [ROOT / "mods" / n for n in mods], tmp_path / "x.syx", log=lambda *_: None)
    print("margine:", m["boot_margin"])
    assert "poly" in m["mods"] and m["boot_margin"] >= bootcheck.MIN_MARGIN


# ------------------------------------------------------------------ emulatore: aiuti
def boot(mods=("poly",), setup=None):
    import screens
    u = screens.UI(list(mods), setup=setup)
    u.call(u.sym["sfcore_bind"])
    return u


def command(u, *words):
    """Comando privato di POLY sulla coda immediata nativa (passa da sfcore come IMMEDIATE): ritorna la parola 5."""
    u.uc.mem_write(CMD, struct.pack(">6I", *(list(words) + [0] * (6 - len(words)))))
    u.call(IMMEDIATE, [CMD])
    return u.long(CMD + 20)


def group(u, track, voices, mode=None):
    """Gruppo come dalla pagina: POLY ON con VOICES; mode 1 = PLAY POLY, 0 = M.LFO."""
    assert command(u, POLY, 0x43464731, track, 1, voices) == 1
    if mode is not None:
        command(u, POLY, CFG2, track, mode)


def state(u):
    cfg = u.sym["poly_seq_config"]
    return list(u.uc.mem_read(cfg + 8, 12)), list(u.uc.mem_read(cfg + 20, 12))


def record(u):
    return bytes(u.uc.mem_read(u.long(SEQ_PTR) + RECORD, 7))


def crc16(p):
    crc = 0xFFFF
    for b in p[:5]:
        crc ^= b << 8
        for _ in range(8):
            crc = ((crc << 1) ^ (0x1021 if crc & 0x8000 else 0)) & 0xFFFF
    return crc


def sound(u, t):
    kit = u.long(KIT_PTR)
    return bytes(u.uc.mem_read(kit + 0x2A + t * 0x123, 0x123))


def tick(u):
    ctrl = 0x4FE0_4000
    u.uc.mem_write(ctrl, bytes(0x40))
    u.call(u.sym["core_tick"], [ctrl])


class Trig:
    """La vista TRIG di una traccia digitale (l'emulatore la costruisce con le pagine analogiche [1, 3])."""

    def __init__(self, u):
        self.u, self.t = u, u.tab("TRIG")
        u.put(u.long(self.t + 0x7C), ">I", 2)          # pagine digitali [2, 3]: MainScreen 0x4003209C, ROM 0x401C8224
        self.ids(0)                                     # PAGE_NAV: POLY sincronizza la vista (terza pagina)

    def pages(self):
        L = self.u.long
        return [L(x) for x in range(L(self.t + 0x7C), L(self.t + 0x80), 4)]

    def ids(self, page):
        self.u.page(self.t, page)
        return [self.u.param(self.t, e) for e in "ABCDEFGH"]

    def turn(self, enc, delta):
        """Encoder come sul dispositivo: la vista TRIG passa prima ogni giro della pagina con id 3 allo stato del
        primo encoder (0x400415D0): qui quello stato e' appena oltre il ritardo anti-tocco, cosi' gli scatti
        arrivano alla manopola girata (sul dispositivo dopo una pausa)."""
        import screens
        u, t = self.u, self.t
        st = t + 180 + 20 * (screens.ENC[enc] - 1)
        for off, v in ((8, 0), (12, 0), (16, 0)):
            u.put(st + off, ">i", v)
        u.put(t + 180 + 16, ">i", 26)
        u.uc.mem_write(screens.EV, bytes(32))
        u.put(screens.EV + 12, ">iiB", screens.ENC[enc], delta, 0)
        u.call(u.long(u.long(t) + 68), [t, screens.EV])

    def draw(self):
        """La vista e poi il suo contesto DRAW (core_view_draw, come drawAll dopo ogni vista)."""
        import screens
        u = self.u
        u.uc.mem_write(screens.FB, bytes(1024))
        u.call(screens.BITMAP_CTOR, [screens.BM, 128, 64, screens.FB, screens.BITMAP_CLIP])
        u.call(u.long(u.long(self.t) + 16), [self.t, screens.BM])
        u.call(u.sym["core_event_view"], [1, self.t, screens.BM, 0])
        return screens.frame_bytes(bytes(u.uc.mem_read(screens.FB, 1024)))


# ------------------------------------------------------------------ pagina e topologia
@needs_os()
def test_binding_and_interest_without_groups():
    u = boot()
    st = struct.unpack(">8I", u.uc.mem_read(u.sym["sfcore_status"], 32))
    assert st[5] == 1 and sum(st) == 1
    interest = bytes(u.uc.mem_read(u.sym["core_native_interest"], 16))
    # senza gruppi: TRIG, IMMEDIATE, intestazione, pagine; niente ENQUEUE/PUBLISH/TYPE/guardie/MOD/LFO
    assert [i for i, b in enumerate(interest) if b] == [0, 2, 5, 6, 9, 10, 11, 12, 13]
    assert u.long(u.sym["core_native_page_view"]) == 0x401C_9A9C          # solo la vista TRIG (1.41 0x401C97FC)
    assert record(u) == bytes(7) and state(u) == ([0] * 12, list(range(12)))


@needs_os()
def test_trig_page_three_turns_poly_on():
    u = boot()
    v = Trig(u)
    assert v.pages() == [2, 3, 3]                       # terza pagina TRIG, solo sulle tracce digitali
    assert v.ids(2) == [0] * 8                          # POLY OFF: solo la manopola A
    v.turn("A", 4)
    assert state(u)[0][:2] == [3, 0] and state(u)[1][:3] == [0, 0, 2]
    assert v.ids(2) == [0, 0, 0, 0, 0x15, 0x1E, 0x1F, 0x20]          # E: NOTE, F..H: NOT2..NOT4
    for want in (4, 5, 5):                              # VOICES 3, 4, non oltre 4
        v.turn("B", 4)
        assert state(u)[0][0] == want
    assert state(u)[1][:5] == [0, 0, 0, 0, 4]
    rec = record(u)
    assert rec[:2] == b"PQ" and crc16(rec) == rec[5] << 8 | rec[6]
    v.turn("C", -4)                                     # PLAY: POLY (voci indipendenti), record PR
    rec = record(u)
    assert rec[:2] == b"PR" and crc16(rec) == rec[5] << 8 | rec[6]
    assert u.uc.mem_read(u.sym["poly_modes"], 1)[0] == 1
    # il modello del pattern (PatternSettings dell'interfaccia) ha la stessa copia: si salva col pattern
    app = u.long(v.t + 0x68)
    model = u.call(0x4001_9000, [app]) + 0x2C
    header = u.call(u.long(u.long(model) + 0x28), [model])
    assert bytes(u.uc.mem_read(header + 0x21, 7)) == rec
    frame = v.draw()
    v.turn("A", -4)                                     # POLY OFF: le schiave tornano tracce
    assert state(u)[1][:4] == [0, 1, 2, 3]
    assert v.draw() != frame


@needs_os()
def test_analog_tracks_have_no_poly_page():
    u = boot()
    t = u.tab("TRIG")                                   # pagine analogiche [1, 3]: nessuna terza pagina
    u.param(t, "A")
    L = u.long
    assert [L(x) for x in range(L(t + 0x7C), L(t + 0x80), 4)] == [1, 3]
    assert command(u, POLY, 0x43464731, 8, 1, 2) == 0   # nessun gruppo sulle tracce 9..12
    assert command(u, POLY, 0x43464731, 6, 1, 3) == 0   # ne' oltre il confine digitale/analogico


@needs_os()
def test_saved_analog_group_is_ignored():
    """Un pattern di Synfact con un gruppo analogico (PQ con flag 0x5C: 9x2): le tracce digitali restano."""
    u = boot()
    seq = u.long(SEQ_PTR)
    rec = bytearray(b"P\x5c" + bytes([0x60, 0, 0]))                   # 1x2 digitale + 9x2 analogico
    c = crc16(rec)
    u.uc.mem_write(seq + RECORD, bytes(rec) + bytes([c >> 8, c & 0xFF]))
    assert command(u, POLY, SYNC) == 1
    s, o = state(u)
    assert s[:2] == [3, 0] and s[8:] == [0] * 4 and o[8:] == [8, 9, 10, 11]


# ------------------------------------------------------------------ schiave e Sound
def fm4_page2(u):
    import screens
    src = u.tab("SRC")
    screens.syn_page(u, src, 1)
    return src


@needs_os()
def test_slaves_take_the_master_sound_with_xparams():
    """SY FM4 (pagine 2/3 e 3/3 nelle parole di xparams, lix 0x36..0x3D) e SAMPLER (machine 44 dai valori di menu
    45..48): il Sound delle schiave e' quello del master, intero, all'ingresso nel gruppo e dopo ogni modifica."""
    import screens
    u = boot(("poly", "sy-fm4", "sampler"), setup=screens.machine(4))
    group(u, 0, 3)
    assert [sound(u, t)[0xA2] for t in range(4)] == [4, 4, 4, sound(u, 3)[0xA2]] and sound(u, 3)[0xA2] != 4
    assert sound(u, 1) == sound(u, 0) == sound(u, 2)
    src = fm4_page2(u)
    u.set(src, "B", 90)                                 # LEV3 del master, una parola di xparams
    lix = [k for k in range(0x36, 0x3E) if sound(u, 0)[0x14 + 2 * k] == 90]
    assert lix, sound(u, 0)[0x14 + 0x6C:0x14 + 0x7C].hex()
    assert sound(u, 1) != sound(u, 0)                   # la copia la fa il tick dell'interfaccia
    tick(u)
    assert sound(u, 1) == sound(u, 0) == sound(u, 2)
    work = lambda t, k: struct.unpack(">H", u.uc.mem_read(0x8000_21CC + t * ROW + 2 * k, 2))[0]   # noqa: E731
    assert work(1, lix[0]) == work(2, lix[0]) == 90 << 8 # valori per traccia che xparams manda alla CPU #2
    # cambio di machine: rifiutato su una schiava, propagato dal master (SAMPLER WERP: menu 46)
    s1 = u.call(screens.TRACK_SOUND, [u.project + 304, 1])
    assert u.call(screens.SET_MACHINE, [s1, 0, 1, 1], count=400_000_000) & 0xFF == 0
    assert sound(u, 1)[0xA2] == 4
    s0 = u.call(screens.TRACK_SOUND, [u.project + 304, 0])
    assert u.call(screens.SET_MACHINE, [s0, 46, 0, 1], count=400_000_000) & 0xFF == 1
    tick(u)
    assert [sound(u, t)[0xA2] for t in range(3)] == [44, 44, 44]
    assert sound(u, 1) == sound(u, 0) == sound(u, 2)
    assert struct.unpack(">H", sound(u, 2)[0x14 + 2 * 0x1A:0x16 + 2 * 0x1A])[0] == 1 << 8      # tipo WERP


@needs_os()
def test_slave_view_is_locked():
    u = boot()
    group(u, 0, 2)
    v = Trig(u)
    model = u.long(v.t + 0x74)
    track = u.call(0x4001_FF74, [model])
    assert track == 0
    normal = v.draw()
    # la vista sulla schiava: la traccia della vista e' l'indice (+8) dell'oggetto che il modello rende (vt+40)
    obj = u.call(u.long(u.long(model) + 40), [model])
    u.put(obj + 8, ">I", 1)
    assert u.call(0x4001_FF74, [model]) == 1
    slave = v.draw()
    assert slave != normal
    # TRACK IN / SLAVE MODE al posto dei parametri: la parte destra dello schermo e' testo su fondo pulito
    v.ids(0)
    before = u.raw(v.t, "B")
    v.turn("B", 8)                                      # encoder bloccato dalla guardia (PAGE_GUARD)
    assert u.raw(v.t, "B") == before


# ------------------------------------------------------------------ tastiera e MIDI
def live(u, track, note, on, origin):
    """Nota dal costruttore vero (0x40119848, fino all'evento completo), poi l'instradamento di POLY con il
    chiamante della tastiera sulla pila (KEY_PRESS / KEY_RELEASE), come sul dispositivo."""
    from unicorn.m68k_const import UC_M68K_REG_A3, UC_M68K_REG_A7, UC_M68K_REG_SR
    import screens
    u.uc.mem_write(WORK, struct.pack(">15I", track, note, 100, on, *([0] * 11)))
    sp = screens.STACK - 8
    u.uc.mem_write(sp, struct.pack(">2I", screens.RET, WORK))
    u.uc.reg_write(UC_M68K_REG_SR, 0x2700)
    u.uc.reg_write(UC_M68K_REG_A7, sp)
    u.uc.emu_start(LIVE_CREATE, LIVE_CREATED, count=100_000)
    node = u.uc.reg_read(UC_M68K_REG_A3)
    ev = bytearray(u.uc.mem_read(node, 80))
    w = struct.unpack(">20I", ev)
    assert w[2] == track and w[3] == 2 and w[6] == note and w[10] == 0
    struct.pack_into(">I", ev, 0, 1)                    # evento prestato: POLY non lo libera nel pool
    u.uc.mem_write(WORK + 0x100, bytes(ev))
    u.uc.mem_write(screens.STACK, bytes(0x200))
    u.put(screens.STACK + 0x100, ">I", origin)
    consumed = u.call(u.sym["poly_preview_locked"], [WORK + 0x100])
    w = struct.unpack(">20I", u.uc.mem_read(WORK + 0x100, 80))
    assert consumed or w[2] == track or w[18] == w[2]       # una voce spostata: traccia e destinazione
    return None if consumed else w[2]


@needs_os()
@pytest.mark.parametrize("voices", [2, 3, 4])
def test_keyboard_and_midi_allocate_one_voice_per_key(voices):
    u = boot()
    group(u, 0, voices, mode=1)
    for origin, release in ((KEY_PRESS, KEY_RELEASE), (0x4010_55CC, 0x4010_5488)):   # tastiera, MIDI
        # la stessa nota ripetuta ruota le voci
        got = []
        for _ in range(voices * 2):
            got.append(live(u, 0, 60, 1, origin))
            assert live(u, 0, 60, 2, release) == got[-1]
        assert got == [(got[0] + i) % voices for i in range(2 * voices)], got
        # tasti tenuti: una voce ciascuno, poi il piu' vecchio rubato; il suo rilascio e' assorbito
        notes = list(range(48, 48 + voices))
        held = [live(u, 0, n, 1, origin) for n in notes]
        assert sorted(held) == list(range(voices))
        stolen = live(u, 0, 72, 1, origin)
        assert stolen == held[0]
        assert live(u, 0, notes[0], 2, release) is None
        assert live(u, 0, 72, 2, release) == stolen
        for n, t in zip(notes[1:], held[1:]):
            assert live(u, 0, n, 2, release) == t
    # una schiava suona solo dal master
    assert live(u, 1, 60, 1, KEY_PRESS) is None


POOL = 0x444D_F440                                   # testa della lista libera degli eventi nativi (1.41 0x444DE440)


def free_list(u, n):
    """L'avvio dell'emulatore non riempie il pool degli eventi (80 B, prossimo a +76): n eventi nel buffer dei test."""
    base = WORK + 0x2000
    for i in range(n):
        u.uc.mem_write(base + 80 * i, bytes(76) + struct.pack(">I", base + 80 * (i + 1) if i + 1 < n else 0))
    u.put(POOL, ">I", base)


@needs_os()
def test_chord_from_trig_lanes():
    """Trig del sequencer: NOTE sul master, NOT2..NOT4 (intervalli attorno a 64, 64 = spento) sulle schiave."""
    u = boot()
    group(u, 0, 4)
    seq = u.long(SEQ_PTR)
    step = 5
    for i, iv in ((1, 64 + 4), (2, 64), (3, 255)):      # passo: +4, spento, eredita il default
        u.uc.mem_write(seq + 0x2C0 + i * 0x40 + step, bytes([iv]))
    u.uc.mem_write(seq + 0x3C5 + 3, bytes([64 + 7]))    # default di NOT4: +7
    free_list(u, 8)
    src = WORK + 0x400
    u.uc.mem_write(src, struct.pack(">20I", 1, 1, 0, 1, 0, 0, 60, *([0] * 13)))
    count = u.call(u.sym["poly_prepare"], [src, seq, step, 4, WORK + 0x500])
    out = struct.unpack(">4I", u.uc.mem_read(WORK + 0x500, 16))
    got = [(u.long(e + 8), u.long(e + 24)) for e in out[:count]]
    for e in out[:count]:
        u.call(EVENT_FREE, [e])
    assert got == [(0, 60), (1, 64), (3, 67)], got


# ------------------------------------------------------------------ pubblicazione M.LFO
def topologies():
    """Ogni topologia digitale (Synfact: 517 con PLAY): gruppi di 2..4 tracce contigue in 0..7, che non si sovrappongono."""
    def rec(t):
        if t >= 8:
            yield []
            return
        yield from rec(t + 1)
        for w in (2, 3, 4):
            if t + w <= 8:
                for rest in rec(t + w):
                    yield [(t, w)] + rest
    return list(rec(0))                                 # anche nessun gruppo


def oracle(work, groups, modes):
    out = bytearray(work)
    for (m, w) in groups:
        if modes[m]:                                    # PLAY POLY: le voci tengono la propria uscita
            continue
        for t in range(m + 1, m + w):
            out[2 * t:2 * t + 2] = work[2 * m:2 * m + 2]
            out[0x1C + t * ROW:0x1C + (t + 1) * ROW] = work[0x1C + m * ROW:0x1C + (m + 1) * ROW]
            a, b = 0x754 + t * 124, 0x754 + m * 124
            out[a:a + 101] = work[b:b + 101]           # 101..103 e 123 restano (riempimento)
            out[a + 104:a + 123] = work[b + 104:b + 123]
    return bytes(out)


@needs_os()
def test_publication_matches_the_oracle_for_every_topology():
    u = boot()
    seq = u.long(SEQ_PTR)
    rnd = random.Random(7)
    size = 0x754 + 13 * 124
    cases = 0
    for groups in topologies():
        for play in itertools.product((0, 1), repeat=len(groups)):
            states = [0] * 12
            modes = [0] * 8
            for (m, w), p in zip(groups, play):
                states[m] = w + 1
                modes[m] = p
            u.uc.mem_write(u.sym["poly_next_modes"], bytes(modes))
            u.uc.mem_write(WORK + 0x800, bytes(states))
            assert u.call(u.sym["poly_commit"], [seq, WORK + 0x800]) == 1
            work = bytes(rnd.randrange(256) for _ in range(size))
            u.uc.mem_write(WORK + 0x1000, work)
            u.put(WORK + 0x900, ">I", WORK + 0x1000)
            assert u.call(u.sym["poly_native"], [3, WORK + 0x900, WORK + 0x904]) == 0   # notifica, non consuma
            got = bytes(u.uc.mem_read(WORK + 0x1000, size))
            assert got == oracle(work, groups, modes), (groups, play)
            shared = any(not p and w > 1 for (_, w), p in zip(groups, play))
            assert u.uc.mem_read(u.sym["core_native_interest"] + 3, 1)[0] == int(shared)
            cases += 1
    print("topologie x PLAY:", cases)
    assert cases == 517


# ------------------------------------------------------------------ interrupt audio
def isr_run(mods, uses=(), groups=(), setup=None, blocks=6):
    import isr
    m = isr.Isr(mods, uses=uses, setup=setup)
    m.ui.call(m.ui.sym["sfcore_bind"])
    for g in groups:
        group(m.ui, *g)
    m.scene("max")
    st = m.run()
    m.fast(blocks)
    return m, st


def sram(m):
    return bytes(m.uc.mem_read(0x8000_0000, 0x1_0000))


USES = sorted(SPEC["uses"])


@needs_os()
def test_interrupt_with_poly_off_is_the_same():
    s, a = isr_run(["sfcore"], USES)
    m, b = isr_run(["poly"])
    assert sram(s) == sram(m)
    print("istruzioni per blocco: sfcore", a.n, "POLY spento", b.n)
    assert b.n - a.n <= 60, (a.n, b.n)                  # render_in: poly_frame, il controllo rapido del record


@needs_os()
def test_interrupt_with_groups():
    """M.LFO: le schiave ricevono l'uscita del master (pubblicazione); POLY: nessun lavoro in piu' per blocco."""
    import isr
    _, off = isr_run(["poly"])
    m, mlfo = isr_run(["poly"], groups=[(0, 4, 0)])
    rows = [bytes(m.uc.mem_read(isr.SMOOTH_OUT + 0x1C + t * ROW, ROW)) for t in range(5)]
    assert rows[1] == rows[2] == rows[3] == rows[0]
    _, poly = isr_run(["poly"], groups=[(0, 4, 1)])
    print("istruzioni per blocco: spento", off.n, "M.LFO 1x4", mlfo.n, "POLY 1x4", poly.n)
    assert mlfo.n - off.n <= 520 and abs(poly.n - off.n) <= 40      # M.LFO: Synfact ~507, qui 482 (2026-11-07)


# ------------------------------------------------------------------ PatternSettings 0x21..0x27
@needs_os()
def test_pattern_settings_bytes_are_free_on_1_42():
    """Sulla 1.42 nessun codice stock legge o scrive i 7 byte del record (copia del sequencer): avvio di un
    progetto nuovo, interrupt audio, pagine. Solo POLY (area mod) e le copie dell'intestazione."""
    import isr
    from unicorn import UC_HOOK_MEM_READ, UC_HOOK_MEM_WRITE
    from unicorn.m68k_const import UC_M68K_REG_PC
    import modarea_layout as MA
    m = isr.Isr(["poly"])
    m.ui.call(m.ui.sym["sfcore_bind"])
    seq = m.ui.long(SEQ_PTR)
    seen = set()

    def hit(uc, acc, a, n, v, d):
        pc = uc.reg_read(UC_M68K_REG_PC)
        if not MA.RAM <= pc < MA.RAM + MA.SIZE:
            seen.add(pc)
    m.uc.hook_add(UC_HOOK_MEM_READ | UC_HOOK_MEM_WRITE, hit, begin=seq + RECORD, end=seq + RECORD + 6)
    m.scene("max")
    m.run()
    v = Trig(m.ui)
    v.turn("A", 4)
    m.run()
    print("accessi stock:", [hex(p) for p in sorted(seen)])
    assert not seen
