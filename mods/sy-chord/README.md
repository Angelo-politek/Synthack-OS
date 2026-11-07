# SY CHORD wave bank for Syntakt OS 1.41

Replaces the 31 editable SY CHORD wave slots with a selected bank of saw, pulse, harmonic, synthetic, and chord spectra. The shared **WAVE 0** sine frame is left unchanged. The mod also replaces the matching waveform pictures in the SY CHORD UI.

The 31 slots are: Saw, Soft saw, Bright saw, Odd saw, Folded saw, Reverse saw, Square, Pulse 25, Pulse 12, Pulse 38, Soft pulse, Double pulse, Organ 1-2-4, Drawbar, Hollow odd, Fifth stack, Octave stack, FM bright, FM glass, FM wood, Wavefold, Formant, Sync edge, Maj, Min, Sus4, Dim, Maj7, 7, m7, and Maj9.

## Compatibility

- Targets only the verified Syntakt OS 1.41 stock input.
- Uses stock section 7 waveform storage and stock section 3 graphics. It needs no loader extension and has no mod dependencies.
- Existing sounds that select an edited CHORD waveform can sound different after applying this mod.
- The same bank is hardware-proven only as part of Kri's separate Syntakt MAX build. This standalone modular build remains hardware-untested until tested independently.

## Regenerating patch.json

The committed manifest contains only replacement bytes and hashes of the expected stock bytes; it contains no Elektron firmware. To regenerate it, use a verified stock OS 1.41 file and Node.js:

    python mods/sy-chord/make_patch.py --stock /path/to/Syntakt_OS1.41.syx --node node

The generator is derived from Bezronczek's MIT-licensed Syntakt Firmware Workbench at the revision recorded in THIRD_PARTY_NOTICES.md.
