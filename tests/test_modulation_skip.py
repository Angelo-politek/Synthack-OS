"""modulation-skip (mods/modulation-skip): la modulazione saltata scrive gli stessi valori dello stock, bit per bit.

Due interrupt audio interi (tools/emu/isr.py) in parallelo, stock e con la mod, con le stesse modifiche tra un blocco
e l'altro: velocity, tabelle delle sorgenti, valori di partenza (smussati) delle destinazioni, dati machine scritti
come fa lo scrittore dell'OS (contatore), parametri del kit dall'OS. Dopo ogni blocco la SRAM (fuori dalle code della
mod) e' identica. Poi: uno scrittore sconosciuto spegne la mod; il costo in cicli di un blocco saltato e di uno
ricalcolato.
"""

import random
import struct
import sys
from pathlib import Path

import pytest

pytest.importorskip("unicorn")

ROOT = Path(__file__).resolve().parents[1]
SY = ROOT / "firmware" / "Syntakt_OS1.42.syx"
pytestmark = pytest.mark.skipif(not SY.exists(), reason="OS stock assente")
sys.path[:0] = [str(ROOT / "tools" / "emu"), str(ROOT / "tools" / "build")]
import registry as R  # noqa: E402

WORKING, VEL = 0x8000_6348, 0x8000_4670
MIRROR = 0x4198                     # dati machine = copia (memcpy 0x4011613C, ogni blocco) di raw(t) - MIRROR
ST = 0x8000_FC20
FIELDS = ("mode", "valid", "n", "ticks", "count", "writes", "seen", "capture", "outside", "blocks", "hits", "skips",
          "errors")
OURS = [(a, b) for a, b, who, _ in R.SRAM if who == "modulation-skip"]


def raw(t):
    return WORKING + 0x754 + 0x7C * t


def state(m):
    return dict(zip(FIELDS, struct.unpack(">13I", m.uc.mem_read(ST, 52))))


def sram(m):
    """SRAM della CPU #1 senza le code di modulation-skip."""
    out, pos = bytearray(), 0x8000_0000
    for a, b in sorted(OURS):
        out += m.uc.mem_read(pos, a - pos)
        pos = b
    return bytes(out + m.uc.mem_read(pos, 0x8001_0000 - pos))


@pytest.fixture(scope="module")
def pair():
    import isr
    s, m = isr.Isr([]), isr.Isr(["modulation-skip"])
    for x in (s, m):
        x.scene("max")
    assert state(m)["mode"] == 2                                  # ON dopo l'init di sfcore
    return s, m


def both(pair, fn):
    for x in pair:
        fn(x)


def test_skipped_blocks_are_bit_exact(pair):
    s, m = pair
    rnd = random.Random(7)
    assert sram(s) == sram(m)
    start = state(m)
    for blk in range(400):
        k = rnd.randrange(12)
        if k == 0:                                                # velocity di una traccia
            t, v = rnd.randrange(12), rnd.randrange(0x8000)
            both(pair, lambda x: x.put16(VEL + 2 * t, v))
        elif k == 1:                                              # tabella delle sorgenti
            a, v = rnd.choice(range(0x8000_46B8, 0x8000_4760, 4)), rnd.getrandbits(32)
            both(pair, lambda x: x.put32(a, v))
        elif k == 2:                                              # valore smussato di partenza (copia dei parametri)
            t, w, v = rnd.randrange(12), rnd.randrange(71), rnd.randrange(0x7F00)
            both(pair, lambda x: x.put16(0x8000_21B0 + 142 * t + 2 * w, v))
        elif k == 3:                                              # dati machine, come lo scrittore dell'OS
            t, g, e = rnd.randrange(13), rnd.randrange(6), rnd.randrange(4)
            amount, index = rnd.randrange(-0x8000, 0x8000), rnd.randrange(71)
            a = raw(t) + 0x10 * g + 4 * e - MIRROR
            both(pair, lambda x: x.put32(a, (amount & 0xFFFF) << 16 | index))
            n = struct.unpack(">I", m.uc.mem_read(ST + 0x14, 4))[0]
            m.put32(ST + 0x14, n + 2)
        for x in pair:
            x.fast(1)
        assert sram(s) == sram(m), (blk, k, state(m))
        if k == 3:
            assert struct.unpack(">I", m.uc.mem_read(a + MIRROR, 4))[0] == (amount & 0xFFFF) << 16 | index
    end = state(m)
    print({f: end[f] - start[f] for f in ("blocks", "hits", "skips", "errors")}, "destinazioni", end["n"])
    assert end["errors"] == 0 and end["mode"] == 2
    assert end["skips"] - start["skips"] >= 40                    # un blocco su tre cambia qualcosa: 52 saltati su 400 (2026-11-05)


def test_kit_parameter_changes_through_the_os(pair):
    """Mandate e parametri cambiati dall'OS (vset): la stessa uscita, e la mod resta accesa."""
    s, m = pair
    for pid, v in ((10, 40), (11, 90), (40, 3), (41, 100), (10, 127)):
        both(pair, lambda x: x.vset(pid, v))
        for _ in range(5):
            for x in pair:
                x.fast(1)
            assert sram(s) == sram(m), pid
    assert state(m)["errors"] == 0


def test_unknown_writer_turns_it_off():
    import isr
    s, m = isr.Isr([]), isr.Isr(["modulation-skip"])
    for x in (s, m):
        x.scene("max")
    a = raw(3) + 0x10 + 4 - MIRROR
    for x in (s, m):
        x.put32(a, 0x1234_0005)                                  # nessuna scrittura contata
    for _ in range(70):
        for x in (s, m):
            x.fast(1)
    st = state(m)
    assert st["errors"] >= 1 and st["mode"] == 3                 # OFF: stock per il resto della sessione
    for _ in range(3):
        for x in (s, m):
            x.fast(1)
        assert sram(s) == sram(m)


def test_cycles_of_a_skipped_and_of_a_recomputed_block():
    """Modello delle cache (tools/emu/cycles.py): un blocco saltato costa molto meno dello stock; uno con le
    destinazioni da ricalcolare costa lo stock piu' poco (il caso peggiore per blocco)."""
    import cycles
    import isr
    stock = cycles.measure((), "rest")
    miss = cycles.calibrate(stock, 1.0)
    base = cycles.measure((), "max").cycles(1.0, miss)
    m = isr.Isr(["modulation-skip"])
    m.scene("max")
    c = cycles.Cycles(m)
    c.run()
    skipped = c.run().cycles(1.0, miss) - base
    m.put16(VEL, 0x1234)                                          # velocity cambiata: stock e confronto
    changed = c.run().cycles(1.0, miss) - base
    print(f"blocco saltato {skipped:+.0f} cicli, ricalcolato {changed:+.0f}")
    assert skipped <= -5000, skipped
    assert changed <= 3000, changed
