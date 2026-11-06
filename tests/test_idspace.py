"""idspace (mods/idspace): id dei parametri oltre 504.

- Con idspace l'interfaccia stock non cambia: stesse schede disegnate, stessi id sotto gli encoder, stessi valori.
- La copia dei descrittori e' identica alla tabella dell'OS; gli id delle mod vuoti valgono come l'id 0.
- Gli oggetti per parametro: id dell'OS come prima, id delle mod costruiti dal modello alla prima ricerca.
- Limiti: tutti alzati tranne i tre cicli d'avvio (mappe inverse e CC).
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

import idspace_layout as I  # noqa: E402

SPEC = json.loads((ROOT / "mods" / "idspace" / "patch.json").read_text(encoding="utf-8"))
SYM = {k: int(v, 16) for k, v in SPEC["symbols"].items()}
DESC, OBJ = 0x4022_D83C, 0x41BA_0A24
TABS = ["TRIG", "SRC", "FLTR", "AMP", "DELAY", "REVERB", "MIX", "A.FLTR", "A.AMP", "FX.SYN", "FX.FLTR", "FX.AMP"]


@pytest.fixture(scope="module")
def uis():
    import screens
    return screens.UI([]), screens.UI(["idspace"])


def pages(ui, tab):
    t = ui.tab(tab)
    n = (ui.long(t + 128) - ui.long(t + 124)) // 4
    out = []
    for p in range(n):
        ui.page(t, p)
        out.append(([ui.param(t, e) for e in "ABCDEFGH"], ui.draw(t)))
    return out


@pytest.mark.parametrize("tab", TABS)
def test_stock_pages_unchanged(uis, tab):
    stock, ids = uis
    assert pages(stock, tab) == pages(ids, tab)


def test_descriptor_copy(uis):
    stock, ids = uis
    assert bytes(ids.uc.mem_read(I.TABLE, 52 * 505)) == bytes(stock.uc.mem_read(DESC, 52 * 505))
    zero = bytes(stock.uc.mem_read(DESC, 52))
    for pid in range(I.FIRST, I.N):                                  # nessuna mod: come l'id 0
        assert bytes(ids.uc.mem_read(I.TABLE + 52 * pid, 52)) == zero


def test_limits_raised_except_boot_loops():
    lim = [p for p in SPEC["patches"] if p["what"].startswith("limite")]
    assert len(lim) == 61
    assert {int(p["addr"], 16) - 2 for p in lim}.isdisjoint({0x4001_4708, 0x4002_4352, 0x400A_61A0})
    refs = [p for p in SPEC["patches"] if p["what"].startswith("descrittori")]
    assert len(refs) == 68


def test_objects(uis):
    _, ui = uis
    for pid in (0, 72, 249, 504):
        assert ui.call(SYM["ids_obj32"], [pid]) == OBJ + 84 * pid
    assert ui.call(SYM["ids_obj32"], [I.FIRST]) == OBJ                 # nessuna definizione: oggetto 0
    assert ui.call(SYM["ids_obj32"], [600]) == OBJ
    # una definizione: modello 249, testo dal prototipo dell'id 72 (+20)
    ui.put(I.objdef(I.FIRST + 3), ">4I", 249, OBJ + 84 * 72 + 20, 0, 0)
    ui.put(I.BUILT, ">I", 0)                                                # come all'avvio: definizioni gia' scritte
    a = ui.call(SYM["ids_obj32"], [I.FIRST + 3])
    assert a == I.OBJ + 84 * 3 and ui.long(I.BUILT) == 1
    obj = lambda o, f: bytes(ui.uc.mem_read(o + f + 8, 8))                  # noqa: E731 (manager, invoker)
    assert obj(a, 20) == obj(OBJ + 84 * 72, 20)
    for f in (36, 52, 68):
        assert obj(a, f) == obj(OBJ + 84 * 249, f)
    assert bytes(ui.uc.mem_read(a, 20)) == bytes(ui.uc.mem_read(OBJ + 84 * 249, 20))


def test_extra_pages(uis):
    _, ui = uis
    for i in (0, 24, 36):
        assert ui.call(SYM["ids_page"], [i]) == 0x41BA_03C8 + 44 * i
    assert ui.call(SYM["ids_page"], [37]) == I.PAGEDEF
    assert ui.call(SYM["ids_page"], [40]) == I.PAGEDEF + 3 * 44
