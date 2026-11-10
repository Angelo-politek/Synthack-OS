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


def test_dest_menu_starts_from_the_group_of_the_first_item(uis):
    """Gruppo iniziale del menu (0x4004E542): dalla prima voce da 16 bit della riga, come l'OS dalla prima parola
    lunga della riga stock (con la parola intera il menu si apriva con un gruppo ERR, segnalato sulla macchina)."""
    stock, ui = uis
    first = SYM["ids_dest_first"]
    for m in range(I.DEST_ROWS):
        packed = struct.unpack(">I", bytes(ui.uc.mem_read(I.ROWS + 2 * I.DEST_N * m, 4)))[0]
        want = stock.call(0x400A_5CE4, [struct.unpack(">I", bytes(stock.uc.mem_read(DEST_STOCK + 132 * m, 4)))[0]])
        assert ui.call(first, [packed]) == want, m
    assert ui.call(first, [0xFFFF_FFFF]) == stock.call(0x400A_5CE4, [0xFFFF_FFFF])
    site = next(p for p in SPEC["patches"] if p.get("addr", "").upper() == "0X4004E542")
    assert site["hex"] == f"4eb9{first:08x}"


def test_dest_groups_and_knob_list_with_the_mod_ids(uis):
    """Gruppo di un id (0x400A5CE4, tutto l'OS) e filtro della lista della manopola DEST (0x4001476E).
    Sulla macchina: sotto LFO2 una sezione ERR in testa con i nomi di LFO1 (gli id 530..537 di LFO3, flag di LFO1,
    gruppo -1) e niente pagine 2/3 e 3/3 di SY FM4 (521..528, flag 0)."""
    import screens
    stock, _ = uis
    ui = screens.UI(["sy-fm4", "sampler", "fx3", "lfo3", "idspace"])
    T, F = 0x400A_5CE4, SYM["ids_dest_flags"]
    assert [ui.call(T, [i]) for i in range(521, 529)] == [4] * 8                 # con la machine 4, come 190..197
    for i in (0, 19, 86, 99, 190, 497, 504, 600, 0xFFFF_FFFF):
        assert ui.call(T, [i]) == stock.call(T, [i]), i                          # id dell'OS e sconosciuti: come l'OS
    assert ui.call(T, [529]) == 44 and ui.call(T, [530]) == 0xFFFF_FFFF
    for i in (19, 86, 96, 190, 197, 300, 504):
        assert ui.call(F, [i]) == stock.call(0x400A_66E2, [i]), i
    from unicorn.m68k_const import UC_M68K_REG_A5
    obj, inner, vt, stub, sound = 0x4FE0_6000, 0x4FE0_6040, 0x4FE0_6080, 0x4FE0_6100, 0x4FE0_6200
    ui.put(obj + 16, ">I", inner)                                              # modello della traccia (a5): +16 ->
    ui.put(inner, ">I", vt)                                                    # oggetto con vt[0x28] = il Sound
    ui.put(vt + 40, ">I", stub)
    ui.uc.mem_write(stub, bytes.fromhex("203c") + sound.to_bytes(4, "big") + bytes.fromhex("4e75"))

    def listed(dest, machine):                                                  # come 0x400149F0..0x4001479E
        ui.uc.mem_write(sound + 162, bytes([machine]))
        ui.uc.reg_write(UC_M68K_REG_A5, obj)
        x = ui.long(I.TABLE + 52 * dest + 36)
        m = 0xE00 if x >> 17 & 1 else 0x600 if x >> 16 & 1 else 0
        out = set()
        for i in range(505, 569):
            ui.uc.reg_write(UC_M68K_REG_A5, obj)
            if (~ui.call(F, [i])) & m == 0:
                out.add(i)
        return out
    for dest in (89, 99, 533):                                                  # LFO1, LFO2, LFO3
        fm4, other, smp = listed(dest, 4), listed(dest, 0), listed(dest, 44)
        assert set(range(521, 529)) <= fm4 and not fm4 & set(range(530, 538)) and 529 not in fm4, (dest, sorted(fm4))
        assert not other & set(range(521, 530)) and not other & set(range(530, 538)), (dest, sorted(other))
        assert 529 in smp and not smp & set(range(521, 529)), (dest, sorted(smp))
    for m in range(I.DEST_ROWS):                                                # menu: nessuna voce sotto ERR
        row = struct.unpack(f">{I.DEST_N}H", bytes(ui.uc.mem_read(I.ROWS + 2 * I.DEST_N * m, 2 * I.DEST_N)))
        assert all(ui.call(T, [x]) != 0xFFFF_FFFF for x in row if x != 0xFFFF), m


def test_fx_track_dest_list_has_the_mod_parameters():
    """Lista della manopola DEST (0x4001471C): per ogni indice 0..70 chiede l'id al modello della traccia
    (vt[80] = 0x40011F6C -> 0x400A6464(indice, machine)). Le tabelle dell'OS sono per tipo di traccia, e la FX track
    (machine 45) usa quella delle tracce analogiche: i parametri della pagina FX3 (parole libere del kit FX) non
    c'erano. Sulla macchina (RC1): nessun parametro di FX3 tra le destinazioni dell'LFO della FX track."""
    import screens
    from unicorn.m68k_const import UC_M68K_REG_A5
    stock = screens.UI([])
    ui = screens.UI(["fx3", "sy-fm4", "idspace"])
    obj, inner, vt, stub, sound = 0x4FE0_6000, 0x4FE0_6040, 0x4FE0_6080, 0x4FE0_6100, 0x4FE0_6200
    for u in (stock, ui):
        u.put(obj + 16, ">I", inner)
        u.put(inner, ">I", vt)
        u.put(vt + 40, ">I", stub)
        u.uc.mem_write(stub, bytes.fromhex("203c") + sound.to_bytes(4, "big") + bytes.fromhex("4e75"))

    def ids(u, machine):
        u.uc.mem_write(sound + 162, bytes([machine]))
        return [u.call(0x4001_1F6C, [obj, k]) for k in range(71)]
    fx = ids(ui, 45)
    want = {struct.unpack(">I", bytes(ui.uc.mem_read(I.TABLE + 52 * pid + 4, 4)))[0]: pid
            for k in range(I.DESTX_N)
            for m, _, pid in [struct.unpack(">BBH", bytes(ui.uc.mem_read(I.DESTX + 4 * k, 4)))] if m == 45 and pid}
    assert len(want) == 6 and set(want.values()) == {506, 507, 508, 509, 510, 512}
    assert {k: v for k, v in enumerate(fx) if v >= I.FIRST} == want
    base = ids(stock, 45)
    assert [v for k, v in enumerate(fx) if k not in want] == [v for k, v in enumerate(base) if k not in want]
    for machine in (0, 4, 20, 44):                           # le altre tracce: come l'OS
        assert ids(ui, machine) == ids(stock, machine), machine
    for pid in want.values():                                # e passano il filtro della lista
        ui.uc.reg_write(UC_M68K_REG_A5, obj)
        assert ui.call(SYM["ids_dest_flags"], [pid]) == 0xE00
