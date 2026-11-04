# Mods

One folder per mod. Target: Syntakt OS 1.42.

| Mod | Kind | What | Requires |
|---|---|---|---|
| [splash](splash) | base | Logo, version and optional name after the official intro | — |
| [master-comp](master-comp) | feature | Compressor on the FX track bus; UI on the FX track SYN page | modarea, vparams, fastmix |
| [readable-values](readable-values) | feature | Real units (Hz, dB, ms, %) instead of 0–127 | modarea |
| [perf-fx](perf-fx) | feature | Mod A (FUNC+15): keys 13–16 repeat, reverse or half-speed the pattern; quantized retrig | modarea |
| [fx3](fx3) | feature | Third send effect (chorus, flanger, phaser, crusher): SND3 per track, REVERB tab page 2 | modarea, vparams, fastmix |
| [dual-mono](dual-mono) | feature | EXTERNAL IN mono: separate IN L / IN R levels and sends | modarea, vparams, kitstore, fastmix |
| [sy-fm4](sy-fm4) | machine | SY TONE becomes a 4-operator FM machine (Rxuting, MIT); three SYN pages, algorithm drawn on 3/3; ALGO 0 = SY TONE | modarea, modarea7, syn-pages, xparams, fastmix |
| [sampler](sampler) | machine | SP TWINSHOT becomes the Digitakt's sample machines: ONESHOT, WERP, REPITCH, SLICE, four machines in the menu; SYN 1/2 as the Digitakt's, 2/2 waveform and one parameter of each machine | modarea, modarea7, syn-pages, xparams |
| [modarea](modarea) | infra | Unpacks the compressed mod code at boot into a 128 KB block of the OS heap; boot list for setup functions | — |
| [modarea7](modarea7) | infra | Room for machine code on the sound engine (CPU #2): section 7 travels compressed | — |
| [syn-pages](syn-pages) | infra | SYN pages of its own for a machine: up to 4 pages, names, drawing | modarea |
| [xparams](xparams) | infra | Eight more parameters per track (logical indices 0x36–0x3D): saved, p-lockable, sent to the voice CPU | modarea |
| [vparams](vparams) | infra | Virtual parameters shared by mods: kit-parameter hooks + registration table | modarea |
| [kitstore](kitstore) | infra | 36 words saved with the kit (reserved bytes of the per-track kit blocks) | modarea |
| [fastmix](fastmix) | infra | Two hot OS audio routines (bus sums, parameter smoothing) rewritten: same output, ~11 000 fewer instructions per block | modarea |
| [projstore](projstore) | infra | 256 bytes saved with the project (reserved area of the project settings) | modarea |
| [cpu-meter](cpu-meter) | test | Diagnostic: audio interrupt load measured on the device (DTIM0), average and peak on the parameter pages | modarea |
| [mod-zero](mod-zero) | test | Example: renames a menu entry; smallest possible mod | — |

## Files

| File | Content |
|---|---|
| `patch.json` | `name`, `os`, `requires`, `patches`: list of `{section, addr, len, expect_sha256, hex}`; `"append": true` for mod-area code |
| `make_patch.py` | Rebuilds `patch.json` from our sources (mod-zero: hand-written `patch.json`) |
| `mod.json` | Card for the web builder: `{title, kind, summary}` |
| `README.md` | Use, how it works, tests |

Each mod has a test in `tests/`. Shared resources (mod area, boot list, engine area, shared RAM, ids): [docs/registry.md](../docs/registry.md).
