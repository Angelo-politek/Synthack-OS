## Why SyntHack?

A firmware hack on its own only works alone. In SyntHack your mod is one folder next to everyone else's, and the
structure keeps them compatible: a shared mod area for code, a registry of who uses which memory, parameter ids,
pages and storage, automatic dependency resolution, a build that checks every byte it writes, CI on every pull
request, and emulator tests that run the original OS code. Once merged, your mod reaches every user through the web
builder, combined with whatever else they pick, and you don't have to re-port it alone when the base changes. Your
name stays on it: the mod's README credits its authors, and third-party code keeps its license and notice.

## Architecture

**Supported OS:** Syntakt OS 1.41 today; OS 1.42 from v1.0 (the 1.42 port is in progress, and new work can already
target it). Addresses on this page and in the linked docs are for the supported OS.

```
stock .syx (user's own)          mods/<name>/patch.json (ours)
        │                                 │
        └──────────► build ◄──────────────┘    tools/build/build.py  or  the web builder (same bytes)
                       │
                       ▼
           verified .syx + build report (.json)
```

- **`patch.json`** holds no Elektron bytes: for each change, the section, address, length, SHA-256 of the original
  bytes it expects, and our new bytes (`hex` or `ascii`). Code for the mod area uses `"append": true` (no hash: it
  replaces nothing). Other fields: `name` (= folder name), `os`, `requires`, `generated_by`.
- **The build** checks the stock OS fingerprint, adds and orders dependencies (`requires`), checks every hash and
  every overlap between mods, refuses sections other than 3 and 7, compresses the mod area, replays the boot
  decompression (fails under 4 KB of margin) and compares the result section by section with the declared patches.
- **Section 3** is the main OS on CPU #1: UI, sequencer, mixer, delay, reverb. Almost every mod patches it.
- **Section 7** is the voice engine on CPU #2 (digital machines), stored uncompressed. In-place patches are allowed;
  appending code is refused until `modarea7` exists (see [Machines](#machines)).
- **Sections 2 (bootstrap) and 6 (boot)** are never touched: they hold the recovery path.
- **Mod area** ([`modarea`](https://github.com/Angelo-politek/Synthack-OS/blob/dev/mods/modarea/README.md)): 64 KB
  reserved from the OS heap at boot, stored compressed in the image. Larger code goes here, at an offset you claim in
  the registry. The free fill of section 3 (`0x40338740–0x40339000`) is nearly full.
- **vparams** ([`vparams`](https://github.com/Angelo-politek/Synthack-OS/blob/dev/mods/vparams/README.md)): virtual
  parameters. Register `{id, get, set}` in a slot and the OS kit-parameter functions call your code for that id.
- **kitstore** ([`kitstore`](https://github.com/Angelo-politek/Synthack-OS/blob/dev/mods/kitstore/README.md)): 36
  words saved with the kit, in bytes the OS file format leaves unused.
- **projstore** ([`projstore`](https://github.com/Angelo-politek/Synthack-OS/blob/dev/mods/projstore/README.md)): 256
  bytes saved with the project.
- **modarea7**: a shared code area on CPU #2 for new machines. In progress
  ([#1](https://github.com/Angelo-politek/Synthack-OS/issues/1)).
- **Registry** ([`docs/registry.md`](https://github.com/Angelo-politek/Synthack-OS/blob/dev/docs/registry.md),
  generated from `tools/build/registry.py`): mod-area offsets, section 3 free fill, zones that look free but are read,
  vparams slots, parameter ids, pages, kit and project storage. `tests/test_registry.py` checks every `patch.json`
  against it.
- **`mod.json`**: the card shown by the web builder, `{"title", "kind", "summary"}`.

| `kind` | Meaning |
|---|---|
| `base` | part of every build (the boot splash) |
| `feature` | a mod users pick |
| `machine` | a new synth machine on CPU #2 |
| `infra` | needed by other mods, added automatically |
| `test` | hidden from users (e.g. `mod-zero`) |

## Workflow

1. **Coordinate.** Open an issue ([mod proposal](https://github.com/Angelo-politek/Synthack-OS/issues/new?template=mod_proposal.md))
   before writing code, and check the [registry](https://github.com/Angelo-politek/Synthack-OS/blob/dev/docs/registry.md)
   for what is taken.
2. **Fork and branch from `dev`.** `main` holds the last release.
   ```sh
   git clone https://github.com/<you>/Synthack-OS && cd Synthack-OS
   git checkout -b my-mod origin/dev
   git config core.hooksPath tools/hooks          # blocks firmware files from commits
   ```
3. **Set up the toolchain** (Windows 11 + WSL Ubuntu, or Linux; Python 3.11+, Node.js 24):
   ```sh
   bash tools/unpack/setup_eft.sh                 # elektron-firmware-tool, pinned commit
   pip install pytest unicorn numpy pyfiglet
   sudo apt install binutils-m68k-linux-gnu gcc-13-m68k-linux-gnu
   cd web-builder && npm ci && cd ..
   ```
   Put your stock OS in `firmware/` (git-ignored; see
   [`firmware/README.md`](https://github.com/Angelo-politek/Synthack-OS/blob/dev/firmware/README.md)) and check it
   with `python tools/unpack/eft.py info firmware/<file>.syx` (must say Syntakt, `checksums : ok`).
4. **Claim your resources** in `tools/build/registry.py` (mod-area range, section 3 bytes, vparams slots, parameter
   ids, pages); kit and project slices go in `tools/build/kitstore_layout.py` and `projstore_layout.py`. Then
   regenerate the docs: `python tools/build/registry.py`.
5. **Write the mod** in `mods/<name>/`: sources (`.S` or `.c`), and `make_patch.py`, which compiles them
   (`m68k-linux-gnu-as` / `-gcc`, `-mcpu=54418`) and writes `patch.json`. Never write `patch.json` by hand except for
   trivial text patches like `mod-zero`. Declare `"requires": ["modarea", ...]` if you use shared infrastructure.
   Start from the [modding guide](https://github.com/Angelo-politek/Synthack-OS/blob/dev/docs/modding-guide.md) and
   copy patterns from existing mods (`fx3` and `master-comp` are the most complete).
6. **Test in the emulator.** `tests/test_<name>.py` loads the stock section, applies your patch and runs the
   **original** OS code around it in Unicorn (`tools/emu`), comparing with the stock behavior. Test what you store
   with a save → reload round trip through the OS's own writer and reader, and old files without your data.
7. **Measure the audio cost** if your code runs in the audio interrupt (see [CPU budget](#cpu-budget)).
8. **Build with every other mod:**
   ```sh
   python tools/build/build.py --stock firmware/<file>.syx mods/<name> mods/splash mods/dual-mono \
       mods/master-comp mods/readable-values mods/perf-fx mods/fx3 -o out/test.syx
   ```
9. **Add `mod.json` and `README.md`.** `mod.json`: exactly `title`, `kind`, `summary`; summary in plain ASCII English.
   README: what it does on the device (keys, pages, where it is saved), how it works (hooks, addresses), what the
   tests cover, credits.
10. **Try it on the site.** Load your `patch.json` in the **Create your mod** page and build an OS with it, next to
    the other mods. It stays in your browser.
11. **Test on the device.** Flash, then check save/reload, pattern change and power cycle for anything you store.
12. **Run the checks CI runs:**
    ```sh
    python -m pytest
    cd web-builder && npm test && npm run build && cd ..
    python tools/build/registry.py && git diff --exit-code docs/registry.md
    ```
    CI has no stock OS, so tests that need it are skipped there. Run them locally and say so in the PR.
13. **Open the pull request against `dev`**, one mod per PR. See
    [Create your mod](https://github.com/Angelo-politek/Synthack-OS/blob/dev/web-builder/content/create-mod.md#submit-it).

## Rules

1. **No Elektron firmware bytes in the repository.** No `.syx`, no extracted or disassembled sections. Patches hold
   addresses, SHA-256 of the expected original bytes, and our bytes. `.gitignore`, the pre-commit hook and CI enforce
   it.
2. **Never touch sections 2 and 6.** The build refuses; don't work around it.
3. **Don't change boot timing.** A longer intro hangs the OS on "PREPARING SAMPLES". Set up from hooks or from a stub
   in the OS page initializer, not with extra boot work.
4. **Emulate before flashing.** Every mod has tests that run the original OS code.
5. **Claim shared resources** in `tools/build/registry.py` and regenerate `docs/registry.md`.
6. **Zero bytes are not free space.** Tables and buffers can be zero and still be read. The registry test rejects
   writes over stock zeros outside the registered free zones.
7. **One mod per folder** (`mods/<name>/`, `name` in `patch.json` = folder name), one mod per pull request.
8. **Pull requests against `dev`**, with CI green.
9. **Every mod has a `mod.json`** and a README.
10. **Respect the audio CPU budget** (below).
11. **Third-party code** only under a compatible license (MIT), with its notice and credit.
12. **Don't post mods or instructions on Elektronauts**: it is forbidden there. Use GitHub.

## Pitfalls

- **RAM above the BSS** (`0x45565490–0x48000000`) has no code reference, but the OS writes over it when it loads
  samples ([#4](https://github.com/Angelo-politek/Synthack-OS/issues/4)). Mod memory comes from the mod area.
- **Boot decompression margin.** The bootstrap unpacks section 3 almost in place; the build fails under 4 KB of margin.
  Zero padding is the worst case.
- **Hidden ids are not free.** Many ids without a page or MIDI CC are aliases the OS shows in some modes.
  `tests/test_id_audit.py` rejects aliases, MIDI CC/NRPN and ids shared between mods. Ids above 504 do not exist.
- **Kit files drop words.** The OS writes kits to storage through position tables that don't keep every word. Any new
  kit word must survive a save → reload through the OS writer and reader.
- **Files must survive builds without your mod.** A kit or project saved with your mod and opened on the stock OS (or
  a build without it) must not crash. Store values XOR their default, so old files (zeros) load the defaults.
- **Hooks:** replace at least 6 bytes with `jsr`, replay the replaced instructions, save every register you use.
- **No `.bss`** in mod code (put variables in `.data`); **no libgcc** (`nm -u` must be empty).
- **ColdFire:** no `exg`; `movem` only with `(An)` / `d16(An)`; `muls.l` takes no absolute address; short branches
  reach ±127 bytes.
- **EMAC:** set `MACSR` yourself and leave `ACC0` at 0. List your EMAC sites for the emulator.
- **`std::function` objects** (texts, icons) may be rewritten only from UI code, never from the audio interrupt.

## CPU budget

The audio interrupt runs once per 32-sample block (1,500 times per second). The stock OS already uses about 89 % of
the CPU in it at rest; the UI and the sequencer get the rest. A few thousand extra instructions per block are enough to
make the UI lag.

- **Measure** the instructions your mod adds per block in the emulator (`UC_HOOK_CODE`, after `uc.ctl_flush_tb()`),
  as `counted()` does in
  [`tests/test_cpu_budget.py`](https://github.com/Angelo-politek/Synthack-OS/blob/dev/tests/test_cpu_budget.py). That
  test sums the worst case of all audio mods together against a ceiling.
- **Keep a regression test** of your cost (e.g. `tests/test_fx3.py::test_cost_per_block`) and give idle and worst-case
  numbers in the PR.
- **Do nothing when idle**: no sends, silent input, tail done. Work at 24 kHz where the sound allows it. Recompute
  constants only when a knob moves. Make ramps end (snap when close).
- Reference costs per block: reverb ~8,200; bus compressor ~100 off / ~600 on; FX3 ~60 idle, ~1,300–1,700 with one
  track sending.

## Machines

New synth machines run on CPU #2 (section 7). They need **`modarea7`**, a shared code area on CPU #2 that is being
prepared in [#1](https://github.com/Angelo-politek/Synthack-OS/issues/1): until it lands, the build refuses to append
code to section 7. Machines target OS 1.42. Propose one with a
[machine proposal](https://github.com/Angelo-politek/Synthack-OS/issues/new?template=machine_proposal.md) before
starting; details in [Create your mod](https://github.com/Angelo-politek/Synthack-OS/blob/dev/web-builder/content/create-mod.md#machines).

## Technical docs

| Doc | Content |
|---|---|
| [modding-guide.md](https://github.com/Angelo-politek/Synthack-OS/blob/dev/docs/modding-guide.md) | hooks, parameters, pages, texts and icons, saving, audio processing |
| [registry.md](https://github.com/Angelo-politek/Synthack-OS/blob/dev/docs/registry.md) | shared resources and who uses them |
| [memory-map.md](https://github.com/Angelo-politek/Synthack-OS/blob/dev/docs/memory-map.md) | CPU #1 memory, boot, mod area, screen |
| [audio-path.md](https://github.com/Angelo-politek/Synthack-OS/blob/dev/docs/audio-path.md) | CPU #2 engines, mix, sends, CPU load, parameters |
| [ui-parameters.md](https://github.com/Angelo-politek/Synthack-OS/blob/dev/docs/ui-parameters.md) | descriptors, pages, drawing, keys, kit storage |
| [firmware-format.md](https://github.com/Angelo-politek/Synthack-OS/blob/dev/docs/firmware-format.md) | `.syx` layers, sections, boot decompression limit |
| [emulation.md](https://github.com/Angelo-politek/Synthack-OS/blob/dev/docs/emulation.md) | the emulator and how mods are tested |
| [CONTRIBUTING.md](https://github.com/Angelo-politek/Synthack-OS/blob/dev/CONTRIBUTING.md) | setup and the rules list |
| [RECOVERY.md](https://github.com/Angelo-politek/Synthack-OS/blob/dev/RECOVERY.md) | what to do if the OS doesn't boot |
| [LEGAL.md](https://github.com/Angelo-politek/Synthack-OS/blob/dev/LEGAL.md) | what may and may not be in the repository |
