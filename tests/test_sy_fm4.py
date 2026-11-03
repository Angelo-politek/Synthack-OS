"""SY FM4 (Rxuting, MIT) sull'OS 1.42: port dei siti, avvio della CPU #1, motore sulla CPU #2.

- Port: ogni sito della sezione 3 con indirizzi, riportato agli indirizzi della 1.40A, ha l'impronta del patcher
  originale (provato sulla macchina da Rxuting); i siti senza indirizzi hanno gli stessi byte.
- CPU #1: salvataggio, p-lock e copia della pagina 2/3 verso la CPU #2 sono in xparams (tests/test_xparams.py);
  qui i default di 2/3 per i suoni di un OS stock.
- CPU #2: la sezione 7 compressa della build vera, avvio a freddo; ALGO 0 suona come SY TONE stock, campione per
  campione; ALGO 1-11 suonano e sono diversi.
"""

import hashlib
import json
import math
import struct
import sys
from pathlib import Path

import pytest

pytest.importorskip("unicorn")

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "tests"), str(ROOT / "tools" / "emu"), str(ROOT / "tools" / "build"),
                str(ROOT / "tools" / "unpack")]
import build  # noqa: E402
import eft  # noqa: E402
import modarea_layout as M  # noqa: E402

STOCK = ROOT / "firmware" / "Syntakt_OS1.42.syx"
pytestmark = pytest.mark.skipif(not STOCK.exists(), reason="firmware stock assente")
SPEC = json.loads((ROOT / "mods" / "sy-fm4" / "patch.json").read_text(encoding="utf-8"))
SYM = {k: int(v, 16) for k, v in SPEC["symbols"].items()}
LOAD = 0x4000_0400
DESC = 0x4022_D83C                       # descrittori, 52 B per id
TO_140A = {0x4023_441C: 0x4022_067C, 0x4023_4344: 0x4022_05A4, 0x43BD_E73C: 0x43BC_65E4, 0x43BD_F44C: 0x43BC_72F4}
# (sito 1.42, lunghezza, impronta dei byte stock della 1.40A nel patcher di Rxuting: patch/s3patch.py)
RXUTING = [(0x400A_706A, 34, "05940b0d2349f1f1c2ab4128a080a7a1663c0ed93299b900b0c038eb396ea31b"),
           (0x400A_7452, 2, "52df7f2f1048dc2201a77314d0f8b6896e89a31c0d6f679874a9f29a4dea2bf3"),
           (0x400A_803E, 2, "cb0f6349d7f4b961d8b4c8deb6f4744d68bdc98d27283aefd7b40869c9d0c2fe"),
           (0x400A_6D32, 6, "3be507936205af3def3579799b294d7edfd234979554e6c0dd020b9b0d8f8740"),
           (0x400A_20AE, 6, "1d0f8d759721ca0afb32976fc47fd063ea80bed69b7aa8927c10146be4d173fa"),
           (0x400A_61B0, 6, "9afe6ac16a3c77f05bd62a80e1554027625cb4c1eda2dfd69e986eb36491a906"),
           (0x4025_38C7, 8, "d7e4479bceefa3f00a29e38e34dddd9bf3fe0f282248a4dfed4506266ba21ef5"),
           (0x4025_38CF, 5, "74e17376873aceed5a8c09e09452536cc08ca0f25cf379fc308b05c59bb3c16d")]


@pytest.fixture(scope="module")
def stock():
    t = ROOT / "unpacked" / STOCK.stem
    f = eft.unpack(STOCK, t, ids=[3, 7])
    return f[3].read_bytes(), f[7].read_bytes()


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    t = tmp_path_factory.mktemp("fm4")
    out = t / "o.syx"
    build.build(STOCK, [ROOT / "mods" / "sy-fm4"], out, log=lambda *_: None)
    f = eft.unpack(out, t / "u", ids=[3, 7])
    return f[3].read_bytes(), f[7].read_bytes()


def test_sites_are_the_ones_of_the_original_patcher(stock):
    sec3, _ = stock
    for addr, n, want in RXUTING:
        b = bytearray(sec3[addr - LOAD:addr - LOAD + n])
        for new, old in TO_140A.items():
            k = b.find(struct.pack(">I", new))
            while k >= 0:
                b[k:k + 4] = struct.pack(">I", old)
                k = b.find(struct.pack(">I", new), k + 1)
        assert hashlib.sha256(bytes(b)).hexdigest() == want, hex(addr)
    xp = json.loads((ROOT / "mods" / "xparams" / "patch.json").read_text(encoding="utf-8"))
    sites = {int(p["addr"], 16) for spec in (SPEC, xp) for p in spec["patches"] if not p.get("append")}
    assert {a for a, _, _ in RXUTING} <= sites                          # i siti di salvataggio e copia: in xparams


def test_page2_descriptors_replace_midi_track_cc_values(stock):
    sec3, _ = stock
    rows = [p for p in SPEC["patches"] if p["what"].startswith("descrittore ") and "2/2" in p["what"]]
    assert [int(p["addr"], 16) for p in rows] == [0x4022_D83C + 52 * i for i in range(254, 262)]
    for k, p in enumerate(rows):
        owner, lix, mn, mx, de, _r5, cc, nrpn, rid = struct.unpack(">9I", bytes.fromhex(p["hex"])[:36])
        assert (owner, lix, rid) == (0xFFFF_FFFF, 0x36 + k, 254 + k)
        assert (cc, nrpn) == (0xFFFF_FFFF, 0xFFFF_FFFF)                # niente MIDI sulla pagina 2/2
        assert mn <= de <= mx <= 0x7F00


def test_stock_sound_gets_page2_defaults(built):
    """Suono salvato da un OS stock (zeri negli indici 0x36..0x3d): xparams chiama fm4m_empty, registrato da
    fm4m_boot, che scrive i default della pagina 2/3 (ALGO 0 = SY TONE, DET al centro)."""
    import test_modarea as MA
    xp = {k: int(v, 16) for k, v in json.loads((ROOT / "mods" / "xparams" / "patch.json").read_text(
        encoding="utf-8"))["symbols"].items()}
    uc, _ = MA.boot(built[0])
    sound, storage = 0x47FF_0000, 0x47FF_1000
    uc.mem_write(sound, bytes(0x100))
    uc.mem_write(storage, bytes(0x100))
    MA.call(uc, xp["xp_load_params"], sound, storage)
    got = struct.unpack(">8H", uc.mem_read(sound + 20 + 2 * 0x36, 16))
    recs = [struct.unpack(">I", bytes.fromhex(p["hex"])[16:20])[0] for p in SPEC["patches"]
            if p["what"].startswith("descrittore ") and "2/2" in p["what"]]
    assert list(got) == recs and got[7] == 0x4000


def play(e, machine, page2=None, blocks=60):
    import cli
    params = cli.make_params(machine, 60)
    out = []
    for b in range(blocks):
        if page2 is not None:
            e.uc.mem_write(0x700, struct.pack(">8h", *[v << 8 for v in page2]))
        q = bytearray(params)
        if b in (0, 2):
            q[0x180] = 1
        out += e.render_block(bytes(q))[0]
    return out


def test_engine_on_the_voice_cpu(built):
    import engine as eng
    _, sec7 = built
    e = eng.Engine(image=sec7)
    e.boot(cold=True)
    ref = eng.Engine()
    ref.boot()
    tone = play(ref, 4)
    assert play(e, 4, [0, 64, 64, 64, 64, 64, 64, 64]) == tone             # ALGO 0 = SY TONE
    assert play(e, 44) == play(ref, 44)                                     # le altre machine non cambiano
    seen = set()
    for algo in range(1, 12):
        o = play(e, 4, [algo, 64, 100, 80, 64, 100, 80, 64], blocks=40)
        assert math.sqrt(sum(x * x for x in o) / len(o)) > 1e6, algo
        assert o != tone[:len(o)]
        seen.add(tuple(o))
    assert len(seen) == 11


def test_syn_page_on_an_fm4_track():
    """Pagina SYN di una traccia SY FM4 (vista SRC nell'emulatore dell'interfaccia, machine del suono = 4), dalle
    pagine di syn-pages: la prima apertura porta l'elenco delle pagine da 1 a 3 in un blocco nuovo dell'heap; la
    1/3 ha i descrittori di SY TONE con i nomi di SY FM4 (operatore 2 sotto: rapporto, livello, decay); la 2/3 i
    descrittori 254..261 (operatore 3 sopra, 4 sotto, ALGO nell'ultima casella); la 3/3 ALGO e LEV; il titolo e' una std::string costruita in a0; la vista si disegna; nessuna scrittura
    nel codice dell'OS. Prima delle correzioni, due eccezioni sulla macchina: il puntatore del malloc dell'OS (d0)
    letto da a0, e il titolo restituito come char * invece della std::string."""
    from syn_view import SynView
    from unicorn import UC_HOOK_MEM_WRITE
    v = SynView(["sy-fm4"], machine=4)
    ui = v.ui
    bad = []
    ui.uc.hook_add(UC_HOOK_MEM_WRITE, lambda _uc, _k, a, *_: bad.append(a) if a < 0x401C_0000 else None)
    sp = json.loads((ROOT / "mods" / "syn-pages" / "patch.json").read_text(encoding="utf-8"))["symbols"]
    assert v.slot(47) == int(sp["sp_record"], 16) and v.slot(19) == int(sp["sp_title"], 16)
    old = ui.long(v.view + 0x7C)
    assert v.knobs() == [190, 195, 197, 196, 193, 191, 192, 194, 10]       # TUNE PNCH DEC1 OVER / FDBK RAT2 LEV2 DEC2
    begin = ui.long(v.view + 0x7C)
    assert begin != old and ui.long(v.view + 0x80) == begin + 12 and ui.long(v.view + 0x84) == begin + 16
    assert ui.long(begin) == ui.long(begin + 4) == ui.long(begin + 8)
    short = [bytes(ui.uc.mem_read(ui.long(DESC + 52 * i + 48), 5)).split(b"\0")[0] for i in range(190, 198)]
    assert short == [b"TUNE", b"RAT2", b"LEV2", b"FDBK", b"DEC2", b"PNCH", b"OVER", b"DEC1"]
    assert v.title() == b"SY FM4 1/3"
    v.page(1)
    assert v.knobs() == [255, 256, 257, 261, 258, 259, 260, 254, 10]         # op3 DET / op4 ALGO
    assert v.title() == b"SY FM4 2/3"
    v.frame()
    v.page(2)
    assert v.knobs() == [254, 0, 0, 0, 0, 0, 0, 0, 10]
    assert v.title() == b"SY FM4 3/3"
    v.frame()
    assert bad == []


def test_algorithm_page():
    """Pagina 3/3: lo schema dell'algoritmo della traccia sulle colonne B..D, diverso per ogni algoritmo, sotto la
    riga 13 (sopra l'OS scrive il valore girato). Girando ALGO il numero e' solo nell'icona: sotto resta il nome
    (l'evidenza della sua manopola spenta), sulla 2/3 e sulla 3/3. La 2/3 non disegna niente sopra le icone."""
    import screens
    from syn_view import SynView
    v = SynView(["sy-fm4"], machine=4)
    v.page(1)
    plain = v.frame()
    v.highlight(7)                                                      # ALGO: sotto resta il nome
    assert v.frame() == plain
    v.set_value(0, 0x36, 5 << 8)
    v.highlight(4)
    cols = lambda f: [r[44:] for r in screens.pixels(f)]                   # noqa: E731
    assert cols(v.frame()) == cols(plain)                               # E (DET) mostra il valore, B..D intatte
    v.highlight(None)
    v.page(2)
    still = v.frame()
    v.highlight(0)
    assert v.frame() == still
    v.highlight(None)
    frames = []
    for n in range(12):
        v.set_value(0, 0x36, n << 8)
        frames.append(v.frame())
        rows = screens.pixels(frames[-1])
        assert not any(rows[y][x] for y in range(13) for x in range(44, 128))
        assert sum(rows[y][x] for y in range(13, 64) for x in range(44, 128)) > 60
    assert len(set(frames)) == 12


def text(ui, fn: int, view: int) -> bytes:
    """Slot 19 (titolo): std::string per valore, costruita all'indirizzo in a0 e restituita in d0; la stringa
    (GCC) e' un puntatore ai caratteri."""
    from unicorn.m68k_const import UC_M68K_REG_A0
    out = 0x4FE0_3000
    ui.put(out, ">I", 0)
    ui.uc.reg_write(UC_M68K_REG_A0, out)
    assert ui.call(fn, [view]) == out
    return bytes(ui.uc.mem_read(ui.long(out), 32)).split(b"\0")[0]


def test_title_of_other_machines_is_the_stock_one():
    """Senza SY FM4 il titolo e' quello della funzione stock (0x40044894), stessa stringa."""
    import screens
    ui = screens.UI(["sy-fm4"])
    src = ui.tab("SRC")
    ours = text(ui, ui.long(ui.long(src) + 4 * 19), src)
    assert ours and ours == text(ui, 0x4004_4894, src)
