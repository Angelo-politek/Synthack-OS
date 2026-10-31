# splash

SyntHack logo (figlet *smslant*), version and optional name after the official boot animation. `kind: base`: in every build.

| Item | Value |
|---|---|
| Code and logo | `0x40339740–0x40339BD8`, section 3 free fill |
| Hooks | 5 `pea` instructions redirected |
| Frames | last 57 frames of each of the 5 official animations |
| Version text | `VERSION` in `make_patch.py` |
| Name | `build.py --name`, or the web builder. Redrawn into the logo at build time; position in `layout` of `patch.json` |
| Test | `tests/test_splash_mod.py` |

- The intro task plays lists of `{function, frames}`. `splash_draw` copies a 1024-byte logo into the frame buffer.
- The logo replaces frames, so **boot time is unchanged**. A longer intro hangs the OS on "PREPARING SAMPLES".
- The screen is upside down during the intro. The logo is stored flipped.
