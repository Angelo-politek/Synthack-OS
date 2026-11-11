"""Registro delle risorse condivise tra le mod (OS 1.42): chi usa cosa.

Una mod nuova prende qui il suo spazio, prima di scrivere codice; tests/test_registry.py controlla che i
patch.json rispettino il registro e docs/registry.md ne e' la copia leggibile:

    python tools/build/registry.py            # rigenera docs/registry.md

Indirizzi: offset nell'area mod (RAM a modarea_layout.RAM), indirizzi assoluti per la sezione 3.

Le mod nuove non toccano questo file: prenotano in mods/<nome>/claims.json (vedi CLAIMS piu' sotto), cosi' due
richieste di mod diverse non modificano lo stesso file. Qui restano le mod che c'erano prima del 2026-11-09.
"""

from __future__ import annotations

import json
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
    (0x5000, 0x5800, "dual-mono", "dualmono2.c; header read by fx3 at +0x5000 (dualmono_layout.py)"),
    (0x5800, 0x6700, "sy-fm4", "main CPU side: pages, algorithm drawings, page 1/3 names"),
    (0x6700, 0x6DC0, "xparams", "table (xparams_layout.TABLE), storage tables, sound loader, shared RAM publisher"),
    (0x6DC0, 0x7000, "cpu-meter", "code and data: audio interrupt load on screen (diagnostic)"),
    (0x7000, 0x7200, "projstore", "code (the bytes saved with the project: +0x58000)"),
    (0x7200, 0x7400, "kitstore", "code"),
    (0x7400, 0x7420, "modarea", "boot list: 8 pointers, called after unpacking (BOOT_SLOTS)"),
    (0x7420, 0x7E00, "syn-pages", "machine table (synpages_layout.TABLE), SRC view: pages, titles, drawing"),
    (0x7E00, 0x8000, "vparams", "code"),
    (0x8000, 0x8180, "vparams", "table: 32 entries of 12 B, one per virtual parameter (VPARAMS_SLOTS)"),
    (0x8180, 0xA000, "modulation-skip", "code (Synfact port), shadow of the machine data; hot data in SRAM (SRAM)"),
    (0xA000, 0xDFF0, "fx3", "code and data"),
    (0xDFF0, 0xF000, "fx3", "delay line (+0xE000, 4 KB); +0xDFF0..+0xE000 unused since 2026-11-05"),
    (0xF000, 0xFFF0, "fastmix", "code and data: faster OS audio routines"),
    (0xFFF0, 0x18000, "long-samples", "Synfact HZFS storage, plan and upload of long samples (GPL-2.0-or-later)"),
    (0x18000, 0x1B000, "sampler", "main CPU side: pages, sample menu, one list of samples, knob graphics, waveform, value texts, tempo"),
    (0x1B000, 0x1B020, "sfcore", "module table: 8 pointers to Synfact module descriptors, written by each port (SFCORE_SLOTS)"),
    (0x1B040, 0x1FFF0, "sfcore", "Synfact core subset: event bus, adapters, native transactions, host API (GPL-2.0-or-later)"),
    # 256 KB area from 2026-11-05: the Synfact ports, claimed before their code exists (port plan)
    (0x20000, 0x26000, "recorder", "Synfact recorder port: code and data (PCM in the OS heap)"),
    (0x26000, 0x2A000, "lfo3", "third LFO (Synfact port): engine (source of the SRAM copy), page, actions"),
    (0x32000, 0x38000, "arp", "arpeggiator (Synfact port): code and data"),
    (0x38000, 0x3E000, "poly", "POLY (Synfact port): groups, voice allocation, TRIG page 3 (GPL-2.0-or-later)"),
    (0x3E000, 0x3FFF0, "idspace", "code; descriptors, object definitions and pages the mods write (idspace_layout)"),
    # 512 KB area from 2026-11-06: the second half is runtime RAM only (zeroed by the loader)
    (0x40000, 0x4C000, "idspace", "runtime: descriptor table copy (569 x 52 B), mod parameter objects, packed LFO DEST rows (+0xA000)"),
    (0x4C000, 0x58000, "recorder", "BSS of the recorder (runtime RAM only, zeroed by the loader)"),
    (0x58000, 0x58200, "projstore", "the bytes saved with the project (projstore_layout: SIZE, PARTS)"),
    (0x58200, 0x5C000, "arp", "BSS of the arpeggiator (runtime RAM only, zeroed by the loader)"),
    # 0x5C000..0x7FFF0: free (runtime RAM only)
]

# ---- mod con spazio prenotato ma non ancora scritte (port di Synfact, piano 2026-11-05): ammesse come proprietarie
PLANNED: set[str] = set()

# ---- tabella dei moduli di sfcore (area mod + SFCORE_TABLE): posto -> mod. sfcore li inizializza in quest'ordine.
SFCORE_TABLE, SFCORE_N = 0x1B000, 8
SFCORE_SLOTS = {0: "modulation-skip", 1: "about", 2: "recorder", 3: "lfo3", 4: "arp", 5: "poly", 6: "sample-manager"}

# ---- SRAM interna della CPU #1 (0x80000000): code che l'avvio stock azzera (0x4000045C) e che nessun operando
# assoluto della 1.42 usa (tests/test_sfcore.py controlla che l'OS non le legga ne' scriva). Dati e codice qui non
# mancano mai la cache (tools/emu/cycles.py). Fine esclusa.
SRAM = [
    (0x8000_7330, 0x8000_7780, "lfo3", "copy of the LFO3 kernel (render.s) from +0x10"),
    (0x8000_7780, 0x8000_8000, "modulation-skip", "destinations: address, value before and after (6 B each)"),
    (0x8000_F860, 0x8000_FC20, "lfo3", "LFO3 state, RNG and parameter bank (944 B) from +0x10"),
    (0x8000_FC20, 0x8001_0000, "modulation-skip", "state, input tables, destination bitmap"),
]
SRAM_FREE = [(0x8000_7330, 0x8000_8000), (0x8000_F860, 0x8001_0000)]

# ---- sezione 3, riempimento del linker 0x40339740..0x4033A000 (byte a zero non usati dall'OS)
SEC3_FREE = (0x4033_9740, 0x4033_A000)
SEC3_FILL = [
    (0x4033_9740, 0x4033_9BE0, "splash", "code, logo, animation entries"),
    (0x4033_9BE0, 0x4033_9D80, "dual-mono", "dualmono.S (input VCAs, names)"),
    (0x4033_9D80, 0x4033_A000, "modarea", "mod-area loader"),
]

# ---- zone che sembrano libere (a zero nello stock) ma che l'OS legge: mai da usare come spazio libero
SEC3_NOT_FREE = [
    (0x402A_BC3C, 0x402C_BC3C, "two 128x128 tables of longs read by 0x400AD480 (conversion of loaded "
                               "sounds/kits); rows are zero but read"),
]

# ---- area dei motori sulla CPU #2 (mods/modarea7, RAM a engine_layout.RAM): (inizio, fine) come offset
ENGINE = [
    (0x0000, 0x4000, "sy-fm4", "voice engine (engine 4) and its state"),
    (0x4000, 0x20000, "sampler", "voice engine (engine 11), interpolation table, zero-crossing grids"),
    (0x20000, 0x20400, "long-samples", "runtime receiver of long samples (engine/rx.c), end of the audio interrupt"),
]

# ---- lista di avvio dell'area mod: posto -> mod (modarea_layout.boot_slot)
BOOT_SLOTS = {0: "sy-fm4", 1: "sampler", 2: "xparams", 3: "sfcore", 4: "idspace"}

# ---- RAM condivisa tra le CPU: offset (CPU #1 a 0x10000000 + offset, CPU #2 a offset). Fine esclusa.
SHARED_RAM = [
    (0x000, 0x1B0, "OS", "voice frames: 0x1B0 B from 0x80002000 every block (eDMA ch. 47)"),
    (0x1B0, 0x5B0, "OS", "voice output: 8 x 32 x int32 back to CPU #1"),
    (0x5B0, 0x630, "sampler", "waveform: request +0x5B0, slot +0x5B4, columns done +0x5B6, length +0x5B8, "
                              "address +0x5BC, 112 peaks +0x5C0"),
    (0x640, 0x6E0, "xparams", "machine words, logical indices 0x11..0x1a of each digital track as set (locks applied, not smoothed), 20 B a track"),
    (0x700, 0x780, "xparams", "logical indices 0x36..0x3d of each digital track, locks applied (sy-fm4 pages 2/3 and 3/3, sampler knob H)"),
    (0x780, 0x7C8, "long-samples", "the project's list of long samples: 'LSM1' +0x780, count +0x784, 64 positions "
                                   "+0x788 (index in the CPU #2 table, 0xFF = empty), read by the SAMPLER engine"),
    (0x7F0, 0x7F4, "sampler", "tempo, BPM x 120"),
    (0x800, 0x1000, "OS", "boot-time upload window; after boot 0x800..0xC00 is long-samples' runtime upload "
                          "window (Synfact's: request +0x800, answer +0x818, data +0x820)"),
]

# ---- vparams: posto nella tabella -> (mod, id)
VPARAMS_SLOTS = {
    **{s: ("master-comp", 514 + s) for s in range(7)},
    7: ("fx3", 513),
    8: ("fx3", 144),
    **{9 + n: ("fx3", pid) for n, pid in enumerate((505, 506, 507, 509, 510, 511, 508, 512))},
    17: ("dual-mono", 129),
    18: ("dual-mono", 130),
}

# ---- id dei parametri che una mod rinomina, rende virtuali o di cui cambia il comportamento
IDS = {
    47: ("perf-fx", "QNT (Mod A DEST): quantized retrig, Retrig page"),
    **{i: ("perf-fx", f"Perf FX {i - 47} (Mod A M{i - 47})") for i in range(48, 52)},
    72: ("fx3", "SND3 (amp \"Delay Time\", saved per track)"),
    125: ("dual-mono", "IN R: alias of BAL"),
    144: ("fx3", "FX track SND3, FX track AMP page (was hidden FX amp \"Delay Time\", NRPN cleared)"),
    129: ("dual-mono", "DEL: R side while the IN R page is open"),
    130: ("dual-mono", "REV: R side while the IN R page is open"),
    **{i: ("fx3", "FX3 page (idspace)") for i in range(505, 513)},
    **{i: ("master-comp", "compressor (idspace)") for i in range(514, 521)},
    513: ("fx3", "external input SND3 (idspace)"),
    **{190 + k: ("sy-fm4", f"SYN page 1/3 {n} (SY TONE's {w}, renamed)") for k, (n, w) in enumerate(
        (("TUNE", "TUNE"), ("RAT2", "RATIO"), ("LEV2", "MOD"), ("FDBK", "FDBK"), ("DEC2", "MENV"), ("PNCH", "PNCH"),
         ("OVER", "OVER"), ("DEC1", "DEC")))},
    **{521 + k: ("sy-fm4", f"SYN {p} {n} (idspace)")
       for k, (n, p) in enumerate((("ALGO", "pages 2/3 and 3/3"), *((n, "page 2/3") for n in (
           "RAT3", "LEV3", "DEC3", "RAT4", "LEV4", "DEC4", "DET"))))},
    **{530 + k: ("lfo3", f"LFO3 page {n} (idspace, index {0x3E + k:#x})") for k, n in enumerate(
        ("SPD", "MULT", "FADE", "DEST", "WAVE", "SPH", "MODE", "DEP"))},
    529: ("sampler", "knob H of page 2/2 (index 0x36) as an LFO destination (idspace)"),
    **{497 + k: ("sampler", f"SAMPLER knob {n} (was SP TWINSHOT {w})") for k, (n, w) in enumerate(
        (("A TUNE", "TUN1"), ("B PLAY", "SMP1"), ("C BR", "FLT1"), ("G LOOP/BARS/GRID, lix 0x18", "MIX"),
         ("E STRT/SEG/SLICE", "TUN2"), ("F LEN/MODE", "SMP2"), ("H LEV, lix 0x19 (the machine type in lix 0x1A, set from the machine menu)", "OVER"),
         ("D SAMP, lix 0x15", "DEC1")))},
}

# ---- pagine dell'interfaccia (indice -> mod) riusate
# ---- voci in piu' del menu DEST degli LFO (idspace_layout.DESTX): posto -> mod
DESTX_SLOTS = {**{k: "sy-fm4" for k in range(13)}, 13: "sampler", **{k: "fx3" for k in range(14, 20)},
               **{k: "idspace" for k in range(20, 24)}}       # 20..23: external input on the FX track's LFOs

PAGES = {25: ("fx3", "REVERB page 2 (was OB8)"), 37: ("dual-mono", "IN R in the MIXER tab (idspace page)"),
         38: ("lfo3", "third page of the LFO tab (idspace page)")}


# ---- prenotazioni per mod: mods/<nome>/claims.json, tutte le chiavi facoltative
#   "modarea":    [["0x2A000", "0x2A800", "code and data"], ...]   offset nell'area mod, dentro COMMUNITY (codice e
#                                                                  dati nell'immagine) o COMMUNITY_RAM (solo RAM)
#   "engine":     [["0x21000", "0x22000", "voice engine"], ...]    offset nell'area dei motori (CPU #2)
#   "shared_ram": [["0x7C8", "0x7D0", "..."], ...]                 offset nella RAM condivisa tra le CPU
#   "boot_slot":  5                                                posto nella lista di avvio
#   "ids":        {"540": "CUT (idspace)"}                         id dei parametri (505..568 per quelli nuovi)
#   "pages":      {"39": "..."}                                    pagine
#   "vparams":    {"19": 540}                                      posto di vparams -> id
#   "destx":      [20, 21]                                         voci in piu' del menu DEST degli LFO
COMMUNITY = (0x2A000, 0x32000)
COMMUNITY_RAM = (0x5C000, 0x7FFF0)
CLAIM_KEYS = {"modarea", "engine", "shared_ram", "boot_slot", "ids", "pages", "vparams", "destx"}


class ClaimError(ValueError):
    pass


def read_claims(mods_dir: Path) -> dict[str, dict]:
    out = {}
    for f in sorted(Path(mods_dir).glob("*/claims.json")):
        c = json.loads(f.read_text(encoding="utf-8"))
        if not isinstance(c, dict) or set(c) - CLAIM_KEYS:
            raise ClaimError(f"{f}: chiavi ammesse {sorted(CLAIM_KEYS)}")
        out[f.parent.name] = c
    return out


def merge_claims(claims: dict[str, dict]) -> None:
    """Aggiunge le prenotazioni delle mod alle tabelle; ClaimError se una risorsa e' gia' presa."""
    def take(table: dict, key, value, who: str, what: str) -> None:
        if key in table:
            other = table[key][0] if isinstance(table[key], tuple) else table[key]
            raise ClaimError(f"{who}: {what} {key} is taken by {other}")
        table[key] = value

    def ranges(table: list, rows, who: str, what: str, zones=None) -> None:
        for lo, hi, use in rows:
            a, b = int(lo, 16), int(hi, 16)
            if not a < b:
                raise ClaimError(f"{who}: {what} {lo}..{hi} is empty")
            if zones and not any(z0 <= a and b <= z1 for z0, z1 in zones):
                raise ClaimError(f"{who}: {what} {lo}..{hi} is outside the zones for new mods "
                                 + ", ".join(f"{z0:#x}..{z1:#x}" for z0, z1 in zones))
            for x, y, other, _ in table:
                if a < y and x < b:
                    raise ClaimError(f"{who}: {what} {lo}..{hi} overlaps {other} ({x:#x}..{y:#x})")
            table.append((a, b, who, use))

    for who, c in claims.items():
        ranges(MODAREA, c.get("modarea", []), who, "mod area", (COMMUNITY, COMMUNITY_RAM))
        ranges(ENGINE, c.get("engine", []), who, "engine area")
        ranges(SHARED_RAM, c.get("shared_ram", []), who, "shared RAM")
        if "boot_slot" in c:
            take(BOOT_SLOTS, int(c["boot_slot"]), who, who, "boot slot")
        for pid, use in c.get("ids", {}).items():
            take(IDS, int(pid), (who, use), who, "parameter id")
        for page, use in c.get("pages", {}).items():
            take(PAGES, int(page), (who, use), who, "page")
        for slot, pid in c.get("vparams", {}).items():
            take(VPARAMS_SLOTS, int(slot), (who, int(pid)), who, "vparams slot")
        for k in c.get("destx", []):
            take(DESTX_SLOTS, int(k), who, who, "DEST entry")


CLAIMS = read_claims(Path(__file__).resolve().parents[2] / "mods")
merge_claims(CLAIMS)


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
    L = ["# Shared resources (OS 1.42)",
         "",
         "Generated from `tools/build/registry.py` (`python tools/build/registry.py`); `tests/test_registry.py` checks "
         "every `patch.json` against it. **A new mod claims its space there first.**",
         "",
         f"## Mod area (RAM `{modarea_layout.RAM:#010x}`, offsets)",
         "",
         "| From | To | Mod | Use |", "|---|---|---|---|"]
    zone = lambda a, b: ("for new mods: code and data" if COMMUNITY[0] <= a and b <= COMMUNITY[1] else
                         "for new mods: runtime RAM only" if COMMUNITY_RAM[0] <= a and b <= COMMUNITY_RAM[1] else "")
    rows = [(a, b, who, use) for a, b, who, use in MODAREA] + [(a, b, "**free**", zone(a, b)) for a, b in free_modarea()]
    L += [f"| {h(a)} | {h(b)} | {who} | {use} |" for a, b, who, use in sorted(rows)]
    L += ["", f"Boot list (`+{modarea_layout.BOOT_LIST:#06x}`, {modarea_layout.BOOT_N} pointers called after unpacking): "
          + ", ".join(f"slot {s} {who}" for s, who in sorted(BOOT_SLOTS.items())) + ".",
          "", f"sfcore module table (`+{SFCORE_TABLE:#06x}`, {SFCORE_N} pointers, initialized in this order): "
          + ", ".join(f"slot {s} {who}" for s, who in sorted(SFCORE_SLOTS.items())) + ".",
          "", "New mods claim in `mods/<name>/claims.json` (keys: " + ", ".join(f"`{k}`" for k in sorted(CLAIM_KEYS))
          + "), inside the free zones marked for new mods. `python tools/new_mod.py <name>` writes it.",
          "", "## SRAM (CPU #1, internal: never a cache miss)", "",
          "Free tails that the stock boot zeroes: " + ", ".join(f"`{a:#010x}–{b:#010x}`" for a, b in SRAM_FREE) + ".",
          "", "| From | To | Mod | Use |", "|---|---|---|---|"]
    L += [f"| {h(a)} | {h(b)} | {who} | {use} |" for a, b, who, use in SRAM]
    L += ["",
          "", "## Engine area (CPU #2, `mods/modarea7`, RAM `0x47000000`, offsets)", "",
          "| From | To | Mod | Use |", "|---|---|---|---|"]
    L += [f"| {h(a)} | {h(b)} | {who} | {use} |" for a, b, who, use in sorted(ENGINE)]
    L += ["", "## Shared RAM (CPU #1 at `0x10000000` + offset, CPU #2 at offset)", "",
          "| From | To | Owner | Use |", "|---|---|---|---|"]
    L += [f"| {h(a)} | {h(b)} | {who} | {use} |" for a, b, who, use in sorted(SHARED_RAM)]
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
    L += ["", "Ids without a page often carry a MIDI CC or are aliases: clear the CC, check aliases. Ids above 504 do "
          "not exist. "
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
