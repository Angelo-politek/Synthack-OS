# Modding guide

How the mods in this repository are built, and how to do the common things: hook code, add a page or a parameter, give it a name, a text and an icon, save its value, add audio processing without slowing the UI down, replace a machine. Addresses are for Syntakt OS 1.42, CPU #1 (section 3). Reference material: [memory-map](memory-map.md), [ui-parameters](ui-parameters.md), [audio-path](audio-path.md), [emulation](emulation.md), [firmware-format](firmware-format.md).

## 1. Workflow

1. `python tools/new_mod.py <name>` writes a mod that already compiles and passes its test: a C source, `make_patch.py`, `mod.json`, `README.md`, `claims.json` (its space in the mod area) and `tests/test_<name>.py`.
2. `mods/<name>/make_patch.py` compiles the code and writes `patch.json`: for each change, the address, a SHA-256 of the original bytes and our bytes. It uses [`tools/build/modkit.py`](../tools/build/modkit.py): `compile` (GNU as or gcc for ColdFire, `-mcpu=54418`, at the space the mod claimed), `area` (code appended to the [mod area](../mods/modarea)), `hook` (`jmp` or `jsr` over OS instructions, checked against the bytes you expect), `replace` (data), `write`. C sources include [`sdk/synthack.h`](../sdk/synthack.h): types, `DATA`, and names for the OS functions and buffers mods use most.
3. `tests/test_<name>.py` runs your code in the emulator: `screens.UI(["<name>"])` boots the stock OS with the mod and calls functions (`ui.call`); for audio code, load the stock section 3 into Unicorn, apply the patch and run the original code around it. EMAC instructions run in Python (`tools/emu/emac.py`): give it the list of EMAC sites of your code.
4. `tools/build/build.py` checks every hash, overlaps and the boot decompression margin, and writes the `.syx`.
5. Flash, test on the device, only then publish.

Mod area: first 512 KB block of the OS heap, from `modarea_layout.RAM`: code and data unpacked at boot in the first half, runtime RAM in the second, zeroed beyond the code. Who uses which offsets, boot-list slots, the engine area, shared RAM, the section 3 free fill, vparams slots, parameter ids and pages: **[registry.md](registry.md)**. A new mod claims in its own `mods/<name>/claims.json`, inside the zones marked for new mods (`new_mod.py` picks the space); `tests/test_registry.py` checks every `patch.json` against the claims, and a resource that is already taken is an error naming its owner.

**Rules learned the hard way**

- Never touch sections 2 and 6; never make the boot intro longer.
- Never use the RAM above the BSS (`0x45566490–0x48000000`): no code refers to it, but the OS writes all over it when it loads samples ([#4](https://github.com/Angelo-politek/Synthack-OS/issues/4)). Memory for mods comes from the mod area, i.e. from the OS heap.
- Keep the boot decompression margin (build fails under 4 KB). Zero padding is the worst case.
- No `.bss` in mod code: put variables in `.data` (`__attribute__((section(".data")))`). The mod area is zeroed anyway, but the build checks.
- No libgcc: `nm -u` must be empty. ColdFire has `divu.l`/`remu.l`, `ff1`, `mvs`/`mvz`, `sats` — GCC uses them.
- ColdFire limits: `muls.l` takes no absolute address (use `d16(An)`), no `exg`, `movem` only with `(An)`/`d16(An)`, short branches reach ±127 B.
- **OS calls from C**: the OS returns every result in `d0`, pointers included; `m68k-linux-gnu-gcc` (SVR4 ABI) reads a pointer result from `a0`. Declare OS functions with an integer return and cast: `((u32 (*)(u32))addr)`, not `((u32 *(*)(u32))addr)`. `tests/test_os_abi.py` rejects the pointer form. SY FM4 crashed on the device from this: the page list went where `a0` pointed.
- **`std::string` by value** (e.g. a page name, vtable slot 19 of the SRC view): the caller passes the string to construct in `a0` and gets it back in `d0`. Build it with the OS constructor (`0x401BF31E`, `(string, text, allocator)`) at that address. GCC can't express this: use an assembly wrapper (`mods/syn-pages/synpages.c`).

## 2. Hooking code

A hook replaces ≥ 6 bytes of OS code with `jsr ours` (padded with `nop`), and the trampoline **replays the replaced instructions** before returning. The patch stores the hash of the original bytes, so a different OS version fails the build instead of crashing.

- Save every register you use; the OS keeps values in registers across the hook point.
- Replaced `pea` pairs (arguments of the next call): pop the return address, push the arguments, `jmp` back (`fx3_mix_hook`).
- Replaced `jsr f`: do your work, then call `f` with its arguments untouched (`sm_block` in [sampler](../mods/sampler)).
- Replaced OS loop: `jsr ours ; jmp <end of the loop>`, using only the registers the loop itself clobbers (`fx3_del_hook`, `fx3_rev_hook`: same result as the OS loop, checked against the stock bytes in `tests/test_fx3.py`).
- Replaced EMAC instructions: replay them first (`fx3_trk_hook`). If your code uses EMAC, set `MACSR` yourself and leave `ACC0` at 0 (the OS sum routines start from it).
- One-time setup at boot: hook an instruction of the page initializer (`0x40188796…`), e.g. a `clr.l` that empties a page slot (`fx3_page_stub`, `comp_page_stub`). Objects built earlier in that initializer are ready.
- Setup before the OS starts: a slot in the mod area's **boot list** (`+0x7400`, 8 pointers, `BOOT_SLOTS` in `tools/build/registry.py`). The loader calls it after unpacking, before the static constructors: fill tables the OS reads early, register with [syn-pages](../mods/syn-pages). No OS objects exist yet. See [memory-map](memory-map.md#mod-area).

## 3. Parameters

Logical id → descriptor (`0x4022D83C + 52·id`: group, internal id, min/max/default, MIDI, names at +40/+48). An id without a page or a MIDI CC is not necessarily free: if another descriptor has the same group and internal id, it is an **alias** that the OS can put on a page in some modes (#3). `tests/test_id_audit.py` rejects aliases, MIDI CC/NRPN and ids shared between mods; ids in use are listed in [ui-parameters](ui-parameters.md#hidden-ids-used-by-the-mods). Patch min/max/default and the name pointers in the descriptor to make the id yours.

**New parameters: ids 505–568** ([idspace](../mods/idspace)). The OS has 505 ids and all are in use, as parameters, aliases or MIDI CCs. idspace copies the descriptor table to a larger one at boot. A mod writes the descriptor of its id (`idspace_layout.desc(id)`, 52 B) and its object definition (`idspace_layout.objdef(id)`: a model id whose text, icon and style it copies), and claims the id in `claims.json` (`"ids"`). To make it an LFO destination, add an entry to the DEST list (`idspace_layout.destx`, claim `"destx"`). Examples: `mods/fx3`, `mods/sy-fm4`.

**Virtual parameters** ([vparams](../mods/vparams)): register `{id, get, set}` in the table and the three kit functions (is-kit, get, set) call your functions for that id. Values are 0…0x7F00 (127 × 256). `set` must request a redraw: `*(*0x444E2334 + 96) = 1`.

**Saving.** Two kinds of spare storage, both saved by the OS without knowing:

- **Per track**: engine word +106 (internal id 39, hidden id 72 "amp delay time") is saved per track and p-lockable. fx3 uses it for SND3 (a real OS parameter: only its descriptor and page slot change).
- **Per kit (pattern)**: `*0x800030BC` is the pattern kit = the FX track's parameters, one word per internal id (offset = 2 × id, 142 B). Words with no use: ids 0, 0x1A, 0x24, 0x27, 0x29, 0x2A, 0x37, 0x46 and 0x38 (hidden id 144). master-comp uses 0x24/0x27/0x29/0x2A, fx3 0/0x1A/0x38/0x46; 0x37 is free again since v0.9 (perf-fx stores its settings in the native Mod A values). Store values **XOR their default**, so old projects (zero words) load with defaults. Read the word on every use (pattern changes swap the kit); fall back to RAM while the pointer is 0. With *global* FX blocks the OS uses a container at `0x41B9E3B0` instead (master-comp follows the SYN flag).
- **Per kit, more room**: [kitstore](../mods/kitstore) saves words 41–43 of the 12 per-track kit blocks (Digitakt MIDI-track data, unused on the Syntakt); take words in `tools/build/kitstore_layout.py`.
- **Per project**: [projstore](../mods/projstore) keeps 256 bytes in the reserved area of the project settings file; take a slice in `tools/build/projstore_layout.py`.
- **Kit on storage** (FUNC+YES/NO, project save): the FX block goes through a position table that drops words 0x1A and 0x46 and reads word 0 back from 0x1A. fx3 keeps those three words in 8 reserved bytes of the stored block (hooks at `0x400A6E0E` / `0x400A6DA6`). Any new kit word must survive the round trip tested in `tests/test_fx3.py`.

## 4. Pages and tabs

- **Page objects** live in BSS (array at `0x41BA03C8`, 44 B each): names and 8 slot ids. Slots are read at draw time: write a slot to move a parameter, write 0 to empty it (fx3 hides the crusher's unused knobs this way, `SLOTS[4..5]`).
- **AMP pages** (track), first slot (A) of each variant: page 1 `0x41BA060C` (AHD envelope) / `0x41BA0638` (ADSR), page 2 `0x41BA0664` / `0x41BA0690`; 4 B per slot. fx3 puts SND3 in slot G of page 1 (`0x41BA0624`, `0x41BA0650`) and PAN in slot E of page 2 (`0x41BA0674`, `0x41BA06A0`), from a stub at the end of the AMP pages in the initializer (`0x40194C14`).
- **Tabs** are built from constant arrays of page indices plus a count, e.g. REVERB `{21}` (count at `0x4003588C`, array pointer at `0x40035892`). To add a page: point the array to your own `{21, 25}` and set the count to 2 — the tab key then cycles the pages. Page 25 ("OB8") is a Digitakt leftover, free.
- **Tab classes** can draw slots their own way: the DELAY/REVERB class draws slots 5–6 as one filter box (fx3 sends page 25 to the generic 8-slot draw `0x4003A244`); the AMP class draws ids 73–77 and unknown ids as the envelope (a patched branch at `0x40041E84` lets id 72 draw normally).
- Page names: pointers in the initializer (`fx3` patches two `pea`); to rename at runtime, point them to a RAM buffer and rewrite it.

## 5. Text, icons and styles

Each parameter has an object at `0x41BA0A24 + 84·id` with `std::function`s (16 B: `data0, data1, manager, invoker`):

| Offset | Called as | Role |
|---|---|---|
| +20 | `invoker(fn, value, char *buf)` | value → text (≤ 6 characters fit a slot) |
| +36 | `invoker(fn, value, ctx, x, y)` | icon / value graphic |
| +68 | (style) | how the value is shown around the icon: bar, knob, … ; empty = default renderer |

At boot the initializer copies shared **prototypes** into each object (`pea <prototype>` before `0x40188482`). Two ways to change them:

- **At build time** (fixed look): patch the `pea` operand of that id to another prototype — this is how SND3 got the machines' MOD icon and the delay-send bar.
- **At runtime** (look depends on state): write the 16 bytes yourself as `{0, 0, our_manager, invoker}`, where `our_manager` is a no-op (`return 0`) and `invoker` is your function, or the invoker read from a prototype's +12. Only do this for invokers that ignore the functor data (check the disassembly: they never read the first argument), and **only from UI code** (formatters, graphics, set): if the audio interrupt rewrote a `std::function` while the UI was calling it, the UI would jump to a half-written address. Don't raw-copy OS prototypes: their data points to a heap functor shared with the prototype.

Useful prototypes (+36 icon, +68 style as the OS pairs them; "frames" icons pick a picture by value):

| Prototype | Used by | Notes |
|---|---|---|
| `0x41B9ECD0` | most knobs | plain knob |
| `0x41B9EC70` + `D660` | LFO DEP, delay WID | bipolar value |
| `0x41B9EBD0` / `DBA0` + `D5D0` | track DEL / REV send | send icon + bar |
| `0x41B9EB80` + `D660` | PAN, BAL | pan |
| `0x41B9EC00` + `D5C0` | track VOL | level |
| `0x41B9ECB0` + `D670` | OVER (all machines) | overdrive, frames |
| `0x41B9E6B0` | SPD (machine 467) | frames |
| `0x41B9E730` | MOD | frames |
| `0x41B9E7D0` / `D7E0` | sweep time / depth | frames |
| `0x41B9E740` / `D760` / `D780` + `D660` | BAL / TONE / noise colour | frames |
| `0x41B9E830` | TICK | frames |
| `0x41B9ECD0` + `D5E0` | delay FDBK | feedback style |

Avoid prototypes whose invoker reads project state (e.g. `0x41B9EB90`, `DBB0`, `DBC0` read the FX routing; `D8F0`, `D920`, `DB10` read the project): they would draw the OS state, not your value. The full list (id → prototypes) can be rebuilt by scanning the initializer for `pea 0x41B9Dxxx` before each object address.

Drawing yourself: text `0x400F8DDC(ctx, font, x, y, centred, 0, width_template, fmt, ...)` (fonts `0x402A9510` 4×6, `0x402AA114` 3×6); images `0x400F8F70(ctx, image, x, y, centred)`, 1-bit, 28 B header (+4 width, +8 height, +12 words per row, +16 pixels, +20 mask); icon sets are built from resources at boot (`0x444E….`), frame by value with `0x400F9440(set, value)`. The slot box is about x−1…x+18, y…y+16.

## 6. Audio processing

Everything runs in the audio interrupt (`0x400A38CE`), once per 32-sample block (1 500 per second). The OS already uses ~89 % of the CPU at rest; the UI and the sequencer get the rest. **A few thousand instructions per block are enough to make the UI lag.** fx3 is the reference for adding an effect:

- **Where**: the mix function `0x4008F242`. Per-track loop `0x4008F296` (track gains, sends, mute mask at `fp−508`); sends summed by OS routines with EMAC `msac` (result = −Σ g·x, keep that sign convention); delay call `0x4008F8A0`; master sums before `0x4008FB7C`, after which the direct bus `0x8000DAD0` can still be modified. Sources: digital tracks `0x80003D50`, analog `0x80003950`, 128 B per channel.
- **Cost**: count instructions in the emulator (`UC_HOOK_CODE`; call `uc.ctl_flush_tb()` first or already-translated blocks are not counted) and keep a regression test (`tests/test_fx3.py::test_cost_per_block`). The whole interrupt with your mod: `python tools/emu/isr.py --scene max <mod>` (call tree, instructions per routine).
- **Cheap by design**: do nothing when there is nothing to do (no sends, output not listened to, silent input and tail done); compute at 24 kHz where the sound allows it (average pairs in, linear interpolation out); sum only the tracks that send; write results straight into the OS bus instead of an extra pass; run hot loops in assembly; skip work at steady state (fx3's gain ramp only runs when a target changed — flagged by the per-track hook).
- **Smoothing that ends**: a ramp `c += (t − c) >> n` never reaches `t`; snap when close, or the effect never goes idle.
- **Bounded reads**: a modulated delay line read without wrap checks must limit how far the delay moves per block (fx3: 8 samples, a sudden TIME change glides).
- **Not idle time**: the DSPI wait at the start of the interrupt (`0x4010222A`) is ~0 in practice (the transfer of the previous block is already over).

## 7. Machines

A machine replaces a stock engine on CPU #2: [sy-fm4](../mods/sy-fm4) replaces SY TONE (engine 4), [sampler](../mods/sampler) SP TWINSHOT (engine 11). Engines are listed in [audio-path](audio-path.md#cpu-2--voice-engine-section-7).

| Part | CPU | How |
|---|---|---|
| Sound | #2 | New prep and render for the engine, in the [modarea7](../mods/modarea7) engine area (`0x47000000` + offset, `ENGINE` in the registry). CPU #1 stages section 7 in a buffer with ~9 KB left: modarea7 sends it compressed to make room. |
| Parameters | #1 | Rewrite the descriptors of the replaced machine (names, ranges, defaults; sampler: 497–504). Extra parameters take ids above 504 from [idspace](../mods/idspace) (sy-fm4: 521–528) and storage slots in the sound from [xparams](../mods/xparams). |
| SYN pages | #1 | [syn-pages](../mods/syn-pages): register `{key, pages, record, title, draw}` from the boot list. Key = descriptor of knob A on the machine's stock page. Up to 4 pages; `record` gives the descriptor under each knob, `title` the page name, `draw` draws after the stock page. |
| Data to CPU #2 | #1 → #2 | Values that are not in the voice frame go through [shared RAM](memory-map.md#shared-ram): sy-fm4 copies its extra page values (locks applied) once per block, sampler the tempo. |
| Data from CPU #2 | #2 → #1 | Same RAM, the other way: the sampler's waveform. CPU #1 asks, CPU #2 answers over several blocks; CPU #1 redraws when more is ready. |

- The CPU #2 budget is separate from CPU #1's: count instructions per block with 8 voices in the section 7 emulator (`tests/test_sampler.py`: 8 SAMPLER voices ~84 000, 8 SP TWINSHOT ~64 000).
- Files: sounds made with the stock machine open with the new one. Make the default sound the same (sy-fm4: `ALGO` 0 = SY TONE) or say it in the README.
- Test the UI side with `tests/syn_view.py`: the SRC view of a track with your machine in the main CPU emulator (pages, titles, drawing).

## 8. Testing on the device

- Keep a test build only when the emulator cannot answer (timing, analog parts). Measurements done so far: interrupt load with DTIM0 (`0xFC07000C`) at entry/exit; analog curves recorded through an audio interface (`tools/measure`).
- Check save/reload, pattern change and power cycle for anything stored in the kit.
