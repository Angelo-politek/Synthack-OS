# SyntHack OS

Unofficial, modular firmware mods for the **Elektron Syntakt** (OS 1.41).
Each mod is a small patch applied to the stock OS you download from elektron.se — no firmware is distributed here.

> **Not affiliated with Elektron.** Modified firmware can make your device unusable and may void your warranty.
> Learn the [recovery procedure](RECOVERY.md) before flashing. Use at your own risk.

**Status:** `v0.5.0` — five mods running on real hardware.

## Features

| Feature | Status | What it does |
|---|---|---|
| [Master compressor](mods/master-comp) | ✅ v0.5.0 | Bus compressor on the **analog master** (via the master VCAs). Digitakt-style curves. THR · ATK · REL · MUP · RAT + gain-reduction meter + ON/OFF switch on the FX track SYN page, values in dB / ms / ratio. Saved per pattern, or global with *SYN global*. |
| [Dual mono input](mods/dual-mono) | ✅ v0.5.0 | With EXTERNAL IN set to mono, **IN L** and **IN R** get independent levels on the External Mixer page. |
| [Boot splash](mods/splash) | ✅ v0.5.0 | "SyntHack v0.5.0" logo after the official intro. Boot time unchanged. |
| [Mod area](mods/modarea) | ✅ infra | 32 KB of RAM for mod code, loaded at boot. |
| [Readable parameter values](mods/readable-values) | ✅ v0.5.0 | Hz, dB, ms and % instead of 0–127: filters, envelopes, levels, sends, delay and reverb, on every track and the FX track. Computed from the same data the DSP uses; analog parts measured on the device. |
| PIN lock | ⬜ planned | Optional PIN at power-on, as a theft deterrent. Recovery via OS reflash stays possible. |
| Dual mono v2 | ⬜ planned | Separate IN L / IN R pages with their own FX sends. |
| New LFO shapes · 3rd LFO / mod matrix | ⬜ planned | |
| Master FX suite · beat repeat | ⬜ planned | |
| Arpeggiator · Euclidean circle UI | ⬜ planned | |
| Resampling to SP TWINSHOT · advanced sampler | ⬜ planned | |
| New machines: RISER / DOWNFILTER, SY SWARM+ | ⬜ planned | Requires custom audio-engine code (CPU #2). |
| Web builder | ⬜ planned | Pick mods in the browser, build your `.syx` locally. |

## Roadmap

```mermaid
flowchart LR
  A["Foundations ✅<br/>unpack/repack · emulator<br/>build tool · recovery"] --> B["First mods ✅<br/>splash · dual mono<br/>master compressor"]
  B --> C["UI & usability<br/>readable values ✅ · PIN lock<br/>dual mono v2"]
  C --> D["FX & performance<br/>master FX · beat repeat<br/>arp · euclidean UI · LFOs"]
  D --> E["Engine mods<br/>new machines · sampler<br/>resampling"]
  B -.-> W["Web builder"]
```

## How it works

- `tools/unpack` — unpack/repack the `.syx` (wraps [elektron-firmware-tool](https://github.com/mischa85/elektron-firmware-tool)).
- `mods/<name>/patch.json` — *where* to patch, a hash of the expected original bytes, and **our** new bytes.
- `tools/build/build.py` — stock OS + chosen mods → verified `.syx` (refuses wrong OS, overlaps, protected sections).
- `tools/emu` — ColdFire emulator (Unicorn + our EMAC model). Every mod is tested against the original code before flashing.

Technical findings: [docs/](docs).

## Build your OS

Requires Python 3, WSL/Linux and your own `Syntakt_OS1.41.syx` (see [firmware/README.md](firmware/README.md)).

```sh
bash tools/unpack/setup_eft.sh                 # once (WSL/Linux)
git config core.hooksPath tools/hooks          # once: blocks firmware files from commits
python tools/build/build.py --stock firmware/Syntakt_OS1.41.syx \
    mods/splash mods/dual-mono mods/modarea mods/master-comp mods/readable-values -o out/synthack.syx
```

Flash `out/synthack.syx` with Elektron Transfer (USB, *Drop* page). To go back, flash the stock OS the same way.

## Contributing

Issues and pull requests are welcome — see [CONTRIBUTING.md](CONTRIBUTING.md).
Please don't post mods or instructions on Elektronauts (forbidden there); use GitHub.

## License

MIT for everything in this repository ([LICENSE](LICENSE)). See [LEGAL.md](LEGAL.md).
