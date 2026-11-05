# modulation-skip

Skips the stock modulation matrix of the audio interrupt (CPU #1) in blocks where it would write the same values as in the last block. **Same output, bit for bit.** No UI, nothing saved. Port of Synfact's `modulation-skip-st` (GSM1980 and contributors, on elekloader by irpina), GPL-2.0-or-later.

## What changes

The OS runs its modulation `0x40097B74` (velocity and source modulation of every track) in every block: 6 614 instructions. Its output depends only on:

- the velocity and source tables: 45 longwords in SRAM;
- the machine data it reads: 13 × 24 longwords, written only by `0x400A313C` (Sound publication, machine change);
- the values of its destination words on entry.

When all three equal the last real run's, the mod writes that run's results and returns. Otherwise the OS routine runs and the mod records its results.

| Mode | Behavior |
|---|---|
| ON (the mod) | skips; every 64th block that could skip runs the OS routine and compares. The first difference turns it OFF: stock until the next boot. |
| VERIFY (`make_patch.py --verify <folder>`, diagnostic) | never skips; runs the OS routine every block and compares |

A line on the screen bottom, every other 4 s, only after a difference, OFF or in VERIFY: `MSKIP ON  H99 S98 E000` = mode, % of blocks with the same inputs, % skipped, differences.

## Changes from Synfact

| Synfact | Here |
|---|---|
| Sites written at run time | patched by the build: `0x40097B7C` (body after the prologue), `0x400A313C` (machine-data writer) |
| State in its RAM (DDR) | hot data in the internal SRAM: no cache miss in a skipped block ([registry](../../docs/registry.md), SRAM) |
| Check, then write | one pass: compare and write; a difference restores the written words and runs the OS routine |
| Destination list rebuilt on every run | rebuilt only when the machine data change |
| 4 KB byte map of destinations | 128-byte bitmap |

`[!]` The machine-data copy (1.2 KB) stays in the mod area: read only in blocks after a write and every 64th block.

## Cost

Cycles per block, emulator with the cache model ([tests/test_modulation_skip.py](../../tests/test_modulation_skip.py), scene `max`):

| Block | Cycles vs stock |
|---|---|
| skipped | −6 174 (−3.7 % of the block) |
| inputs changed: OS routine, then record | +2 594 (worst block) |
| every mod together, skipped block | 21 131 → 14 956 over stock (101.7 % → 98.0 %) |

Skipped share: steady sounds and patterns skip almost every block. A block skips only when velocity, LFO-driven tables, parameter values and machine data stayed put since the last block. In the emulator test with a change in one block of three: 52 of 400 skipped.

## Tests

[tests/test_modulation_skip.py](../../tests/test_modulation_skip.py): the whole interrupt with and without the mod, side by side, 400 blocks with random changes of velocity, source tables, destination values and machine data, then kit parameters set by the OS: SRAM identical after every block. An unknown writer turns the mod off. Cycles of a skipped and of a recomputed block.

## Device

1. Build with `--verify` and cpu-meter. Play a project with LFOs, velocity and p-locks for a session: the line must show `E000`.
2. Build the normal mod. Compare cpu-meter with and without it.
