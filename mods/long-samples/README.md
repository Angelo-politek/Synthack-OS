# long-samples

Samples longer than 5 s. The storage is **Synfact's** ([GSM1980/synfact-dev](https://github.com/GSM1980/synfact-dev), on [elekloader](https://github.com/irpina/elekloader) by irpina; GPL-2.0-or-later), ported to OS 1.42. The SAMPLER machines play them as slots 65–128 (`L1`–`L64`).

## Use

1. Build with `mods/long-samples` and `mods/sampler`. Flash.
2. Back up your projects and samples with Transfer first. This mod writes the internal eMMC (high zone only).
3. Send a sample with Synfact's tool, from a checkout of synfact-dev, Syntakt connected over USB, Transfer closed:
   ```sh
   pip install python-rtmidi
   python -m elekloader.sdk.syntakt.long_samples ls
   python -m elekloader.sdk.syntakt.long_samples put pad.wav --yes-write-device
   ```
4. Power cycle. "PREPARING SAMPLES" now also sends the long samples to the voice CPU.
5. On a SAMPLER track, turn `SAMP` past 64: `L1` is the first file of the catalogue, `L2` the second, …

| | |
|---|---|
| Length | up to ~5.8 min per file, ~31 MB in all with the stock samples (the voice CPU holds 64 MB) |
| Format | 48 kHz mono 16-bit (the tool converts and resamples) |
| Order | catalogue order (`ls`); the first 64 files |
| Stock slots | Transfer still writes slots 1–64, cut at 5 s by the OS; a write over 5 s or across a slot is refused |

`[!]` Files beyond the 64th, or beyond the voice CPU's memory, stay on the eMMC and don't play.

`[!]` Synfact's own docs say its hardware transfer on the device is still to be confirmed. Test with backups.

## How it works

| Part | Where | From |
|---|---|---|
| HZFS: catalogues A/B at eMMC `0x30000000`, files in 512 KB windows from `0x30100000`; never formats a zone that isn't blank | `synfact/hzfs.c`, `crc.c`, `high-storage.c` | Synfact, unchanged |
| Data RPC: raw windows `/samples/(8185 + k)` (route `0x400B8100`), stock-slot write guard (`0x400B6204`) | `glue.S`, `synfact/high-storage.c` | Synfact's veneers, 1.42 addresses |
| Catalogues checked at startup (`0x4008271E`) | `glue.S` → `core_hzfs_startup` | Synfact |
| Plan after the stock image is built (`0x4008287A`): first 64 files that fit | `pool.c` | ours |
| Upload (`0x40082FB6` page count, `0x40082FCE` page source): after the stock pages, a table page (`SHLS`, count, {pointer, frames}) then each file read from the eMMC, 2 KB a page | `pool.c` | ours (same sites as Synfact's core_pool_count/map) |
| Playback: the SAMPLER engine finds the table after the stock image on CPU #2 | `mods/sampler/engine/syn.c` | ours |

Services of the OS (`fw_mmc_read` `0x4010F612`, `fw_mmc_write` `0x4010F7F8`, …): Synfact's 1.41 addresses translated with `tools/build/osmap.py` and checked on the 1.42 code. `fw_malloc` is wrapped: the OS returns the pointer in `d0`, our compiler reads `a0`.

Not ported: Synfact's project pool (128 positions saved in the project), its Sample Manager and recorder.

## Test

`tests/test_long_samples.py` (eMMC double in the emulator): catalogues created on a blank disk, only in the high zone; a 12 s file written by Synfact's `core_hzfs_put`; the plan and every page sent to CPU #2 equal to the file; no catalogue: upload unchanged; stock-slot guard; route of a high window. `tests/test_sampler.py::test_long_sample_slot_65`: a 15 s sample played from 12.5 s.
