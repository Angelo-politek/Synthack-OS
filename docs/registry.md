# Shared resources (OS 1.42)

Generated from `tools/build/registry.py` (`python tools/build/registry.py`); `tests/test_registry.py` checks every `patch.json` against it. **A new mod claims its space there first.**

## Mod area (RAM `0x444e48d0`, offsets)

| From | To | Mod | Use |
|---|---|---|---|
| `0x0000` | `0x2000` | master-comp | code and data |
| `0x2000` | `0x4000` | readable-values | code and data |
| `0x4000` | `0x5000` | perf-fx | code and data |
| `0x5000` | `0x5800` | dual-mono | dualmono2.c; header read by fx3 at +0x5000 (dualmono_layout.py) |
| `0x5800` | `0x7000` | sy-fm4 | main CPU side: pages, algorithm drawings, storage tables, shared RAM publisher |
| `0x7000` | `0x7200` | projstore | code, then the 256 bytes saved with the project |
| `0x7200` | `0x7400` | kitstore | code |
| `0x7400` | `0x7420` | modarea | boot list: 8 pointers, called after unpacking (BOOT_SLOTS) |
| `0x7420` | `0x7e00` | syn-pages | machine table (synpages_layout.TABLE), SRC view: pages, titles, drawing |
| `0x7e00` | `0x8000` | vparams | code |
| `0x8000` | `0x8180` | vparams | table: 32 entries of 12 B, one per virtual parameter (VPARAMS_SLOTS) |
| `0x8180` | `0xa000` | sampler | main CPU side: pages, knob graphics, waveform, value texts, tempo to shared RAM |
| `0xa000` | `0xdff0` | fx3 | code and data |
| `0xdff0` | `0xf000` | fx3 | feedback (+0xDFFC) and delay line (+0xE000, 4 KB) |
| `0xf000` | `0xfff0` | **free** |  |

Boot list (`+0x7400`, 8 pointers called after unpacking): slot 0 sy-fm4, slot 1 sampler.

## Engine area (CPU #2, `mods/modarea7`, RAM `0x47000000`, offsets)

| From | To | Mod | Use |
|---|---|---|---|
| `0x0000` | `0x4000` | sy-fm4 | voice engine (engine 4) and its state |
| `0x4000` | `0x00020000` | sampler | voice engine (engine 11), interpolation table, zero-crossing grids |

## Shared RAM (CPU #1 at `0x10000000` + offset, CPU #2 at offset)

| From | To | Owner | Use |
|---|---|---|---|
| `0x0000` | `0x01b0` | OS | voice frames: 0x1B0 B from 0x80002000 every block (eDMA ch. 47) |
| `0x01b0` | `0x05b0` | OS | voice output: 8 x 32 x int32 back to CPU #1 |
| `0x05b0` | `0x0630` | sampler | waveform: request +0x5B0, slot +0x5B4, columns done +0x5B6, length +0x5B8, address +0x5BC, 112 peaks +0x5C0 |
| `0x0700` | `0x0780` | sy-fm4 | pages 2/3 and 3/3: 8 words per track, locks applied |
| `0x07f0` | `0x07f4` | sampler | tempo, BPM x 120 |
| `0x0800` | `0x1000` | OS | boot-time upload window |

## Section 3 free fill (`0x40339740–0x4033a000`)

| From | To | Mod | Use |
|---|---|---|---|
| `0x40339740` | `0x40339be0` | splash | code, logo, animation entries |
| `0x40339be0` | `0x40339d80` | dual-mono | dualmono.S (input VCAs, names) |
| `0x40339d80` | `0x4033a000` | modarea | mod-area loader |

## Zero in stock but read by the OS — not free

| From | To | Why |
|---|---|---|
| `0x402abc3c` | `0x402cbc3c` | two 128x128 tables of longs read by 0x400AD480 (conversion of loaded sounds/kits); rows are zero but read |

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
| 190 | sy-fm4 | SYN page 1/3 TUNE (SY TONE's TUNE, renamed) |
| 191 | sy-fm4 | SYN page 1/3 RAT2 (SY TONE's RATIO, renamed) |
| 192 | sy-fm4 | SYN page 1/3 LEV2 (SY TONE's MOD, renamed) |
| 193 | sy-fm4 | SYN page 1/3 FDBK (SY TONE's FDBK, renamed) |
| 194 | sy-fm4 | SYN page 1/3 DEC2 (SY TONE's MENV, renamed) |
| 195 | sy-fm4 | SYN page 1/3 PNCH (SY TONE's PNCH, renamed) |
| 196 | sy-fm4 | SYN page 1/3 OVER (SY TONE's OVER, renamed) |
| 197 | sy-fm4 | SYN page 1/3 DEC1 (SY TONE's DEC, renamed) |
| 246 | fx3 | FX3 page |
| 247 | fx3 | FX3 page |
| 248 | fx3 | FX3 page |
| 249 | fx3 | FX3 page |
| 250 | fx3 | FX3 page |
| 251 | fx3 | FX3 page |
| 252 | fx3 | FX3 page |
| 253 | fx3 | FX3 page |
| 254 | sy-fm4 | SYN pages 2/3 and 3/3 ALGO (was Digitakt MIDI CC1 Value, MIDI CC cleared) |
| 255 | sy-fm4 | SYN page 2/3 RAT3 (was Digitakt MIDI CC2 Value, MIDI CC cleared) |
| 256 | sy-fm4 | SYN page 2/3 LEV3 (was Digitakt MIDI CC3 Value, MIDI CC cleared) |
| 257 | sy-fm4 | SYN page 2/3 DEC3 (was Digitakt MIDI CC4 Value, MIDI CC cleared) |
| 258 | sy-fm4 | SYN page 2/3 RAT4 (was Digitakt MIDI CC5 Value, MIDI CC cleared) |
| 259 | sy-fm4 | SYN page 2/3 LEV4 (was Digitakt MIDI CC6 Value, MIDI CC cleared) |
| 260 | sy-fm4 | SYN page 2/3 DEC4 (was Digitakt MIDI CC7 Value, MIDI CC cleared) |
| 261 | sy-fm4 | SYN page 2/3 DET (was Digitakt MIDI CC8 Value, MIDI CC cleared) |
| 262 | master-comp | compressor |
| 263 | master-comp | compressor |
| 264 | master-comp | compressor |
| 265 | master-comp | compressor |
| 266 | master-comp | compressor |
| 267 | master-comp | compressor |
| 268 | master-comp | compressor |
| 269 | fx3 | external input SND3 |
| 497 | sampler | SAMPLER knob A TUNE (was SP TWINSHOT TUN1) |
| 498 | sampler | SAMPLER knob B PLAY (was SP TWINSHOT SMP1) |
| 499 | sampler | SAMPLER knob C BR (was SP TWINSHOT FLT1) |
| 500 | sampler | SAMPLER knob G LOOP/BARS/GRID, lix 0x18 (was SP TWINSHOT MIX) |
| 501 | sampler | SAMPLER knob E STRT/SEG/SLICE (was SP TWINSHOT TUN2) |
| 502 | sampler | SAMPLER knob F LEN/MODE (was SP TWINSHOT SMP2) |
| 503 | sampler | SAMPLER knob H LEV, lix 0x19 (TYPE, lix 0x1A, on page 2/2) (was SP TWINSHOT OVER) |
| 504 | sampler | SAMPLER knob D SAMP, lix 0x15 (was SP TWINSHOT DEC1) |

Ids without a page often carry a MIDI CC or are aliases: clear the CC, check aliases. Ids above 504 do not exist. See [ui-parameters.md](ui-parameters.md#hidden-ids-used-by-the-mods).

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
