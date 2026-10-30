# Contributing

This file is the canonical list of rules. The step-by-step guide is
[web-builder/content/modders.md](web-builder/content/modders.md); submitting is described in
[web-builder/content/create-mod.md](web-builder/content/create-mod.md).

**Supported OS:** Syntakt OS 1.41 today; OS 1.42 from v1.0 (port in progress, new work can target it).

## Setup

- **Windows 11 + WSL (Ubuntu)** or Linux. Python 3.11+, Node.js 24.
- `bash tools/unpack/setup_eft.sh` — builds elektron-firmware-tool (pinned commit) into `third_party/`.
- `pip install pytest unicorn numpy pyfiglet`
- ColdFire binutils and gcc in WSL: `sudo apt install binutils-m68k-linux-gnu gcc-13-m68k-linux-gnu` (or unpack the `.deb`s into `~/tools/m68k/root`, as the `make_patch.py` scripts expect).
- `cd web-builder && npm ci`
- `git config core.hooksPath tools/hooks` — blocks firmware files from commits.
- Put your stock OS in `firmware/` (see [firmware/README.md](firmware/README.md)) and run `python -m pytest` (tests needing it are skipped otherwise).

## Rules

1. **Never commit firmware bytes.** No `.syx`, no extracted or disassembled sections. Patches hold addresses, a SHA-256 of the bytes they replace, and our bytes ([LEGAL.md](LEGAL.md)).
2. **Never touch sections 2 (bootstrap) or 6 (boot).** They hold the recovery path; the build refuses them. Don't work around it.
3. **Don't change boot timing.** The OS hangs on "PREPARING SAMPLES" if the intro gets longer.
4. **Emulate before flashing.** Every mod has tests that run the original OS code in `tools/emu` and compare.
5. **Claim shared resources first** in `tools/build/registry.py` (mod-area offsets, section 3 bytes, vparams slots, parameter ids, pages; kit/project slices in `kitstore_layout.py` / `projstore_layout.py`) and run `python tools/build/registry.py` to refresh [docs/registry.md](docs/registry.md). `tests/test_registry.py` fails otherwise.
6. **Zero bytes are not free space.** Tables and buffers can be zero and still be read. The registry test rejects writes over stock zeros outside the registered free zones.
7. **One mod per folder** (`mods/<name>/`, `name` in `patch.json` = folder name), **one mod per pull request**.
8. **Every mod has** `make_patch.py` (writes `patch.json`), `mod.json`, `README.md` and `tests/test_<name>.py`.
9. **Respect the audio CPU budget.** The stock OS uses ~89 % of the audio interrupt at rest. Measure the instructions your mod adds per block (see `tests/test_cpu_budget.py`) and keep a regression test.
10. **Files must stay safe.** Kits and projects saved with your mod must survive the OS's save → reload, and load without crashing on the stock OS or on builds without the mod.
11. **Pull requests against `dev`**, with CI green. `main` holds the latest release.
12. **Third-party code** only under a compatible license, with its notice and credit.
13. **Don't post mods or instructions on Elektronauts** (forbidden there). Use GitHub.

## Writing a mod

- Start from [docs/modding-guide.md](docs/modding-guide.md): hooks, parameters, pages, icons, saving, audio cost.
- `mods/<name>/make_patch.py` builds your code (`m68k-linux-gnu-as` or `-gcc`, `-mcpu=54418`) and writes `patch.json`.
- Code larger than a few hundred bytes goes in the mod area: link at `tools/build/modarea_layout.py` RAM + your offset and add `"requires": ["modarea"]`. The free fill of section 3 is nearly full.
- `mods/<name>/mod.json`: exactly `{"title", "kind", "summary"}`, summary in plain ASCII English. `kind`: `feature` (users pick it), `machine` (synth machine on CPU #2), `infra` (required by other mods).
- New machines need `modarea7`, the shared CPU #2 code area being prepared in [#1](https://github.com/Angelo-politek/Synthack-OS/issues/1).
- ColdFire gotchas: no `exg`, `movem` only with `(An)`/`d16(An)`, `muls.l` takes no absolute address, short branches reach ±127 B. No `.bss`, no libgcc.
- Document new findings in [docs/](docs), briefly.

## Before the pull request

```sh
python -m pytest
cd web-builder && npm test && npm run build && cd ..
python tools/build/registry.py && git diff --exit-code docs/registry.md
```

CI runs the same checks without the stock OS: run the skipped tests locally and say so in the pull request. Fill in the [pull request template](.github/PULL_REQUEST_TEMPLATE.md).

## Where to start

Open an issue to coordinate ([mod proposal](.github/ISSUE_TEMPLATE/mod_proposal.md), [machine proposal](.github/ISSUE_TEMPLATE/machine_proposal.md)). Good first targets: PIN lock, an arpeggiator.
