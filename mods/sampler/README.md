# sampler

SP TWINSHOT becomes **SAMPLER**: the Digitakt's sample machines ONESHOT, WERP, REPITCH and SLICE, rewritten from scratch for the Syntakt.

## Use

1. Load samples as for SP TWINSHOT (64 slots).
2. Pick **SAMPLER** as the machine of a digital track (it replaces SP TWINSHOT in the list).
3. **SYN** page, as the Digitakt's: `TUNE PLAY BR SAMP` / `E F G TYPE`. `TYPE` picks the machine; knobs E, F, G follow it.

| `TYPE` | E | F | G |
|---|---|---|---|
| `ONE` (ONESHOT) | `STRT` 0–120 | `LEN` 0–120 | `LOOP` (`STRT` = at the start) |
| `WERP` | `SEG` 1/32, 1/16, 1/8 | `SMOD` segment play mode | `BARS` 1, 2, 4, 8 |
| `PTCH` (REPITCH) | `STRT` | `LEN` | `BARS` 1, 2, 4, 8 |
| `SLIC` (SLICE) | `SLIC` `KEY`, 1–64 | `LEN` 1–64 slices | `GRID` 4, 8, 16, 32, 64 |

| Control | Values |
|---|---|
| `TUNE` | −60 … +24 semitones |
| `PLAY` | `FWD`, `REV`, `FWD.L`, `REV.L` (loop) |
| `BR` | bit reduction 0–127 |
| `SAMP` | slot 1–64 |

- REPITCH plays the part in `BARS` bars at the tempo; `TUNE` and the note transpose it.
- WERP: the sample spans `BARS` bars; each segment starts on time, at its pitch.
- SLICE: slices start on the nearest zero crossing, as on the Digitakt. `SLIC KEY` picks the slice from the trig note.
- Saved with the sound and p-lockable, like any machine's parameters.

`[!]` Sounds made with SP TWINSHOT open as SAMPLER and sound different.

`[!]` No `OVER` and no sample `LEV` on this page: use the track level and the AMP page.

## How it works

| Part | Detail |
|---|---|
| CPU #2 | `engine/`. Engine 11 (SP TWINSHOT) prep/render → SAMPLER, in the [modarea7](../modarea7) engine area. Per block: the part to play, a window of samples (loop or silence past the end), 64 points at 96 kHz, the Syntakt's own half-band filter (`0x400051C6`, the same filter as the Digitakt's) down to 32, then the Syntakt's DEC and VCA. |
| CPU #1 | `main/smp_main.c`, mod area `+0x8D00`. Descriptors 497–504 rewritten (names, ranges, defaults; logical indices `0x12–0x19`). Value texts and the names of knobs E, F, G by `TYPE`. The tempo to shared RAM `0x7F0` once per block. |
| Same as the Digitakt | Start/end of each machine, the 256-point zero-crossing grid, the interpolation arithmetic. Checked against the Digitakt 1.54 code in the emulator, same inputs, same outputs. |
| Ours | The interpolation table: two Kaiser-windowed sincs, five parameters fitted to the Digitakt's response (within 0.2 dB up to half the sample rate). `BR` and WERP's timing (from the trig) are our own. |
| Level | One sample plays at the level of SP TWINSHOT with one sample. |

## Test

`tests/test_sampler.py`: position functions, zero-crossing search, grid and interpolation against the Digitakt 1.54 (local file, never in the repo); table response; on the section 7 emulator (cold boot of the real build) level, TUNE, REV, STRT/LEN, loop, SLICE, REPITCH, WERP, OVER off, other machines unchanged; on the main CPU emulator descriptors, value texts, names per `TYPE`, tempo.

CPU #2, 8 SAMPLER voices: ~84 000 instructions per block (8 SP TWINSHOT: ~64 000; 8 SY SWARM: ~116 000).
