"""Il web builder (TypeScript, web-builder/) deve dare gli stessi byte del tooling Python.

- SHLZ: stesso flusso di tools/build/lz.py (senza firmware, anche in CI);
- build completa: stesso .syx di tools/build/build.py, byte per byte (serve l'OS stock e il tool C);
- ogni mod ha la sua scheda (mod.json) per la pagina del builder.
I test unitari del builder (aPLib, SysEx, ELE3) stanno in web-builder/test e girano con `npm test`.
"""

import json
import random
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
WB = ROOT / "web-builder"
SY = ROOT / "firmware" / "Syntakt_OS1.41.syx"
sys.path.insert(0, str(ROOT / "tools" / "build"))
sys.path.insert(0, str(ROOT / "tools" / "unpack"))
import lz  # noqa: E402

NODE = shutil.which("node")
needs_node = pytest.mark.skipif(not NODE, reason="Node.js assente")
KINDS = {"feature", "infra", "test"}


def test_every_mod_has_a_card():
    for d in sorted(p.parent for p in ROOT.glob("mods/*/patch.json")):
        card = json.loads((d / "mod.json").read_text(encoding="utf-8"))
        assert set(card) == {"title", "kind", "summary"}, d.name
        assert card["kind"] in KINDS and card["title"] and card["summary"].isascii(), d.name
        spec = json.loads((d / "patch.json").read_text(encoding="utf-8"))
        for req in spec.get("requires", []):                # le dipendenze sono infrastruttura
            assert json.loads((ROOT / "mods" / req / "mod.json").read_text(encoding="utf-8"))["kind"] == "infra"


def node(*args, **kw):
    return subprocess.run([NODE, *map(str, args)], capture_output=True, text=True, check=True, **kw)


def samples():
    rnd = random.Random(5)
    yield b""
    yield b"A"
    yield bytes(70000)
    yield bytes(rnd.randrange(256) for _ in range(3000))
    for d in ROOT.glob("mods/*/patch.json"):             # codice vero delle mod
        for p in json.loads(d.read_text(encoding="utf-8"))["patches"]:
            if p.get("append"):
                yield bytes.fromhex(p["hex"])


@needs_node
def test_shlz_same_stream_as_python(tmp_path):
    for k, data in enumerate(samples()):
        src, dst = tmp_path / f"{k}.bin", tmp_path / f"{k}.shlz"
        src.write_bytes(data)
        node(WB / "scripts" / "codec-cli.ts", "shlz", src, dst)
        assert dst.read_bytes() == lz.compress(data), k


MODS = ["splash", "dual-mono", "master-comp", "readable-values", "perf-fx", "fx3"]


@needs_node
@pytest.mark.skipif(not SY.exists(), reason="OS stock assente")
def test_full_build_identical_to_build_py(tmp_path):
    import build
    import eft
    try:
        eft._find_bin()
    except eft.EftError:
        pytest.skip("elektron-firmware-tool assente")
    ref = build.build(SY, [ROOT / "mods" / m for m in MODS], tmp_path / "ref.syx", log=lambda *_: None)
    node(WB / "scripts" / "build-cli.ts", "--stock", SY, *MODS, "-o", tmp_path / "web.syx")
    assert (tmp_path / "web.syx").read_bytes() == (tmp_path / "ref.syx").read_bytes()
    web = json.loads((tmp_path / "web.json").read_text(encoding="utf-8"))
    assert {**web, "output": "ref.syx"} == ref
