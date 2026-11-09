# fx3

Third send effect next to delay and reverb: **chorus**, **flanger**, **phaser** or **crusher**.

## Use

| Control | Where | Saved |
|---|---|---|
| SND3 (shown `FX3`) | every audio track, **AMP page 1**, knob G, next to DEL and REV. PAN moves to page 2, knob E | per track, with the kit; p-lockable; LFO destination |
| External input FX3 send | External Mixer page, knob C. With dual-mono in mono: next to REV | kit: low byte of FX-track word 0x37 |
| FX track FX3 send | FX track **AMP page 1**, knob G, next to DEL and REV. PAN moves to page 2, knob E | kit (kitstore word) |
| FX3 page | FX track → **REVERB** tab, press again for page 2 | kit (pattern) |
| LFO | The FX track's LFO1/LFO2 DEST menu lists SPD, DEP, TIME, FDBK, DEL, REV of the FX3 page (WID not: no free slot) | — |
| Return routing | ROUTING screen (FUNC+FX), **trig 13**, next to delay (14) and reverb (15) | kit: bit 8 of FX-track word 0x37 |

FX3 page: A `TYPE`; B–F change name and range with TYPE; G `DEL`; H `REV`.

| TYPE | B | C | D | E | F |
|---|---|---|---|---|---|
| CHOR | SPD 0.05 … 10 Hz | DEP 0 … 8 ms | TIME 1 … 30 ms | FDBK 0 … 90 % | WID 0 … 180° (L/R LFO phase) |
| FLNG | SPD 0.02 … 5 Hz | DEP 0 … 4 ms | TIME 0.1 … 8 ms | FDBK −95 … +95 % | WID 0 … 180° |
| PHSR | SPD 0.02 … 5 Hz | DEP 0 … 6 oct | FREQ 100 Hz … 4 kHz | FDBK −90 … +90 % | WID 0 … 100 % |
| CRSH | SRR 24 kHz … 750 Hz | BITS 16 … 1 | DRV 0 … 24 dB | – | – |

- `DEL`: FX3 → delay. Continues to the reverb if the delay sends there.
- `REV` (v0.9, replaces VOL): FX3 → reverb.
- Return to the master: fixed at 0 dB. The SND3 sends set the amount.
- Changing TYPE resets SPD…WID to that type's start values. DEL and REV are kept. CRSH starts neutral: 24 kHz, 16 bits, no drive.
- After a TYPE change the effect is silent for 8 blocks (~5 ms) while its delay line clears, 1/8 per block. Clearing it in one block overran the audio interrupt.
- FLNG and PHSR feedback is bipolar: center = none.
- PHSR: four allpass stages. WID turns the right side into the complementary response.
- CRSH is mono. It hides knobs E and F.
- Each knob uses the icon of a similar OS parameter (machine SPD, MOD, sweep time/depth, TONE, BAL, OVER…).
- FX track send: the FX track bus (ADC 6/7, after the analog FX block) into FX3, as the OS feeds it to the delay and reverb. Off while the FX3 return goes to the FX track (ROUTING trig 13), as the OS does for DEL and REV, to avoid a loop.
- SND3 is shown in dB, with the machines' MOD icon. External input send: same gain law as the input DEL/REV (level and balance, then (v/32768)²), from ADC 4/5.

`[!]` Kits saved with v0.8.1 start with REV at 0 (that byte held VOL).

`[!]` Older projects load the default values.

## Storage

- FX3 page: four words of the pattern kit the OS never uses (internal ids 0, 0x1A, 0x38 = hidden id 144, 0x46), one byte per knob.
- The kit file format drops words 0x1A and 0x46 and reads word 0 back from 0x1A (FUNC+YES/NO, project save).
- Hooks on the FX block writer / reader (`0x400A6E0E` / `0x400A6DA6`) keep those three words in 8 bytes the OS zeroes and never reads (marker `SH`).
- Files without the marker load the defaults.

## How it works

| Part | Detail |
|---|---|
| Send gains | Hook in the per-track loop of the mix function (`0x4008F418`). Reads SND3 (engine word +106) and the track's level/pan gain, as the OS does for DEL/REV, mute included. SND3 = 0: returns after a few instructions. |
| Bus, effect, return | After the master sums (`0x4008FB7C`), at **24 kHz**. Sample pairs averaged into the mono bus (EMAC, one pass over sending tracks) → effect → linear interpolation to 48 kHz, added to `0x8000DAD0`. Band ends ~11 kHz, like a BBD chorus. |
| Chorus / flanger | One modulated delay line, two interpolated taps (L/R). TIME changes glide: at most 8 samples per block. |
| DEL / REV sends | Previous block's output goes into the delay and reverb input buses (0.67 ms later), inside our replacement of the OS loops that finish those buses (`0x4008F852`, `0x4008F98A`): same result as the OS loop, fewer instructions. |
| Routing | Hooks on the ROUTING key handler (`0x4004C5E2`), entry state (`0x4004BF86`), drawing of entry 13 (`0x4004C242`), its LED (`0x4004C480`). Return goes to the direct bus, or to the FX track (analog FX block, bus compressor). |
| UI | Page 25 (unused "OB8") becomes REVERB page 2, drawn as 8 plain slots. Controls: ids 505–512 ([idspace](../idspace)) via [vparams](../vparams). Names are RAM strings rewritten with the icons and slots when TYPE changes, from UI code only ([modding guide](../../docs/modding-guide.md#5-text-icons-and-styles)). The AMP tab is patched to give SND3 its own graphic. |
| LFO | The FX3 controls take internal ids of FX kit words the OS does not use (0x24, 0x27, 0x29, 0x1A, 0x46, 0x37): the FX track's LFOs compute their modulation there and nobody else applies it. Each block the audio hook reads the two DESTs (a 256-byte table); on a hit the page values + modulation give the derived values, then the knob values return. |
| Idle | Nothing runs without sends, or once the inputs are silent (sequencer stopped) and the tail has died out. |

## Cost

Instructions per 32-sample block over stock, emulator, without the per-track hook. The stock OS uses ~89 % of the CPU at rest ([docs/audio-path.md](../../docs/audio-path.md#cpu-load)).

| Case | Instructions |
|---|---|
| Idle | ~−100 (the replaced OS loops cost more) |
| One track: CHOR / FLNG / PHSR / CRSH | ~1,030 / ~1,210 / ~1,320 / ~780 |
| Worst case: 12 tracks and the input sending, maximum feedback and sends | ~2,660 (ceiling 2,700 in `tests/test_cpu_budget.py`) |

Instructions are not the time: the audio interrupt doesn't fit the 8 KB instruction cache, so every 16-byte code line run and every DDR data line touched is a DDR read each block (`tools/emu/cycles.py`, calibrated with cpu-meter). So the per-block path is compact assembly kept together, its state is one 432-byte block (23 lines with the chorus), the effect output is 16-bit, and knob-derived values are computed when a knob moves. Only rare work is C: parameters changed, TYPE change, line clear, crusher.

| Cache model, scene max | Before (C `fx3_run`) | Now |
|---|---|---|
| fx3 cycles per block over fastmix | ~14,400 | ~10,700 |
| Code / data lines per block | 153 / 41 | 105 / 32 |
| Interrupt, fx3 alone | 95.6 % | 92.7 % |
| fx3 + master-comp + dual-mono | 99.3 % | 96.2 % |
| Every audio mod | 101.2 % | 97.3 % |

Same output as the C version, bit for bit: `test_same_output_as_the_c_version` runs both (`tests/data/fx3_c.json`) on random blocks.

`[!]` With fx3, master-comp and dual-mono together the interrupt is still above ~95 %: the UI may lag. To measure on the device ([docs/status.md](../../docs/status.md#audio-cpu)).

## Build and test

```sh
python mods/fx3/make_patch.py
python -m pytest tests/test_fx3.py
```

`tests/test_fx3.py` covers: send gains like the OS, mute, bus sums, chorus as a pure delay, reads inside the line with sudden TIME changes, phaser and crusher against bit-exact models, return interpolation, sign and saturation, send to delay, idle after heavy use and with silent inputs, cost per block and per type, same output as the previous C version on random blocks, kit storage and pattern change, kit file round trip through the OS writer/reader, names and texts per type, page and drawing hooks, ROUTING key 13 and the return on the FX-track bus.
