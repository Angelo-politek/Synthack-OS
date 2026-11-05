"""Cicli dell'interrupt audio con le cache (tools/emu/cycles.py): taratura sullo stock e costo delle mod.

Il conteggio delle istruzioni non basta: l'interrupt stock esegue ~19 KB di codice per blocco con una cache
istruzioni da 8 KB, quindi ogni riga di codice o di dati in DDR in piu' e' una lettura dalla DDR a ogni blocco.
Questi test tengono il sito (tools/build/budget.py, AUDIO_CYCLES) sopra il misurato e fermano le regressioni
dell'impronta in cache.
"""

import sys
from pathlib import Path

import pytest

pytest.importorskip("unicorn")

ROOT = Path(__file__).resolve().parent
SY = ROOT.parent / "firmware" / "Syntakt_OS1.42.syx"
pytestmark = pytest.mark.skipif(not SY.exists(), reason="OS stock assente")
sys.path[:0] = [str(ROOT.parent / "tools" / "emu"), str(ROOT.parent / "tools" / "build")]

AUDIO = ["fx3", "master-comp", "dual-mono", "xparams", "sampler", "sy-fm4"]


@pytest.fixture(scope="module")
def stock():
    import cycles
    return cycles.measure((), "rest")


def test_cache_model_reproduces_the_stock_load(stock):
    import cycles
    # l'interrupt stock non sta nella cache: quasi ogni riga eseguita e' una mancata
    assert 1100 <= stock.imiss <= 1300, stock
    for cpi in cycles.CPIS:
        miss = cycles.calibrate(stock, cpi)
        assert 15 <= miss <= 80, (cpi, miss)                      # una lettura dalla DDR2: decine di cicli
        assert abs(stock.cycles(cpi, miss) / cycles.BLOCK - cycles.STOCK_LOAD) < 0.001


def cost(stock, mods, base=None):
    import cycles
    miss = cycles.calibrate(stock, 1.0)
    c = cycles.measure(mods, "max")
    return c.cycles(1.0, miss) - (base if base is not None else stock.cycles(1.0, miss)), c


def test_site_shows_at_least_the_estimated_cycles(stock):
    import budget
    shown = budget.AUDIO_CYCLES
    fm, _ = cost(stock, ["fastmix"])
    xp, _ = cost(stock, ["xparams"])
    import cycles
    miss = cycles.calibrate(stock, 1.0)
    got = {"fastmix": fm, "xparams": xp}
    for name in ("fx3", "master-comp", "dual-mono"):
        got[name] = cost(stock, [name])[0] - fm
    got["sampler"] = cost(stock, ["sampler"])[0] - xp
    got["sy-fm4"] = cost(stock, ["sy-fm4"])[0] - xp - fm
    got["modulation-skip"] = cost(stock, ["modulation-skip"])[0]    # blocco saltato: credito
    every, c = cost(stock, AUDIO)
    print("cicli in piu' per blocco:", {k: round(v) for k, v in got.items()}, "tutte:", round(every), c,
          f"MISS {miss:.0f}")
    for k, v in got.items():
        assert v <= shown[k] + 300, (k, v, shown[k])               # margine: rumore del modello tra le build
    assert every <= budget.shown(AUDIO) + 1000


def test_xparams_copy_is_compact(stock):
    _, c = cost(stock, ["xparams"])
    # copia srotolata (fino al 2026-11-03): +113 righe di codice per blocco; in un ciclo per traccia: ~+30
    assert c.imiss - stock.imiss <= 40, c


def test_code_in_sram_is_not_a_cache_miss():
    import cycles
    c = object.__new__(cycles.Cycles)
    c.ic, c.on = cycles.Cache(), True
    for pc in range(0x8000_7330, 0x8000_7730, 2):                 # 1 KB eseguito dalla SRAM (kernel di LFO3)
        c._fetch(None, pc, 2, None)
    assert c.ic.miss == 0
    c._fetch(None, 0x4011_942A, 2, None)                         # codice dell'OS in DDR: una riga
    assert c.ic.miss == 1


def test_profiles_are_shown_at_least_as_measured(stock):
    """Combinazioni misurate intere (budget.PROFILES): il sito, che somma le mod, non mostra meno del misurato."""
    import budget
    for name, p in budget.PROFILES.items():
        got, c = cost(stock, [m for m in p["mods"] if m != "mod-zero"])
        print(name, round(got), c)
        assert abs(got - p["cycles"]) <= 1500, (name, round(got), p["cycles"])   # profilo da rimisurare
        assert budget.shown(p["mods"]) >= got - 300, (name, budget.shown(p["mods"]), round(got))
