"""Schermate vere dell'interfaccia (CPU #1, OS 1.42) disegnate dal codice dell'OS in Unicorn.

Niente RTOS ne' periferiche: si esegue solo cio' che serve a disegnare una pagina di parametri.

    ui = UI(["readable-values"])     # OS stock + patch delle mod (con le dipendenze)
    tab = ui.tab("FLTR")             # una delle viste a schede di ParameterPagesView
    ui.turn(tab, "A", +5)            # encoder come dalla tastiera: valore cambiato dall'OS
    fb = ui.draw(tab)                # 1024 byte, orientamento dello schermo (vedi frame_bytes)

Avvio: copia dei dati in SRAM (0x4000045C), i 136 costruttori statici (0x40339510), init del
sequencer (0x4008C5D8, con lunghezza e scala del pattern 0 gia' a 16 passi: senza il progetto
caricato dal +Drive dividerebbe per zero), dati del progetto (vt+36 del progetto: li assegna e
collega i kit ai modelli dei parametri; sul device li fornisce il caricamento dal +Drive),
Project::initializeNewProject(-1) (0x4001D16A), poi la vista dei parametri (costruttore 0x400351FA, 0x288 B dall'heap dell'OS). Ogni scheda e' una View:
+16 draw(view, bitmap), +68 consumeEncoderEvent(view, ev); +144 pagina corrente del tab.

Bitmap (0x400F72BE): +4 larghezza, +8 altezza, +12 parole per colonna, +16 dati. In memoria
y = 0 e' il fondo dello schermo (pannello montato capovolto): frame_bytes raddrizza.
"""

from __future__ import annotations

import base64
import collections
import json
import struct
import sys
from pathlib import Path

from unicorn import UC_ARCH_M68K, UC_HOOK_BLOCK, UC_HOOK_MEM_UNMAPPED, UC_MODE_BIG_ENDIAN, Uc, UcError
from unicorn.m68k_const import UC_CPU_M68K_ANY, UC_M68K_REG_A7, UC_M68K_REG_D0, UC_M68K_REG_PC, UC_M68K_REG_SR

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "tools" / "unpack"))
import eft  # noqa: E402

SYX = REPO / "firmware" / "Syntakt_OS1.42.syx"
LOAD = 0x4000_0400
W, H = 128, 64

# --- OS 1.42
SRAM_COPY = 0x4000_045C
CTOR_COUNT, CTOR_TABLE = 0x4033_950C, 0x4033_9510
SEQ_INIT = 0x4008_C5D8
PATTERN0 = 0x40A3_9B34                          # pattern 0: +0x21374 lunghezza, +0x2137A scala
PROJECT = 0x4016_E9C8                           # singleton del progetto
PROJECT_DATA = 0x4600_0000                      # dati del progetto (pattern, kit): ~18 MB, sopra il BSS
NEW_PROJECT = 0x4001_D16A                       # Project::initializeNewProject(this, int)
MALLOC = 0x4010_394C
PAGES_VIEW, PAGES_VIEW_SIZE = 0x4003_51FA, 0x288
BITMAP_CTOR, BITMAP_CLIP = 0x400F_72BE, 0x405D_4618
PARAM_VALUE = 0x4003_9160                       # ParameterPageView::getParamValueToShow(this, id, bool *)
SLOT = 180                                      # vista: 20 B per encoder; +0 tempo del valore in evidenza,
                                                # +16 attesa prima che gli scatti contino (ritardo anti-tocco)

# schede della vista dei parametri: offset del shared_ptr nell'oggetto -> nome
TABS = {
    "TRIG": 248, "SRC": 256, "FLTR": 264, "AMP": 272, "DELAY": 288, "REVERB": 296, "MIX": 304,
    "RETRIG": 312,
    "A.TRIG": 320, "A.SRC": 328, "A.FLTR": 336, "A.AMP": 344,
    "FX.TRIG": 464, "FX.SYN": 472, "FX.FLTR": 480, "FX.AMP": 488,
}
ENC = {k: i + 1 for i, k in enumerate("ABCDEFGH")}

STACK, RET = 0x4FF0_0000, 0x4FF0_F000
BM, FB, EV = 0x4FE0_0000, 0x4FE0_1000, 0x4FE0_2000


def section3() -> bytes:
    raw = REPO / "unpacked" / SYX.stem / "section_3_MAIN_OS.bin"
    if not raw.exists():
        raw = eft.unpack(SYX, REPO / "unpacked" / SYX.stem, ids=[3])[3]
    return raw.read_bytes()


def with_deps(mods: list[str]) -> list[str]:
    """Mod e dipendenze ("requires"), dipendenze prima; modarea sempre (prenota il blocco dell'heap)."""
    out: list[str] = []

    def add(name: str) -> None:
        if name in out:
            return
        for dep in json.loads((REPO / "mods" / name / "patch.json").read_text(encoding="utf-8")).get("requires", []):
            add(dep)
        out.append(name)
    add("modarea")
    for m in mods:
        add(m)
    return out


class EmuError(RuntimeError):
    pass


class UI:
    def __init__(self, mods: list[str] = (), sec3: bytes | None = None, setup=None):
        """setup(ui): chiamata prima di costruire la vista (impostazioni lette dal costruttore)."""
        self.mods = with_deps(list(mods))
        self.setup = setup
        uc = self.uc = Uc(UC_ARCH_M68K, UC_MODE_BIG_ENDIAN, cpu=UC_CPU_M68K_ANY)
        for base, size in ((0x0, 0x2_0000), (0x1000_0000, 0x2_0000), (0x4000_0000, 0x1000_0000),
                           (0x8000_0000, 0x1_0000), (0xEC00_0000, 0x10_0000), (0xFC00_0000, 0x10_0000)):
            uc.mem_map(base, size)
        uc.mem_write(LOAD, sec3 or section3())
        self.sym: dict[str, int] = {}
        for m in self.mods:
            spec = json.loads((REPO / "mods" / m / "patch.json").read_text(encoding="utf-8"))
            for p in spec["patches"]:
                uc.mem_write(int(p["ram"], 16) if p.get("append") else int(p["addr"], 16), bytes.fromhex(p["hex"]))
            self.sym.update({k: int(v, 16) for k, v in spec.get("symbols", {}).items()})
        uc.mem_write(RET, b"\x4e\x75")
        self.ring: collections.deque[int] = collections.deque(maxlen=32)
        uc.hook_add(UC_HOOK_BLOCK, lambda _uc, a, _s, _d: self.ring.append(a))
        uc.hook_add(UC_HOOK_MEM_UNMAPPED, self._unmapped)
        self._boot()

    def _unmapped(self, uc, _acc, addr, _size, _val, _d):
        raise_at = uc.reg_read(UC_M68K_REG_PC)
        self.unmapped = (raise_at, addr)
        return False

    # ------------------------------------------------------------------ chiamate
    def call(self, fn: int, args=(), count: int = 50_000_000) -> int:
        uc = self.uc
        sp = STACK - 4 * (len(args) + 1)
        uc.mem_write(sp, struct.pack(f">{len(args) + 1}I", RET, *[a & 0xFFFF_FFFF for a in args]))
        uc.reg_write(UC_M68K_REG_SR, 0x2700)            # prima SR, poi A7
        uc.reg_write(UC_M68K_REG_A7, sp)
        try:
            uc.emu_start(fn, RET, count=count)
        except UcError as e:
            raise EmuError(f"{fn:#x}: {e} at {uc.reg_read(UC_M68K_REG_PC):#x}; "
                           + " ".join(hex(a) for a in self.ring)) from None
        if uc.reg_read(UC_M68K_REG_PC) != RET:
            raise EmuError(f"{fn:#x}: not finished after {count} instructions")
        return uc.reg_read(UC_M68K_REG_D0) & 0xFFFF_FFFF

    def long(self, a: int) -> int:
        return struct.unpack(">I", self.uc.mem_read(a, 4))[0]

    def put(self, a: int, fmt: str, *v) -> None:
        self.uc.mem_write(a, struct.pack(fmt, *v))

    # ------------------------------------------------------------------ avvio
    def _boot(self) -> None:
        self.call(SRAM_COPY)
        n = self.long(CTOR_COUNT)
        for f in struct.unpack(f">{n}I", self.uc.mem_read(CTOR_TABLE, 4 * n)):
            self.call(f)
        self.put(PATTERN0 + 0x21374, ">H", 16)
        self.put(PATTERN0 + 0x2137A, ">B", 3)
        self.call(SEQ_INIT)
        self.project = self.call(PROJECT)
        self.call(self.long(self.long(self.project) + 36), [self.project, PROJECT_DATA], count=200_000_000)
        self.call(NEW_PROJECT, [self.project, 0xFFFF_FFFF], count=400_000_000)
        if self.setup:
            self.setup(self)
        self.view = self.call(MALLOC, [PAGES_VIEW_SIZE])
        self.call(PAGES_VIEW, [self.view], count=200_000_000)

    # ------------------------------------------------------------------ viste
    def tab(self, name: str) -> int:
        return self.long(self.view + TABS[name])

    def tabs(self) -> set[int]:
        return {self.tab(n) for n in TABS}

    def page(self, tab: int, index: int) -> None:
        """Pagina del tab (come il tasto della pagina che le scorre)."""
        n = (self.long(tab + 128) - self.long(tab + 124)) // 4
        assert 0 <= index < n, (index, n)
        self.put(tab + 144, ">I", index)

    def turn(self, tab: int, enc: str, delta: int, fine: bool = False) -> None:
        """Encoder A..H girato di delta scatti: EncoderEvent +12 encoder (1..8), +16 scatti, +20 fine."""
        st = tab + SLOT + 20 * (ENC[enc] - 1)
        self.put(st + 8, ">i", 0)                       # niente accelerazione dagli scatti precedenti
        self.put(st + 16, ">i", 0)                      # ne' attesa anti-tocco
        self.uc.mem_write(EV, bytes(32))
        self.put(EV + 12, ">iiB", ENC[enc], delta, int(fine))
        self.call(self.long(self.long(tab) + 68), [tab, EV])

    def param(self, tab: int, enc: str) -> int:
        """Id logico sotto l'encoder (vt+188), 0 = casella vuota."""
        return self.call(self.long(self.long(tab) + 188), [tab, ENC[enc] - 1])

    def raw(self, tab: int, enc: str) -> int:
        """Valore mostrato (0..0x7F00) del parametro sotto l'encoder."""
        return self.call(PARAM_VALUE, [tab, self.param(tab, enc), EV + 28])

    def value(self, tab: int, enc: str) -> int:
        return self.raw(tab, enc) >> 8

    def set(self, tab: int, enc: str, v: int) -> None:
        """Porta il parametro a v (0..127) girando l'encoder. Di norma un'unita' vuole qualche scatto;
        FREQ avanza di 1/256 a scatto: se si avanza meno di 1/4 di unita' gli scatti raddoppiano, e
        tornano singoli quando si supera il bersaglio."""
        want, d, moved = v << 8, 1, 0
        for _ in range(2000):
            cur = self.raw(tab, enc)
            if cur == want or (cur >> 8 == v and moved >= 0x100):   # a passi grossi (RAT): l'unita' basta
                return
            sign = 1 if want > cur else -1
            self.turn(tab, enc, sign * d)
            new = self.raw(tab, enc)
            moved = abs(new - cur)
            if (want - new) * sign < 0:
                d = 1
            elif abs(new - cur) < 0x40:                 # fermo o a frazioni di unita'
                d = min(512, d * 2)
        raise EmuError(f"encoder {enc}: {self.raw(tab, enc):#x}, wanted {want:#x}")

    def show_value(self, tab: int, enc: str | None) -> None:
        """Valore in evidenza (come dopo un giro di encoder) solo per enc; None: nessuno."""
        for k, i in ENC.items():
            self.put(tab + SLOT + 20 * (i - 1), ">i", 40 if k == enc else 0)

    def new_view(self, ctor: int, size: int) -> int:
        """View costruita come fa l'OS: new(size) dall'heap, poi il costruttore (this)."""
        v = self.call(MALLOC, [size])
        self.call(ctor, [v], count=200_000_000)
        return v

    def key(self, view: int, code: int, down: bool = True) -> None:
        """KeyEvent +12 codice (tasti trig 1..16 = 24..39), +16 flag (bit 0 = premuto) -> vt+8."""
        self.uc.mem_write(EV, bytes(32))
        self.put(EV + 12, ">ii", code, int(down))
        self.call(self.long(self.long(view) + 8), [view, EV])

    def press(self, view: int, trig: int) -> None:
        self.key(view, 23 + trig, True)
        self.key(view, 23 + trig, False)

    def paint(self, fn: int, args=()) -> bytes:
        """fn(*args, bitmap) su una bitmap vuota (animazioni d'avvio: fn(frame, totale, bitmap))."""
        self.uc.mem_write(FB, bytes(W * H // 8))
        self.call(BITMAP_CTOR, [BM, W, H, FB, BITMAP_CLIP])
        self.call(fn, [*args, BM])
        return frame_bytes(bytes(self.uc.mem_read(FB, W * H // 8)))

    def draw(self, view: int) -> bytes:
        """View +16: draw(view, bitmap)."""
        return self.paint(self.long(self.long(view) + 16), [view])


def frame_bytes(raw: bytes) -> bytes:
    """Bitmap dell'OS (colonne di 2 parole, MSB = y basso dello schermo) -> righe dall'alto,
    16 byte per riga, bit 7 = pixel a sinistra."""
    out = bytearray(W * H // 8)
    for x in range(W):
        col = int.from_bytes(raw[x * 8:x * 8 + 8], "big")        # bit 63 = y 0 in memoria
        for y in range(H):
            if col >> (63 - y) & 1:
                r = H - 1 - y
                out[r * 16 + x // 8] |= 0x80 >> (x % 8)
    return bytes(out)


def pixels(frame: bytes) -> list[list[int]]:
    return [[frame[r * 16 + x // 8] >> (7 - x % 8) & 1 for x in range(W)] for r in range(H)]


def png(frame: bytes, path: Path, scale: int = 4) -> None:
    from PIL import Image
    img = Image.new("L", (W, H))
    img.putdata([255 if v else 0 for row in pixels(frame) for v in row])
    path.parent.mkdir(parents=True, exist_ok=True)
    img.resize((W * scale, H * scale), Image.NEAREST).save(path)




# ====================================================================== scene per il sito
# Una scena = id stabile "<mod>/<nome>" (usato dal sito e dai marcatori della documentazione),
# didascalia, fotogrammi. Le scene di una mod girano nella stessa macchina, in ordine (lo stato
# passa dall'una all'altra). Gli encoder si girano con UI.set(): il valore che si vede e' quello che
# l'OS ha scritto nel kit e riletto per il disegno.

FPS = 8
EXT_IN_MONO = 0x8000_3146                       # EXTERNAL IN: 0 = mono (copia del motore)
SETTINGS = PROJECT_DATA + 0x116_4778            # impostazioni del progetto nei dati del progetto
SETTINGS_TO_ENGINE = 0x400A_33FE
ROUTING_VIEW, ROUTING_SIZE = 0x4004_BE26, 0x74  # FUNC+FX: ROUTING, tracce + effetti


class Recorder:
    def __init__(self, ui: UI):
        self.ui, self.frames = ui, []

    def hold(self, view: int, n: int = 1, show: str | None = None) -> None:
        if show is not None or view in self.ui.tabs():
            self.ui.show_value(view, show)
        self.frames += [self.ui.draw(view)] * n

    def sweep(self, tab: int, enc: str, values, n: int = 1) -> None:
        """Gira enc passando per values, n fotogrammi per valore, valore in evidenza."""
        for v in values:
            self.ui.set(tab, enc, v)
            self.hold(tab, n, show=enc)

    def preset(self, tab: int, values: dict[str, int]) -> None:
        for enc, v in values.items():
            self.ui.set(tab, enc, v)


def steps(a: int, b: int, n: int) -> list[int]:
    return [round(a + (b - a) * i / (n - 1)) for i in range(n)]


# ---------------------------------------------------------------------- readable-values
def rv_filter(r: Recorder) -> None:
    flt = r.ui.tab("FLTR")                                  # traccia 1 (digitale)
    r.preset(flt, {"A": 6, "B": 64, "C": 70, "D": 48, "E": 92, "F": 40, "H": 90})
    r.hold(flt, 6)
    r.sweep(flt, "E", steps(92, 120, 8) + steps(120, 70, 10))
    r.hold(flt, 6, show="E")
    r.sweep(flt, "A", steps(6, 40, 8))
    r.hold(flt, 6, show="A")
    r.sweep(flt, "B", steps(64, 100, 7))
    r.hold(flt, 6, show="B")
    r.sweep(flt, "C", steps(70, 30, 7))
    r.hold(flt, 8, show="C")


def rv_amp(r: Recorder) -> None:
    amp = r.ui.tab("AMP")
    r.preset(amp, {"A": 2, "B": 30, "C": 70, "E": 40, "F": 60, "H": 100})
    r.hold(amp, 6)
    r.sweep(amp, "C", steps(70, 110, 6))
    r.hold(amp, 6, show="C")
    r.sweep(amp, "E", steps(40, 80, 6))
    r.hold(amp, 6, show="E")
    r.sweep(amp, "H", steps(100, 70, 6))
    r.hold(amp, 8, show="H")


def rv_delay(r: Recorder) -> None:
    dly = r.ui.tab("DELAY")                                 # FX track: TIME X WID FDBK / HPF LPF REV VOL
    r.preset(dly, {"A": 32, "C": 100, "D": 60, "E": 10, "F": 110, "G": 40, "H": 90})
    r.hold(dly, 6)
    r.sweep(dly, "E", steps(10, 60, 6))
    r.hold(dly, 6, show="E")
    r.sweep(dly, "F", steps(110, 70, 6))
    r.hold(dly, 6, show="F")
    r.sweep(dly, "H", steps(90, 120, 5))
    r.hold(dly, 8, show="H")


# ---------------------------------------------------------------------- master-comp
def mc_page(r: Recorder) -> None:
    syn = r.ui.tab("FX.SYN")
    r.preset(syn, {"A": 76, "B": 20, "C": 64, "D": 32, "E": 63})
    r.hold(syn, 6)
    r.sweep(syn, "A", steps(76, 90, 5))
    r.hold(syn, 4, show="A")
    r.sweep(syn, "B", steps(20, 40, 5))
    r.hold(syn, 4, show="B")
    r.sweep(syn, "E", [79, 95, 63], 4)                      # RAT 6:1, 8:1, 4:1
    r.sweep(syn, "D", steps(32, 50, 5))
    r.hold(syn, 6, show="D")


def mc_meter(r: Recorder) -> None:
    syn = r.ui.tab("FX.SYN")
    meter = r.ui.sym["k_meter"]                             # riduzione: 2^23 unita' per dB
    db = 0.0
    for k in range(48):                                     # un colpo ogni mezzo secondo, poi il rilascio
        db = (9.0, 5.0, 12.0, 6.0)[(k // 4) % 4] if k % 4 == 0 else max(0.0, db - 2.5)
        r.ui.put(meter, ">i", int(db * 2 ** 23))
        r.hold(syn, 1, show="F" if k < 16 else None)


# ---------------------------------------------------------------------- fx3
def fx3_page(r: Recorder) -> None:
    ui = r.ui
    rev = ui.tab("REVERB")                                  # FX track, tab REVERB: pagina 2 = FX3
    ui.page(rev, 1)
    r.preset(rev, {"A": 0, "G": 40, "H": 70})
    r.hold(rev, 6)
    r.sweep(rev, "B", steps(60, 90, 6))
    r.hold(rev, 5, show="B")
    for t in (1, 2, 3):
        ui.set(rev, "A", t)                                 # TYPE: nomi, icone e testi cambiano
        r.hold(rev, 6, show="A")
        r.hold(rev, 4)
        if t == 2:
            r.sweep(rev, "D", steps(64, 30, 5))
            r.hold(rev, 4, show="D")
        if t == 3:
            r.sweep(rev, "C", steps(0, 90, 6))
            r.hold(rev, 5, show="C")
    ui.set(rev, "A", 0)
    r.hold(rev, 8, show="A")


def fx3_amp(r: Recorder) -> None:
    amp = r.ui.tab("AMP")                                   # traccia 1: SND3 accanto a DEL e REV
    r.preset(amp, {"B": 30, "C": 70, "E": 40, "F": 60, "H": 100})
    r.hold(amp, 6)
    r.sweep(amp, "G", steps(0, 90, 8))
    r.hold(amp, 8, show="G")


def fx3_routing(r: Recorder) -> None:
    ui = r.ui
    v = ui.new_view(ROUTING_VIEW, ROUTING_SIZE)
    r.hold(v, 8)
    for trig in (13, 1, 2, 13, 13):                         # 13 = ritorno di FX3 nella FX track
        ui.press(v, trig)
        r.hold(v, 6)


# ---------------------------------------------------------------------- perf-fx
def pf_moda(r: Recorder) -> None:
    ui = r.ui
    tab = ui.tab("RETRIG")                                  # FUNC+15: pagina Mod A dei modificatori
    ui.page(tab, 2)
    ui.put(tab + 424, ">i", 2)                              # modificatore attivo: Mod A
    r.preset(tab, {"E": 1, "F": 2, "G": 8, "H": 11})        # 1/16 1/8 R1/4 HALF
    r.hold(tab, 8)
    r.sweep(tab, "E", range(2, 11), 3)
    r.sweep(tab, "E", [1])
    r.hold(tab, 6, show="E")
    r.hold(tab, 6)


def pf_retrig(r: Recorder) -> None:
    ui = r.ui
    tab = ui.tab("RETRIG")                                  # FUNC+13: Retrig, QNT in D
    ui.page(tab, 0)
    ui.put(tab + 424, ">i", 0)
    r.hold(tab, 8)
    r.sweep(tab, "D", [1], 10)                              # QNT ON
    r.hold(tab, 4)
    r.sweep(tab, "E", [2, 3, 4], 4)
    r.hold(tab, 6)


# ---------------------------------------------------------------------- dual-mono
def dm_inr(r: Recorder) -> None:
    ui = r.ui
    mix = ui.tab("MIX")                                     # EXTERNAL IN = mono: 4 pagine
    ui.page(mix, 2)                                         # External Mixer = IN L
    r.preset(mix, {"A": 100, "E": 50, "F": 40, "G": 80})
    r.hold(mix, 10)
    ui.page(mix, 3)                                         # IN R, livello e mandate proprie
    r.preset(mix, {"A": 72, "E": 0, "F": 70, "G": 40})
    r.hold(mix, 8)
    r.sweep(mix, "A", steps(72, 110, 5))
    r.hold(mix, 5, show="A")
    r.sweep(mix, "E", steps(0, 60, 5))
    r.hold(mix, 5, show="E")
    r.sweep(mix, "G", steps(40, 90, 5))
    r.hold(mix, 8, show="G")


def mono(ui: UI) -> None:
    """SETTINGS > AUDIO ROUTING > EXTERNAL IN = mono: impostazione del progetto (+256) passata al
    motore come fa l'OS (0x400A33FE scrive 0x80003146); nomi IN L / IN R come al primo blocco audio."""
    ui.put(SETTINGS + 256, ">i", 0)
    ui.call(SETTINGS_TO_ENGINE, [SETTINGS])
    assert ui.uc.mem_read(EXT_IN_MONO, 1)[0] == 0
    ui.call(ui.sym["ui_mono"])


# ---------------------------------------------------------------------- splash
def sp_boot(r: Recorder) -> None:
    """Solo lo splash della mod (l'intro ufficiale che lo precede e' grafica Elektron: non la mostriamo)."""
    ui = r.ui
    spec = json.loads((REPO / "mods" / "splash" / "patch.json").read_text(encoding="utf-8"))
    entry = int(spec["patches"][1]["hex"], 16)
    _, _, splash, sframes = struct.unpack(">4I", ui.uc.mem_read(entry, 16))
    r.frames += [bytes(1024)] * 4                           # fine dell'intro: nero
    for i in range(0, sframes, 3):
        r.frames.append(ui.paint(splash, [i, sframes]))
    r.frames += [r.frames[-1]] * 8


# mod del sito -> (mod applicate, impostazioni prima della vista, [(scena, didascalia, funzione)])
SCENES = {
    "readable-values": (["readable-values"], None, [
        ("filter", "FILTER page with times and frequencies", rv_filter),
        ("amp", "AMP page with times and levels", rv_amp),
        ("delay", "DELAY page in Hz and dB", rv_delay)]),
    "master-comp": (["master-comp"], None, [
        ("page", "Compressor on the FX track SYN page", mc_page),
        ("meter", "Gain-reduction meter following the hits", mc_meter)]),
    "fx3": (["fx3"], None, [
        ("page", "FX3 page cycling through the four types", fx3_page),
        ("amp", "SND3 send on the AMP page", fx3_amp),
        ("routing", "ROUTING screen, key 13 is FX3", fx3_routing)]),
    "perf-fx": (["perf-fx"], None, [
        ("moda", "Mod A page: one effect per key", pf_moda),
        ("retrig", "Retrig page with QNT", pf_retrig)]),
    "dual-mono": (["fx3", "dual-mono"], mono, [
        ("inr", "IN L and the new IN R page", dm_inr)]),
    "splash": (["splash"], None, [
        ("boot", "SyntHack logo after the official intro", sp_boot)]),
}


def render(mod: str, sec3: bytes | None = None) -> dict[str, list[bytes]]:
    """Scena -> fotogrammi (righe dall'alto, 16 byte per riga)."""
    mods, setup, scenes = SCENES[mod]
    r = Recorder(UI(mods, sec3, setup))
    out = {}
    for name, _caption, fn in scenes:
        r.frames = []
        fn(r)
        out[name] = r.frames
    return out


def encode(scenes: dict[str, list[bytes]], fps: int = FPS) -> dict:
    """JSON del sito: fotogrammi distinti in base64 (righe dall'alto, 16 byte per riga, bit 7 = pixel
    a sinistra) e, per scena, la sequenza come coppie [indice, ripetizioni]."""
    uniq: dict[bytes, int] = {}
    seqs: dict[str, list[list[int]]] = {}
    for name, frames in scenes.items():
        seq = seqs[name] = []
        for f in frames:
            i = uniq.setdefault(f, len(uniq))
            if seq and seq[-1][0] == i:
                seq[-1][1] += 1
            else:
                seq.append([i, 1])
    return {"fps": fps, "w": W, "h": H, "scenes": seqs, "frames": [base64.b64encode(f).decode() for f in uniq]}


FRAMES_DIR = REPO / "web-builder" / "src" / "previews" / "frames"


def dump(data: dict) -> str:
    """Testo del file: un fotogramma per riga (diff leggibili)."""
    scenes = ",\n".join(f'"{k}":{json.dumps(v, separators=(",", ":"))}' for k, v in data["scenes"].items())
    return (f'{{"fps":{data["fps"]},"w":{data["w"]},"h":{data["h"]},\n"scenes":{{\n{scenes}\n}},\n'
            + '"frames":[\n' + ",\n".join(f'"{f}"' for f in data["frames"]) + "\n]}\n")


def index() -> dict[str, str]:
    """Id delle scene -> didascalia (per il sito e per i marcatori <!-- @screen:id --> dei testi)."""
    return {f"{m}/{name}": caption for m, (_, _, scenes) in SCENES.items() for name, caption, _ in scenes}


def main(argv=None) -> None:
    import argparse
    ap = argparse.ArgumentParser(description="Schermate delle mod disegnate dal codice dell'OS (Unicorn).")
    ap.add_argument("mods", nargs="*", default=list(SCENES), help="mod da generare (default: tutte)")
    ap.add_argument("--png", type=Path, help="cartella per i PNG dei fotogrammi distinti (controllo a vista)")
    a = ap.parse_args(argv)
    sec3 = section3()
    FRAMES_DIR.mkdir(parents=True, exist_ok=True)
    (FRAMES_DIR / "index.json").write_text(json.dumps(index(), indent=1) + "\n", encoding="utf-8", newline="\n")
    for mod in a.mods:
        data = encode(render(mod, sec3))
        (FRAMES_DIR / f"{mod}.json").write_text(dump(data), encoding="utf-8", newline="\n")
        print(f"{mod}: " + ", ".join(f"{k} {sum(n for _, n in v)}" for k, v in data["scenes"].items())
              + f" frames, {len(data['frames'])} distinct")
        if a.png:
            for name, seq in data["scenes"].items():
                for i, _ in seq:
                    png(base64.b64decode(data["frames"][i]), a.png / mod / name / f"{i:03d}.png")


if __name__ == "__main__":
    main()
