# Status

Snapshot of `dev`, 2026-11-04. Target: SyntHack 1.0 on Syntakt OS 1.42, with the web builder and the docs.

## Summary

| Area | State |
|---|---|
| Build chain (`build.py`, SHA-256 checks, protected sections) | `[ok]` |
| Web builder | `[ok]` same bytes as `build.py` (`tests/test_web_builder.py`). `[wip]` not online |
| Emulator, CPU #1 and CPU #2 | `[ok]` instructions per block (`isr.py`), cache model (`cycles.py`, new) |
| Tests | 575 (`python -m pytest`), 489 need the stock OS. CI runs the other 86 |
| Feature mods | 6: splash, master-comp, dual-mono, readable-values, perf-fx, fx3 |
| Machines | 2: sy-fm4, sampler. Not tested on 1.42 hardware |
| Infra mods | 9: modarea, modarea7, vparams, kitstore, projstore, fastmix, syn-pages, xparams, mod-zero (example) |
| Audio CPU | `[!]` above stock with fx3 or the machines (cache misses, see [fx3 CPU](#fx3-cpu)) |
| Sample length | `[wip]` the stock upload cuts at 5 s. Port of Synfact's long samples ([plan](#sample-management)) |

## Release 1.0

| # | Item | State |
|---|---|---|
| 1 | Audio interrupt ≤ ~95 % of the block in the worst case of every mod combination | `[wip]` calibration on the device needed |
| 2 | fx3 without UI lag, 12 tracks sending | `[wip]` |
| 3 | sy-fm4, sampler, fastmix tested on 1.42 hardware | open |
| 4 | Sample management: samples longer than 5 s | open, scope to decide (1.0 or 1.1) |
| 5 | Web builder online | open |
| 6 | README, users and modders guides match the release | `[wip]` |
| 7 | Release `.syx` checklist: build from the site = build from `build.py`, recovery tested | open |

## Mods

Cycles: extra CPU #1 cycles per block, worst case, cache model at CPI 1.0 (`AUDIO_CYCLES`, [budget.py](../tools/build/budget.py)). Device: what the mod README states.

| Mod | Kind | Tests | Device | Cycles | Findings | Action |
|---|---|---|---|---|---|---|
| [fx3](../mods/fx3) | feature | 130 | not stated | ~15 000 | 164 code lines and 41 DDR data lines per block. The C control code of `fx3_run` is the biggest part: 76 lines, ~700 instructions, 4 divisions. TYPE change cleared 4 KB in one block: fixed (8 blocks). | Precompute knob-derived values when a knob moves; move `fx3_run`'s steady path to compact assembly; measure on the device |
| [fastmix](../mods/fastmix) | infra | 47 | to check | ~−600 | −10 000 instructions, but the smoothing keeps a 1.9 KB copy of the inputs in DDR: 117 data lines per block. The gain depends on the real CPI (−600 to −10 000 cycles). | Measure on the device. Option: test the fixed point from the state in SRAM (`0 ≤ x·2¹⁶ − s ≤ 33`), no copy |
| [xparams](../mods/xparams) | infra | 3 | — | ~5 200 | Copy unrolled to 870 B: fixed (one loop per track, −4 500 cycles). Still 288 shared-RAM accesses per block. | Measure the shared-RAM access cost. Option: write changed words only |
| [master-comp](../mods/master-comp) | feature | 34 | `[ok]` v0.9 | ~3 700 | Toggling *global* for the external input also copies the compressor settings (known). | — |
| [dual-mono](../mods/dual-mono) | feature | 47 | `[ok]` v0.9 | ~2 400 | MIDI CC for input DEL/REV goes to IN R while that page is open (known). | — |
| [sampler](../mods/sampler) | machine | 21 | not stated | ~400 | CPU #2: 8 voices ~84 000 instructions per block (SP TWINSHOT 64 000, SY SWARM 116 000). Samples limited to ~5 s by the OS. | Device test; sample management |
| [sy-fm4](../mods/sy-fm4) | machine | 7 | 1.40A (Rxuting), 1.42 open | ~0 | Locks of pages 2/3–3/3 lost on a stock OS (documented). | Device test on 1.42 |
| [readable-values](../mods/readable-values) | feature | 45 | `[ok]` curves measured | 0 (UI) | — | — |
| [perf-fx](../mods/perf-fx) | feature | 94 | not stated | 0 (sequencer) | — | — |
| [splash](../mods/splash) | base | 8 | released (v0.9) | 0 | Boot time unchanged. | — |
| [modarea](../mods/modarea) | infra | 5 | released (v0.8.1) | 0 | 64 KB in the OS heap. | — |
| [modarea7](../mods/modarea7) | infra | 5 | not stated | 0 | ~2.4 M instructions at boot on CPU #2. | Device test with a machine |
| [syn-pages](../mods/syn-pages), [vparams](../mods/vparams), [kitstore](../mods/kitstore), [projstore](../mods/projstore) | infra | kitstore 6, projstore 5; the others through the mods using them | released (v0.9), syn-pages new | 0 | vparams: not for p-lockable sound parameters ([#1](https://github.com/Angelo-politek/Synthack-OS/issues/1)). | — |

## fx3 CPU

Why the UI lags:

1. The MCF54418 has an 8 KB instruction cache and an 8 KB data cache. The stock interrupt runs ~1 200 distinct 16-byte code lines (~19 KB) per block. Nothing stays in the cache between blocks.
2. So each line of code a mod runs, and each DDR data line it touches, costs a DDR read every block. Instruction counts miss this: fastmix's −10 000 instructions bought fx3 room on paper, not in time.
3. Cache model (`tools/emu/cycles.py`), calibrated on the stock 89 %:

| Build, scene `max` | Instructions | CPI 1.0 | CPI 1.5 |
|---|---|---|---|
| stock | 68 434 | 89 % | 89 % |
| fastmix | 57 434 | 88.6 % | 82.8 % |
| fx3 | 60 338 | 97.6 % | 89.6 % |
| all audio mods | 62 036 | 107 % | 96.6 % |

The user report (fx3 lags) fits CPI ≈ 1.0.

Plan:

1. `[wip]` Measure on the device with [cpu-meter](../mods/cpu-meter) (DTIM0 at interrupt entry and exit, shown on the parameter pages): a build with fx3, 12 tracks sending, chorus at maximum, DEL and REV up. That point fixes CPI and the miss penalty.
2. `[ ]` fx3: compute the knob-derived values (rates, delays, feedback, divisions) in `sync()`, only when a knob moves. Then the steady path of `fx3_run` in compact assembly. Target: −40 code lines (~−2 000 cycles).
3. `[ ]` fastmix: smoothing without the DDR copy, if the device shows the copy costs more than it saves.
4. `[ ]` xparams: write changed words only, if shared-RAM accesses are slow on the device.
5. `[ ]` Release gate in `tests/test_cycles.py`: every combination ≤ the calibrated limit.

Done (2026-11-04): cpu-meter diagnostic mod; cache model and tests; site load indicator in cycles (limit 10 000 ≈ interrupt at 95 %); xparams −4 500 cycles; fx3 TYPE-change overrun removed.

## Sample management

Decision (2026-11-04): port the long samples of [Synfact](https://github.com/GSM1980/synfact-dev) (GSM1980, on elekloader by irpina; GPL-2.0-or-later, OS 1.41) as they are. SyntHack is GPL-2.0-or-later from that date ([NOTICE](../NOTICE)).

Checked on the device: a long sample loaded with Transfer is cut at 5 s. Synfact documents why: the stock upload converts to 48 kHz mono PCM16 and crops to 240 000 frames (5 s) before writing the slot. Transfer can't carry long samples; Synfact sends them with its own tool over MIDI.

### What Synfact does

| Part | Detail |
|---|---|
| HZFS | Named long samples in the high eMMC zone (`0x30100000` … card end, ~1 GB): two catalogues (A/B, CRC32, sequence), contiguous extents of 512 KB windows, stock `SAMP` header + PCM16BE 48 kHz mono. Never formats a zone that isn't blank |
| Data RPC | Raw windows `/samples/(8185 + k)` for the high zone (`core_fs_route`); a write guard refuses stock-slot writes over 5 s or across slots (`core_fs_write`) |
| PC tool | `python -m elekloader.sdk.syntakt.long_samples put / get / ls / rm / fsck` (python-rtmidi). Same protocol once ported: their tool works with SyntHack |
| Project pool | 128 positions in the project header (`POOL` record, `0xF0..0x200`): 1–64 stock slots, `0x8000 + id` HZFS files |
| Boot | after the stock sample blob, long PCM planned into CPU #2 RAM and sent with the same uploader and progress bar (`core_pool_count`, `core_pool_map`, `core_pool_blob`) |
| Playback | their sampler machines read pool positions; CPU #2 service `audio-pool.c` |

### Port to OS 1.42

The 16 hook sites of the long-sample parts, translated with `tools/build/osmap.py`:

| Synfact hook | 1.41 | 1.42 | Stock bytes on 1.42 |
|---|---|---|---|
| `core_fs_route` | `0x400b8088` | `0x400b8100` | same |
| `core_fs_write` | `0x400b618c` | `0x400b6204` | same |
| `core_fs_written` | `0x4010b8da` | `0x4010ba9e` | same after translating the call target (osmap) |
| `core_storage_boot` | `0x400826a6` | `0x4008271e` | same after translating the call target (osmap) |
| `core_pool_count` | `0x40082f3e` | `0x40082fb6` | same |
| `core_pool_map` | `0x40082f56` | `0x40082fce` | same after translating the call target (osmap) |
| `core_pool_blob` | `0x40082802` | `0x4008287a` | same after translating the call target (osmap) |
| `core_pool_initialize` | `0x4001d16a` | `0x4001d16a` | same |
| `core_pool_new` | `0x40018ab0` | `0x40018ab0` | same |
| `core_pool_snapshot` | `0x4019ffd4` | `0x401a0198` | same |
| `core_pool_validate` | `0x400afa7e` | `0x400afaf6` | same |
| `core_pool_load` | `0x4001d6fe` | `0x4001d6fe` | same |
| `core_pool_save` | `0x4001a7be` | `0x4001a7be` | same after translating the call target (osmap) |
| `core_pool_sound_menu` | `0x40064918` | `0x40064990` | same |
| `core_pool_value` | `0x4007bb6a` | `0x4007bbe2` | same |
| `core_machine_sample_dial` | `0x40011e74` | `0x40011e74` | same |

The other services (`fw_mmc_read`, `fw_mmc_write`, `fw_malloc`, …, in their `fw.s`) are 1.41 addresses: translate the same way, check each against the 1.42 code.

Steps:

1. `[ok]` Mod area 64 → 128 KB (`HEAP_BLOCK_SIZE`): room for the port (`+0xFFF0`…`+0x1FFF0`).
2. `[ ]` `long-samples` mod, storage only: `hzfs.c`, `high-storage.c/.s`, `crc.c`, the route and write-guard hooks. Tests: host build of `hzfs.c` against a block-device double (their `tests/`); the route and the guard in the emulator. Device: `long_samples init/put/get/ls` round trip.
3. `[ ]` Project pool and boot upload (`sample-pool.c`, the pool hooks above); CPU #2 side in modarea7.
4. `[ ]` SAMPLER machines on pool positions 65–128 (`SAMP` 1–128).
5. `[ ]` Web builder: a long-sample uploader over WebMIDI (port of `long_samples.py`), optional.

`[!]` Steps 2–3 write the internal eMMC. Test on the device only after the emulator and host tests, with a backup of the projects (Transfer).

Found here before the decision (still valid, OS 1.42): stock slots at `(k + 8) × 0x80000`, header check `0x401132EC` (`0x7FFC0`), slot read `0x401133CE`, pool image `0x40082334`, upload `0x40082F90`, CPU #2 pool `0x4004F750` (64 MB) and its parser `0x40000D06`.

## Next session

1. Device measurement (fx3 CPU, item 1).
2. fx3 items 2–5.
3. Sample management items 1–2: scope for 1.0.
