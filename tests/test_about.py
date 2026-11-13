"""about (mods/about): la riga SYNTHACK del menu delle impostazioni e il suo elenco."""

import importlib.util
import json
import struct
import sys
from pathlib import Path

import pytest

pytest.importorskip("unicorn")

ROOT = Path(__file__).resolve().parents[1]
SY = ROOT / "firmware" / "Syntakt_OS1.42.syx"
MOD = ROOT / "mods" / "about"
PATCH = MOD / "patch.json"
needs_os = pytest.mark.skipif(not SY.exists() or not PATCH.exists(), reason="OS stock o patch.json assente")
sys.path[:0] = [str(ROOT / "tools" / "emu"), str(ROOT / "tools" / "build"), str(ROOT / "tools" / "unpack")]
LOAD = 0x4000_0400


def make_patch():
    spec = importlib.util.spec_from_file_location("about_make_patch", MOD / "make_patch.py")
    mp = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mp)
    return mp


def symbols():
    return {k: int(v, 16) for k, v in json.loads(PATCH.read_text(encoding="utf-8"))["symbols"].items()}


def test_generated_rows_are_current():
    """about_data.h segue le schede delle mod, il registro e la versione dello splash: rigenerarlo con make_patch.py."""
    mp = make_patch()
    assert (MOD / "about_data.h").read_text(encoding="utf-8") == mp.header()
    rows = mp.rows()
    assert f'#define VERSION "{mp.version()}"' in mp.header()
    assert all(len(t) <= mp.WIDTH for _, t, _, _ in rows)
    mods = [(t, st) for k, t, st, p in rows if k == "M"]
    assert len(mods) >= 12 and ("SY FM4", 1) in mods and not any("ABOUT" in t for t, _ in mods)
    assert {st for _, st in mods} == {0, 1, 2}
    assert [t for k, t, _, _ in rows if k == "H"] == ["MODS IN THIS BUILD", "SOURCE", "CREDITS"]


@needs_os
def test_hook_site_and_module_slot():
    import eft
    import modarea_layout as M
    import registry
    spec = json.loads(PATCH.read_text(encoding="utf-8"))
    sym = symbols()
    sec3 = eft.unpack(SY, ROOT / "unpacked" / SY.stem, ids=[3])[3].read_bytes()
    assert sec3[0x4005_F176 - LOAD:0x4005_F17C - LOAD].hex() == "205248780002"       # movea.l (a2),a0 ; pea 2.w
    hook = next(p for p in spec["patches"] if p["addr"].upper() == "0X4005F176")
    assert hook["hex"] == f"4ef9{sym['about_settings']:08x}"
    slot = next(s for s, who in registry.SFCORE_SLOTS.items() if who == "about")
    entry = next(p for p in spec["patches"] if p.get("ram") == f"{M.RAM + registry.SFCORE_TABLE + 4 * slot:#010x}")
    assert entry["hex"] == f"{sym['about_module']:08x}"


@needs_os
def test_list_shows_only_the_mods_of_the_build():
    """Una mod che non e' nella build ha zeri all'inizio del suo spazio: la sua riga non compare."""
    import screens
    mp = make_patch()
    probes = [(t, p) for _, t, _, p in mp.rows() if p]
    few = screens.UI(["splash", "about", "fx3"])
    few.call(few.sym["sfcore_bind"])
    assert few.long(few.sym["sfcore_status"] + 4) == 1                         # legata da sfcore, posto 1
    there = {t for t, p in probes if few.long(p)}
    assert any(t.startswith("THIRD SEND FX") for t in there) and not any(t.startswith("ARPEGGIATOR") for t in there)
    every = screens.UI(sorted(p.parent.name for p in ROOT.glob("mods/*/mod.json") if p.parent.name != "mod-zero"))
    assert all(every.long(p) for _, p in probes), [t for t, p in probes if not every.long(p)]


@needs_os
def test_list_is_drawn_and_takes_the_keys(tmp_path):
    import screens
    ui = screens.UI(["splash", "about", "fx3", "sy-fm4"])
    sym = symbols()
    first = ui.paint(sym["about_paint"])                                       # la copertina: il logo dello splash
    assert sum(bin(b).count("1") for b in first) > 400
    ui.put(sym["about_top"], ">I", 1)
    listed = ui.paint(sym["about_paint"])                                      # l'elenco: barra in alto invertita
    assert listed[0:16].count(0xFF) >= 12                                      # (riga in cima: quasi tutta accesa)
    screens.png(first, tmp_path / "about.png")
    ev = 0x4FE0_6000

    def key(code, down=1):
        ui.uc.mem_write(ev, bytes(12) + struct.pack(">II", code, down))
        return ui.call(sym["about_key"], [0, ev])
    assert key(15) == 0                                                         # chiuso: i tasti sono dell'OS
    ui.put(sym["about_open"], ">I", 1)
    ui.put(sym["about_top"], ">I", 0)
    assert key(15) == 1 and ui.long(sym["about_top"]) == 1                      # DOWN: dalla copertina all'elenco
    assert ui.paint(sym["about_paint"]) != first
    assert key(14) == 1 and ui.long(sym["about_top"]) == 0                      # UP
    assert key(5) == 1 and key(5, 0) == 1                                       # un altro tasto: nostro, col rilascio
    assert key(9) == 0 and key(11) == 0                                         # trasporto all'OS
    assert key(13) == 1 and ui.long(sym["about_open"]) == 0                     # NO chiude
    assert key(13, 0) == 1 and key(13, 0) == 0                                  # e il suo rilascio e' ancora nostro
