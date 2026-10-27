"""Registro delle risorse condivise tra le mod (OS 1.41): chi usa cosa.

Una mod nuova prende qui il suo spazio, prima di scrivere codice; tests/test_registry.py controlla che i
patch.json rispettino il registro e docs/registry.md ne e' la copia leggibile:

    python tools/build/registry.py            # rigenera docs/registry.md

Indirizzi: offset nell'area mod (RAM a modarea_layout.RAM), indirizzi assoluti per la sezione 3.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import kitstore_layout  # noqa: E402
import modarea_layout  # noqa: E402
import projstore_layout  # noqa: E402

# ---- area mod: (inizio, fine) come offset, proprietario, uso. Fine esclusa.
MODAREA = [
    (0x0000, 0x2000, "master-comp", "code and data"),
    (0x2000, 0x4000, "readable-values", "code and data"),
    (0x4000, 0x5000, "perf-fx", "code and data"),
    (0x5000, 0x7000, "dual-mono", "dualmono2.c; header read by fx3 at +0x5000 (dualmono_layout.py)"),
    (0x7000, 0x7200, "projstore", "code, then the 256 bytes saved with the project"),
    (0x7200, 0x7400, "kitstore", "code"),
    (0x7E00, 0x8000, "vparams", "code"),
    (0x8000, 0x8180, "vparams", "table: 32 entries of 12 B, one per virtual parameter (VPARAMS_SLOTS)"),
    (0xA000, 0xDFF0, "fx3", "code and data"),
    (0xDFF0, 0xF000, "fx3", "feedback (+0xDFFC) and delay line (+0xE000, 4 KB)"),
]

# ---- sezione 3, riempimento del linker 0x40338740..0x40339000 (byte a zero non usati dall'OS)
SEC3_FREE = (0x4033_8740, 0x4033_9000)
SEC3_FILL = [
    (0x4033_8740, 0x4033_8BE0, "splash", "code, logo, animation entries"),
    (0x4033_8BE0, 0x4033_8D80, "dual-mono", "dualmono.S (input VCAs, names)"),
    (0x4033_8D80, 0x4033_9000, "modarea", "mod-area loader"),
]

# ---- zone che sembrano libere (a zero nello stock) ma che l'OS legge: mai da usare come spazio libero
SEC3_NOT_FREE = [
    (0x402A_B8EC, 0x402C_B8EC, "two 128x128 tables of longs read by 0x400AD408 (conversion of loaded "
                               "sounds/kits); rows are zero but read"),
]

# ---- vparams: posto nella tabella -> (mod, id)
VPARAMS_SLOTS = {
    **{s: ("master-comp", 262 + s) for s in range(7)},
    7: ("fx3", 269),
    **{9 + n: ("fx3", pid) for n, pid in enumerate((246, 247, 248, 250, 251, 252, 249, 253))},
    17: ("dual-mono", 129),
    18: ("dual-mono", 130),
}

# ---- id dei parametri che una mod rinomina, rende virtuali o di cui cambia il comportamento
IDS = {
    47: ("perf-fx", "QNT (Mod A DEST): quantized retrig, Retrig page"),
    **{i: ("perf-fx", f"Perf FX {i - 47} (Mod A M{i - 47})") for i in range(48, 52)},
    72: ("fx3", "SND3 (amp \"Delay Time\", saved per track)"),
    125: ("dual-mono", "IN R: alias of BAL"),
    129: ("dual-mono", "DEL: R side while the IN R page is open"),
    130: ("dual-mono", "REV: R side while the IN R page is open"),
    **{i: ("fx3", "FX3 page") for i in range(246, 254)},
    **{i: ("master-comp", "compressor") for i in range(262, 269)},
    269: ("fx3", "external input SND3"),
}

# ---- pagine dell'interfaccia (indice -> mod) riusate
PAGES = {25: ("fx3", "REVERB page 2 (was OB8)"), 27: ("dual-mono", "IN R in the MIXER tab (was MIDI Source)")}


def modarea_owner(off: int) -> str | None:
    for a, b, who, _ in MODAREA:
        if a <= off < b:
            return who
    return None


def free_modarea() -> list[tuple[int, int]]:
    """Intervalli liberi dell'area mod (offset)."""
    out, pos = [], 0
    for a, b, _, _ in sorted(MODAREA):
        if a > pos:
            out.append((pos, a))
        pos = max(pos, b)
    if pos < modarea_layout.SIZE:
        out.append((pos, modarea_layout.SIZE))
    return out


def markdown() -> str:
    h = lambda v: f"`{v:#06x}`" if v < 0x10000 else f"`{v:#010x}`"
    L = ["# Shared resources (OS 1.41)",
         "",
         "Generated from `tools/build/registry.py` (`python tools/build/registry.py`); `tests/test_registry.py` checks "
         "every `patch.json` against it. **A new mod claims its space there first.**",
         "",
         f"## Mod area (RAM `{modarea_layout.RAM:#010x}`, offsets)",
         "",
         "| From | To | Mod | Use |", "|---|---|---|---|"]
    rows = [(a, b, who, use) for a, b, who, use in MODAREA] + [(a, b, "**free**", "") for a, b in free_modarea()]
    L += [f"| {h(a)} | {h(b)} | {who} | {use} |" for a, b, who, use in sorted(rows)]
    L += ["", f"## Section 3 free fill (`{SEC3_FREE[0]:#010x}–{SEC3_FREE[1]:#010x}`)", "",
          "| From | To | Mod | Use |", "|---|---|---|---|"]
    L += [f"| {h(a)} | {h(b)} | {who} | {use} |" for a, b, who, use in SEC3_FILL]
    L += ["", "## Zero in stock but read by the OS — not free", "", "| From | To | Why |", "|---|---|---|"]
    L += [f"| {h(a)} | {h(b)} | {why} |" for a, b, why in SEC3_NOT_FREE]
    L += ["", "Zero bytes are not free space: check that no code reads them (pointers, tables indexed from a nearby "
          "base) before using them, and register them here.", "", "## vparams slots", "",
          "| Slot | Mod | Id |", "|---|---|---|"]
    L += [f"| {s} | {who} | {pid} |" for s, (who, pid) in sorted(VPARAMS_SLOTS.items())]
    free_slots = [s for s in range(32) if s not in VPARAMS_SLOTS]
    L += [f"| {', '.join(map(str, free_slots))} | **free** | |", "", "## Parameter ids", "",
          "| Id | Mod | Use |", "|---|---|---|"]
    L += [f"| {i} | {who} | {use} |" for i, (who, use) in sorted(IDS.items())]
    L += ["", "Ids 254–261 (Digitakt MIDI CC values) are free but have MIDI CCs; ids above 504 do not exist. "
          "See [ui-parameters.md](ui-parameters.md#hidden-ids-used-by-the-mods).", "", "## Pages", "",
          "| Page | Mod | Use |", "|---|---|---|"]
    L += [f"| {p} | {who} | {use} |" for p, (who, use) in sorted(PAGES.items())]
    L += ["", "## Saved with the kit / project", "", "| Store | Mod | Slots |", "|---|---|---|"]
    L += [f"| kitstore | {who} | " + ", ".join(f"block {b} word {k}" for b, k in parts) + " |"
          for who, parts in kitstore_layout.PARTS.items()]
    L += [f"| projstore | {who} | {o}–{o + n} |" for who, (o, n) in projstore_layout.PARTS.items()]
    if not projstore_layout.PARTS:
        L += ["| projstore | — | 256 bytes, all free |"]
    return "\n".join(L) + "\n"


if __name__ == "__main__":
    out = Path(__file__).resolve().parents[2] / "docs" / "registry.md"
    out.write_text(markdown(), encoding="utf-8")
    print(f"scritto {out}")
