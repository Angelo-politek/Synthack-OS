# vparams

Virtual parameters: hidden parameter ids that a mod reads and writes its own way (RAM state, free kit words…) instead of the OS.

| Item | Value |
|---|---|
| Hooks | kit-parameter functions: is-kit `0x4000D870`, get `0x4000D94A`, set `0x4000DA32` |
| Table | mod-area offset `+0x8000`, 32 entries `{id, get, set}` |
| Slots | 0–6 master-comp, 7 and 9–16 fx3, 17–18 dual-mono; owners in [docs/registry.md](../../docs/registry.md) |
| Tests | `tests/test_master_comp.py` (other ids behave as the original), `tests/test_fx3.py` |

- Each mod writes its entries with `vparams.entry(slot, id, get, set)`, as an appended patch.
- Registered ids report "kit = 1". get/set jump to the mod with the OS stack layout.
- Other ids resume the original code unchanged.

`[!]` Not for sound parameters that need p-locks: "kit = 1" sends edits to the kit path ([#1](https://github.com/Angelo-politek/Synthack-OS/issues/1)).
