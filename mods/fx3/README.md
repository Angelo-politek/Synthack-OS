# fx3

A **third send effect** next to delay and reverb. First effect: stereo **chorus**.

## Use

- **SND3**: every audio track, **AMP page 2**, slot E (under DEL/REV of page 1). Saved per track with the kit, p-lockable, shown in dB like the other sends.
- **FX3 page**: FX track → **REVERB** tab, press it again for page 2 (*Chorus*):

| Knob | Range |
|---|---|
| TYPE | effect type (CHOR for now) |
| SPD | LFO speed, 0.05 … 10 Hz |
| DEP | depth, 0 … 8 ms |
| TIME | base delay, 1 … 30 ms |
| FDBK | feedback, 0 … 90 % |
| WID | L/R LFO phase, 0 … 180° |
| DEL | FX3 → delay send (the chorus goes into the delay, and on to the reverb if the delay sends there) |
| VOL | return level, independent of delay and reverb |

The return goes to the direct bus (like delay and reverb with *FX Routing* off). Page values are not saved yet (they reset at power-on).

## How it works

- **Send gains:** a hook in the per-track loop of the mix function (`0x4008F3A0`) reads SND3 from the engine copy of the track (word +106) and the track's level/pan gain, like the OS does for DEL/REV, mute included. With SND3 at 0 it returns after a few instructions.
- **Bus 3, chorus and return** run after the master sums (`0x4008FB04`), at **24 kHz**: each pair of samples is averaged into the mono bus (EMAC, one pass over the sending tracks), the chorus is one modulated delay line with two interpolated taps (L/R), and the return is brought back to 48 kHz by linear interpolation while it is added to `0x8000DAD0`. The chorus band ends around 11 kHz, like a BBD chorus.
- **DEL send:** the chorus output of the previous block goes into the delay bus right before the delay (`0x4008F828`), 0.67 ms later.
- **Cost** (instructions per 32-sample block, emulator): ~40 idle; ~1 250 with one track sending; ~2 200 worst case (12 tracks, feedback, DEL). Nothing runs without sends, with VOL and DEL at 0, or once the inputs are silent (sequencer stopped) and the tail has died out. The OS already uses ~89 % of the CPU at rest, so this matters: see [docs/audio-path.md](../../docs/audio-path.md#cpu-load).
- **UI:** page 25 (unused "OB8" page) becomes REVERB page 2; the DELAY/REVERB tab is told to draw it as 8 plain slots. Controls are hidden ids 246–253 (Digitakt MIDI-track parameters) via [vparams](../vparams). The AMP tab is patched to give SND3 its own graphic (delay-send icon).
- Needs id 72 free: [master-comp](../master-comp) ATK moved to id 122.

## Build / test

```sh
python mods/fx3/make_patch.py
```

Test: `tests/test_fx3.py` (send gains like the OS, mute, bus sums, chorus as a pure delay, reads inside the line, return interpolation, sign and saturation, send to delay, idle after heavy use and with silent inputs, cost per block, page and drawing hooks, texts).
