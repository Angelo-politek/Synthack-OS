# modarea7

Room for machine code on the sound engine (CPU #2). Required by the machines (`"requires": ["modarea7"]`).

| | |
|---|---|
| Limit | CPU #1 stages section 7 in 0x60000 bytes (`0x40082D66`). Stock uses 383 760: 9 451 left. |
| Receiver | The CPU #2 bootloader (section 6, untouched) takes up to 2 MB (`0x800003F8`). |
| Idea | Section 7 travels compressed (SHLZ, `tools/build/lz.py`): ~265 KB. Room left for machines: ~125 KB compressed. |
| Engine area | `0x47000000`, 256 KB on CPU #2: above its BSS (sample memory included, up to ~`0x4405F750`), below its stack (`0x48000000`). |
| Cost | ~2.4 million instructions at boot on CPU #2, before the original entry. |

## Image

| Offset | Content |
|---|---|
| +0 | entry pointer → stub (the bootloader jumps to `*(0x40000400)`) |
| +4 | `stub.S`, 192 B |
| `hdr` | total length, original entry `0x40001070`, engine RAM, bytes to clear after the engine code |
| | SHLZ stream: section 7 with the patches → `0x40000400` |
| | SHLZ stream: engine area → `0x47000000` (4-byte aligned, optional) |

Boot:

1. The stub copies the image to `0x46000000` and continues there.
2. It unpacks the section to `0x40000400` and the engine area to `0x47000000`, then clears the rest of the area.
3. It invalidates the caches (CACR as the bootloader sets it) and jumps to the original entry with the bootloader's stack.

CPU #1, the staging buffer, the bootloader and the reload path (`0x40083202`) stay stock.

## Use

A machine links its CPU #2 code at `0x47000000 + offset` and appends it to section 7 at `0x4005DF10 + offset` (`tools/build/engine_layout.py`). Claim the range in `ENGINE` of `tools/build/registry.py`. `build.py` and the web builder pack the section.

## Test

`tests/test_modarea7.py`: cold boot in the section 7 emulator, like the bootloader. Memory after boot equals stock, engine area in place and cleared beyond, SY TONE, SP TWINSHOT and BD MODERN sample-identical to stock, bootloader stack preserved, stub cost.
