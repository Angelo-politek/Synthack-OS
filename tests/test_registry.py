"""Registro delle risorse condivise (tools/build/registry.py): i patch.json di tutte le mod lo rispettano.

Senza firmware: nomi e dipendenze, area mod, riempimento della sezione 3, posti di vparams, id dei parametri,
zone "a zero ma lette", docs/registry.md aggiornato. Con l'OS stock: nessuna patch scrive su byte a zero fuori
dalle zone libere registrate (a zero non vuol dire libero).
"""

import json
import struct
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "tools" / "build"), str(ROOT / "tools" / "unpack")]
import engine_layout as EN  # noqa: E402
import idspace_layout as IL  # noqa: E402
import kitstore_layout as KS  # noqa: E402
import modarea_layout as MA  # noqa: E402
import registry as R  # noqa: E402

LOAD, DESC, N_IDS = 0x4000_0400, 0x4022_D83C, 505
VP_TABLE, VP_N = MA.RAM + 0x8000, 32
SY = ROOT / "firmware" / "Syntakt_OS1.42.syx"


def specs():
    out = {}
    for f in sorted((ROOT / "mods").glob("*/patch.json")):
        out[f.parent.name] = json.loads(f.read_text(encoding="utf-8"))
    return out


def patches(fixed=True):
    for name, sp in specs().items():
        for p in sp["patches"]:
            if bool(p.get("append")) != fixed:
                yield name, p, int(p["ram" if p.get("append") else "addr"], 16), p["len"]


def owners(ranges, a, b):
    return {who for lo, hi, who, _ in ranges if lo < b and a < hi}


def test_names_and_requires():
    sp = specs()
    for folder, s in sp.items():
        assert s["name"] == folder
        assert set(s.get("requires", [])) <= set(sp), (folder, s.get("requires"))


def test_allocations_disjoint_and_inside():
    for table, lo, hi in ((R.MODAREA, 0, MA.SIZE), (R.SEC3_FILL, *R.SEC3_FREE)):
        rows = sorted(table)
        assert all(lo <= a < b <= hi for a, b, _, _ in rows)
        assert all(x[1] <= y[0] for x, y in zip(rows, rows[1:]))
    assert all(who in specs() or who in R.PLANNED for _, _, who, _ in R.MODAREA + R.SEC3_FILL)
    assert not R.PLANNED & set(specs()), "una mod scritta non e' piu' in PLANNED"


def test_sram_inside_the_free_tails_and_disjoint():
    rows = sorted(R.SRAM)
    assert all(any(lo <= a < b <= hi for lo, hi in R.SRAM_FREE) for a, b, _, _ in rows)
    assert all(x[1] <= y[0] for x, y in zip(rows, rows[1:]))
    assert {w for *_, w, _ in rows} <= set(specs()) | R.PLANNED


def test_sram_writes_inside_own_space():
    """Patch che scrivono SRAM al caricamento non ce ne sono: le mod la riempiono a runtime. I simboli in SRAM che
    una mod esporta (patch.json, "sram") devono stare nel suo spazio."""
    for name, sp in specs().items():
        for sym, a in sp.get("sram", {}).items():
            a = int(a, 16)
            assert owners(R.SRAM, a, a + 1) == {name}, f"{name}: {sym} a {a:#x} fuori dal suo spazio in SRAM"


BOOT = MA.RAM + MA.BOOT_LIST
SFC = MA.RAM + R.SFCORE_TABLE


def test_mod_area_writes_inside_own_space():
    for name, p, ram, n in patches(fixed=False):
        if p["section"] == 7:
            off = ram - EN.RAM
            assert owners(R.ENGINE, off, off + n) == {name}, f"{name}: area motori {off:#x}..{off + n:#x} non sua"
        elif BOOT <= ram < BOOT + 4 * MA.BOOT_N:
            assert (ram - BOOT) % 4 == 0 and n == 4
            assert R.BOOT_SLOTS.get((ram - BOOT) // 4) == name, f"{name}: posto {(ram - BOOT) // 4} della lista di avvio"
        elif SFC <= ram < SFC + 4 * R.SFCORE_N:
            assert (ram - SFC) % 4 == 0 and n == 4
            assert R.SFCORE_SLOTS.get((ram - SFC) // 4) == name, f"{name}: posto {(ram - SFC) // 4} dei moduli sfcore"
        elif IL.EXT <= ram < IL.PAGEDEF:                         # idspace: descrittore o oggetto di un id
            base, size = (IL.EXT, 52) if ram < IL.OBJDEF else (IL.OBJDEF, 16)
            pid = IL.FIRST + (ram - base) // size
            assert (ram - base) % size == 0 and n == size
            assert R.IDS.get(pid, ("",))[0] == name, f"{name}: id {pid} (idspace) non registrato"
        elif IL.PAGEDEF <= ram < IL.PAGEDEF + 44 * IL.PAGE_N:     # idspace: pagine in piu'
            assert (ram - IL.PAGEDEF) % 44 == 0 and n == 44
            assert R.PAGES.get(IL.PAGE_FIRST + (ram - IL.PAGEDEF) // 44, ("",))[0] == name, f"{name}: pagina"
        elif VP_TABLE <= ram < VP_TABLE + 12 * VP_N:
            slot = (ram - VP_TABLE) // 12
            pid = struct.unpack(">H", bytes.fromhex(p["hex"])[:2])[0]
            assert (ram - VP_TABLE) % 12 == 0 and n == 12
            assert R.VPARAMS_SLOTS.get(slot) == (name, pid), f"{name}: vparams[{slot}] = id {pid} non registrato"
        else:
            off = ram - MA.RAM
            assert owners(R.MODAREA, off, off + n) == {name}, f"{name}: {off:#x}..{off + n:#x} fuori dal suo spazio"


def test_engine_area_and_boot_slots():
    rows = sorted(R.ENGINE)
    assert all(0 <= a < b <= EN.SIZE for a, b, _, _ in rows)
    assert all(x[1] <= y[0] for x, y in zip(rows, rows[1:]))
    used = {(ram - BOOT) // 4: name for name, p, ram, n in patches(fixed=False)
            if p["section"] == 3 and BOOT <= ram < BOOT + 4 * MA.BOOT_N}
    assert used == R.BOOT_SLOTS
    assert set(R.BOOT_SLOTS.values()) | {w for *_, w, _ in R.ENGINE} <= set(specs())
    mods = {(ram - SFC) // 4: name for name, p, ram, n in patches(fixed=False)
            if p["section"] == 3 and SFC <= ram < SFC + 4 * R.SFCORE_N}
    assert mods == {s: w for s, w in R.SFCORE_SLOTS.items() if w in specs()}
    assert set(R.SFCORE_SLOTS.values()) <= set(specs()) | R.PLANNED


def test_shared_ram_disjoint():
    """RAM condivisa tra le CPU: intervalli disgiunti dentro i 4 KB in uso, di mod esistenti o dell'OS."""
    rows = sorted(R.SHARED_RAM)
    assert all(0 <= a < b <= 0x1000 for a, b, _, _ in rows)
    assert all(x[1] <= y[0] for x, y in zip(rows, rows[1:]))
    assert {w for *_, w, _ in rows} - {"OS"} <= set(specs())


def test_vparams_slots_all_used_as_registered():
    used = {}
    for name, p, ram, n in patches(fixed=False):
        if VP_TABLE <= ram < VP_TABLE + 12 * VP_N:
            used[(ram - VP_TABLE) // 12] = (name, struct.unpack(">H", bytes.fromhex(p["hex"])[:2])[0])
    assert used == R.VPARAMS_SLOTS


def test_free_fill_writes_inside_own_space():
    lo, hi = R.SEC3_FREE
    for name, p, a, n in patches():
        if p["section"] == 3 and a < hi and lo < a + n:
            assert owners(R.SEC3_FILL, a, a + n) == {name}, f"{name}: {a:#x} nel riempimento libero fuori dal suo spazio"


def test_nothing_in_zones_the_os_reads():
    for name, p, a, n in patches():
        if p["section"] == 3:
            for lo, hi, why in R.SEC3_NOT_FREE:
                assert not (a < hi and lo < a + n), f"{name}: {a:#x} dentro {lo:#x}..{hi:#x} ({why})"


def test_descriptor_patches_belong_to_the_owner_of_the_id():
    for name, p, a, n in patches():
        if p["section"] == 3 and a < DESC + 52 * N_IDS and DESC < a + n:
            for i in range((a - DESC) // 52, (a + n - 1 - DESC) // 52 + 1):
                assert R.IDS.get(i, (None,))[0] == name, f"{name}: descrittore dell'id {i} non registrato"


def test_kit_and_project_slices():
    for store, parts in (("kitstore", KS.PARTS),):
        seen = {}
        for who, slots in parts.items():
            assert who in specs(), (store, who)
            for s in slots:
                assert s not in seen, f"{store}: {s} di {who} e {seen[s]}"
                seen[s] = who


def test_docs_in_sync():
    doc = (ROOT / "docs" / "registry.md").read_text(encoding="utf-8")
    assert doc == R.markdown(), "docs/registry.md non aggiornato: python tools/build/registry.py"


@pytest.mark.skipif(not SY.exists(), reason="OS stock assente")
def test_zero_bytes_are_not_free_space():
    """Una patch che sostituisce un tratto di zeri dello stock deve stare in una zona libera registrata."""
    import eft
    sec3 = eft.unpack(SY, ROOT / "unpacked" / SY.stem, ids=[3])[3].read_bytes()
    lo, hi = R.SEC3_FREE
    for name, p, a, n in patches():
        if p["section"] != 3 or n < 16:
            continue
        old = sec3[a - LOAD:a - LOAD + n]
        if not any(old):
            assert lo <= a and a + n <= hi, f"{name}: {a:#x} ({n} B a zero) non e' una zona libera registrata"
