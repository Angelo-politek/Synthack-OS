import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MOD = ROOT / "mods" / "sy-chord"
LOAD = 0x40000400
WAVE0_OFFSET = 0x53E50
WAVE_REGION = (0x1E3FC - 31 * 0x404, 0x1E3FC)

def patches(moddir):
    return json.loads((moddir / "patch.json").read_text())["patches"]

def test_manifest_declares_only_stock_section_wave_and_graphics_regions():
    data = patches(MOD)
    assert {p["section"] for p in data} == {3, 7}
    for p in data:
        raw = bytes.fromhex(p["hex"])
        assert len(raw) == p["len"]
        assert len(p["expect_sha256"]) == 64
        off = int(p["addr"], 16) - LOAD
        if p["section"] == 7:
            assert WAVE_REGION[0] <= off < off + p["len"] <= WAVE_REGION[1]
            assert not off <= WAVE0_OFFSET < off + p["len"]

def test_manifest_does_not_overlap_existing_upstream_mod_patches():
    mine = []
    for p in patches(MOD):
        mine.append((p["section"], int(p["addr"], 16), int(p["addr"], 16) + p["len"]))
    for path in (ROOT / "mods").iterdir():
        if path == MOD or not (path / "patch.json").is_file():
            continue
        for p in patches(path):
            if p.get("append"):
                continue
            start = int(p["addr"], 16); end = start + p["len"]
            assert not any(section == p["section"] and start < b and a < end for section, a, b in mine), path.name

def test_attribution_and_regeneration_material_are_present():
    notice = (MOD / "THIRD_PARTY_NOTICES.md").read_text()
    assert "Bezronczek" in notice and "MIT License" in notice
    assert (MOD / "generate.mjs").is_file()
    assert (MOD / "make_patch.py").is_file()
