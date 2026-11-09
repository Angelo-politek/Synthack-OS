# Contributing

The canonical rules list. Guides: [modders](web-builder/content/modders.md), [create your mod](web-builder/content/create-mod.md). Writing rules for every text: [docs/writing-style.md](docs/writing-style.md).

**Target:** Syntakt OS 1.42.

- Port a 1.41 mod: `python tools/build/port_source.py 1.42 mods/<name> tests/test_<name>.py`, then rerun `make_patch.py` and the tests.
- `docs/` uses 1.41 addresses. Convert them with `tools/build/osmap.py`.

## Setup

1. Use Windows 11 + WSL (Ubuntu), or Linux. Python 3.11+, Node.js 24.
2. Build elektron-firmware-tool (pinned commit) into `third_party/`: `bash tools/unpack/setup_eft.sh`
3. `pip install pytest unicorn numpy pyfiglet`
4. Install ColdFire binutils and gcc in WSL: `sudo apt install binutils-m68k-linux-gnu gcc-13-m68k-linux-gnu`. Or unpack the `.deb`s into `~/tools/m68k/root`, where the `make_patch.py` scripts look.
5. `cd web-builder && npm ci`
6. Block firmware files from commits: `git config core.hooksPath tools/hooks`
7. Put your stock OS in `firmware/` ([firmware/README.md](firmware/README.md)). Run `python -m pytest`. Without it, those tests are skipped.

## Rules

1. **No firmware bytes.** No `.syx`, no extracted or disassembled sections. Patches hold addresses, the SHA-256 of the bytes they replace, our bytes ([LEGAL.md](LEGAL.md)).
2. **Never touch sections 2 (bootstrap) or 6 (boot).** They hold the recovery path. The build refuses them. Don't work around it.
3. **Don't change boot timing.** A longer intro hangs the OS on "PREPARING SAMPLES".
4. **Emulate before flashing.** Every mod has tests that run the original OS code in `tools/emu`.
5. **Claim shared resources first** in `tools/build/registry.py`: mod-area offsets, section 3 bytes, vparams slots, parameter ids, pages. Kit and project slices: `kitstore_layout.py`, `projstore_layout.py`. Run `python tools/build/registry.py` to refresh [docs/registry.md](docs/registry.md). `tests/test_registry.py` fails otherwise.
6. **Zero bytes are not free space.** Tables and buffers can be zero and still be read. The registry test rejects writes over stock zeros outside registered free zones.
7. **One mod per folder** (`mods/<name>/`, `name` = folder name). **One mod per pull request.**
8. **Every mod has** `make_patch.py` (writes `patch.json`), `mod.json`, `README.md`, `tests/test_<name>.py`.
9. **Audio CPU budget.** The stock OS uses ~89 % of the audio interrupt at rest. Count the instructions your mod adds per block (`tests/test_cpu_budget.py`) and estimate its cycles with the cache model (`tools/emu/cycles.py`, `tests/test_cycles.py`): code and DDR data lines cost a DDR read every block. Keep a regression test. Enter the worst case in `AUDIO_CPU` and `AUDIO_CYCLES` of `tools/build/budget.py` and run it: the site's load indicator reads `web-builder/src/budget.json`.
10. **Safe files.** Kits and projects saved with your mod survive the OS save → reload. They load on the stock OS and on builds without the mod, without crashing.
11. **Pull requests against `dev`.** CI green. `main` holds the latest release.
12. **Third-party code:** a license compatible with GPL-2.0-or-later, its notice, credit in [NOTICE](NOTICE).
13. **Text follows [docs/writing-style.md](docs/writing-style.md).**
14. **No mods or instructions on Elektronauts.** It is forbidden there. Use GitHub.

## Writing a mod

- Start from [docs/modding-guide.md](docs/modding-guide.md): hooks, parameters, pages, icons, saving, audio cost.
- `mods/<name>/make_patch.py` compiles (`m68k-linux-gnu-as` or `-gcc`, `-mcpu=54418`) and writes `patch.json`.
- Code over a few hundred bytes goes in the mod area: link at `tools/build/modarea_layout.py` RAM + your offset, add `"requires": ["modarea"]`. The section 3 free fill is nearly full.
- `mods/<name>/mod.json`: exactly `{"title", "kind", "status", "summary"}`. Summary: ASCII English, ≤ 140 characters. `kind`: `feature` (users pick it), `machine` (synth machine on CPU #2), `infra` (required by other mods).
- `status`: `experimental` (first device tests; every new mod starts here), `beta` (works on the device, tested by more than one person or in more than one session), `stable` (in a release candidate for two sessions with no open bug). Never above the status of a mod it requires. The site selects the stable mods by default. A maintainer promotes it.
- New machines put their CPU #2 code in `modarea7` and their own SYN pages in `syn-pages`. Examples: `mods/sy-fm4`, `mods/sampler`. See [docs/modding-guide.md](docs/modding-guide.md#7-machines).
- ColdFire: no `exg`. `movem` only with `(An)` / `d16(An)`. `muls.l` takes no absolute address. Short branches: ±127 B. No `.bss`, no libgcc.
- New findings go in [docs/](docs), briefly.

## Before the pull request

```sh
python -m pytest
cd web-builder && npm test && npm run build && cd ..
python tools/build/registry.py && git diff --exit-code docs/registry.md
python tools/build/budget.py && git diff --exit-code web-builder/src/budget.json
```

- CI runs the same checks without the stock OS. Run the skipped tests locally. Say so in the pull request.
- Fill in the [pull request template](.github/PULL_REQUEST_TEMPLATE.md).

## Where to start

- Open an issue first: [mod proposal](.github/ISSUE_TEMPLATE/mod_proposal.md), [machine proposal](.github/ISSUE_TEMPLATE/machine_proposal.md).
- First targets: PIN lock, arpeggiator.
