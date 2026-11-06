"""La machine MIDI resta quella dell'OS con tutte le mod (bug 2026-11-06: le mod usavano gli id 246-269 e la pagina 27).

Pagine della machine MIDI: 26 TRIG, 27 SRC "MIDI Source" (246-253), 28 VAL "CC Value" (254-261), 29 SEL "CC Select"
(262-269), 30 LFO. Con ogni mod: elementi di pagina, descrittori e oggetti per parametro di quegli id come nello
stock, e nessuna mod li registra in vparams.
"""

import json
import struct
import sys
from pathlib import Path

import pytest

pytest.importorskip("unicorn")

ROOT = Path(__file__).resolve().parents[1]
SY = ROOT / "firmware" / "Syntakt_OS1.42.syx"
pytestmark = pytest.mark.skipif(not SY.exists(), reason="OS stock assente")
sys.path[:0] = [str(ROOT / "tools" / "emu"), str(ROOT / "tools" / "build")]

PAGES, OBJ, DESC = 0x41BA_03C8, 0x41BA_0A24, 0x4022_D83C
MIDI_IDS = range(246, 270)
EVERY = sorted(p.parent.name for p in (ROOT / "mods").glob("*/mod.json") if p.parent.name != "mod-zero")


@pytest.fixture(scope="module")
def uis():
    import screens
    return screens.UI([]), screens.UI(EVERY)


def table(ui):
    """Descrittori come li legge l'OS: la copia di idspace se c'e'."""
    import idspace_layout as I
    return I.TABLE if "idspace" in ui.mods else DESC


def string(ui, a):
    p = ui.long(a)
    return bytes(ui.uc.mem_read(p, 32)).split(b"\0")[0]


@pytest.mark.parametrize("page", [26, 27, 28, 29, 30])
def test_midi_pages_are_stock(uis, page):
    stock, every = uis
    a = PAGES + 44 * page
    assert bytes(every.uc.mem_read(a + 8, 36)) == bytes(stock.uc.mem_read(a + 8, 36))
    assert string(every, a) == string(stock, a) and string(every, a + 4) == string(stock, a + 4)


@pytest.mark.parametrize("pid", MIDI_IDS)
def test_midi_descriptors_and_objects_are_stock(uis, pid):
    stock, every = uis
    d = lambda ui: bytes(ui.uc.mem_read(table(ui) + 52 * pid, 52))          # noqa: E731
    assert d(every) == d(stock), pid
    o = lambda ui, f: bytes(ui.uc.mem_read(OBJ + 84 * pid + f + 8, 8))       # noqa: E731
    for f in (20, 36, 52, 68):
        assert o(every, f) == o(stock, f), (pid, f)


def test_no_mod_registers_midi_ids():
    for f in sorted((ROOT / "mods").glob("*/patch.json")):
        spec = json.loads(f.read_text(encoding="utf-8"))
        for p in spec["patches"]:
            if p.get("append") and p.get("what", "").startswith("vparams["):
                pid = struct.unpack(">H", bytes.fromhex(p["hex"])[:2])[0]
                assert pid not in MIDI_IDS, (spec["name"], pid)
