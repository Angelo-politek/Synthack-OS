"""Controllo di avvio: margine della decompressione della sezione 3 (vedi tools/build/bootcheck.py)."""

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "tools" / "unpack"), str(ROOT / "tools" / "build")]
import bootcheck  # noqa: E402
import build  # noqa: E402
import eft  # noqa: E402

STOCK = ROOT / "firmware" / "Syntakt_OS1.41.syx"
pytestmark = pytest.mark.skipif(not STOCK.exists(), reason="firmware stock assente")


def test_stock_margin_and_size(tmp_path):
    size, margin = bootcheck.check(STOCK)
    assert size == len(eft.unpack(STOCK, tmp_path / "u", ids=[3])[3].read_bytes())
    assert margin == 99938


def test_build_refuses_image_that_would_not_boot(tmp_path):
    """Come la v0.4.93 (provata: resta sul logo): sezione 3 allungata a zeri fino a 0x40350000."""
    pad = tmp_path / "pad"
    pad.mkdir()
    (pad / "patch.json").write_text(json.dumps({"name": "pad", "os": "1.41", "patches": [
        {"section": 3, "addr": "0x4034FFF0", "len": 16, "append": True, "hex": "00" * 16}]}))
    out = tmp_path / "o.syx"
    with pytest.raises(build.BuildError, match="margine"):
        build.build(STOCK, [pad], out, log=lambda *_: None)
    assert not out.exists()
