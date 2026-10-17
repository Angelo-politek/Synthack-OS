# fx3

A **third send effect** next to delay and reverb: **chorus**, **flanger**, **phaser** or **crusher**.

## Use

- **External input** (v0.9): its own FX3 send, slot C of the External Mixer page, stereo and mono. Same gain law as the input's DEL/REV sends (level and balance, then (v/32768)²), from ADC 4/5 into the FX3 bus; value saved with the kit (low byte of FX-track word 0x37).
- **SND3**: every audio track, **AMP page 1**, slot G, next to DEL and REV (PAN moves to page 2, slot E). Saved per track with the kit, p-lockable, shown in dB like the other sends, with the machines' MOD icon. Since v0.9 it is also an LFO destination, like DEL and REV (same descriptor flags).
- **FX3 page**: FX track → **REVERB** tab, press it again for page 2. TYPE picks the effect; the next five knobs change name and range with it:

| TYPE | B | C | D | E | F |
|---|---|---|---|---|---|
| CHOR | SPD 0.05 … 10 Hz | DEP 0 … 8 ms | TIME 1 … 30 ms | FDBK 0 … 90 % | WID 0 … 180° (L/R LFO phase) |
| FLNG | SPD 0.02 … 5 Hz | DEP 0 … 4 ms | TIME 0.1 … 8 ms | FDBK −95 … +95 % | WID 0 … 180° |
| PHSR | SPD 0.02 … 5 Hz | DEP 0 … 6 oct | FREQ 100 Hz … 4 kHz | FDBK −90 … +90 % | WID 0 … 100 % |
| CRSH | SRR 24 kHz … 750 Hz | BITS 16 … 1 | DRV 0 … 24 dB | – | – |

- **DEL**: FX3 → delay send (the effect goes into the delay, and on to the reverb if the delay sends there). **REV** (v0.9, in place of VOL): FX3 → reverb send. The return to the master is fixed at full level (0 dB); the amount of effect is set by the SND3 sends. Kits saved with v0.8.1 start with REV at 0 (that byte used to hold VOL).
- Changing TYPE resets SPD…WID to that type's starting values; CRSH starts neutral (24 kHz, 16 bits, no drive), so landing on it by accident doesn't wreck the sound. DEL and REV are kept.
- FLNG and PHSR feedback is bipolar: centre = none. PHSR is four allpass stages; WID turns the right side into the complementary response (notches where the left has peaks). CRSH is mono and hides the two knobs it doesn't use.
- Each knob takes the icon of a similar OS parameter (machine SPD, MOD, sweep time/depth, TONE, BAL, OVER…), so every effect looks different.
- **Routing** (v0.9): the return goes to the direct bus, or to the FX track (analog FX block and bus compressor) with **trig 13 on the ROUTING screen** (FUNC+FX), next to delay (14) and reverb (15). Saved with the kit (bit 8 of FX-track word 0x37). Hooks on the screen's key handler (`0x4004C5E2`), entry state (`0x4004BF86`), drawing of the empty entry 13 (`0x4004C242`) and its LED (`0x4004C480`).
- **Saved with the kit** (per pattern, like delay and reverb): in four words of the pattern kit the OS never uses (internal ids 0, 0x1A, 0x38 = hidden id 144, 0x46), one byte per knob. Older projects load with the default values. The OS kit file format drops words 0x1A and 0x46 and reads word 0 back from 0x1A (FUNC+YES/NO, project save): hooks on the FX block writer/reader (`0x400A6D96` / `0x400A6D2E`) keep the three words in 8 bytes of the block the OS zeroes and never reads (marker `SH`). Files without the marker load the defaults.

## How it works

- **Send gains:** a hook in the per-track loop of the mix function (`0x4008F3A0`) reads SND3 from the engine copy of the track (word +106) and the track's level/pan gain, like the OS does for DEL/REV, mute included. With SND3 at 0 it returns after a few instructions.
- **Bus 3, effect and return** run after the master sums (`0x4008FB04`), at **24 kHz**: each pair of samples is averaged into the mono bus (EMAC, one pass over the sending tracks), then the effect, and the return is brought back to 48 kHz by linear interpolation while it is added to `0x8000DAD0`. The band ends around 11 kHz, like a BBD chorus.
- **Chorus / flanger**: one modulated delay line with two interpolated taps (L/R). A sudden TIME change glides (at most 8 samples per block), so the taps never jump.
- **DEL send:** the chorus output of the previous block goes into the delay bus right before the delay (`0x4008F828`), 0.67 ms later.
- **Cost** (instructions per 32-sample block, emulator, one track sending): CHOR ~1 300, FLNG ~1 500, PHSR ~1 700, CRSH ~850; ~60 idle; ~2 300 worst case (12 tracks, feedback, DEL). Nothing runs without sends, or once the inputs are silent (sequencer stopped) and the tail has died out. The OS already uses ~89 % of the CPU at rest, so this matters: see [docs/audio-path.md](../../docs/audio-path.md#cpu-load).
- **UI:** page 25 (unused "OB8" page) becomes REVERB page 2; the DELAY/REVERB tab is told to draw it as 8 plain slots. Controls are hidden ids 246–253 (Digitakt MIDI-track parameters) via [vparams](../vparams); their names are RAM strings rewritten when TYPE changes, together with the icons and the page slots — from UI code only (see [modding guide](../../docs/modding-guide.md#5-text-icons-and-styles)). The AMP tab is patched to give SND3 its own graphic (delay-send icon).
- Needs id 72 free: [master-comp](../master-comp) ATK moved to id 122.

## Build / test

```sh
python mods/fx3/make_patch.py
```

Test: `tests/test_fx3.py` (send gains like the OS, mute, bus sums, chorus as a pure delay, reads inside the line with sudden TIME changes, phaser and crusher against bit-exact models, return interpolation, sign and saturation, send to delay, idle after heavy use and with silent inputs, cost per block and per type, kit storage and pattern change, kit file round trip through the OS writer/reader, names and texts per type, page and drawing hooks, ROUTING key 13 and the return on the FX-track bus).
