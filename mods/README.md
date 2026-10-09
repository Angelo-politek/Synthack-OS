# Mods

| Mod | What | Needs |
|---|---|---|
| [master-comp](master-comp) | VCA bus compressor on the analog master, UI on the FX track SYN page | modarea |
| [readable-values](readable-values) | Real units (Hz, dB, ms, %) instead of 0–127 | modarea |
| [dual-mono](dual-mono) | Independent IN L / IN R levels when EXTERNAL IN is mono | — |
| [splash](splash) | "SyntHack v0.5.0" logo after the official intro | — |
| [modarea](modarea) | Loads 32 KB of mod code into RAM at boot | — |
| [mod-zero](mod-zero) | Example: renames a menu entry (smallest possible mod) | — |

Each folder has `make_patch.py` (rebuilds `patch.json` from our sources) and a test in `tests/`.
`patch.json` = list of `{section, addr, len, expect_sha256, hex}`; `"append": true` for mod-area code.
