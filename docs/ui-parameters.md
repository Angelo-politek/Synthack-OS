# UI and parameters

## Parameter descriptors

Table at `0x4022D59C`, **505 records × 52 B, index = logical id**.

| Offset | Field |
|---|---|
| +0 / +4 | group / internal id (the value key) |
| +8 / +12 / +16 | min / max / default (UI values, 0..0x7F00 = 0..127) |
| +24 / +28 | MIDI CC (`cc<<16 \| 0xFFFF`) / NRPN |
| +32 | storage index |
| +36 | capability flags (e.g. `0xE00` → listed as modulation destination) |
| +40 / +48 | long / short name pointers |

Aliases share group + internal id. Ids 270–504 are machine parameters; hidden leftovers include 59, 72, 91, 101, 127, 144.

## Pages

Static C++ initializer `0x401885D2–0x401968F4` builds page objects in BSS (44 B: short name, long name, 8 logical ids).

| Page | Address | Slots |
|---|---|---|
| MIX3 External Mixer | `0x41B9F7E8` | `126 · – · – · – · 129 · 130 · 128 · 132` |
| FX track SYN (FX Drive) | `0x41B9F948` | `– ×7 · 150 (DRIVE)` |

Slots are read at draw time: changing them at runtime changes the page.

## Per-parameter objects

`0x41B9FA24 + 84·id` (built at boot). Four `std::function`s copied from shared prototypes:

| Offset | Role |
|---|---|
| +20 | value → text formatter, called as `invoker(fn, value 0..0x7F00, char *buf)` (numeric: `0x40077F86`) |
| +36 | value graphic (knob / bar / bipolar). DRIVE has its own (`0x40071408`) |
| +68 | graphic style: `0x41B9D5D0` bar, `0x41B9D670` knob, `0x41B9D660` bipolar ("hourglass") |

The init code (`pea <prototype>`) decides the look of each id; patching that operand changes it.

## Reading and writing values

Kit-level parameters go through three functions, keyed by **logical id**:

| Function | Address |
|---|---|
| is kit parameter? | `0x4000D870(obj, id)` |
| get | `0x4000D94A(obj, id)` → value |
| set | `0x4000DA32(obj, id, value, flag)` → clamps, stores, notifies (UI redraw) |

Group handlers use jump tables by logical id (e.g. external mixer: get `0x4000C8B0`, set `0x4000C9A4`).

## Kit storage and "global FX"

- UI kit struct (`obj->vfunc40`): internal mixer +2…+26, external +28…+45, DRIVE +46, FX filter +48…+71, FX amp +72…+99.
- Pattern kit (`*0x800030BC`): external +70…+87, filter +88…+111, amp +112…+139, DRIVE +124.
- Global flags `0x43BDE444`: bit 0 internal mixer, 1 external, **2 SYN (DRIVE)**, 3 filter, 4 amp. Enabled blocks are copied (memcpy) between kit and the global container `0x41B9D3B0`; the engine sync `0x400A1D18` copies whole blocks.
- **Unused words** in the external block: UI +30, +36, +40, +42 (pattern kit +72, +78, +82, +84). Saved with the kit; used by the master compressor.
