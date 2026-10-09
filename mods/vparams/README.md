# vparams

Shared "virtual parameters" for mods: hidden parameter ids that a mod reads and writes its own way (RAM state, free kit words…) instead of the OS.

- Hooks the three central kit-parameter functions: is-kit `0x4000D870`, get `0x4000D94A`, set `0x4000DA32`.
- Table at `0x46008000`: 32 entries `{id, get, set}`. Each mod writes its entries with `vparams.entry(slot, id, get, set)` (an appended patch). Registered ids report "kit = 1"; get/set jump to the mod with the OS stack layout. Other ids resume the original code unchanged.
- Slots: 0–6 master-comp, 7 beat-repeat.

Tested through `tests/test_master_comp.py` (including "other ids behave exactly like the original") and `tests/test_beat_repeat.py`.
