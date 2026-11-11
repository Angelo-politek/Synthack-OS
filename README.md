# SyntHack OS

**Make your Syntakt yours.**
Mods and machines for the **Elektron Syntakt**, OS 1.42. You pick them, and build your OS from the stock file you download from elektron.se. No firmware is distributed here.

> **Not affiliated with Elektron.** Modified firmware can make your device unusable and may void your warranty.
> Read the [recovery procedure](RECOVERY.md) before flashing. Use at your own risk.

**Status:** `v1.0` (OS 1.42) is on `dev`, release planned for 2026-11-29. `v0.9.0` (OS 1.41) is on `main`: its MIDI machine pages move mod parameters, fixed in v1.0.

## What you get

| Mod | Status | What it does |
|---|---|---|
| [Readable values](mods/readable-values) | stable | Hz, dB, ms, % instead of 0–127. |
| [Performance FX](mods/perf-fx) | stable | Repeat, reverse, half speed on keys 13–16 (`FUNC` + `15`). |
| [Bus compressor](mods/master-comp) | beta | Compressor on the FX track bus, makeup up to +24 dB. |
| [Third send FX](mods/fx3) | beta | A third send on every track: chorus, flanger, phaser or crusher. |
| [Dual mono input](mods/dual-mono) | beta | Two mono instruments on the inputs, each with level and sends. |
| [SY FM4](mods/sy-fm4) | beta, machine | 4-operator FM on three SYN pages. By Rxuting. |
| [SAMPLER](mods/sampler) | beta, machine | ONESHOT, WERP, REPITCH, SLICE in place of SP TWINSHOT. |
| [Long samples](mods/long-samples) | beta | Samples longer than 5 s, sent from the site, one list per project. |
| [Modulation skip](mods/modulation-skip) | beta | Same sound, about 4 % more CPU free. |
| [Third LFO](mods/lfo3) | experimental | A third LFO on every audio track. |
| [Arpeggiator](mods/arp) | experimental | Mode, speed, range, length, 16-step offsets, p-locks. Double-tap `TRIG`. |
| [POLY](mods/poly) | experimental | 2 to 4 tracks played as one polyphonic instrument. |
| [Sample manager](mods/sample-manager) | experimental | Your long samples in a list on the device: put one on a track, reorder, delete. |
| [About SyntHack](mods/about) | beta | A SYNTHACK row in the settings menu: version, mods in the build, credits. |
| [Audio recorder](mods/recorder) | experimental | Record up to 60 s, trim, normalize, play it at once. Double-tap `SOUND`. |

- **stable**: tested on the device over many sessions. **beta**: works on the device, newer. **experimental**: first device tests only.
- The mods above use shared parts that the build adds by itself: [mod area](mods/modarea), [parameter ids](mods/idspace), [extra track parameters](mods/xparams), [SYN pages](mods/syn-pages), [kit](mods/kitstore) and [project](mods/projstore) storage, [engine area](mods/modarea7), [faster mixing](mods/fastmix).
- Every build shows the [boot splash](mods/splash) with the version, and your name if you want.

## Build your OS

Requirements: Python 3.11+, WSL or Linux, your own `Syntakt_OS1.42.syx` ([firmware/README.md](firmware/README.md)).

```sh
bash tools/unpack/setup_eft.sh                 # once (WSL/Linux)
git config core.hooksPath tools/hooks          # once: blocks firmware files from commits
python tools/build/build.py --stock firmware/Syntakt_OS1.42.syx \
    mods/readable-values mods/perf-fx mods/master-comp mods/fx3 -o out/synthack.syx
```

- Required mods are added automatically. `--name YOURNAME` puts your name on the boot screen.
- The [web builder](web-builder) does the same in the browser, with the same bytes. It goes online with v1.0.
- Flash `out/synthack.syx` with Elektron Transfer: USB, **Drop** page. Go back: flash the stock OS the same way.

The build checks the stock file, every patch against the bytes it expects, overlaps between mods, the protected boot sections and the boot unpacking margin. It refuses a result it cannot verify.

## Make a mod

```sh
python tools/new_mod.py my-mod                 # a mod that compiles and passes its test
python mods/my-mod/make_patch.py
python tools/check_mod.py my-mod               # before the pull request
```

| For | Read |
|---|---|
| Musicians | [Users guide](web-builder/content/users.md): build, flash, use each mod, go back |
| Modders | [Modders guide](web-builder/content/modders.md) · [Modding guide](docs/modding-guide.md) · [UI guide](docs/ui-guide.md) |
| Everyone | [CONTRIBUTING.md](CONTRIBUTING.md) · [Registry](docs/registry.md) · [Status](docs/status.md) · [RECOVERY.md](RECOVERY.md) · [LEGAL.md](LEGAL.md) |

Issues and pull requests: [CONTRIBUTING.md](CONTRIBUTING.md). Pull requests go to `dev`.
Don't post mods or instructions on Elektronauts. It is forbidden there. Use GitHub.

## Known issues

| Issue | Status |
|---|---|
| UI lag with many tracks on FX3, the compressor and dual mono together | Estimated worst case ~97 % of the audio block (stock: 89 %). With Modulation skip ~93 %. The site shows the load of your selection |
| Recorder: an analog track or MAIN does not sound like the output | The Syntakt sums in analog: see [what each source records](mods/recorder#what-each-source-records) |
| Bus compressor: toggling *global* for the external input mixer also copies the compressor settings | known |

## License and credits

GPL-2.0-or-later ([LICENSE](LICENSE)). Authors, third-party code and the earlier MIT releases: [NOTICE](NOTICE). See [LEGAL.md](LEGAL.md).

SyntHack builds on [elektron-firmware-tool](https://github.com/mischa85/elektron-firmware-tool) (Marcel Bierling), [SY FM4](https://github.com/Rxuting/sy-fm4) (Rxuting), [Synfact](https://github.com/GSM1980/synfact-dev) (GSM1980 and contributors) and [elekloader](https://github.com/irpina/elekloader) (irpina and contributors).
