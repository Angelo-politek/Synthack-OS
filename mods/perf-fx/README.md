# perf-fx

Performance effects on the sequencer, on trig keys 13–16. Replaces beat-repeat (v0.6–v0.8).

## Use

1. Press **FUNC + 15** (trig modifier *Mod A*). Keys 13–16 become performance FX keys, on any track.
2. Hold a key. Its effect plays.
3. Release. Playback resumes **in time**, where the pattern would have been.

| Control | Where | Values | Saved |
|---|---|---|---|
| M1–M4 | Mod A setup page (`Perf FX`) | effect of keys 13–16, shown as text | kit (FUNC+YES/NO included) |
| `QNT` | Retrig setup page (FUNC + 13), knob D | OFF / ON | kit |

| Text | Effect |
|---|---|
| `1/16` `1/8` `3/16` `1/4` `1/2` `1BAR` | repeat the slice that holds the step just played |
| `R1/8` `R1/4` `R1/2` `RBAR` | the same slice backwards |
| `HALF` | half speed inside an 8-step slice (each step twice) |
| `--` | nothing |

- Defaults: `1/16`, `1/8`, `R1/4`, `HALF`. Kits from older versions (Mod A values out of range) use the defaults.
- Several keys held: the last one pressed wins.
- FUNC + 13, 14 and 16 keep the stock modifiers. In keyboard mode, keys 13–16 stay notes.
- Works on steps (notes and p-locks): **all tracks, analog included**. No audio processing: no cost in the audio interrupt.

**Quantized retrig** (v0.9), QNT on, sequencer running:

- A retrig on keys 13–16 (or 1–12 while holding one of them) starts on the **next step** of its track.
- A key released before that step still plays one step.
- Sequencer stopped, or QNT off: plays at once, as stock.

## How it works

| Part | Detail |
|---|---|
| Sequencer | Tick `0x4008C99C`: per track, step index `0x43BD83FC + t` advances and wraps. Hook at the end of each track's iteration (`0x4008D1CA`) moves it inside the slice and keeps the real position. |
| Keys | Hook in the keys 13–16 branch of `KeyboardView::consumeKeyEvent` (`0x4002EA92`), after the OS mode checks. Active only when the modifier is Mod A (byte +29 of the project settings, read with `0x40015AF6`). Releases also caught at the event dispatcher (`0x4000B420`). |
| Settings | Mod A M1–M4 = ids 48–51 (group 63), in the active kit (`*0x800030B8 + 0x15B6`, words). Descriptors: range 0–11. Objects: text formatter, text slot graphic. DEST leaves the page (slot D). Page name "Perf FX", message "Perf FX ON". |
| Quantized retrig | Hook at the entry of the live retrig note (`0x4002E18C`, view and key). The sequencer hook marks the note due on the track's next step and posts a type-6 message (`std::function` run by the UI loop) to the UI queue `0x405D4A7C` with `0x40001C0E`, the call a timer interrupt uses. The UI plays the note. An early release is held at the dispatcher and posted back one step later. |
| QNT | Id 47 (Mod A DEST, unused by perf-fx): range 0–1, text OFF/ON. |
| Code | `perf.c` (C, ColdFire gcc), mod area `+0x4000`. |

## Test

`tests/test_perf_fx.py`: repeat, reverse and half speed at every length; release in time; short tracks; effect switch; out-of-range values; keys only in Mod A and not in keyboard mode; native fallback; dispatcher; texts, page, descriptors. Quantized retrig: wait for the track's step, message run through the OS UI-loop code, early release, stop before the step, full queue, busy message, QNT page and parameter.
