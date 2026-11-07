# arp

The arpeggiator of [Synfact](https://github.com/GSM1980/synfact-dev) (`mods/arp-st`, by GSM1980 and contributors, on elekloader by irpina) on OS 1.42, over [sfcore](../sfcore). License: GPL-2.0-or-later. Sources in [synfact/](synfact/), changes in [synfact/ORIGIN](synfact/ORIGIN).

## Use

- Press TRIG twice on an audio track (main screen): the ARPEGGIATOR view opens. NO closes it.
- A MODE (OFF, TRUE, UP, DOWN, CYCL), B SPEED (1/1 … 1/96), C RANGE (1–4 octaves), D LEN (note length), E OFS (note offset of the selected step), F number of steps.
- The 16 trig keys are the arp's steps: press to select, release to mute or unmute; turn any encoder while holding steps to set their offsets. LEFT/RIGHT select, UP/DOWN change the offset, YES mutes.
- A trig with ARP on starts the arp, which runs as long as the trig's length. Held keys (keyboard, MIDI) play it live.
- p-locks: with REC on, hold trigs and turn A..D. Press A..D while holding them to clear that lock.

## Differences from Synfact

| | Synfact | Here |
|---|---|---|
| Settings | per Sound (side storage) | per audio track, saved with the project ([projstore](../projstore), 24 bytes a track) |
| p-locks | four lanes of LFO3's lock service | one native lock on the Sound's spare logical index `0x46`, saved as lane `0x60` by [xparams](../xparams): the OS saves, copies, pastes and clears it like any lock |
| LEN | 128 values | 56 values (the packed lock must stay below `0x8000`) |

The lock packs MODE, SPEED, RANGE and LEN, each with "not locked", in mixed radix 6 × 19 × 5 × 57. A pattern has room for 79 lock lanes; the first ARP lock of a track takes one.

`[!]` A project with ARP locks opened on a stock OS loses those locks; ARP settings are ignored.

## Cost

Idle (no arp running): the render-in call counts the block and returns. Running arps: Synfact measured ~8 % of the audio interrupt for 12 tracks.

## Test

[tests/test_arp.py](../../tests/test_arp.py): sources and patch; binding; the selector against Digitone 1.44's (Synfact's differential test); packed locks through the OS's own lock functions and lock objects; settings round trip; project file lane `0x60`; idle cost.
