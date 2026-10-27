# Contributing

## Setup

- **Windows 11 + WSL (Ubuntu)** or Linux. Python 3.11+.
- `bash tools/unpack/setup_eft.sh` — builds elektron-firmware-tool (pinned commit) into `third_party/`.
- `pip install unicorn pytest`
- ColdFire binutils and gcc in WSL: `sudo apt install binutils-m68k-linux-gnu gcc-13-m68k-linux-gnu` (or unpack the `.deb`s into `~/tools/m68k/root`, as the `make_patch.py` scripts expect).
- `git config core.hooksPath tools/hooks`
- Put your stock OS in `firmware/` and run `python -m pytest` (tests needing it are skipped otherwise).

## Rules

1. **Never commit firmware bytes.** Patches hold our bytes + a hash of what they replace.
2. **Emulate before flashing.** Every mod has tests that run the original OS code in `tools/emu` and compare.
3. **Never touch sections 2 (bootstrap) or 6 (boot).** `eft.py` refuses; don't work around it.
4. **Don't change boot timing.** The OS hangs on "PREPARING SAMPLES" if the intro gets longer.
5. One mod per folder (`mods/<name>/`), one topic per pull request.
6. Open pull requests against the **`dev`** branch: `main` holds the latest release.

## Writing a mod

- Start from [docs/modding-guide.md](docs/modding-guide.md): hooks, parameters, pages, icons, saving, audio cost.
- `mods/<name>/make_patch.py` builds your code (`m68k-linux-gnu-as` or `-gcc`, `-mcpu=54418`) and writes `patch.json`.
- Add `mods/<name>/mod.json` — `{"title", "kind", "summary"}` in English, `kind` `feature` (or `infra` for a mod others require) — so the [web builder](web-builder) lists it.
- **Claim your resources first** in `tools/build/registry.py` (mod-area offsets, vparams slots, parameter ids, pages) and run `python tools/build/registry.py` to refresh [docs/registry.md](docs/registry.md); `tests/test_registry.py` fails otherwise.
- The free fill of section 3 is nearly full: link in the mod area (`tools/build/modarea_layout.py` + your offset) and add `"requires": ["modarea"]`.
- **Zero bytes in the OS image are not free space**: tables and buffers can be zero and still be read. The registry test rejects writes over stock zeros outside the registered free zones.
- ColdFire gotchas: no `exg`, `movem` only with `(An)`/`d16(An)`, `muls.l` takes no absolute address, short branches reach ±127 B.
- Document new findings in [docs/](docs), briefly.

## Where to start

Good first targets: PIN lock, an arpeggiator, more Syntakt OS versions (1.42+). Open an issue to coordinate.
