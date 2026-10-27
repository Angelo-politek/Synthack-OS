# Shared resources (OS 1.41)

Generated from `tools/build/registry.py` (`python tools/build/registry.py`); `tests/test_registry.py` checks every `patch.json` against it. **A new mod claims its space there first.**

## Mod area (RAM `0x444e38d0`, offsets)

| From | To | Mod | Use |
|---|---|---|---|
| `0x0000` | `0x2000` | master-comp | codice e dati |
| `0x2000` | `0x4000` | readable-values | codice e dati |
| `0x4000` | `0x5000` | perf-fx | codice e dati |
| `0x5000` | `0x7000` | dual-mono | dualmono2.c; intestazione letta da fx3 a +0x5000 (dualmono_layout.py) |
| `0x7000` | `0x7200` | projstore | codice, poi i 256 byte salvati col progetto |
| `0x7200` | `0x7400` | kitstore | codice |
| `0x7400` | `0x7e00` | **free** |  |
| `0x7e00` | `0x8000` | vparams | codice |
| `0x8000` | `0x8180` | vparams | tabella: 32 voci da 12 B, una per parametro virtuale (VPARAMS_SLOTS) |
| `0x8180` | `0xa000` | **free** |  |
| `0xa000` | `0xdff0` | fx3 | codice e dati |
| `0xdff0` | `0xf000` | fx3 | retroazione (+0xDFFC) e linea di ritardo (+0xE000, 4 KB) |
| `0xf000` | `0xfff0` | **free** |  |

## Section 3 free fill (`0x40338740–0x40339000`)

| From | To | Mod | Use |
|---|---|---|---|
| `0x40338740` | `0x40338be0` | splash | codice, logo, voci delle animazioni |
| `0x40338be0` | `0x40338d80` | dual-mono | dualmono.S (VCA degli ingressi, nomi) |
| `0x40338d80` | `0x40339000` | modarea | caricatore dell'area mod |

## Zero in stock but read by the OS — not free

| From | To | Why |
|---|---|---|
| `0x402ab8ec` | `0x402cb8ec` | due tabelle 128x128 di long lette da 0x400AD408 (conversione di suoni/kit caricati); righe a zero ma lette (PR #5) |

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
| 47 | perf-fx | QNT (DEST di Mod A): retrig quantizzato, pagina Retrig |
| 48 | perf-fx | Perf FX 1 (M1 di Mod A) |
| 49 | perf-fx | Perf FX 2 (M2 di Mod A) |
| 50 | perf-fx | Perf FX 3 (M3 di Mod A) |
| 51 | perf-fx | Perf FX 4 (M4 di Mod A) |
| 72 | fx3 | SND3 ("Delay Time" dell'amp, salvato per traccia) |
| 125 | dual-mono | IN R: alias di BAL |
| 129 | dual-mono | DEL: lato R quando la pagina IN R e' aperta |
| 130 | dual-mono | REV: lato R quando la pagina IN R e' aperta |
| 246 | fx3 | pagina FX3 |
| 247 | fx3 | pagina FX3 |
| 248 | fx3 | pagina FX3 |
| 249 | fx3 | pagina FX3 |
| 250 | fx3 | pagina FX3 |
| 251 | fx3 | pagina FX3 |
| 252 | fx3 | pagina FX3 |
| 253 | fx3 | pagina FX3 |
| 262 | master-comp | compressore |
| 263 | master-comp | compressore |
| 264 | master-comp | compressore |
| 265 | master-comp | compressore |
| 266 | master-comp | compressore |
| 267 | master-comp | compressore |
| 268 | master-comp | compressore |
| 269 | fx3 | SND3 dell'ingresso |

Ids 254–261 (Digitakt MIDI CC values) are free but have MIDI CCs; ids above 504 do not exist. See [ui-parameters.md](ui-parameters.md#hidden-ids-used-by-the-mods).

## Pages

| Page | Mod | Use |
|---|---|---|
| 25 | fx3 | REVERB pagina 2 (era OB8) |
| 27 | dual-mono | IN R nel tab MIXER (era MIDI Source) |

## Saved with the kit / project

| Store | Mod | Slots |
|---|---|---|
| kitstore | dual-mono | block 0 word 0, block 0 word 1, block 0 word 2 |
| projstore | — | 256 bytes, all free |
