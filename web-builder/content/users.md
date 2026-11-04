## Why SyntHack

Sooner or later every artist needs one more feature, shaped around their own workflow.
SyntHack adds features to the Syntakt and lets the community build and share them:
mods for the OS, and machines, new digital synthesis engines.

It started with one need: a compressor on the master.

- The Syntakt's final mix is analog. It comes out low and flat next to other instruments.
- The Digitakt has a master compressor. The Syntakt sums in analog, so there was no place for one.
- The fix: drive the VCA of the FX send. An analog compressor with digital control.

One idea changed the sound of the Syntakt. The next ideas come from the community.

- Pick the mods you want. Each one is checked against the stock OS and against the others.
- Build the OS in your browser, from your own stock file. Nothing is uploaded.
- To undo it, flash the stock OS.

## What you need

- Elektron Syntakt.
- Stock **Syntakt OS 1.42** from [elektron.se](https://www.elektron.se/support-downloads/syntakt), unmodified.
- Elektron Transfer, from elektron.se.
- USB cable.
- Desktop browser.
- For recovery only: a MIDI interface with a 5-pin MIDI OUT.

`[!]` Not affiliated with Elektron. Modified firmware can make your device unusable and may void your warranty.

## Build

1. Download the stock OS from elektron.se.
2. Open **Create your OS** on the home page.
3. Choose or drop the `.syx` file. The page checks its SHA-256 and refuses any other file.
4. Optional: type your name for the boot screen.
5. Select your mods. Required mods are added automatically.
6. Click **Build my OS**. It takes 30–60 s.
7. Download `synthack.syx` and the build report (`.json`). Keep the report for bug reports.

## Flash

1. Back up your projects and sounds with Transfer.
2. Read [RECOVERY.md](https://github.com/Angelo-politek/Synthack-OS/blob/main/RECOVERY.md). Do one dry run with the stock OS.
3. Connect the Syntakt over USB.
4. Open Transfer. Go to the **Drop** page.
5. Drop `synthack.syx`. Wait until the update is finished. Don't power off.
6. Restart. The SyntHack logo appears at the end of the official intro.

## Go back

1. Open Transfer. Go to the **Drop** page.
2. Drop the stock `.syx` from elektron.se. Wait until the update is finished.

Projects and samples stay on the device.

`[!]` OS doesn't start: follow the MIDI DIN procedure in [RECOVERY.md](https://github.com/Angelo-politek/Synthack-OS/blob/main/RECOVERY.md).

## Readable values

Set an envelope in milliseconds, not in steps of 0–127. Real units: Hz, ms, s, dB, %.

<!-- @screen:readable-values/filter -->
<!-- @screen:readable-values/amp -->
<!-- @screen:readable-values/delay -->

1. Turn any covered knob. The value shows in its unit.

| Parameter | Shown as | Saved |
|---|---|---|
| Filter FREQ, tracks 1–8 | `4.9Hz` … `20.3k` | display only |
| Filter BASE / WDTH, tracks 1–8 | `5.0Hz` … `24.0k` | display only |
| Filter env DEL / ATK / DEC / REL, tracks 1–8 | `0.7ms` … `10.0s`, `INF` | display only |
| Amp ATK / DEC / REL, tracks 1–8; HOLD, all tracks | `0.1ms` … `30.0s`, `INF`; HOLD 127 `NOTE` | display only |
| SUS, filter and amp | `0%` … `100%` | display only |
| LEV, VOL, IN | `-inf` … `0.0dB` | display only |
| Sends DEL / REV: tracks, FX track, external in | `-inf` … `-0.1dB` | display only |
| Delay and reverb HPF / LPF | `5.0Hz` … `24.0k` | display only |
| Delay REV / VOL, reverb VOL | dB | display only |
| Reverb PRE | `0.8ms` … `337ms` | display only |
| Reverb shelving FREQ / GAIN | `974Hz` … `14.0k` / dB | display only |
| Analog filter FREQ, tracks 9–12 and FX track | `15Hz` … `21.5k` | display only |
| Analog amp ATK / DEC / REL, tracks 9–12 and FX track | `~275ms`, `~7.58s` | display only |

`[!]` `~` marks an estimate: ±10–20 %.

`[!]` Still numbers: LFOs, RESO, filter envelope and BASE / WDTH on analog tracks and the FX track, parameters without a unit.

## Bus compressor

More level from the analog output. Compresses the tracks routed to the FX track, together.

<!-- @screen:master-comp/page -->
<!-- @screen:master-comp/meter -->

1. Route the tracks to compress to the FX track.
2. Select the FX track. Open the **SYN** page.
3. Turn **RAT** above `OFF`.
4. Set **THR**. Watch **GR**.
5. Set **MUP** to restore the level.

| Knob | Range | Saved |
|---|---|---|
| A `THR` threshold | −60 … 0 dB | kit (pattern) |
| B `ATK` attack | 0.1 … 100 ms | kit (pattern) |
| C `REL` release | 10 ms … 2 s | kit (pattern) |
| D `MUP` makeup | 0 … +24 dB | kit (pattern) |
| E `RAT` ratio | `OFF`, 1.5:1, 2:1, 3:1, 4:1, 6:1, 8:1, 16:1, 20:1 | kit (pattern) |
| F `GR` gain reduction | meter, 0 … −18 dB; full bar = no reduction | — |
| G `COMP` | ON / OFF, for A/B comparison | not saved, starts ON |
| H `DRIVE` | stock | stock |

`[!]` Tracks not routed to the FX track are not compressed.

`[!]` With *SYN global* on, the settings are global instead of per pattern.

`[!]` Existing projects load with the compressor off.

`[!]` No dry/wet: the compressor drives the analog VCAs.

## Third send FX

A third send effect next to delay and reverb: chorus, flanger, phaser or crusher.

<!-- @screen:fx3/amp -->
<!-- @screen:fx3/page -->
<!-- @screen:fx3/routing -->

1. Select a track. Open **AMP** page 1.
2. Turn **G** (`FX3`, the send). PAN is now on AMP page 2, knob E.
3. Select the FX track. Open the **REVERB** tab. Press it again for page 2 (`FX3`).
4. Turn **A** (`TYPE`) to pick the effect.
5. Optional: open ROUTING (`FUNC` + `FX`). Press trig 13 to send the return to the FX track.

| Knob | CHOR | FLNG | PHSR | CRSH |
|---|---|---|---|---|
| A `TYPE` | `CHOR` | `FLNG` | `PHSR` | `CRSH` |
| B | `SPD` 0.05 … 10 Hz | `SPD` 0.02 … 5 Hz | `SPD` 0.02 … 5 Hz | `SRR` 24 kHz … 750 Hz |
| C | `DEP` 0 … 8 ms | `DEP` 0 … 4 ms | `DEP` 0 … 6 oct | `BITS` 16 … 1 |
| D | `TIME` 1 … 30 ms | `TIME` 0.1 … 8 ms | `FREQ` 100 Hz … 4 kHz | `DRV` 0 … 24 dB |
| E | `FDBK` 0 … 90 % | `FDBK` −95 … +95 % | `FDBK` −90 … +90 % | — |
| F | `WID` 0 … 180° | `WID` 0 … 180° | `WID` 0 … 100 % | — |
| G `DEL` | FX3 → delay | same | same | same |
| H `REV` | FX3 → reverb | same | same | same |

| Control | Where | Saved |
|---|---|---|
| Track send `FX3` | AMP page 1, knob G | per track, in the kit; p-lockable; LFO destination |
| External input send `FX3` | External Mixer page | kit |
| FX3 page | REVERB tab, page 2 | kit (pattern) |
| Return to FX track | ROUTING, trig 13 | kit |

`[!]` Changing TYPE resets knobs B–F to that type's start values. CRSH starts neutral.

`[!]` Older projects load the default values.

`[!]` FX3 uses CPU only while tracks send to it. Many sending tracks with high feedback can make the UI lag. See [Known issues](#known-issues).

## Performance FX

Live effects on keys 13–16: repeat, reverse, half speed, on all tracks. Quantized retrig stays in time.

<!-- @screen:perf-fx/moda -->
<!-- @screen:perf-fx/retrig -->

1. Press `FUNC` + `15`. Mod A is on (`Perf FX ON`) and its setup page opens: M1–M4 set the effect of each key.
2. Hold a key 13–16. Its effect plays.
3. Release. Playback resumes in time.

| Control | Values | Saved |
|---|---|---|
| M1–M4: effect of keys 13–16 | `--`, `1/16`, `1/8`, `3/16`, `1/4`, `1/2`, `1BAR`, `R1/8`, `R1/4`, `R1/2`, `RBAR`, `HALF` | kit |
| `QNT`: Retrig setup page (`FUNC` + `13`), knob D | `OFF` / `ON` | kit |

| Value | Effect |
|---|---|
| `1/16` … `1BAR` | repeat the slice that holds the step just played |
| `R1/8` … `RBAR` | the same slice, backwards |
| `HALF` | half speed inside an 8-step slice |
| `--` | nothing |

Defaults: `1/16`, `1/8`, `R1/4`, `HALF`.

**Quantized retrig:** with `QNT` on and the sequencer running, a retrig played on keys 13–16 starts on the next step of its track.

`[!]` Several keys held: the last one pressed wins.

`[!]` `FUNC` + `13`, `14`, `16` keep their stock modifiers. In keyboard mode, keys 13–16 stay notes.

`[!]` No audio processing: no load on the audio CPU.

## Dual mono input

Two mono instruments on the inputs, as separate channels: IN L and IN R, each with its own level and sends.

<!-- @screen:dual-mono/inr -->

1. Set **SETTINGS → AUDIO ROUTING → EXTERNAL IN** to **mono**.
2. Open the **MIXER** tab, page 3 (External Mixer): this is IN L.
3. Press the tab again until the last page, page 4: this is IN R.

| Page | Knobs | Saved |
|---|---|---|
| MIXER page 3, External Mixer (IN L) | `IN L`; `DEL`, `REV`, `FX3`, `FX` | kit |
| MIXER page 4, IN R | `IN R`; `DEL`, `REV`, `FX3` | kit |

`[!]` Page 4 exists only in mono.

Dry signal: IN L on the left output, IN R on the right. Delay, reverb, FX3 and the FX track (ROUTING, trig 16) get both inputs centered.

`[!]` In stereo, everything works as in the stock OS.

`[!]` Kits from older versions start with the IN R sends at 0.

## SY FM4

A 4-operator FM machine in place of SY TONE. `ALGO` 0 is SY TONE. By Rxuting.

<!-- @screen:sy-fm4/pages -->
<!-- @screen:sy-fm4/algo -->

1. Select a digital track. Pick **SY FM4** as its machine. It replaces SY TONE in the list.
2. Open the **SYN** page: page 1/3.
3. Press **SYN** again for page 2/3, again for page 3/3.
4. Turn `ALGO` above 0. Operators 3 and 4 join in.

| Page | Knobs A–D | Knobs E–H |
|---|---|---|
| 1/3 | `TUNE` `PNCH` `DEC1` `OVER` | `FDBK` `RAT2` `LEV2` `DEC2` |
| 2/3 | `RAT3` `LEV3` `DEC3` `DET` | `RAT4` `LEV4` `DEC4` `ALGO` |
| 3/3 | `ALGO`; the algorithm drawn on the right | — |

| Control | Values |
|---|---|
| `TUNE`, `PNCH`, `OVER`, `FDBK` | as on SY TONE |
| `DEC1` | decay of operator 1, the carrier (SY TONE's DEC) |
| `RAT2`, `LEV2`, `DEC2` | operator 2: SY TONE's RATIO, MOD, MENV |
| `RAT3`, `LEV3`, `DEC3` / `RAT4`, `LEV4`, `DEC4` | ratio, level and decay of operators 3 and 4 |
| `DET` | detune of operators 2–4, ±16 semitones, fine steps |
| `ALGO` | 0 = SY TONE, 1–8 classic 4-operator set, 9 tree, 10 diamond, 11 ring |

The drawing: operators in boxes, modulation as lines, carriers dotted up to the output, feedback as a loop.

Saved with the sound. Every parameter is p-lockable.

`[!]` Sounds and projects made with SY TONE open as SY FM4, `ALGO` 0. They sound the same.

`[!]` Pages 2/3 and 3/3 have no MIDI CC. Their p-locks are lost on a stock OS.

`[!]` Not tested yet on a Syntakt with OS 1.42.

## SAMPLER

The Digitakt's sample machines in place of SP TWINSHOT: ONESHOT, WERP, REPITCH and SLICE, four machines in the menu.

<!-- @screen:sampler/page -->
<!-- @screen:sampler/wave -->

1. Load samples as for SP TWINSHOT. 64 slots.
2. Select a digital track. Pick **ONESHOT**, **WERP**, **REPITCH** or **SLICE** as its machine. They replace SP TWINSHOT in the menu. Knobs E, F, G start at the machine's values; coming from another machine, `TUNE`, `PLAY`, `BR` and `LEV` start at their defaults too.
3. Open the **SYN** page: page 1/2, laid out as the Digitakt's. The page title shows the machine: `SAMPLE`, `WERP`, `REPITCH`, `SLICE`.
4. Press **SYN** again for page 2/2: the sample's waveform.

| Page | Knobs A–D | Knobs E–H |
|---|---|---|
| 1/2 | `TUNE` `PLAY` `BR` `SAMP` | E F G by machine, `LEV` |
| 2/2 | waveform | E F G by machine, H the machine's own |

| Machine | E | F | G |
|---|---|---|---|
| ONESHOT | `STRT` 0–120 | `LEN` 0–120 | `LOOP` (`OFF` = loop from `STRT`) |
| WERP | `SEG` 1/32, 1/16, 1/8 | `MODE` segment play mode | `BARS` 1, 2, 4, 8 |
| REPITCH | `STRT` | `LEN` | `BARS` 1, 2, 4, 8 |
| SLICE | `SLICE`: `NOTE`, 1–64 | `LEN` 1–64 slices | `GRID` 4, 8, 16, 32, 64 |

Knob H on page 2/2, each machine's own (0 = as the Digitakt):

| Machine | H | Does |
|---|---|---|
| ONESHOT | `XFAD` 0–127 | crossfade at the loop point with `FWD.L`/`REV.L`: the end fades into the samples before the loop start (127 ≈ half the loop) |
| WERP | `RAND` 0–127 | chance that a segment jumps to a random place of the sample |
| REPITCH | `KEY` `OFF`/`ON` | `ON`: the note and `TUNE` transpose, the length stays in `BARS` |
| SLICE | `ORDR` `SLICE`/`NEXT`/`RAND` | which slice a trig plays: the `SLICE` knob, the next one on each trig (from `SLICE`), or a random one |

| Control | Values |
|---|---|
| `TUNE` | −60 … +24 semitones |
| `PLAY` | `FWD`, `REV`, `FWD.L`, `REV.L` (loop) |
| `BR` | bit reduction, 0–127 |
| `SAMP` | slot 1–64 |
| `LEV` | sample level 0–127; 100 = the level of SP TWINSHOT |

On page 2/2:

- The part that plays is solid, the rest dotted. A line marks each end.
- ONESHOT: the loop point is a dashed line, flagged at the bottom.
- SLICE: the grid's slices are dotted, the slice picked is solid.

| Machine | How it plays |
|---|---|
| WERP | the sample spans `BARS` bars at the tempo, from each trig; each segment starts on time, at its pitch |
| REPITCH | the part plays in `BARS` bars at the tempo; `TUNE` and the note don't transpose it |
| SLICE | slices start on the nearest zero crossing; with `SLICE` at `NOTE` the note picks the slice |

With `SLICE` at `NOTE`, slice = (note − 12) modulo the number of slices. Up to 16 slices, C4 plays slice 1. The note doesn't transpose. Play the slices from the keyboard in chromatic mode.

Saved with the sound. Every parameter is p-lockable.

`[!]` Sounds made with SP TWINSHOT open as SAMPLER and sound different.

`[!]` No `OVER` on these machines. Elsewhere in the OS (the machine knob's name) the four show as `SAMPLER`.

`[!]` The track's AMP envelope still shapes the sound. `HOLD` at `NOTE` (127) holds it for the trig's length only: for whole samples, use a long `HOLD` or `DEC` at `INF`.

## Long samples

`[wip]` Not tested on the device yet. Back up projects and samples with Transfer first.

Transfer cuts samples at 5 s. Longer samples go through [Synfact](https://github.com/GSM1980/synfact-dev)'s tool over MIDI, into their own storage on the internal memory.

1. Build with **Long samples** and **SAMPLER**. Flash.
2. On the computer, from a checkout of synfact-dev, Transfer closed: `pip install python-rtmidi`, then `python -m elekloader.sdk.syntakt.long_samples put pad.wav --yes-write-device`.
3. Power cycle. "PREPARING SAMPLES" takes longer: it also sends the long samples.
4. On a SAMPLER track, press **SYN** three times: **SAMPLE POOL** lists the long samples with name and length. Turn knob A to pick one: `L1`, `L2`, … in the order `long_samples ls` lists them. Or turn `SAMP` past 64 on page 1/3.

| | |
|---|---|
| Length | up to ~5.8 min per file, ~31 MB in all with the stock samples |
| Files | the first 64 |

## Boot splash

The SyntHack logo, version and your name after the official intro. Part of every build.

<!-- @screen:splash/boot -->

1. Type your name in **Create your OS**, step 2. Up to 20 characters: letters, digits, space, `.` and `-`. Shown in capitals.
2. Build and flash.

`[!]` Boot time is unchanged.

## Known issues

| Issue | Workaround | Status |
|---|---|---|
| UI lag with FX3 together with the compressor, dual mono and the machines | Leave one of them out (the load meter on the site shows it) | `[wip]` being optimized |
| Bus compressor: toggling *global* for the external input mixer also copies the compressor settings | — | known |

## Support

- **Warranty:** modified firmware may void it. Flash the stock OS before you contact Elektron.
- **Sharing:** don't share your built `.syx`. It contains Elektron's OS. Share your mod list instead.
- **Elektronauts:** posting modified firmware is forbidden there. Use [GitHub](https://github.com/Angelo-politek/Synthack-OS).
- **Bugs:** open a [bug report](https://github.com/Angelo-politek/Synthack-OS/issues/new?template=bug_report.md). Attach the build report. Check the stock OS first.
