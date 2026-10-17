# Déjà Vu LFO

Adds two shapes after the seven stock LFO shapes on the existing **WAVE** control:

- **DV-F**: a looping random sequence that runs freely.
- **DV-T**: the same sequence, restarted by a note trigger.

For either shape, **MODE** selects a 2, 4, 8, 16, or 32 step loop. **SPH** controls the Deja Vu behaviour: 0 continually generates values, 64 repeats the loop, and 127 changes the ordering of the loop values.

The patch extends existing LFO tables and keeps the stock WAVE parameter, so it does not introduce descriptor IDs, virtual parameters, or a new persistence format. The seven stock shapes remain in their original positions.

## Status

This is an OS 1.41 modular-port candidate. The implementation was integrated into Kári's MAX build and exercised on hardware there; this standalone upstream composition still requires its own emulator and hardware validation before it can be described as hardware-proven.

## Attribution

The original Déjà Vu algorithm, OS 1.41 patch design, and artwork are by **Bezronczek**, from [Syntakt Firmware Workbench](https://github.com/Bezronczek/syntakt-firmware-workbench), under the MIT License. Kári G. contributed the SyntHack modular-port work, integration, and validation plan. See [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).

The make_patch.py generator creates patch.json from a user-supplied official Syntakt OS 1.41 image; neither firmware nor extracted firmware data belongs in this repository.
