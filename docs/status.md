# Status

Snapshot of `dev`, 2026-11-05. Target: SyntHack 1.0 on Syntakt OS 1.42, with the web builder and the docs.

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
| Audio CPU | `[wip]` fx3 alone ~93 %, every mod ~97 % (cache model, see [fx3 CPU](#fx3-cpu)); device measurement open |
| Sample length | `[wip]` long samples ported from Synfact ([long-samples](../mods/long-samples)): emulator-tested, device test open |

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
| [fx3](../mods/fx3) | feature | 134 | not stated | ~10 900 | Per-block path in assembly, state in one block: 105 code and 32 data lines per block (were 153 and 41). Same output as the C version (test on random blocks). | Measure on the device |
| [fastmix](../mods/fastmix) | infra | 47 | to check | ~−4 300 | −10 000 instructions, but the smoothing keeps a 1.9 KB copy of the inputs in DDR: 117 data lines per block. The gain depends on the real CPI (−600 to −10 000 cycles). | Measure on the device. Option: test the fixed point from the state in SRAM (`0 ≤ x·2¹⁶ − s ≤ 33`), no copy |
| [xparams](../mods/xparams) | infra | 3 | — | ~1 700 | Copy unrolled to 870 B: fixed (one loop per track, −4 500 cycles). Copied twice a block (both calls of the eDMA wait): now once, 72 shared-RAM writes. | Measure the shared-RAM access cost |
| [master-comp](../mods/master-comp) | feature | 34 | `[ok]` v0.9 | ~3 500 | Toggling *global* for the external input also copies the compressor settings (known). | — |
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

Why the UI lags: the MCF54418 has 8 KB instruction and 8 KB data caches; the stock interrupt runs ~1 200 distinct 16-byte code lines (~19 KB) per block. Every line of code a mod runs, and every DDR data line it touches, is a DDR read in every block. Instruction counts miss this.

Measured on the device with [cpu-meter](../mods/cpu-meter) (2026-11-04): every mod at 110 % and more. The cache model at CPI 1.0 had predicted 107 %: that calibration is the right one.

Fixes, cache model at CPI 1.0, worst case (scene `max`):

| Build | Before | 2026-11-04 | 2026-11-05 |
|---|---|---|---|
| stock | 89 % | 89 % | 89 % |
| fx3 | 97.6 % | 95.6 % (device: under 100 %, almost no lag) | 92.7 % |
| fx3 + master-comp + dual-mono | — | 99.3 % | 96.2 % |
| machines (sy-fm4, sampler) | 94 % | 89 % | — |
| every audio mod | 107 % (110+ measured) | 101.2 % | 97.3 % |

1. `[ok]` fastmix: smoothing unhooked (−2 700 cycles): its DDR copy cost more than it saved.
2. `[ok]` xparams: copy in a loop (−4 500), then in long words (half the shared-RAM accesses).
3. `[ok]` fx3: knob-derived values computed when a knob moves, not every block; TYPE change no longer overruns.
4. `[ok]` fx3: per-block path in assembly (run, chorus/phaser control, ramp, input send, return, DEL/REV sends) kept together; state in one 432-byte block; 16-bit effect output; DEL/REV gains computed when they change; input send skipped when off. 153 → 105 code lines, 41 → 32 data lines, −3 700 cycles. Bit for bit as before (`test_same_output_as_the_c_version`).
5. `[ok]` fastmix: one entry chain for the 8/9/10-channel sums, zeros in a loop, one dense loop (−1 300). xparams: one copy a block, not two (−1 250). master-comp: per-block code and data together (−150).
6. `[ ]` Measure with cpu-meter: `out/2-fx3-meter.syx` (fx3), `out/3-all-meter.syx` (every mod but mod-zero). Read the box left of the tempo on a parameter page: average and peak, % of the block. Expected ~93 and ~97 average with sends at maximum.
7. `[ ]` Still above ~95 % with fx3 + master-comp + dual-mono. Left on the CPU #1 without changing the sound: master-comp (42 code lines a block) and dual-mono (31) rewritten compact (~−1 500); OS copies for USB/Overbridge (~1 900 instructions) skipped without streaming (needs the USB state). Otherwise FX3 on the CPU #2 (after 1.0).

Until 6: fx3 with master-comp and dual-mono may still lag the UI. The site's load indicator marks it.

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
2. `[ok]` [long-samples](../mods/long-samples): Synfact's storage (`hzfs.c`, `crc.c`, `high-storage.c` unchanged), route and write guard. Emulator: eMMC double, catalogues, put, route, guard. `[ ]` Device: `long_samples ls/put/get` round trip.
3. `[ok]` Boot upload (ours, at Synfact's sites `0x40082FB6`/`0x40082FCE`, plan at `0x4008287A`): a table and the files after the stock pages. `[ ]` Synfact's project pool (128 positions saved in the project) not ported: files map to slots in catalogue order.
4. `[ok]` SAMPLER: one list of samples (stock slots that hold a sample, then the long ones), sample menu on knob D of SYN 1/2 (names, lengths, waveform). Engine test: 15 s sample played from 12.5 s. Device: `ls`, `put`, playback checked (2026-11-04); the menu and the one list: device test open.
4b. `[ok]` Web builder **Samples** page (WebMIDI): list, add WAV files, order (catalogue slot map), remove. Tested against a device double; device test open.
5. `[ ]` Synfact's Sample Manager menu and project pool (assignments saved per project, folders).
6. `[ ]` Web builder: a long-sample uploader over WebMIDI (port of `long_samples.py`), optional.

`[!]` Steps 2–3 write the internal eMMC. Test on the device only after the emulator and host tests, with a backup of the projects (Transfer).

Found here before the decision (still valid, OS 1.42): stock slots at `(k + 8) × 0x80000`, header check `0x401132EC` (`0x7FFC0`), slot read `0x401133CE`, pool image `0x40082334`, upload `0x40082F90`, CPU #2 pool `0x4004F750` (64 MB) and its parser `0x40000D06`.

## Synfact features to port

SyntHack is GPL-2.0-or-later since 2026-11-04: Synfact's mods can be ported. They run on Synfact's core (hook bus, events) and OS 1.41: each port maps their hook sites to 1.42 (`tools/build/osmap.py`, as for long samples) and replaces the events with SyntHack hooks.

| Synfact mod | Size | What | Fits the roadmap |
|---|---|---|---|
| `lfo3-st` | ~4 800 lines | a third LFO on every track | 3rd LFO `[ ]` |
| `arp-st` | ~1 450 | Digitone-style arpeggiator on the audio tracks | Arpeggiator `[ ]` |
| `poly-st` | ~1 900 | polyphonic play for digital and compatible analog tracks | new |
| `recorder-st` | ~1 500 | record, trim, normalize, save samples | new (resampling) |
| `system-info-st` | ~400 | CPU and RAM pages in SETTINGS | overlaps cpu-meter |
| `modulation-skip-st` | ~270 | modulation destinations | new |
| `sample-manager-st` + core pool | — | sample library in folders, pool saved per project | after the SAMPLER menu |

Order: arpeggiator (smallest of the roadmap), then the third LFO. Every port: CPU cost with `tools/emu/cycles.py` before the device (the interrupt has ~7 % left with fx3 alone, ~3 % with every audio mod).

## Next session

1. Device measurement (fx3 CPU, item 1).
2. fx3 items 2–5.
3. Sample management items 1–2: scope for 1.0.
