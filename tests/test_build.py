"""Test di tools/build/build.py: logica delle patch (senza firmware) e build reale (se presente)."""

import hashlib
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools" / "build"))
import build  # noqa: E402


def h(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def patch(section=3, offset=4, data=b"NEW!", expect=b"OLD!", mod="m"):
    return build.Patch(mod, section, build.LOAD_ADDR + offset, data, h(expect))


def sections():
    return {3: bytearray(b"....OLD!...."), 7: bytearray(b"abcdefgh")}


def test_apply_ok():
    s = sections()
    build.apply_patches(s, [patch()])
    assert bytes(s[3]) == b"....NEW!...."


def test_wrong_original_bytes_refused():
    s = sections()
    with pytest.raises(build.BuildError, match="non sono quelli attesi"):
        build.apply_patches(s, [patch(expect=b"XXXX")])
    assert bytes(s[3]) == b"....OLD!...."               # niente applicato a meta'


def test_overlapping_patches_refused():
    s = sections()
    with pytest.raises(build.BuildError, match="stessi byte"):
        build.apply_patches(s, [patch(mod="a"), patch(offset=6, data=b"zz", expect=b"D!", mod="b")])


def test_out_of_range_refused():
    with pytest.raises(build.BuildError, match="fuori"):
        build.apply_patches(sections(), [patch(offset=10)])


def test_protected_sections_refused(tmp_path):
    (tmp_path / "patch.json").write_text(json.dumps({
        "name": "evil", "os": "1.41",
        "patches": [{"section": 2, "addr": "0x40000400", "len": 2, "expect_sha256": "00", "hex": "4e71"}]}))
    with pytest.raises(build.BuildError, match="non modificabile"):
        build.load_mod(tmp_path, "1.41")


def test_mod_for_other_os_refused(tmp_path):
    (tmp_path / "patch.json").write_text(json.dumps({"name": "x", "os": "1.42", "patches": []}))
    with pytest.raises(build.BuildError, match="OS 1.42"):
        build.load_mod(tmp_path, "1.41")


STOCK = ROOT / "firmware" / "Syntakt_OS1.41.syx"


@pytest.mark.skipif(not STOCK.exists(), reason="firmware stock assente")
def test_build_mod_zero(tmp_path):
    out = tmp_path / "mz.syx"
    lines = []
    m = build.build(STOCK, [ROOT / "mods" / "mod-zero"], out, log=lines.append)
    assert m["mods"] == ["mod-zero"]
    assert lines[0].startswith("  avvio: margine di decompressione ")
    assert m["boot_margin"] >= 4096
    assert lines[1:] == ["  sezione 3: 8 byte modificati, tutti dentro le patch"]
    assert build.eft.info(out).checksums_ok
