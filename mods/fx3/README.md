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

- **Send gains:** a hook in the per-track loop of the mix function (`0x4008F3A0`) reads SND3 from the engine copy of the track (word +106) and the track's level/pan gain, like the OS does for DEL/REV, mute included.
- **Bus 3 and chorus** run right before the delay (`0x4008F828`): mono sum of the 8 digital and 4 analog tracks (EMAC, gains smoothed per block), then one modulated delay line with two interpolated taps (L/R). The output can feed the delay bus in the same loop.
- **Return** added to `0x8000DAD0` after the master sums (`0x4008FB04`).
- **Cost** (instructions per 32-sample block, emulator): ~300 idle — nothing runs without sends or with VOL and DEL at 0 — ~3 100 with 12 tracks sending, ~3 800 worst case. Hot loops in assembly. The OS already uses ~89 % of the CPU at rest, so this matters: see [docs/audio-path.md](../../docs/audio-path.md#cpu-load).
- **UI:** page 25 (unused "OB8" page) becomes REVERB page 2; the DELAY/REVERB tab is told to draw it as 8 plain slots. Controls are hidden ids 246–253 (Digitakt MIDI-track parameters) via [vparams](../vparams). The AMP tab is patched to give SND3 its own graphic (delay-send icon).
- Needs id 72 free: [master-comp](../master-comp) ATK moved to id 122.

## Build / test

```sh
python mods/fx3/make_patch.py            # normal
python mods/fx3/make_patch.py --meter    # test build: audio-interrupt load (avg/peak %) in the TYPE slot
```

Test: `tests/test_fx3.py` (send gains like the OS, mute, bus sums, chorus as a pure delay, send to delay in every loop variant, return sign and saturation, idle after heavy use, cost per block, page and drawing hooks, texts).
