# Web builder

Build a SyntHack OS `.syx` in the browser from your own stock `Syntakt_OS1.41.syx`. Nothing is uploaded: the page
reads the file, applies the mods and runs every check locally, in a Web Worker.

It is a TypeScript port of the command-line chain and gives **the same bytes** as `tools/build/build.py` for the same
mods (`tests/test_web_builder.py` checks it on the real OS).

| File | Port of |
|---|---|
| `src/core/transport.ts` | SysEx transport (8-in-7 packets, per-packet checksum) — `transport.c` |
| `src/core/firmware.ts` | ELE3 container: section table, content checksum, optional HMAC trailer — `container.c`, `integrity.c` |
| `src/core/aplib.ts` | aPLib-style codec (same packer, byte-identical output) — `aplib.c`; boot margin — `bootcheck.py` |
| `src/core/shlz.ts` | mod-area compression — `tools/build/lz.py` |
| `src/core/build.ts` | patch checks, dependencies, final verification — `tools/build/build.py` |

The `.c` files are from [elektron-firmware-tool](https://github.com/mischa85/elektron-firmware-tool) by Marcel
Bierling (MIT, see `public/THIRD-PARTY-NOTICES.txt`).

The page lists every mod that has a `mods/<name>/mod.json` card (`kind`: `feature` is shown, `infra` is added when
needed, `test` is hidden).

## Use

Requires Node.js 24 (it runs the TypeScript sources directly).

```sh
cd web-builder
npm ci
npm run dev                  # page at http://localhost:5173
npm test                     # unit tests, no firmware needed
npm run build                # static page in dist/
node scripts/build-cli.ts --stock ../firmware/Syntakt_OS1.41.syx splash fx3 -o ../out/web.syx   # no WSL needed
```

A full build takes about 30 s (recompressing the 3.4 MB OS section).
