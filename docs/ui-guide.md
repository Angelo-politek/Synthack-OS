# UI guide for mods

How a mod should look and behave on the device, so every mod feels like part of the same OS. Technique: [modding-guide](modding-guide.md), sections 3–5.

## Names

- Parameter names: 3 or 4 capital letters, as on the Syntakt (`FREQ`, `DEC`, `SND3`). Reuse the OS name when the function is the same.
- Page titles: one or two words in capitals (`FX3`, `IN R`, `ARPEGGIATOR`).
- Value texts: at most 6 characters. A unit only when it helps (`120ms`, `-6.0dB`). `OFF` for zero when zero switches something off.
- Machine names follow the OS: two letters and a word (`SY FM4`).

## Where things go

1. **An existing page** first: a free slot on the page where the user already looks for that function (fx3: SND3 next to the delay and reverb sends on AMP).
2. **A new page in an existing tab** when the mod has up to 8 parameters of its own (fx3: second page of REVERB; lfo3: third page of LFO). The tab key cycles the pages.
3. **A view of its own** only when the mod needs the whole screen or its own keys (recorder, arpeggiator).

Slots: A–D on the top row, E–H on the bottom row. Put the parameter the user turns most on A. Leave a slot empty rather than fill it with a parameter that does nothing in the current mode.

## Keys

| Gesture | Use |
|---|---|
| Double-tap of a key | Opens the view of the mod tied to that key: double SOUND = recorder, double TRIG = arpeggiator |
| NO | Closes a mod view. Always |
| `FUNC` + key | Reserved for the OS and its own shortcuts. A mod takes one only where the OS leaves it unused, and documents it |
| Tab key again | Next page of the tab |

One gesture, one mod. Before taking a key, search the READMEs in `mods/` for it.

## Icons and values

- Take the icon and the style from an OS parameter of the same kind: knob, bipolar, send bar, pan, level, frames by value ([modding-guide](modding-guide.md#5-text-icons-and-styles), table of prototypes). With idspace this is the *model id* of the object definition.
- Draw your own graphics only for what the OS has no picture for (FM4's algorithm, the sampler's waveform). 1-bit, inside the slot box, same line weight as the OS icons.
- A value shown must be the value used: if the sound follows a curve, show the result (ms, Hz, dB), as [readable-values](../mods/readable-values) does.

## Behaviour users expect

- Parameters are saved where the user expects them: sound parameters with the sound, track settings with the kit, global ones with the project. Say where in the README.
- P-locks work on every sound parameter, or the README says they don't.
- LFOs can modulate every continuous sound parameter: add it to the DEST list (idspace).
- A project made with the mod opens on the stock OS and on builds without the mod. A project made without it opens with the mod at its defaults: silent, off, or the stock behaviour.
- Nothing changes until the user touches the mod: default = stock sound.

## README of a mod

One table of controls (gesture or page, action), then where it saves, the audio cost, what was tested on the device. Template: `python tools/new_mod.py <name>`.
