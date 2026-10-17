# perf-fx

Performance effects on the sequencer, played with trig keys 13–16. Replaces beat-repeat (v0.6–v0.8).

- **FUNC + 15** (trig modifier *Mod A*) turns keys 13–16 into performance FX keys, on any track. Hold a key to play its effect, release to resume **in time**, where the pattern would have been. With several keys held, the last one pressed wins. FUNC + 13, 14 and 16 keep the stock modifiers. In keyboard mode keys 13–16 stay notes.
- **Effects**, one per key, set in the Mod A setup page (M1–M4, shown as text):

| Text | Effect |
|---|---|
| `1/16` `1/8` `3/16` `1/4` `1/2` `1BAR` | repeat the slice that contains the step just played |
| `R1/8` `R1/4` `R1/2` `RBAR` | the same slice backwards |
| `HALF` | half speed inside an 8-step slice (each step twice) |
| `--` | nothing |

- Defaults: 1/16, 1/8, R1/4, HALF. The values are Mod A's own, so the OS saves them with the kit (FUNC+YES/NO included). Kits from older versions, whose Mod A values are out of range, use the defaults.
- It works on steps (notes and p-locks), so on **all tracks, analog ones included**. No audio processing: no CPU cost in the audio interrupt.
- **Quantized retrig** (v0.9): **QNT** in the Retrig setup page (FUNC + 13, slot D), OFF/ON, saved with the kit. With QNT on and the sequencer running, a retrig played with keys 13–16 (or 1–12 while holding one of them) starts on the **next step** of its track. A key released before that step still plays one step. Stopped, or QNT off: plays at once, as stock.

## How it works

- Sequencer tick `0x4008C924`: per track, the step index `0x43BD73FC + t` advances and wraps on the track/pattern length. A hook at the end of each track's iteration (`0x4008D152`) moves it inside the slice and keeps the real position.
- Keys: hook in the keys 13–16 branch of `KeyboardView::consumeKeyEvent` (`0x4002EA92`), after the OS mode checks. It takes the keys only when the active modifier is Mod A (byte +29 of the project settings, read with `0x40015AF6`). Releases are also caught at the event dispatcher (`0x4000B420`).
- Settings: Mod A M1–M4 are ids 48–51 (group 63), stored in the active kit (`*0x800030B8 + 0x15B6`, words). Their descriptors get range 0–11, the objects a text formatter and a text slot graphic. DEST leaves the page (slot D). Page name "Perf FX", message "Perf FX ON".
- Quantized retrig: hook at the entry of the live retrig note (`0x4002E18C`, view and key). While waiting, the sequencer hook marks the note due on its track's next step and posts a type-6 message (a `std::function` run by the UI loop) to the UI queue `0x405D3A7C` with `0x40001C0E`, the same call a timer interrupt uses; the UI then plays the note. An early release is held at the dispatcher and posted back as a key message one step later. QNT is id 47 (Mod A DEST, unused by perf-fx): range 0–1, text OFF/ON.
- `perf.c` (C, ColdFire gcc) in the mod area at offset `+0x4000`.

Test: `tests/test_perf_fx.py` (repeat, reverse and half speed at every length, release in time, short tracks, effect switch, out-of-range values, keys only in Mod A and not in keyboard mode, native fallback, dispatcher, texts, page and descriptors; quantized retrig: wait for the track's step, message run through the OS UI-loop code, early release, stop before the step, full queue, busy message, QNT page and parameter).
