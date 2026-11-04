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
| Sample length | `[!]` the OS cuts samples at ~5 s. Sample management not started ([plan](#sample-management)) |

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

1. `[ ]` Measure on the device, DTIM0 at interrupt entry and exit: a build with fx3, 12 tracks sending, chorus at maximum, DEL and REV up. That point fixes CPI and the miss penalty.
2. `[ ]` fx3: compute the knob-derived values (rates, delays, feedback, divisions) in `sync()`, only when a knob moves. Then the steady path of `fx3_run` in compact assembly. Target: −40 code lines (~−2 000 cycles).
3. `[ ]` fastmix: smoothing without the DDR copy, if the device shows the copy costs more than it saves.
4. `[ ]` xparams: write changed words only, if shared-RAM accesses are slow on the device.
5. `[ ]` Release gate in `tests/test_cycles.py`: every combination ≤ the calibrated limit.

Done (2026-11-04): cache model and tests; site load indicator in cycles (limit 10 000 ≈ interrupt at 95 %); xparams −4 500 cycles; fx3 TYPE-change overrun removed.

## Sample management

The OS cuts samples at ~5 s. Goal: Digitakt-style sample management (longer samples, a shared pool) for the sampler machines.

Leads in OS 1.42 (section 3, CPU #1):

| Lead | Where |
|---|---|
| Pool and transfer classes | `SoundPool` (`updateMirror`), `SampleHandler::register_route`, `SoundManager::copyFilesFromMmcToPool` / `copyFilesFromPoolToMmc` (RTTI strings) |
| Capabilities reported to Transfer | `sample_file.mono_support`, `sample_file.interleaved_stereo_support`, `sample_file.sample_rates` |
| Boot load | `LOADING SAMPLES`, `PREPARING SAMPLES`; path `/samples` |
| Memory | CPU #2: BSS with the sample memory up to ~`0x4405F750`; `0x46000000` used by modarea7's boot copy only; engine area `0x47000000` (256 KB); stack `0x48000000`. CPU #1: `0x45565490–0x48000000` written during sample loading ([#4](https://github.com/Angelo-politek/Synthack-OS/issues/4)) |

Plan:

1. `[ ]` Find the length limit: the loader path from `copyFilesFromMmcToPool` to the CPU #2 transfer. Check the 5 s figure with a long WAV in the emulator.
2. `[ ]` Map the CPU #2 sample memory: slot table, per-slot size, allocator. Check at runtime which RAM above the BSS stays unused (the #4 lesson: no static reference is not proof).
3. `[ ]` Design: one pool for all slots, length bounded by free memory, slot table compatible with stock projects (a stock OS must still load them, rule 10).
4. `[ ]` Sampler machines read the pool (`mods/sampler/engine`).
5. `[ ]` Tests: long sample, slot reuse, save/reload, project opened on a stock OS.

No other Syntakt firmware with Digitakt sample machines was found to copy from (search 2026-11-04). The sampler's positions and interpolation are already checked against the Digitakt 1.54 code.

## Next session

1. Device measurement (fx3 CPU, item 1).
2. fx3 items 2–5.
3. Sample management items 1–2: scope for 1.0.
