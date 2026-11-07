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


# ----------------------------------------------------------------------------- menu DEST degli LFO (66 voci)
DEST_STOCK, DEST_IID, DEST_COPY = 0x4022_B390, 0x400A_65D2, 0x400A_6598


def test_dest_rows_hold_the_stock_rows(uis):
    stock, ui = uis
    for m in range(I.DEST_ROWS):
        want = struct.unpack(">33I", bytes(stock.uc.mem_read(DEST_STOCK + 132 * m, 132)))
        row = struct.unpack(f">{I.DEST_N}H", bytes(ui.uc.mem_read(I.ROWS + 2 * I.DEST_N * m, 2 * I.DEST_N)))
        extra = [x for x in row if x != 0xFFFF][33:]                          # voci registrate dalle mod
        assert [x for x in row if x != 0xFFFF and x not in extra] == list(want) or extra, m
        assert row[-1] == 0xFFFF                                              # sempre una fine


def test_dest_item_to_internal_id_like_the_os(uis):
    """Senza voci delle mod nella riga, voce -> id interno come la funzione dell'OS, per ogni machine e tipo."""
    stock, ui = uis
    for kind in (0, 3, 12, 13):
        for m in (0, 4, 11, 34, 44, 45, 60):
            for item in (0, 1, 3, 4, 20, 32, 33, 40):
                want = stock.call(DEST_IID, [item, m, kind])
                got = ui.call(DEST_IID, [item, m, kind])
                if item <= 32 or want != 0xFFFF_FFFF:
                    row = struct.unpack(">66H", bytes(ui.uc.mem_read(I.ROWS + 132 * (m if m <= 44 else 34), 132)))
                    if len([x for x in row if x != 0xFFFF]) == 33 or kind == 12:
                        assert got == want, (kind, m, item, hex(got), hex(want))


def test_dest_copy_writes_the_packed_row(uis):
    _, ui = uis
    from unicorn.m68k_const import UC_M68K_REG_A0
    buf = 0x4FE0_3000
    for m in (4, 44, 80):
        ui.uc.reg_write(UC_M68K_REG_A0, buf)
        assert ui.call(DEST_COPY, [m]) == buf
        r = m if m <= 0x2C else 0x22
        assert bytes(ui.uc.mem_read(buf, 132)) == bytes(ui.uc.mem_read(I.ROWS + 132 * r, 132))
