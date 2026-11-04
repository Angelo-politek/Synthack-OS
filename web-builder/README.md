# Web builder

Builds a SyntHack OS `.syx` in the browser from your own stock `Syntakt_OS1.42.syx`.

- Nothing is uploaded. The page reads the file, applies the mods and runs every check locally, in a Web Worker.
- TypeScript port of the command-line chain. Same mods → **same bytes** as `tools/build/build.py`. `tests/test_web_builder.py` checks it on the real OS.

## Core

| File | Port of |
|---|---|
| `src/core/transport.ts` | SysEx transport: 8-in-7 packets, per-packet checksum — `transport.c` |
| `src/core/firmware.ts` | ELE3 container: section table, content checksum, optional HMAC trailer — `container.c`, `integrity.c` |
| `src/core/aplib.ts` | aPLib-style codec, byte-identical output — `aplib.c`; boot margin — `bootcheck.py` |
| `src/core/shlz.ts` | mod-area compression — `tools/build/lz.py` |
| `src/core/build.ts` | patch checks, dependencies, final verification — `tools/build/build.py` |
| `src/core/splash.ts` | name on the boot splash — `named_splash` in `tools/build/build.py` |
| `src/core/modfile.ts` | checks a `patch.json` loaded in **Create your mod** |

The `.c` files are from [elektron-firmware-tool](https://github.com/mischa85/elektron-firmware-tool) by Marcel Bierling (MIT, see `public/THIRD-PARTY-NOTICES.txt`).

## Samples page

`samples.html`: long samples over WebMIDI (Synfact's protocol). `src/core/datarpc.ts` (Data RPC SysEx, objects), `src/core/hzfs.ts` (catalogue, put, remove, order = the catalogue's slot map), `src/core/wav.ts` (WAV to 48 kHz mono PCM16): ports of Synfact's `data_rpc.py`, `sample_catalog.py`, `long_samples.py` (GPL-2.0-or-later). `test/samples.test.ts` runs them against a device double; the catalogue the device's C code writes is a fixture (`test/fixtures/hzfs-catalogue.bin`, from `tests/test_long_samples.py`).

## Mod cards

The page lists every mod with a `mods/<name>/mod.json` card:

| `kind` | On the page |
|---|---|
| `base` | in every build |
| `feature` | Mods step |
| `machine` | Machines step |
| `infra` | added when required |
| `test` | hidden |

A `patch.json` loaded in **Create your mod** can carry the same card as a `"card"` object. It stays in that browser.

## Pages

| Page | Text |
|---|---|
| `index.html` | home, Create your OS |
| `users.html` | `content/users.md` |
| `modders.html` | `content/modders.md` |
| `create-mod.html` | `content/create-mod.md`, `content/agent-prompt.md` |

Shared header and footer: `src/partials/`. Markdown is rendered at build time (`vite.config.ts`). Text follows [docs/writing-style.md](../docs/writing-style.md).

## Use

Requires Node.js 24. It runs the TypeScript sources directly.

```sh
cd web-builder
npm ci
npm run dev                  # page at http://localhost:5173
npm test                     # unit tests, no firmware needed
npm run build                # static site in dist/
node scripts/build-cli.ts --stock ../firmware/Syntakt_OS1.42.syx splash fx3 -o ../out/web.syx [--name NAME]   # no WSL needed
```

A full build takes 30–60 s: it recompresses the 3.4 MB OS section.
