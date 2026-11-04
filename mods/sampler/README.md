# sampler

SP TWINSHOT becomes **SAMPLER**: the Digitakt's sample machines ONESHOT, WERP, REPITCH and SLICE, rewritten from scratch for the Syntakt, as four machines in the machine menu.

## Use

1. Load samples as for SP TWINSHOT (64 slots).
2. Pick **ONESHOT**, **WERP**, **REPITCH** or **SLICE** as the machine of a digital track (they replace SP TWINSHOT in the menu). The machine starts with its own values of knobs E, F, G; from another machine, `TUNE`, `PLAY`, `BR` and `LEV` start at their defaults too (`SAMP` stays).
3. **SYN 1/2**, as the Digitakt's page: `TUNE PLAY BR SAMP` / `E F G LEV`.
4. Press **SYN** again for **SYN 2/2**: the sample's waveform, with `E F G` and the machine's own parameter `H` under it. The page title is the Digitakt's machine name: `SAMPLE`, `WERP`, `REPITCH`, `SLICE`.

Knob H of page 2/2, one parameter of each machine's own (0 = as the Digitakt):

| Machine | H | Does |
|---|---|---|
| ONESHOT | `XFAD` 0–127 | crossfade at the loop point with `FWD.L`/`REV.L`: the end fades into the samples before the loop start (127 ≈ half the loop) |
| WERP | `RAND` 0–127 | chance that a segment jumps to a random place of the sample |
| REPITCH | `KEY` `OFF`/`ON` | `ON`: the note and `TUNE` transpose, the length stays in `BARS` |
| SLICE | `ORDR` `SLICE`/`NEXT`/`RAND` | which slice a trig plays: the `SLICE` knob, the next one on each trig (from `SLICE`), or a random one |

Value texts and short names as on the Digitakt 1.54 (`NOTE`, `OFF`, `MODE`, `SLICE`).

`[!]` HOLD on the AMP page at `NOTE` (127) holds the sound for the trig's length only: for whole samples use a long HOLD or DEC.

| Machine | E | F | G |
|---|---|---|---|
| ONESHOT | `STRT` 0–120 | `LEN` 0–120 | `LOOP` (`OFF` = from `STRT`) |
| WERP | `SEG` 1/32, 1/16, 1/8 | `MODE` segment play mode | `BARS` 1, 2, 4, 8 |
| REPITCH | `STRT` | `LEN` | `BARS` 1, 2, 4, 8 |
| SLICE | `SLICE` `NOTE`, 1–64 | `LEN` 1–64 slices | `GRID` 4, 8, 16, 32, 64 |

| Control | Values |
|---|---|
| `TUNE` | −60 … +24 semitones |
| `PLAY` | `FWD`, `REV`, `FWD.L`, `REV.L` (loop) |
| `BR` | bit reduction 0–127 |
| `SAMP` | slot 1–64 |
| `LEV` | sample level 0–127, 100 = as SP TWINSHOT |

**SYN 3/3, SAMPLE POOL** (with [long-samples](../long-samples)): knob A is `SAMP`. Four long samples around it, `L` number, name (8 characters) and length; `>` marks the one the track plays, its waveform underneath. Turning A picks a sample for the machine (p-lockable, like any value). Without long samples: `NO LONG SAMPLES`.

| Page 2/2 | Shows |
|---|---|
| Waveform | The part that plays solid, the rest dotted. A line at each end of the part. |
| ONESHOT | The loop point, dashed, flagged at the bottom (the ends are flagged at the top). |
| SLICE | The bounds of the grid's slices dotted across (32 and 64: every 16th of the sample, a tick for the others); the slice picked solid with a line at each end (`NOTE`: the whole sample). |
| Knob boxes | `PLAY` an arrow (a loop over it), `SAMP` the waveform, `STRT`/`LEN`/`LOOP` the waveform with the part. `BR` and `LEV` the OS's own graphics (SY BITS `BR`, SY RAW `LEV2`). |
| Position | Rows 13–35, the rows of the stock knob graphics: above them the OS writes the value being turned. |

- REPITCH plays the part in `BARS` bars at the tempo; `TUNE` and the note do not transpose it, as on the Digitakt (`0x400756C0`).
- WERP: the sample spans `BARS` bars; each segment starts on time, at its pitch.
- SLICE: slices start on the nearest zero crossing, as on the Digitakt. `SLICE NOTE`: the note picks the slice, (note − 12) modulo the slices (C4 = slice 1 up to 16 slices), and does not transpose, as on the Digitakt (`0x4007576A`). Play them from the keyboard (chromatic mode).
- Saved with the sound and p-lockable, like any machine's parameters. The machine itself is not p-lockable (as on the Digitakt).

`[!]` Sounds made with SP TWINSHOT open as SAMPLER and sound different.

`[!]` No `OVER` on these machines: the machine (ONESHOT..SLICE) is kept in its place.

`[!]` Elsewhere in the OS (e.g. the machine knob's name) the four show as `SAMPLER`.

## How it works

| Part | Detail |
|---|---|
| CPU #2 | `engine/`. Engine 11 (SP TWINSHOT) prep/render → SAMPLER, in the [modarea7](../modarea7) engine area. Per block: the part to play, a window of samples (loop or silence past the end), 64 points at 96 kHz, the Syntakt's own half-band filter (`0x400051C6`, the same filter as the Digitakt's) down to 32, `LEV`, then the Syntakt's DEC and VCA. |
| Waveform | The samples are on CPU #2. The main CPU asks for a slot at `0x5B0` of shared RAM; CPU #2 writes 112 peaks at `0x5C0`, two columns per voice prep (at most 48 samples read per column). |
| CPU #1 | `main/smp_main.c`, mod area `+0x8180`. Descriptors 497–504 rewritten (names, ranges, defaults; logical indices `0x12–0x19`). Two SYN pages through [syn-pages](../syn-pages). Value texts and knob graphics, the names of knobs E, F, G by machine. The tempo to shared RAM `0x7F0` once per block. |
| Four machines | All four are machine 44 for the OS. The machine menu shows menu values 45–48 in its place: the list of machines (`0x400264B6`, its check `0x400A64F2` and loop end), the item's name (`0x4002F286`), the category (`0x4002EEB4`: icon and order) and the cursor (`0x4002FBAE`). Picking one, or turning the machine knob (`0x40031272`), goes through `0x40025594`: in front of it `sm_set_machine` sets machine 44, then writes the type and the start values in the sound's data (sound vtable `+40`, `data + 20 + 2 × index`, the words `0x400A321A` copies to the track) and calls the sound's "changed" (vtable `+16`), as the OS does after a machine change. |
| Type | Logical index `0x1A`, the word of the Syntakt's overdrive (it runs after the engines): CPU #2 zeroes it in the frame. |
| Values as set | The voice frames carry the machine's values smoothed by the main CPU (`0x400979CA`, a few percent a block towards a new value). The engine takes `PLAY`, `SAMP`, knobs E, F, G and the type as set, from [xparams](../xparams) (shared RAM `0x640`): a p-lock or a new value counts from its trig. `TUNE`, `BR`, `LEV` stay smoothed. |
| Knob H of 2/2 | Logical index `0x36`, one of [xparams](../xparams)' extra indices (saved, p-lockable, copied with the locks to shared RAM `0x700` every block). On page 2/2 descriptor 503 is rewritten for it, on 1/2 back as `LEV`. Picking a machine sets it to 0. |
| Same as the Digitakt | Start/end of each machine, the 256-point zero-crossing grid, the interpolation arithmetic. Checked against the Digitakt 1.54 code in the emulator, same inputs, same outputs. |
| Ours | The interpolation table: two Kaiser-windowed sincs, five parameters fitted to the Digitakt's response (within 0.2 dB up to half the sample rate). `BR`, `LEV`'s curve (linear, 100 = unity) and WERP's timing (from the trig, as the Digitakt's `0x400ECE8E`: its phase restarts on each trig and moves with the tempo) is our own code. The second page and its graphics are ours: the Digitakt 1.54 has one page per machine. |
| Level | One sample at `LEV` 100 plays at the level of SP TWINSHOT with one sample. |

## Test

`tests/test_sampler.py`: position functions, zero-crossing search, grid and interpolation against the Digitakt 1.54 (local file, never in the repo); table response; on the section 7 emulator (cold boot of the real build) level, `LEV`, TUNE, REV, STRT/LEN, loop, SLICE, REPITCH, WERP, the type kept from the overdrive, the waveform for the main CPU, other machines unchanged; on the main CPU emulator descriptors, value texts, names per machine, both pages, the waveform drawn, tempo, the machine menu (list, names, categories, start values, cursor).

CPU #2, 8 SAMPLER voices: ~84 000 instructions per block (8 SP TWINSHOT: ~64 000; 8 SY SWARM: ~116 000).
