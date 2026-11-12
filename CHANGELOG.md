# Changelog

## 1.0 (planned 2026-11-29) — Syntakt OS 1.42

Not released yet. This list follows `dev`.

### New

- **OS 1.42.** Every mod is ported. OS 1.41 is no longer supported.
- **SY FM4** (by Rxuting): 4-operator FM machine on three SYN pages, in place of SY TONE.
- **SAMPLER**: ONESHOT, WERP, REPITCH and SLICE machines in place of SP TWINSHOT, with a waveform page.
- **Long samples** (from Synfact): samples longer than 5 s, sent from the site's Samples page, one list per project, playable without a reboot.
- **Third LFO**, **Arpeggiator**, **POLY**, **Audio recorder** (ported from Synfact): experimental.
- **Modulation skip** (from Synfact): same sound, about 4 % more CPU free.
- **LFO destinations for mod parameters**: SY FM4, the SAMPLER's knob H, FX3 (on the FX track's LFOs).
- **Sample manager**: a SAMPLES row in the settings menu: put a long sample on a track, play it, tag, rename, reorder, delete. Experimental.
- **About SyntHack**: a SYNTHACK row in the settings menu lists the version, the mods in the build and the credits.
- **FX3 send on the FX track**: AMP page, next to DEL and REV.
- **Web builder**: build your OS in the browser, same bytes as `build.py`. Presets, load meter, a status on every mod (stable, beta, experimental).

### Fixed

- **MIDI machine**: its SRC, VAL and SEL pages moved mod parameters (v0.9.0). Mods now have parameter ids of their own.
- **Dual mono**: the other input leaked into a channel set to zero. Fixed in the emulator, to confirm on the device.
- **UI lag** with FX3: the audio code of FX3, the mixer sums and the extra parameters were rewritten. Estimated worst case with every mod 96.7 % of the audio block (was over 107 %); stock is 89 %.
- **Boot margin**: no longer shrinks with every byte of mod code.
- **POLY** kept losing its group after a power cycle.
- **Arpeggiator, recorder**: other keys acted under their views. The recorder closes after a save.
- **Input page**: DEL, REV and FX3 side by side, in stereo too.
- **Third LFO**: its page shows the waveform, as LFO1 and LFO2; paste page works between the three LFO pages.
- **Recorder**: screens redrawn, sources named for what they hold, the result of a save is shown.
- **FX track LFOs**: the external input among the destinations.

### For modders

- `tools/new_mod.py`, `tools/build/modkit.py`, `sdk/synthack.h`, `tools/check_mod.py`.
- Each mod claims its resources in its own `claims.json`.
- Parameter ids 505–568, extra pages, LFO DEST entries (`idspace`); eight more saved, p-lockable track parameters (`xparams`); SYN pages per machine (`syn-pages`); room for machine code on the voice CPU (`modarea7`); project storage (`projstore`).
- CPU cache model (`tools/emu/cycles.py`) and UI page rendering (`tools/emu/screens.py`) in the emulator.
- `python -m pytest -m "not slow"`: 6 minutes.

### Changed

- License: GPL-2.0-or-later since 2026-11-04 (MIT before). See NOTICE.

### Known issues

- See [README](README.md#known-issues).

## 0.9.0 (2026-10-19) — Syntakt OS 1.41

Performance FX with quantized retrig, dual mono v2, FX3 (input, reverb send, LFO, FX track routing), kit storage.

## 0.8.1 and earlier

Build, flash and recovery chain, emulator, boot splash, dual mono, bus compressor, readable values, mod area, virtual parameters, FX3. v0.8.1: mod area inside the OS heap ([#4](https://github.com/Angelo-politek/Synthack-OS/issues/4)), no alias ids ([#3](https://github.com/Angelo-politek/Synthack-OS/issues/3)), lower CPU cost ([#2](https://github.com/Angelo-politek/Synthack-OS/issues/2)).
