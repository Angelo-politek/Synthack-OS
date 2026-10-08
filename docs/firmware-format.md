# Firmware format (`.syx`)

Three layers, handled by [elektron-firmware-tool](https://github.com/mischa85/elektron-firmware-tool):

1. **SysEx transport** — 7-bit packed data, per-packet checksum.
2. **ELE3 container** — header, section table, HMAC-SHA256 over everything. The key is derived from the image itself, so the MAC can be recomputed.
3. **Sections** — aPLib-style LZ77 compression (some sections raw).

## Syntakt OS 1.41

Physical order: 5, 2, 1, 3, 4, 6, 7, 8. Sizes are decompressed.

| id | name | bytes | packed | content | we |
|---|---|---:|---|---|---|
| 1 | FPGA | 149 516 | yes | FPGA bitstream | never touch |
| 2 | bootstrap | 30 782 | yes | startup menu / OS upgrade (ColdFire) | **never touch** |
| 3 | MAIN OS | 3 438 480 | yes | OS, UI, sequencer, mixer, FX (CPU #1), loads at `0x40000400` | patched |
| 4 | updater | 32 776 | no | ? | never touch |
| 5 | meta | 15 | no | build timestamp (ASCII) | never touch |
| 6 | boot | 1 744 | no | ColdFire boot stub | **never touch** |
| 7 | blob | 383 760 | **no** | voice engine (CPU #2), loads at `0x40000400`, entry `0x40001070` | patchable |
| 8 | — | 159 948 | yes | second FPGA? | never touch |

Stock OS 1.41 SHA-256: `8e2488f462c4a5656396a895f113bcd415e9900fa8709340dccf45d4cb9ed19e`.

## Notes

- Section 3 may grow: the bootloader accepts it (used by the [mod area](memory-map.md#mod-area)).
- Repacking recompresses changed sections; compressed bytes differ, decompressed content is what we verify.
- The Syntakt accepts rebuilt images (recompressed section 3, recomputed MAC) via USB and MIDI DIN.
