"""Schermate del sito (web-builder/src/previews/frames): rigenerate dal codice dell'OS nell'emulatore
(tools/emu/screens.py) devono coincidere con i file nel repo. Se una patch cambia, rigenerare con

    python tools/emu/screens.py [mod ...]

e guardare i PNG (--png cartella). Serve l'OS Syntakt 1.42 stock (saltato se manca).
"""

import json
import sys
from pathlib import Path

import pytest

pytest.importorskip("unicorn")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools" / "emu"))
import screens  # noqa: E402

pytestmark = pytest.mark.skipif(not screens.SYX.exists(), reason="OS Syntakt 1.42 assente")


@pytest.fixture(scope="module")
def sec3():
    return screens.section3()


def test_index_lists_every_scene():
    index = json.loads((screens.FRAMES_DIR / "index.json").read_text(encoding="utf-8"))
    assert index == screens.index()
    for caption in index.values():
        assert 3 <= len(caption.split()) <= 8, caption


@pytest.mark.parametrize("mod", list(screens.SCENES))
def test_frames_match_the_emulator(sec3, mod):
    want = screens.dump(screens.encode(screens.render(mod, sec3)))
    have = (screens.FRAMES_DIR / f"{mod}.json").read_text(encoding="utf-8")
    assert have == want, f"{mod}: frames out of date, run python tools/emu/screens.py {mod}"


def test_frame_layout():
    """Bitmap dell'OS (colonne, y = 0 in basso) -> righe dall'alto: un pixel per angolo."""
    raw = bytearray(1024)
    raw[0] |= 0x80                                  # x 0, y 0 in memoria = in basso a sinistra
    raw[127 * 8 + 7] |= 0x01                        # x 127, y 63 in memoria = in alto a destra
    px = screens.pixels(screens.frame_bytes(bytes(raw)))
    assert px[63][0] == 1 and px[0][127] == 1 and sum(map(sum, px)) == 2
