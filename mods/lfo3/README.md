# lfo3

A third LFO on every audio track. The engine is the LFO3 kernel of [Synfact](https://github.com/GSM1980/synfact-dev) (`mods/lfo3-st`, by GSM1980 and contributors, on elekloader by irpina), on OS 1.42 over [sfcore](../sfcore). License: GPL-2.0-or-later. Sources in [synfact/](synfact/), origin in [synfact/ORIGIN](synfact/ORIGIN).

## Use

- Press the LFO key until page 3: **LFO3**. Same eight parameters as LFO1: SPD, MULT, FADE, DEST, WAVE, SPH, MODE, DEP.
- DEST lists the same destinations as LFO1, the parameters of the mods included ([idspace](../idspace)).
- p-locks work on the eight parameters.
- Saved with the Sound. A Sound made without the mod has DEST at none: no modulation.
- The FX track has no LFO3: its page 3 is empty.

`[!]` Not there yet: copy, paste and randomize of the LFO3 page.

`[!]` A Sound saved with LFO3 loads on a stock OS without it. Its LFO3 values and locks are ignored there.

## Differences from Synfact

| | Synfact | Here |
|---|---|---|
| Parameters | a shadow of the Sound with its own codec and lock service | eight more track parameters of [xparams](../xparams) (indices `0x3E`–`0x45`, Sound slots 62–69, lock lanes `0x58`–`0x5F`): the OS saves, copies and locks them |
| Page | its own page code and actions | parameter ids 530–537 and page 38 of [idspace](../idspace), added to the LFO tab |
| Engine | the same kernel (`synfact/render.s`) | the same, called from sfcore's LFO operation before the two native LFOs |

## Cost

- No LFO3 with a destination: nothing runs in the audio interrupt but one test a block.
- One LFO3 running: ~2 400 instructions a block. The kernel and its state run from the CPU's internal RAM, which never misses the cache.

## Tests

`tests/test_lfo3.py`: the engine against LFO1 bit for bit, the page, the parameters from the working values, zero cost without a destination.

Tested on the device: in the builds since 2026-11-07, not checked item by item yet (page, DEST list, modulation, save, p-locks, stock Sounds).
