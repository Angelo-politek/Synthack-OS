# Mods

One folder per mod. Target: Syntakt OS 1.42.

| Mod | Kind | What | Requires |
|---|---|---|---|
| [splash](splash) | base | Logo, version and optional name after the official intro | — |
| [master-comp](master-comp) | feature | Compressor on the FX track bus; UI on the FX track SYN page | modarea, vparams |
| [readable-values](readable-values) | feature | Real units (Hz, dB, ms, %) instead of 0–127 | modarea |
| [perf-fx](perf-fx) | feature | Mod A (FUNC+15): keys 13–16 repeat, reverse or half-speed the pattern; quantized retrig | modarea |
| [fx3](fx3) | feature | Third send effect (chorus, flanger, phaser, crusher): SND3 per track, REVERB tab page 2 | modarea, vparams |
| [dual-mono](dual-mono) | feature | EXTERNAL IN mono: separate IN L / IN R levels and sends | modarea, vparams, kitstore |
| [modarea](modarea) | infra | Unpacks the compressed mod code at boot into a 64 KB block of the OS heap | — |
| [vparams](vparams) | infra | Virtual parameters shared by mods: kit-parameter hooks + registration table | modarea |
| [kitstore](kitstore) | infra | 36 words saved with the kit (reserved bytes of the per-track kit blocks) | modarea |
| [projstore](projstore) | infra | 256 bytes saved with the project (reserved area of the project settings) | modarea |
| [mod-zero](mod-zero) | test | Example: renames a menu entry; smallest possible mod | — |

## Files

| File | Content |
|---|---|
| `patch.json` | `name`, `os`, `requires`, `patches`: list of `{section, addr, len, expect_sha256, hex}`; `"append": true` for mod-area code |
| `make_patch.py` | Rebuilds `patch.json` from our sources (mod-zero: hand-written `patch.json`) |
| `mod.json` | Card for the web builder: `{title, kind, summary}` |
| `README.md` | Use, how it works, tests |

Each mod has a test in `tests/`. Shared resources: [docs/registry.md](../docs/registry.md).
