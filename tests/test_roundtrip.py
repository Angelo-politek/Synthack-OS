"""Round-trip sul firmware reale. Saltato se il .syx o il tool non ci sono
(es. in CI: il firmware non e' mai nel repo)."""

import os
from pathlib import Path

import pytest

import eft

SYX = Path(os.environ.get("SYNTAKT_SYX", eft.REPO / "firmware" / "Syntakt_OS1.41.syx"))

pytestmark = [
    pytest.mark.skipif(not SYX.exists(), reason=f"firmware stock assente: {SYX}"),
    pytest.mark.skipif(not Path(os.environ.get("EFT_BIN", eft.DEFAULT_BIN)).exists(),
                       reason="elektron-firmware-tool non compilato (tools/unpack/setup_eft.sh)"),
]


def test_info_is_syntakt():
    i = eft.info(SYX)
    assert "Syntakt" in i.device
    assert i.checksums_ok
    assert {2, 3, 7} <= {s.id for s in i.sections}


def test_roundtrip(tmp_path):
    lines = []
    assert eft.roundtrip(SYX, tmp_path, log=lines.append), "\n".join(lines)
