"""SHLZ (tools/build/lz.py): andata e ritorno, casi limite, rapporto sul codice vero delle mod."""

import json
import random
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools" / "build"))
import lz  # noqa: E402


@pytest.mark.parametrize("data", [
    b"", b"a", b"abc", b"\x00" * 1000, bytes(range(256)) * 20, b"ab" * 777 + b"xyz",
    bytes(random.Random(1).getrandbits(8) for _ in range(5000)),
])
def test_roundtrip(data):
    assert lz.decompress(lz.compress(data)) == data


def test_long_literal_and_match_boundaries():
    rnd = random.Random(2)
    data = bytes(rnd.getrandbits(8) for _ in range(300)) + b"Q" * 500 + bytes(rnd.getrandbits(8) for _ in range(129))
    assert lz.decompress(lz.compress(data)) == data


def test_corrupt_stream_is_rejected():
    blob = bytearray(lz.compress(b"hello hello hello hello"))
    blob[0] = ord("X")
    with pytest.raises(ValueError):
        lz.decompress(bytes(blob))


def test_mod_code_compresses():
    total = b""
    for mod in ("master-comp", "readable-values"):
        spec = json.loads((ROOT / "mods" / mod / "patch.json").read_text(encoding="utf-8"))
        total += b"".join(bytes.fromhex(p["hex"]) for p in spec["patches"] if p.get("append"))
    c = lz.compress(total)
    assert lz.decompress(c) == total
    assert len(c) < 0.8 * len(total)
