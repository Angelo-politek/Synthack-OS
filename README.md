# Syntakt+

An experimental, modular set of **unofficial** firmware mods for the Elektron Syntakt,
built as patches applied to the stock OS that each user downloads from elektron.se.

> **Not affiliated with, endorsed by or supported by Elektron.** Modified firmware can
> leave your device unusable and may void your warranty. Read
> [docs/recovery.md](docs/recovery.md) before flashing anything. Use at your own risk.

## Status

Phase 0 — foundations. Nothing here is flashable yet.

- [x] repo scaffold, safety and legal docs
- [x] unpack/repack wrapper around [elektron-firmware-tool](https://github.com/mischa85/elektron-firmware-tool)
- [ ] byte-identical round-trip verified on Syntakt OS 1.41
- [ ] emulation harness for the audio engine section
- [ ] first map of sections 3 and 7 in Ghidra

## What this repo contains — and what it never contains

- **Contains:** our own code (MIT), patch tables, tools, documentation.
- **Never contains:** any byte of Elektron firmware. `.syx` files are git-ignored and a
  pre-commit hook rejects firmware images. You supply your own stock OS.

## Quick start (Windows + WSL, or Linux)

```sh
# 1. build the external unpack tool (inside WSL or Linux)
bash tools/unpack/setup_eft.sh

# 2. enable the anti-firmware commit hook
git config core.hooksPath tools/hooks

# 3. put your stock OS in firmware/ (see firmware/README.md), then
python tools/unpack/eft.py info      firmware/Syntakt_OS1.41.syx
python tools/unpack/eft.py roundtrip firmware/Syntakt_OS1.41.syx
```

## Docs

- [docs/recovery.md](docs/recovery.md) — how to recover a device (do this dry run first)
- [docs/legal.md](docs/legal.md) — licensing, interoperability, what we do not publish
- [docs/firmware-format.md](docs/firmware-format.md) — `.syx` / ELE3 container notes
- [docs/hardware-notes.md](docs/hardware-notes.md) — hardware hypotheses
- [docs/toolchain.md](docs/toolchain.md) — WSL, Ghidra, cross-compiler setup
- [docs/re-journal.md](docs/re-journal.md) — reverse-engineering log

## License

MIT for the contents of this repository — see [LICENSE](LICENSE).
