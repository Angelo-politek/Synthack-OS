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

## What each source records

The Syntakt sums its tracks in analog and has no converter on the main output: no source holds exactly what you hear.

| Source | Signal | Not in it |
|---|---|---|
| TRK 1-8 | The digital track after its filter and amp. POST adds its level, pan, mute and the delay and reverb returns. | The analog FX block, when the track is routed to the FX track |
| TRK 9-12 | The analog voice as the sends read it (converter channels 0-3), inverted. | Track level and pan, the analog FX block. POST adds only the delay and reverb returns |
| MAIN | What goes through the FX track: tracks routed to it, before its drive, filter and level. PRE removes the delay and reverb returns routed there, POST adds the direct ones. | Every track not routed to the FX track, analog ones included |
| IN L, IN R, IN L+R | The inputs as converted, whatever the EXTERNAL IN level. | — |

Record the real output: cable from MAIN OUT to the inputs, EXTERNAL IN level at 0 (no feedback), source IN L+R.

The chosen track gets the SAMPLER and the take. Its filter, amp, overdrive and LFO pages stay as they were.

## SyntHack changes

| Synfact | Here |
|---|---|
| project pool, slots 65-128 | [long-samples](../long-samples)' list: the take is sent to the voice CPU at once (hot upload) and plays without a reboot |
| SP ONE machine | the [SAMPLER](../sampler), SAMP on the take |
| SMZ module | sfcore module (slot 2), view draw context `sfcore:view` |

Code at mod area `+0x20000`, its 47 KB of BSS at `+0x4C000` (runtime RAM). Sources: [synfact/](synfact) (ORIGIN), glue in [glue.c](glue.c).
