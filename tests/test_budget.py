"""web-builder/src/budget.json (indicatore di carico del sito) allineato a registro, patch.json e misure."""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools" / "build"))
import budget  # noqa: E402


def test_budget_json_is_up_to_date():
    got = json.loads(budget.OUT.read_text(encoding="utf-8"))
    assert got == budget.data(), "rigenera con: python tools/build/budget.py"


def test_every_mod_has_a_budget():
    assert set(budget.data()["mods"]) == {p.parent.name for p in (ROOT / "mods").glob("*/mod.json")}


def test_selected_mods_fit_the_memory_limits():
    mods = budget.data()["mods"].values()
    for key in ("modarea", "kit", "project", "sec7"):
        assert sum(m[key] for m in mods) <= budget.LIMITS[key], key
