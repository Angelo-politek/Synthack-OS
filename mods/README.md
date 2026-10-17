# Mods

| Mod | What | Needs |
|---|---|---|
| [master-comp](master-comp) | VCA bus compressor on the analog master, UI on the FX track SYN page | modarea, vparams |
| [readable-values](readable-values) | Real units (Hz, dB, ms, %) instead of 0–127 | modarea |
| [beat-repeat](beat-repeat) | Sequencer stutter (FX track: retrig keys 13/14, rates on the TRIG page) | modarea, vparams |
| [fx3](fx3) | Third send effect (chorus, flanger, phaser, crusher): SND3 per track, page 2 of the REVERB tab | modarea, vparams |
| [vparams](vparams) | Virtual parameters shared by mods (kit-parameter hooks + registration table) | modarea |
| [dual-mono](dual-mono) | Independent IN L / IN R levels when EXTERNAL IN is mono | — |
| [splash](splash) | "SyntHack" logo and version after the official intro | — |
| [modarea](modarea) | Unpacks the (compressed) mod code at boot into a 64 KB block of the OS heap | — |
| [mod-zero](mod-zero) | Example: renames a menu entry (smallest possible mod) | — |
| [deja-vu](deja-vu) | DV-F / DV-T looping random LFO shapes; standalone hardware validation pending | — |

Each folder has `make_patch.py` (rebuilds `patch.json` from our sources) and a test in `tests/` (mod-zero: hand-written `patch.json`).
`patch.json` = list of `{section, addr, len, expect_sha256, hex}`; `"append": true` for mod-area code.
