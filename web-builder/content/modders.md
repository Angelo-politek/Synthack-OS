## Why SyntHack

A hack alone works alone. Here your mod is one folder next to everyone else's.
Shared mod area, resource registry, automatic dependencies, byte-checked builds, CI and emulator tests keep the mods compatible.
Once merged, your mod reaches every user of the web builder. You don't re-port it alone when the base changes.
Your README credits you. Third-party code keeps its license and notice.

## OS version

- Target: **Syntakt OS 1.42**. Mod sources, tests and `patch.json` use 1.42 addresses.
- `docs/` notes use 1.41 addresses. Convert one with `tools/build/osmap.py`.
- Port a whole 1.41 mod (sources and tests) with `tools/build/port_source.py`.

## Architecture

```
stock .syx (user's own)          mods/<name>/patch.json (ours)
        │                                 │
        └──────────► build ◄──────────────┘    tools/build/build.py  or  the web builder (same bytes)
                       │
                       ▼
           verified .syx + build report (.json)
```

| Part | What it is |
|---|---|
| `patch.json` | Per change: section, address, length, SHA-256 of the expected original bytes, our bytes (`hex` or `ascii`). No Elektron bytes. Mod-area code: `"append": true`, no hash. Fields: `name` (= folder), `os`, `requires`, `generated_by`. |
| Build | Checks the stock SHA-256. Adds and orders `requires`. Checks every hash and overlap. Accepts sections 3 and 7 only. Compresses the mod area. Replays boot decompression: fails under 4 KB margin. Compares the result section by section with the patches. |
| Section 3 | Main OS, CPU #1: UI, sequencer, mixer, delay, reverb. Almost every mod patches it. |
| Section 7 | Voice engine, CPU #2 (digital machines). Uncompressed. In-place patches allowed. Appending refused until `modarea7` exists. |
| Sections 2, 6 | Bootstrap and boot. Never touched: they hold the recovery path. |
| [`modarea`](https://github.com/Angelo-politek/Synthack-OS/blob/dev/mods/modarea/README.md) | 64 KB reserved from the OS heap at boot, stored compressed. Large code goes here, at a claimed offset. |
| Section 3 free fill | `0x40339740–0x4033A000`. Nearly full. |
| [`vparams`](https://github.com/Angelo-politek/Synthack-OS/blob/dev/mods/vparams/README.md) | Virtual parameters. Register `{id, get, set}` in a slot; the OS kit-parameter functions call your code. |
| [`kitstore`](https://github.com/Angelo-politek/Synthack-OS/blob/dev/mods/kitstore/README.md) | 36 words saved with the kit, in bytes the OS file format leaves unused. |
| [`projstore`](https://github.com/Angelo-politek/Synthack-OS/blob/dev/mods/projstore/README.md) | 256 bytes saved with the project. |
| `modarea7` | Shared code area on CPU #2 for machines. `[wip]` [#1](https://github.com/Angelo-politek/Synthack-OS/issues/1). |
| [Registry](https://github.com/Angelo-politek/Synthack-OS/blob/dev/docs/registry.md) | Generated from `tools/build/registry.py`: mod-area offsets, free fill, zero-but-read zones, vparams slots, parameter ids, pages, kit and project storage. `tests/test_registry.py` checks every `patch.json` against it. |
| `mod.json` | Card in the web builder: `{"title", "kind", "summary"}`. |

| `kind` | Meaning |
|---|---|
| `base` | in every build (boot splash) |
| `feature` | users pick it |
| `machine` | synth machine on CPU #2 |
| `infra` | required by other mods, added automatically |
| `test` | hidden (`mod-zero`) |

## Workflow

1. Open a [mod proposal](https://github.com/Angelo-politek/Synthack-OS/issues/new?template=mod_proposal.md). Check the [registry](https://github.com/Angelo-politek/Synthack-OS/blob/dev/docs/registry.md).
2. Fork. Branch from `dev` (`main` holds the last release):
   ```sh
   git clone https://github.com/<you>/Synthack-OS && cd Synthack-OS
   git checkout -b my-mod origin/dev
   git config core.hooksPath tools/hooks          # blocks firmware files from commits
   ```
3. Install the toolchain. Windows 11 + WSL Ubuntu, or Linux. Python 3.11+, Node.js 24.
   ```sh
   bash tools/unpack/setup_eft.sh                 # elektron-firmware-tool, pinned commit
   pip install pytest unicorn numpy pyfiglet
   sudo apt install binutils-m68k-linux-gnu gcc-13-m68k-linux-gnu
   cd web-builder && npm ci && cd ..
   ```
4. Put the stock OS in `firmware/` (git-ignored, see [`firmware/README.md`](https://github.com/Angelo-politek/Synthack-OS/blob/dev/firmware/README.md)). Check it: `python tools/unpack/eft.py info firmware/<file>.syx` must say Syntakt, `checksums : ok`.
5. Claim resources in `tools/build/registry.py`: mod-area range, section 3 bytes, vparams slots, parameter ids, pages. Kit and project slices: `tools/build/kitstore_layout.py`, `projstore_layout.py`. Run `python tools/build/registry.py`.
6. Write `mods/<name>/`: sources (`.S` or `.c`) and `make_patch.py`. It compiles (`m68k-linux-gnu-as` / `-gcc`, `-mcpu=54418`) and writes `patch.json`. Hand-written `patch.json` only for text patches like `mod-zero`. Add `"requires": ["modarea", ...]` for shared infrastructure. Start from the [modding guide](https://github.com/Angelo-politek/Synthack-OS/blob/dev/docs/modding-guide.md); `fx3` and `master-comp` are the fullest examples.
7. Write `tests/test_<name>.py`. Load the stock section, apply the patch, run the **original** OS code around it in Unicorn (`tools/emu`), compare with stock. Round-trip stored data through the OS writer and reader. Load old files without your data.
8. Measure the audio cost if your code runs in the audio interrupt. See [CPU budget](#cpu-budget).
9. Build with every other mod:
   ```sh
   python tools/build/build.py --stock firmware/<file>.syx mods/<name> mods/splash mods/dual-mono \
       mods/master-comp mods/readable-values mods/perf-fx mods/fx3 -o out/test.syx
   ```
10. Add `mod.json` (exactly `title`, `kind`, `summary`; ASCII English) and `README.md` (use on the device, how it works, tests, credits).
11. Load `patch.json` in **Create your mod**. Build an OS with it next to the other mods. It stays in your browser.
12. Flash. Check save/reload, pattern change and power cycle for anything you store.
13. Run the CI checks:
    ```sh
    python -m pytest
    cd web-builder && npm test && npm run build && cd ..
    python tools/build/registry.py && git diff --exit-code docs/registry.md
    ```
    CI has no stock OS and skips the tests that need it. Run them locally. Say so in the PR.
14. Open the pull request against `dev`, one mod per PR. See [Submit it](create-mod.md#submit-it).

## Rules

1. No Elektron firmware bytes in the repository. No `.syx`, no extracted or disassembled sections. `.gitignore`, the pre-commit hook and CI enforce it.
2. Never touch sections 2 and 6. The build refuses them.
3. Don't change boot timing. A longer intro hangs the OS on "PREPARING SAMPLES". Set up from hooks or a stub in the page initializer.
4. Emulate before flashing.
5. Claim shared resources in `tools/build/registry.py`. Regenerate `docs/registry.md`.
6. Zero bytes are not free space. The registry test rejects writes over stock zeros outside registered free zones.
7. One mod per folder (`name` = folder name). One mod per pull request.
8. Pull requests against `dev`. CI green.
9. Every mod has `mod.json` and `README.md`.
10. Respect the [CPU budget](#cpu-budget).
11. Third-party code: compatible license (MIT), notice and credit.
12. Don't post mods or instructions on Elektronauts. It is forbidden there.

## Pitfalls

| Pitfall | Rule |
|---|---|
| RAM above the BSS (`0x45566490–0x48000000`) | No code references it, but the OS writes over it when it loads samples ([#4](https://github.com/Angelo-politek/Synthack-OS/issues/4)). Use the mod area. |
| Boot decompression | Build fails under 4 KB margin. Zero padding is the worst case. |
| Hidden ids | Often aliases the OS shows in some modes. `tests/test_id_audit.py` rejects aliases, MIDI CC/NRPN, shared ids. No ids above 504. |
| Kit files | The OS drops some words on save. New kit words must survive save → reload. |
| Files without your mod | Must load on the stock OS without crashing. Store values XOR their default: zero = default. |
| Hooks | Replace ≥ 6 bytes with `jsr`. Replay the replaced instructions. Save every register you use. |
| Sections | No `.bss` (use `.data`). No libgcc: `nm -u` empty. |
| ColdFire | No `exg`. `movem` only with `(An)` / `d16(An)`. `muls.l` takes no absolute address. Short branches: ±127 B. |
| EMAC | Set `MACSR` yourself. Leave `ACC0` at 0. List your EMAC sites for the emulator. |
| `std::function` (texts, icons) | Rewrite from UI code only, never from the audio interrupt. |

## CPU budget

- The audio interrupt runs once per 32-sample block: 1,500 times per second.
- The stock OS uses ~89 % of the CPU in it at rest. The UI and sequencer get the rest.
- A few thousand extra instructions per block make the UI lag.

1. Count the instructions your mod adds per block in the emulator: `UC_HOOK_CODE`, after `uc.ctl_flush_tb()`. Copy `counted()` from [`tests/test_cpu_budget.py`](https://github.com/Angelo-politek/Synthack-OS/blob/dev/tests/test_cpu_budget.py). That test sums the worst case of all audio mods against a ceiling.
2. Keep a cost regression test, as `tests/test_fx3.py::test_cost_per_block`.
3. Put idle and worst-case counts in the PR.

Keep it cheap:

- Do nothing when idle: no sends, silent input, tail done.
- Run at 24 kHz where the sound allows it.
- Recompute constants only when a knob moves.
- Make ramps end: snap when close.

| Reference | Instructions per block |
|---|---|
| Reverb | ~8,200 |
| Bus compressor | ~100 off, ~600 on |
| FX3 | ~60 idle, ~1,300–1,700 with one track sending |

## Machines

- New synth machines run on CPU #2 (section 7).
- They need `modarea7`, the shared CPU #2 code area. `[wip]` [#1](https://github.com/Angelo-politek/Synthack-OS/issues/1). Until then the build refuses code appended to section 7.
- Target: OS 1.42.
- Start with a [machine proposal](https://github.com/Angelo-politek/Synthack-OS/issues/new?template=machine_proposal.md). Details: [Machines](create-mod.md#machines).

## Technical docs

| Doc | Content |
|---|---|
| [modding-guide.md](https://github.com/Angelo-politek/Synthack-OS/blob/dev/docs/modding-guide.md) | hooks, parameters, pages, texts and icons, saving, audio |
| [registry.md](https://github.com/Angelo-politek/Synthack-OS/blob/dev/docs/registry.md) | shared resources and owners |
| [memory-map.md](https://github.com/Angelo-politek/Synthack-OS/blob/dev/docs/memory-map.md) | CPU #1 memory, boot, mod area, screen |
| [audio-path.md](https://github.com/Angelo-politek/Synthack-OS/blob/dev/docs/audio-path.md) | CPU #2 engines, mix, sends, CPU load |
| [ui-parameters.md](https://github.com/Angelo-politek/Synthack-OS/blob/dev/docs/ui-parameters.md) | descriptors, pages, drawing, keys, kit storage |
| [firmware-format.md](https://github.com/Angelo-politek/Synthack-OS/blob/dev/docs/firmware-format.md) | `.syx` layers, sections, boot limit |
| [emulation.md](https://github.com/Angelo-politek/Synthack-OS/blob/dev/docs/emulation.md) | emulator, how mods are tested |
| [writing-style.md](https://github.com/Angelo-politek/Synthack-OS/blob/dev/docs/writing-style.md) | how to write docs and UI text |
| [CONTRIBUTING.md](https://github.com/Angelo-politek/Synthack-OS/blob/dev/CONTRIBUTING.md) | setup, rules |
| [RECOVERY.md](https://github.com/Angelo-politek/Synthack-OS/blob/dev/RECOVERY.md) | OS doesn't boot |
| [LEGAL.md](https://github.com/Angelo-politek/Synthack-OS/blob/dev/LEGAL.md) | what may be in the repository |
