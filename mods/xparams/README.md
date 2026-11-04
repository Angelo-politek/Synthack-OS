# xparams

Eight more parameters per track for the machines that need them: logical indices `0x36`–`0x3D`, saved with the sound, p-lockable, and sent to the voice CPU every audio block. Used by [sy-fm4](../sy-fm4) (pages 2/3 and 3/3) and [sampler](../sampler) (knob H of page 2/2). The code comes from SY FM4 (Rxuting, MIT).

## Use in a machine

1. Give the parameter a descriptor with a logical index `0x36`–`0x3D` and show it on a page ([syn-pages](../syn-pages)).
2. On the voice CPU, read it at shared RAM `0x700 + 16 × voice + 2 × (index − 0x36)`: the value with this block's p-locks applied.
3. Need a machine word (logical indices `0x11`–`0x1A`) exactly as set? The voice frames carry them smoothed: the main CPU moves them a few percent a block towards a new value (`0x400979CA`), fine for a level, wrong for a choice (a slice, a grid, a mode). Read them at shared RAM `0x640 + 20 × voice + 2 × (index − 0x11)`: as set, with this block's p-locks.
4. Optional: register what a sound saved by a stock OS gets there (zeros otherwise): `xp_on_empty(fn)` from the mod area's boot list (`xparams.h`, `-DXP_TABLE=` from `tools/build/xparams_layout.py`).

The indices are per track: a track has one machine, so two machines can give the same index different meanings.

## How it works

| Part | Detail |
|---|---|
| Storage | The OS maps logical indices `0..0x35` to storage slots (`0x40234344`, back `0x4023441C`). xparams' copies of the two tables run to `0x46`: the extra indices keep their own slots (the sound has 72, 54 used). Saving: `0x400A7436`, bound `0x400A7452`. |
| Loading | The deserializer's slot loop (`0x400A706A`) calls `xp_load_params`: slots to logical indices, then the registered machine's values if the extra indices are all zero. |
| p-locks | Lock lanes `0x50`–`0x57` for the extra indices (`0x400A81CA`, `0x400A8336`, read bound `0x400A803E`); `0x400A6D32` maps a lane back. A stock OS drops lanes above `0x46`. |
| Voice CPU | `0x400A20AE`, the render's wait for eDMA 47, then a copy of the 8 × 8 extra words to shared RAM `0x700` and of the 8 × 10 machine words, as set, to `0x640` (~360 instructions a block, one loop per track: the unrolled copy ran fewer instructions and cost ~4 500 cycles more in cache misses, `tools/emu/cycles.py`). |
| Boot | `xp_boot` from the mod area's boot list fills the tables before the OS reads a sound. |

`[!]` A project with p-locks on these parameters, opened on a stock OS, loses those locks.

## Test

`tests/test_xparams.py`: tables after boot, slots to logical indices, no machine hook, cost and result of the per-block copy. `tests/test_sy_fm4.py`: the sites match the original SY FM4 patcher's; a stock sound gets SY FM4's page 2/3 defaults.
