import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "tools" / "unpack"), str(ROOT / "tools" / "hooks"), str(ROOT / "tools" / "emu")]


SLOW = {l.strip() for l in (ROOT / "tests" / "slow_tests.txt").read_text(encoding="utf-8").splitlines()
        if l.strip() and not l.startswith("#")}


def pytest_collection_modifyitems(items):
    """-m "not slow": i test sotto i 5 secondi (tests/slow_tests.txt elenca gli altri)."""
    import pytest
    for item in items:
        if item.nodeid in SLOW:
            item.add_marker(pytest.mark.slow)
