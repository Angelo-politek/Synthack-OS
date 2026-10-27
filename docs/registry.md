# Shared resources (OS 1.41)

Generated from `tools/build/registry.py` (`python tools/build/registry.py`); `tests/test_registry.py` checks every `patch.json` against it. **A new mod claims its space there first.**

## Mod area (RAM `0x444e38d0`, offsets)

| From | To | Mod | Use |
|---|---|---|---|
| `0x0000` | `0x2000` | master-comp | code and data |
| `0x2000` | `0x4000` | readable-values | code and data |
| `0x4000` | `0x5000` | perf-fx | code and data |
| `0x5000` | `0x7000` | dual-mono | dualmono2.c; header read by fx3 at +0x5000 (dualmono_layout.py) |
| `0x7000` | `0x7200` | projstore | code, then the 256 bytes saved with the project |
| `0x7200` | `0x7400` | kitstore | code |
| `0x7400` | `0x7e00` | **free** |  |
| `0x7e00` | `0x8000` | vparams | code |
| `0x8000` | `0x8180` | vparams | table: 32 entries of 12 B, one per virtual parameter (VPARAMS_SLOTS) |
| `0x8180` | `0xa000` | **free** |  |
| `0xa000` | `0xdff0` | fx3 | code and data |
| `0xdff0` | `0xf000` | fx3 | feedback (+0xDFFC) and delay line (+0xE000, 4 KB) |
| `0xf000` | `0xfff0` | **free** |  |

## Section 3 free fill (`0x40338740–0x40339000`)

| From | To | Mod | Use |
|---|---|---|---|
| `0x40338740` | `0x40338be0` | splash | code, logo, animation entries |
| `0x40338be0` | `0x40338d80` | dual-mono | dualmono.S (input VCAs, names) |
| `0x40338d80` | `0x40339000` | modarea | mod-area loader |

## Zero in stock but read by the OS — not free

| From | To | Why |
|---|---|---|
| `0x402ab8ec` | `0x402cb8ec` | two 128x128 tables of longs read by 0x400AD408 (conversion of loaded sounds/kits); rows are zero but read |

Zero bytes are not free space: check that no code reads them (pointers, tables indexed from a nearby base) before using them, and register them here.

## vparams slots

| Slot | Mod | Id |
|---|---|---|
| 0 | master-comp | 262 |
| 1 | master-comp | 263 |
| 2 | master-comp | 264 |
| 3 | master-comp | 265 |
| 4 | master-comp | 266 |
| 5 | master-comp | 267 |
| 6 | master-comp | 268 |
| 7 | fx3 | 269 |
| 9 | fx3 | 246 |
| 10 | fx3 | 247 |
| 11 | fx3 | 248 |
| 12 | fx3 | 250 |
| 13 | fx3 | 251 |
| 14 | fx3 | 252 |
| 15 | fx3 | 249 |
| 16 | fx3 | 253 |
| 17 | dual-mono | 129 |
| 18 | dual-mono | 130 |
| 8, 19, 20, 21, 22, 23, 24, 25, 26, 27, 28, 29, 30, 31 | **free** | |

## Parameter ids

| Id | Mod | Use |
|---|---|---|
| 47 | perf-fx | QNT (Mod A DEST): quantized retrig, Retrig page |
| 48 | perf-fx | Perf FX 1 (Mod A M1) |
| 49 | perf-fx | Perf FX 2 (Mod A M2) |
| 50 | perf-fx | Perf FX 3 (Mod A M3) |
| 51 | perf-fx | Perf FX 4 (Mod A M4) |
| 72 | fx3 | SND3 (amp "Delay Time", saved per track) |
| 125 | dual-mono | IN R: alias of BAL |
| 129 | dual-mono | DEL: R side while the IN R page is open |
| 130 | dual-mono | REV: R side while the IN R page is open |
| 246 | fx3 | FX3 page |
| 247 | fx3 | FX3 page |
| 248 | fx3 | FX3 page |
| 249 | fx3 | FX3 page |
| 250 | fx3 | FX3 page |
| 251 | fx3 | FX3 page |
| 252 | fx3 | FX3 page |
| 253 | fx3 | FX3 page |
| 262 | master-comp | compressor |
| 263 | master-comp | compressor |
| 264 | master-comp | compressor |
| 265 | master-comp | compressor |
| 266 | master-comp | compressor |
| 267 | master-comp | compressor |
| 268 | master-comp | compressor |
| 269 | fx3 | external input SND3 |

Ids 254–261 (Digitakt MIDI CC values) are free but have MIDI CCs; ids above 504 do not exist. See [ui-parameters.md](ui-parameters.md#hidden-ids-used-by-the-mods).

## Pages

| Page | Mod | Use |
|---|---|---|
| 25 | fx3 | REVERB page 2 (was OB8) |
| 27 | dual-mono | IN R in the MIXER tab (was MIDI Source) |

## Saved with the kit / project

| Store | Mod | Slots |
|---|---|---|
| kitstore | dual-mono | block 0 word 0, block 0 word 1, block 0 word 2 |
| projstore | — | 256 bytes, all free |
