"""Carico audio di tutte le mod insieme, nel caso peggiore (issue #2).

L'interrupt audio (1500 blocchi al secondo da 32 campioni) usa gia' ~89 % della CPU con l'OS stock e
l'interfaccia vive del resto: ogni istruzione in piu' per blocco le toglie tempo. Qui si contano, sul codice
vero nell'emulatore, le istruzioni aggiunte per blocco da ogni mod che gira nell'interrupt audio, con tutto
acceso al massimo, e si controlla che il totale non cresca. perf-fx gira nell'interrupt del sequencer e
readable-values nell'interfaccia: fuori da questo conto.
"""

import random
import struct
import sys
from pathlib import Path

import pytest

pytest.importorskip("unicorn")
from unicorn import UC_HOOK_CODE  # noqa: E402

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
SY = ROOT.parent / "firmware" / "Syntakt_OS1.41.syx"
pytestmark = pytest.mark.skipif(not SY.exists(), reason="OS stock assente")

# tetti (istruzioni per blocco): valori misurati il 2026-10-27, da abbassare con le ottimizzazioni
CEILING = {"fx3": 3600, "master-comp": 650, "dual-mono v2": 340, "dual-mono v1": 140}
TOTAL = 4700


def counted(uc, fn):
    n = [0]
    uc.ctl_flush_tb()                                           # i blocchi gia' tradotti non vedrebbero il gancio
    h = uc.hook_add(UC_HOOK_CODE, lambda *a: n.__setitem__(0, n[0] + 1))
    fn()
    uc.hook_del(h)
    return n[0]


def fx3_worst():
    """12 tracce e l'ingresso in mandata, retroazione e mandate al massimo, ritorno nella FX track."""
    import test_fx3 as T
    worst = 0
    for typ in range(4):
        m = T.Machine()
        kit = 0x5000_6000
        m.uc.mem_write(0x8000_30BC, struct.pack(">I", kit))
        m.uc.mem_write(kit, bytes(142))
        m.uc.mem_write(kit + 110, struct.pack(">H", 0x0100))
        m.param("TYPE", typ)
        for k in ("SPD", "DEP", "TIME", "FDBK", "WID", "DSND", "RSND"):
            m.param(k, 127)
        T.loud(m)
        T.gains(m, [0x4000_0000] * 14)
        for _ in range(40):
            T.run_block(m)
        m.uc.mem_write(T.REVERB, b"\x4e\x75")
        mix = T.block_cost(m)
        rev = counted(m.uc, lambda: m.call(m.sym["fx3_rev_hook"], [0x1111, 0x2222, 0x3333])) - 1
        trk = counted(m.uc, lambda: T.track(m, 4, 0x6000_0000, 0x6000_0000, 0x7F00)) - 1
        inp = counted(m.uc, lambda: T.in_hook(m, -0x5000_0000, -0x2000_0000)) - 1
        worst = max(worst, mix + rev + 12 * trk + inp)
    return worst


def comp_worst():
    import test_master_comp as C
    spec, sec3, _ = C.setup.__wrapped__()
    m = C.Machine(spec, sec3)
    rnd = random.Random(3)
    sig = list(C.signal(rnd, 2))
    m.block(*sig[0], 40000, 40000)
    m.set("RAT", 4 * C.RAT_STEP)
    m.block(*sig[1], 40000, 40000)
    noisy = [rnd.randrange(-2**31, 2**31) for _ in range(32)]
    return C.block_cost(m, noisy, noisy)


def dual_mono_v2():
    import test_dual_mono_v2 as V
    stock, mod = V.Machine(["vparams", "fx3"]), V.Machine(["vparams", "kitstore", "fx3", "dual-mono"])
    V.r_words(mod, 100, 100, 100)
    args = dict(mono=True, inlr=0x7F00, bal=0x6000, dl=0x7F00, rv=0x7F00, route=1)
    return counted(mod.uc, lambda: mod.block(**args)) - counted(stock.uc, lambda: stock.block(**args))


def dual_mono_v1():
    import test_dual_mono as D
    sec3 = D.eft.unpack(D.STOCK, D.ROOT / "unpacked" / D.STOCK.stem, ids=[3])[3].read_bytes()
    stock, mod = D.Machine(sec3, False, 0xA0), D.Machine(sec3, True, 0xA0)
    mod.run(0x6000, 0x3000, 0x2000, 0, True)                    # primo blocco: cambio di modo (interfaccia)
    return (counted(mod.uc, lambda: mod.run(0x6000, 0x3000, 0x2000, 0, True))
            - counted(stock.uc, lambda: stock.run(0x6000, 0x3000, 0x2000, 0, True)))


def test_worst_case_load_of_all_mods():
    got = {"fx3": fx3_worst(), "master-comp": comp_worst(), "dual-mono v2": dual_mono_v2(),
           "dual-mono v1": dual_mono_v1()}
    print("istruzioni in piu' per blocco:", got, "totale", sum(got.values()))
    for k, v in got.items():
        assert v <= CEILING[k], (k, v)
    assert sum(got.values()) <= TOTAL, got
