# sfcore

The part of Synfact's Syntakt core (`mods/core-st`, by GSM1980 and contributors, on elekloader by irpina) that its modules need, on OS 1.42. Ported modules keep Synfact's headers (`include/syntakt/`) and compile nearly unchanged. No UI of its own. Added automatically with the mods that need it.

License: GPL-2.0-or-later. Sources name their Synfact origin in their headers.

## What it has

| Part | From Synfact | Here |
|---|---|---|
| Module table | SMZ4 bank, `modules.c` | 8 pointers at mod area `+0x1B000`. Each port writes its `st_smz_module` descriptor into its slot ([registry](../../docs/registry.md)). |
| Binding | at the SMZ load | at the first UI tick: `init(api)`, then the subscriptions join the event lists, in slot order |
| Events | `core.s`, `accounting.s`, `sample-ui.s`, `files.s` | `ev_tick`, `ev_draw`, `ev_key`, `ev_enc`, `ev_render_in`, `ev_main_mix`, `ev_fs_write`, `ev_fs_written` |
| Native transactions | `native.c`, `native.s`, `note-events.s` | TRIG, ENQUEUE, IMMEDIATE, PUBLISH, TYPE, HEADER_LOAD/RESET, SOUND_ALLOWED, MACHINE_ALLOWED, OWNERS (none), MODULATION, LFO, NOTE_ACCEPT; interest bytes (host API 5) |
| Host API 12 | `machine-host.c` | storage, HZFS and CRC from [long-samples](../long-samples) when it is in the build (bitwise CRC otherwise); native replays and dispatch; parameter provider (stores of IDs `0x3D9`–`0x3F8`) |

Not yet, with their first user:

- `ST_EV_VIEW` / `ST_EV_PRE` contexts (view draw `0x401009F4`, encoder resolver `0x4003B8C6`): recorder.
- PAGE_SYNC/NAV/LAYOUT/BEGIN/END/GUARD and the parameter-provider metadata lookups: LFO3, POLY.
- Sound lifecycle (`SOUND_META`) and pattern locks: `xstore`.

A module that subscribes to an event or context sfcore does not have is not bound (`sfcore_status` = 3).

## Adapters

UI events are always installed. The others have a `service` in `patch.json`. The build installs them only if a mod of the build asks for it, e.g. `"uses": ["sfcore:native"]` ([build.py](../../tools/build/build.py)):

| Service | Sites (OS 1.42) |
|---|---|
| — | `0x4000A220` tick, `0x4000A286` draw, `0x4000839E` key, `0x4000B468` enc |
| `sfcore:render_in` | `0x400A38D6` |
| `sfcore:main_mix` | `0x4008FB86` |
| `sfcore:fs` | `0x400B620C` write, `0x4010BA9E` written |
| `sfcore:native` | 11 sites: [make_patch.py](make_patch.py) |
| `sfcore:lfo` | `0x4011942A`, the LFO operation (alone: LFO3 needs no other audio adapter) |
| `sfcore:sound_set` | `0x40013304`, SOUND_ALLOWED and the parameter provider's Sound setter |

## Shared sites

Where a SyntHack mod already patches Synfact's site, the adapter takes the next instruction. Both run, the existing mod first:

| Synfact site | Owner | sfcore | Order |
|---|---|---|---|
| `0x4000B420` key call | perf-fx | `0x4000839E`, the dispatcher entry | perf-fx's `pf_ev`, then subscribers, then stock |
| `0x400A38CE` IRQ prologue | cpu-meter | `0x400A38D6` | cpu-meter's time includes the subscribers |
| `0x4008FB7C` main mix | fx3 | `0x4008FB86` | subscribers see the bus after fx3 |
| `0x400B6204` Data RPC write | long-samples | `0x400B620C` | subscribers see the writes long-samples declines |
| `0x40025594` set machine | sampler | `0x4002559C` | the sampler's front half, then MACHINE_ALLOWED |

Still to chain, with their users: FX codec `0x400A6E0E`/`0x400A6DA6` (fx3, LFO3 shadow), heap allocator `0x401036D0`/`0x401038D6` (LFO3 lock banks around modarea's reservation), lock lanes (xparams as a client of `xstore`).

`[!]` C functions returning a pointer: `m68k-linux-gnu-gcc` returns it in `a0`, the OS and Synfact's `m68k-elf` in `d0`. Declare OS and host calls that return pointers as returning `u32`.

## Cost

Audio interrupt, emulator ([tests/test_sfcore.py](../../tests/test_sfcore.py)):

| Build | Instructions per block |
|---|---|
| sfcore, UI only (no audio service) | 0 |
| all services, no subscriber | +94 (one `tst.b` and branch per adapter call) |

Same output as stock, bit for bit, with no subscriber and with a subscriber that declines everything, alone and with every other mod.

## Tests

[tests/test_sfcore.py](../../tests/test_sfcore.py): sites and stock bytes, chains with perf-fx, cpu-meter, fx3, long-samples and sampler, build with every mod and every service (boot margin), events delivered to a test module, consumed keys, screens unchanged, interrupt identical to stock, SRAM tails untouched by the OS.
