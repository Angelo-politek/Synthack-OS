"""recorder (mods/recorder): il registratore di Synfact sulla 1.42.

- sfcore lega il modulo (posto 2): eventi tasti, encoder, tick, disegno della vista, mix, scritture dei file.
- A registratore chiuso l'interrupt audio quasi non cambia.
- Il salvataggio assegna SAMP del SAMPLER con l'id di memoria del descrittore 504 (copia di idspace).
"""

import json
import sys
from pathlib import Path

import pytest

pytest.importorskip("unicorn")

ROOT = Path(__file__).resolve().parents[1]
SY = ROOT / "firmware" / "Syntakt_OS1.42.syx"
pytestmark = pytest.mark.skipif(not SY.exists(), reason="OS stock assente")
sys.path[:0] = [str(ROOT / "tools" / "emu"), str(ROOT / "tools" / "build")]

SPEC = json.loads((ROOT / "mods" / "recorder" / "patch.json").read_text(encoding="utf-8"))
SYM = {k: int(v, 16) for k, v in SPEC["symbols"].items()}
SF = {k: int(v, 16) for k, v in json.loads((ROOT / "mods" / "sfcore" / "patch.json").read_text(
    encoding="utf-8"))["symbols"].items()}


def test_bound_by_sfcore_with_every_event():
    import screens
    ui = screens.UI(["recorder"])
    assert ui.long(SF["sfcore_status"] + 4 * 2) == 1
    assert ui.long(SF["sfcore_subscriptions"]) >= 7


def test_idle_costs_almost_nothing():
    import isr

    def cost(mods, uses=()):
        m = isr.Isr(mods, uses=uses)
        m.scene("max")
        m.run()
        m.fast(4)
        return m.run().n
    a = cost(["sfcore", "long-samples", "sampler", "idspace"], uses=["sfcore:main_mix", "sfcore:fs", "sfcore:pages"])
    b = cost(["recorder"])
    print("istruzioni:", a, b)
    assert b - a <= 60


def test_samp_storage_id_for_the_sampler():
    import screens
    ui = screens.UI(["recorder"])
    glue = {k: int(v, 16) for k, v in SPEC["symbols"].items()}
    fn = glue.get("rec_samp_engine")
    if fn is None:
        pytest.skip("simbolo non esportato")
    assert ui.call(fn) == 0x2DF
