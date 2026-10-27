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


# ----------------------------------------------------------------------------- dipendenze
def fake(root, name, requires=()):
    d = root / name
    d.mkdir()
    (d / "patch.json").write_text(json.dumps({"name": name, "os": "1.41", "requires": list(requires), "patches": []}))
    return d


def test_dependencies_added_before_who_needs_them(tmp_path):
    lib = tmp_path / "mods"
    lib.mkdir()
    base, mid = fake(lib, "base"), fake(lib, "mid", ["base"])
    top = fake(tmp_path, "top", ["mid", "base"])
    order, added = build.resolve([top], search=(lib,))
    assert order == [base, mid, top] and added == ["base", "mid"]


def test_given_order_kept_when_complete(tmp_path):
    a, b = fake(tmp_path, "a"), fake(tmp_path, "b", ["a"])
    c = fake(tmp_path, "c")
    order, added = build.resolve([c, a, b], search=())
    assert order == [c, a, b] and added == []


def test_missing_and_circular_dependencies(tmp_path):
    with pytest.raises(build.BuildError, match="non trovata"):
        build.resolve([fake(tmp_path, "x", ["nowhere"])], search=(tmp_path,))
    a, b = fake(tmp_path, "p", ["q"]), fake(tmp_path, "q", ["p"])
    with pytest.raises(build.BuildError, match="circolari"):
        build.resolve([a, b], search=())


def test_same_name_twice_refused(tmp_path):
    a = fake(tmp_path, "dup")
    (tmp_path / "other").mkdir()
    (tmp_path / "other" / "patch.json").write_text((a / "patch.json").read_text())
    with pytest.raises(build.BuildError, match="due volte"):
        build.resolve([a, tmp_path / "other"], search=())


def test_real_mods_resolve():
    order, added = build.resolve([ROOT / "mods" / "dual-mono"])
    names = [build.read_spec(d)["name"] for d in order]
    assert names[-1] == "dual-mono" and set(added) == {"modarea", "vparams", "kitstore"}
    assert names.index("modarea") < names.index("vparams") < names.index("dual-mono")


def test_append_to_section_7_refused():
    s = sections()
    p = build.Patch("x", 7, build.LOAD_ADDR + 8, b"\x4e\x71", "", append=True)
    with pytest.raises(build.BuildError, match="sezione 7"):
        build.apply_patches(s, [p])
