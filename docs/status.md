# Status

Snapshot of `dev`, 2026-11-10. Target: SyntHack 1.0 on Syntakt OS 1.42, planned for 2026-11-29. Features are frozen since 2026-11-09.

## Summary

| Area | State |
|---|---|
| Build chain (`build.py`, SHA-256 checks, protected sections, boot margin) | `[ok]` |
| Web builder | `[ok]` same bytes as `build.py` (`tests/test_web_builder.py`). `[wip]` not online |
| Emulator, CPU #1 and CPU #2 | `[ok]` instructions per block (`isr.py`), cache model (`cycles.py`), UI pages (`screens.py`) |
| Tests | ~735 (`python -m pytest`, ~55 min with the stock OS). CI runs those that need no stock OS |
| Boot margin | `[ok]` 17 727 B with every mod (minimum 4 096), the same whatever the mod code size. `[!]` not flashed yet with the new loader |
| Audio CPU | `[wip]` estimates below; device measurement open |
| Contributor tools | `[ok]` `new_mod.py`, `modkit.py`, `sdk/synthack.h`, `claims.json`, `check_mod.py` |

## Release 1.0

| # | Item | State |
|---|---|---|
| 1 | Boot with the whitened mod area (new loader) on the device | open |
| 2 | Release candidate on the device, two sessions, checklist | open |
| 3 | Recorder: analog tracks and MAIN against the output | `[wip]` sources documented; fixes after device tests |
| 4 | Audio interrupt ≤ ~95 % in the worst case of the default selection | `[ok]` in the model (93–94 % with Modulation skip); device measurement open |
| 5 | Mods promoted to `stable` after the release candidate | open |
| 6 | Web builder online, new home page, previews of every mod | open |
| 7 | Release `.syx` checklist: build from the site = build from `build.py`, recovery tested | open |

## Mods

Status: `mods/<name>/mod.json`. A mod is never above the status of a mod it requires.

| Status | Mods |
|---|---|
| stable | readable-values, perf-fx, splash; infra: modarea, vparams, kitstore, projstore, fastmix |
| beta | master-comp, fx3, dual-mono, sy-fm4, sampler, long-samples, modulation-skip; infra: idspace, xparams, syn-pages, modarea7, sfcore |
| experimental | lfo3, arp, poly, recorder |

master-comp, fx3 and dual-mono were released in v0.9.0 on OS 1.41. On 1.42 they use the new parameter ids of idspace, on the device since 2026-11-07: beta until the release candidate.

## Audio CPU

Why the UI lags: the MCF54418 has 8 KB instruction and 8 KB data caches; the stock interrupt runs ~1 200 distinct 16-byte code lines (~19 KB) per block. Every line of code a mod runs, and every DDR data line it touches, is a DDR read in every block. Instruction counts miss this. The cache model (`tools/emu/cycles.py`) is calibrated on the device: stock at rest = 89 % of the block.

Model, CPI 1.0, 2026-11-10 (`dev` 724bc86):

| Selection | At rest | Worst case (scene `max`) |
|---|---|---|
| stock | 89.0 % | 89.0 % |
| fx3, master-comp, dual-mono, readable-values, perf-fx | 90.0 % | 96.6 % |
| the same with modulation-skip | 86.3 % | 92.9 % |
| stable and beta mods (adds sy-fm4, sampler, long-samples) | 87.8 % | 94.4 % |
| every mod | 90.1 % | 96.7 % |

- Scene `max`: 12 tracks sending to FX3, chorus at maximum, delay and reverb sends, compressor on.
- Measured on the device with [cpu-meter](../mods/cpu-meter) on 2026-11-04, before the optimizations: every mod at 110 % and more, as the model at CPI 1.0 predicted (107 %). The numbers above are not measured on the device yet.
- Left on CPU #1 without changing the sound: master-comp and dual-mono rewritten compact (~−1 500 cycles); OS copies for USB/Overbridge skipped without streaming (~−1 900 instructions). After 1.0.

## Boot margin

The bootstrap unpacks section 3 almost in place: the output must never catch up with the input ([firmware-format](firmware-format.md#boot-decompression-limit-)). `build.py` refuses a build under 4 096 B.

| Build, every mod | Margin |
|---|---|
| mod area as a plain SHLZ stream (until 2026-11-09) | 6 375 B |
| mod area whitened (SHLW) | 17 727 B |
| the same plus one more mod | 17 724 B |

A plain SHLZ stream was packed again by aPLib, so every byte of mod code cost margin. Whitened, it costs none. The ceiling of ~17.7 KB comes from the stock part as our packer packs it.

## Open on GitHub

| Item | State |
|---|---|
| PR #5 Déjà Vu LFO, PR #6 SY CHORD wave bank | waiting for the port to 1.42 (2026-11-20 for v1.0) |
| #8 integer values 0–127 | planned after v1.0 |
| #1 machines, #7 machine id 45 | release candidate announced |
| #2 UI lag | see Audio CPU |

## After 1.0

Arpeggiator settings per pattern · FX3 on CPU #2 · Synfact's sample manager and project pool · PIN lock · new LFO shapes · Euclidean UI · integer values.
