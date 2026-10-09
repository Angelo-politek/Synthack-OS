# Mods

| Mod | What | Needs |
|---|---|---|
| [master-comp](master-comp) | VCA bus compressor on the analog master, UI on the FX track SYN page | modarea, vparams |
| [readable-values](readable-values) | Real units (Hz, dB, ms, %) instead of 0–127 | modarea |
| [beat-repeat](beat-repeat) | Sequencer stutter (FX track: retrig keys 13/14, rates on the TRIG page) | modarea, vparams |
| [vparams](vparams) | Virtual parameters shared by mods (kit-parameter hooks + registration table) | modarea |
| [dual-mono](dual-mono) | Independent IN L / IN R levels when EXTERNAL IN is mono | — |
| [splash](splash) | "SyntHack v0.5.0" logo after the official intro | — |
| [modarea](modarea) | Unpacks the (compressed) mod code into 64 KB of RAM at boot | — |
| [mod-zero](mod-zero) | Example: renames a menu entry (smallest possible mod) | — |

Each folder has `make_patch.py` (rebuilds `patch.json` from our sources) and a test in `tests/`.
`patch.json` = list of `{section, addr, len, expect_sha256, hex}`; `"append": true` for mod-area code.
