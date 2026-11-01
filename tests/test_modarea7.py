"""modarea7: sezione 7 compressa, decompressa dallo stub sulla CPU #2 (emulatore della sezione 7).

Avvio a freddo come il bootloader (da *(0x40000400)), poi lo stesso suono dello stock e l'area dei motori
al suo posto. Serve la sezione 7 stock: saltato se assente.
"""

import json
import math
import random
import struct
import sys
from pathlib import Path

import pytest

pytest.importorskip("unicorn")
from unicorn import UC_HOOK_CODE  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "tools" / "emu"), str(ROOT / "tools" / "build")]
import build  # noqa: E402
import cli  # noqa: E402
import engine as eng  # noqa: E402
import engine_layout as E  # noqa: E402
import memmap  # noqa: E402

RAW = ROOT / "unpacked" / "Syntakt_OS1.42" / "section_7_blob.raw"
pytestmark = pytest.mark.skipif(not RAW.exists(), reason="sezione 7 stock assente")
SPEC = json.loads((ROOT / "mods" / "modarea7" / "patch.json").read_text(encoding="utf-8"))
LAY = build.engine_layout([ROOT / "mods" / "modarea7"])


@pytest.fixture(scope="module")
def stock():
    return RAW.read_bytes()


def play(e, machine, blocks=40):
    params = cli.make_params(machine, 60)
    out = []
    for b in range(blocks):
        q = bytearray(params)
        if b in (0, 2):
            q[0x180] = 1
        out += e.render_block(bytes(q))[0]
    return out


def test_layout_matches_the_stock_section(stock):
    assert E.LOAD + len(stock) == E.IMG == LAY["img"]
    assert struct.unpack_from(">I", stock)[0] == E.ENTRY == LAY["entry"]
    assert LAY["max"] == 0x60000 - 5 and LAY["ram"] == E.RAM and LAY["size"] == E.SIZE


def test_pack_unpack_roundtrip(stock):
    rnd = random.Random(7)
    engine = bytes(rnd.randrange(256) for _ in range(3001))
    packed = build.pack_section7(stock + engine, len(stock), LAY)
    assert build.unpack_section7(packed, LAY) == (stock, engine)
    assert len(packed) <= LAY["max"]
    assert build.unpack_section7(build.pack_section7(stock, len(stock), LAY), LAY) == (stock, b"")


def test_cold_boot_decompresses_and_sounds_like_stock(stock):
    rnd = random.Random(1)
    engine = bytes(rnd.randrange(1, 256) for _ in range(5000))
    packed = build.pack_section7(stock + engine, len(stock), LAY)
    e = eng.Engine(image=packed)
    e.boot(cold=True)
    ref = eng.Engine()
    ref.boot()
    code = 0x4004_F6E0 - E.LOAD                         # da qui in poi e' BSS: lo azzera l'OS stesso
    assert bytes(e.uc.mem_read(E.LOAD, code)) == bytes(ref.uc.mem_read(E.LOAD, code))   # dati scritti dall'avvio compresi
    assert bytes(e.uc.mem_read(E.RAM, len(engine))) == engine
    assert not any(e.uc.mem_read(E.RAM + len(engine), E.SIZE - len(engine)))
    for machine in (4, 44, 0):                         # SY TONE, SP TWINSHOT, BD MODERN
        assert play(e, machine) == play(ref, machine)


def test_stub_is_short(stock):
    """Istruzioni dello stub fino all'entry originale: ~2,4 milioni (decine di ms in piu' all'avvio della CPU #2)."""
    from unicorn.m68k_const import UC_M68K_REG_A7, UC_M68K_REG_SR
    e = eng.Engine(image=build.pack_section7(stock + bytes(60000), len(stock), LAY))
    n = [0]
    e.uc.hook_add(UC_HOOK_CODE, lambda *a: n.__setitem__(0, n[0] + 1))
    e.uc.reg_write(UC_M68K_REG_SR, 0x2700)
    e.uc.reg_write(UC_M68K_REG_A7, 0x8000_FFF0)
    e._run(e.rd32(E.LOAD), E.ENTRY)
    assert e.uc.reg_read(UC_M68K_REG_A7) == 0x8000_FFF0                  # pila del bootloader come prima
    assert n[0] < 3_000_000, n[0]


def test_room_shown_by_the_site(stock):
    import budget
    assert LAY["max"] - len(build.pack_section7(stock, len(stock), LAY)) == budget.SEC7_ROOM
