"""Registro delle risorse condivise tra le mod (OS 1.42): chi usa cosa.

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
    (0x5000, 0x5800, "dual-mono", "dualmono2.c; header read by fx3 at +0x5000 (dualmono_layout.py)"),
    (0x5800, 0x6700, "sy-fm4", "main CPU side: pages, algorithm drawings, page 1/3 names"),
    (0x6700, 0x6D00, "xparams", "table (xparams_layout.TABLE), storage tables, sound loader, shared RAM publisher"),
    (0x6D00, 0x7000, "cpu-meter", "code and data: audio interrupt load on screen (diagnostic)"),
    (0x7000, 0x7200, "projstore", "code, then the 256 bytes saved with the project"),
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
    (0x20000, 0x26000, "recorder", "planned: code and small data (PCM and large state in the OS heap)"),
    (0x26000, 0x2A000, "lfo3", "third LFO (Synfact port): engine (source of the SRAM copy), page, actions"),
    (0x2A000, 0x32000, "xstore", "planned: Sound shadow and pattern locks of LFO3, shared with arp (codec, matrix, events, banks)"),
    (0x32000, 0x38000, "arp", "planned: arpeggiator (cells in the OS heap)"),
    (0x38000, 0x3E000, "poly", "planned: POLY with its native kernels"),
    (0x3E000, 0x3FFF0, "idspace", "code; descriptors, object definitions and pages the mods write (idspace_layout)"),
    # 512 KB area from 2026-11-06: the second half is runtime RAM only (zeroed by the loader)
    (0x40000, 0x48000, "idspace", "parameter ids above 504: descriptor table copy (537 x 52 B), extra parameter objects, extra pages"),
    # 0x48000..0x7FFF0: free (runtime RAM only)
]

# ---- mod con spazio prenotato ma non ancora scritte (port di Synfact, piano 2026-11-05): ammesse come proprietarie
PLANNED = {"recorder", "xstore", "arp", "poly"}

# ---- tabella dei moduli di sfcore (area mod + SFCORE_TABLE): posto -> mod. sfcore li inizializza in quest'ordine.
SFCORE_TABLE, SFCORE_N = 0x1B000, 8
SFCORE_SLOTS = {0: "modulation-skip", 1: "xstore", 2: "recorder", 3: "lfo3", 4: "arp", 5: "poly"}

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
    (0x800, 0x1000, "OS", "boot-time upload window"),
]

# ---- vparams: posto nella tabella -> (mod, id)
VPARAMS_SLOTS = {
    **{s: ("master-comp", 262 + s) for s in range(7)},
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
    **{i: ("master-comp", "compressor") for i in range(262, 269)},
    513: ("fx3", "external input SND3 (idspace)"),
    **{190 + k: ("sy-fm4", f"SYN page 1/3 {n} (SY TONE's {w}, renamed)") for k, (n, w) in enumerate(
        (("TUNE", "TUNE"), ("RAT2", "RATIO"), ("LEV2", "MOD"), ("FDBK", "FDBK"), ("DEC2", "MENV"), ("PNCH", "PNCH"),
         ("OVER", "OVER"), ("DEC1", "DEC")))},
    **{254 + k: ("sy-fm4", f"SYN {p} {n} (was Digitakt MIDI CC{k + 1} Value, MIDI CC cleared)")
       for k, (n, p) in enumerate((("ALGO", "pages 2/3 and 3/3"), *((n, "page 2/3") for n in (
           "RAT3", "LEV3", "DEC3", "RAT4", "LEV4", "DEC4", "DET"))))},
    **{497 + k: ("sampler", f"SAMPLER knob {n} (was SP TWINSHOT {w})") for k, (n, w) in enumerate(
        (("A TUNE", "TUN1"), ("B PLAY", "SMP1"), ("C BR", "FLT1"), ("G LOOP/BARS/GRID, lix 0x18", "MIX"),
         ("E STRT/SEG/SLICE", "TUN2"), ("F LEN/MODE", "SMP2"), ("H LEV, lix 0x19 (the machine type in lix 0x1A, set from the machine menu)", "OVER"),
         ("D SAMP, lix 0x15", "DEC1")))},
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
    L = ["# Shared resources (OS 1.42)",
         "",
         "Generated from `tools/build/registry.py` (`python tools/build/registry.py`); `tests/test_registry.py` checks "
         "every `patch.json` against it. **A new mod claims its space there first.**",
         "",
         f"## Mod area (RAM `{modarea_layout.RAM:#010x}`, offsets)",
         "",
         "| From | To | Mod | Use |", "|---|---|---|---|"]
    rows = [(a, b, who, use) for a, b, who, use in MODAREA] + [(a, b, "**free**", "") for a, b in free_modarea()]
    L += [f"| {h(a)} | {h(b)} | {who} | {use} |" for a, b, who, use in sorted(rows)]
    L += ["", f"Boot list (`+{modarea_layout.BOOT_LIST:#06x}`, {modarea_layout.BOOT_N} pointers called after unpacking): "
          + ", ".join(f"slot {s} {who}" for s, who in sorted(BOOT_SLOTS.items())) + ".",
          "", f"sfcore module table (`+{SFCORE_TABLE:#06x}`, {SFCORE_N} pointers, initialized in this order): "
          + ", ".join(f"slot {s} {who}" for s, who in sorted(SFCORE_SLOTS.items())) + ".",
          "", "Planned (space claimed, code not written yet): " + ", ".join(sorted(PLANNED)) + ".",
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
