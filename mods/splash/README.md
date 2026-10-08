# splash

Shows the **SyntHack** logo (figlet *smslant*) and the version after the official boot animation.

- The intro task plays lists of `{function, frames}`; `splash_draw` copies a 1024-byte logo into the frame buffer.
- The last 57 frames of each of the 5 official animations are replaced by the logo, so **boot time is unchanged** (a longer intro hangs the OS on "PREPARING SAMPLES").
- The screen is upside down during the intro: the logo is stored flipped.
- Code and logo at `0x40338740–0x40338BD8` (free fill); 5 `pea` instructions redirected.

Version text: `VERSION` in `make_patch.py`. Test: `tests/test_splash_mod.py`.
