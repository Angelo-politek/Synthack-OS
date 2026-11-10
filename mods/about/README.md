# about

A **SYNTHACK** row at the end of the settings menu.

| Control | Action |
|---|---|
| Settings menu, SYNTHACK, `YES` | Open the list |
| `UP` / `DOWN`, any encoder | Scroll |
| `NO` | Close |

The list: the SyntHack version, the mods in this build with their status (`(BETA)`, `(EXP)`; nothing = stable), the repository, the credits. Attach it to a bug report: it says what is in the build.

- Saved: nothing.
- Audio cost per block: none.
- Tested on the device: no.

## How it works

- The row is added as [Synfact](https://github.com/GSM1980/synfact-dev) adds its own (`mods/core/settings.s`, `mods/system-info-st`; GSM1980 and contributors, on elekloader by irpina, GPL-2.0-or-later): a hook after the last row of the menu's item builder (`0x4005F176`) and a `MenuItem` built from four `std::function` objects (label, select, draw, change).
- The list is drawn over the frame while it is open and takes every key but transport, through [sfcore](../sfcore)'s draw, key, encoder and tick events (module slot 1).
- `about_data.h` is written by `make_patch.py`: the version from the splash, one row per feature or machine in the repository with its status, and the address of that mod's first bytes in the mod area. The loader zeroes the area beyond the code of the build: a mod that is not in the build reads zero there and its row is skipped. Regenerate it when a mod is added or a status or the version changes.

Tests: `tests/test_about.py`. Space: [claims.json](claims.json).
