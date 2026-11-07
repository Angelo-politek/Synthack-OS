# recorder

Synfact's audio recorder ([recorder-st](https://github.com/GSM1980/synfact-dev), GPL-2.0-or-later) on OS 1.42, as an [sfcore](../sfcore) module.

| Control | Action |
|---|---|
| Double-tap SOUND | Open the recorder |
| A before recording | PRE / POST FX |
| E / F / G / H | Length / threshold / source / input monitor |
| YES / FUNC+YES | Arm on threshold / record now |
| YES while recording | Stop, then normalize (-1 dBFS) |
| A / C, B / D | Trim start / end, zoom and loupe |
| YES, YES | Confirm the trim, name it, choose a track |

Mono 48 kHz, up to 60 s, from IN L/R/L+R, MAIN L/R/L+R or TRK 1-12.

## SyntHack changes

| Synfact | Here |
|---|---|
| project pool, slots 65-128 | [long-samples](../long-samples)' list: the take is sent to the voice CPU at once (hot upload) and plays without a reboot |
| SP ONE machine | the [SAMPLER](../sampler), SAMP on the take |
| SMZ module | sfcore module (slot 2), view draw context `sfcore:view` |

Code at mod area `+0x20000`, its 47 KB of BSS at `+0x4C000` (runtime RAM). Sources: [synfact/](synfact) (ORIGIN), glue in [glue.c](glue.c).
