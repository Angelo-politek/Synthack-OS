# Contributing

## Setup

- **Windows 11 + WSL (Ubuntu)** or Linux. Python 3.11+.
- `bash tools/unpack/setup_eft.sh` — builds elektron-firmware-tool (pinned commit) into `third_party/`.
- `pip install unicorn pytest`
- ColdFire binutils in WSL: `sudo apt install binutils-m68k-linux-gnu` (or unpack the `.deb` into `~/tools/m68k/root`, as `make_patch.py` scripts expect).
- `git config core.hooksPath tools/hooks`
- Put your stock OS in `firmware/` and run `python -m pytest` (tests needing it are skipped otherwise).

## Rules

1. **Never commit firmware bytes.** Patches hold our bytes + a hash of what they replace.
2. **Emulate before flashing.** Every mod has tests that run the original OS code in `tools/emu` and compare.
3. **Never touch sections 2 (bootstrap) or 6 (boot).** `eft.py` refuses; don't work around it.
4. **Don't change boot timing.** The OS hangs on "PREPARING SAMPLES" if the intro gets longer.
5. One mod per folder (`mods/<name>/`), one topic per pull request.

## Writing a mod

- `mods/<name>/make_patch.py` assembles your code (`m68k-linux-gnu-as -mcpu=54418`) and writes `patch.json`.
- Small code: free space at `0x40338740–0x40339000`. Larger: link at `0x46000000+` and add `"requires": ["modarea"]` (see [mods/modarea](mods/modarea)).
- ColdFire gotchas: no `move.l #imm` to memory with displacement, no `exg`, `movem` only with `(An)`/`d16(An)`, `mulu.l`/`divu.l` need a register operand.
- Document new findings in [docs/](docs), briefly.

## Where to start

Good first targets: readable parameter values, PIN lock, more Syntakt OS versions (1.42+). Open an issue to coordinate.
