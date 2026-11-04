# fastmix

Two hot routines of the audio interrupt (CPU #1) rewritten to do the same work in fewer instructions. **Same output, bit for bit.** No UI, nothing saved.

Added automatically with the mods that run in the audio interrupt (fx3, master-comp, dual-mono, sy-fm4).

## What changes

| OS routine | Stock | fastmix |
|---|---|---|
| Bus sums `0x4008EF8C` (10 ch), `0x4008F024` (9), `0x4008F0B6` (8): 14 calls per block | 685–811 instructions per call, every channel, gain ramp `g += inc` every sample | Gains steady (all `inc` = 0): no gain: zeros. 1–5 gains: those channels only. More: all channels, no ramp, gains not written back. A ramping gain runs the OS routine (+16 instructions). |
| Parameter smoothing `0x400979CA`: 938 words of the engine parameter copy, `s = C·x + K·s` per block | ~7 000 instructions, every word, every block | Groups of 16 words. A group whose state stopped moving and whose inputs are the same as then: output = inputs, nothing else. Otherwise the OS computation; every 16 blocks it also checks whether the state stopped. |

`[!]` Since 2026-11-04 the smoothing is **not hooked**. On the device (cpu-meter, with the cache model `tools/emu/cycles.py` calibrated on it) it cost more time than it saved: 5 300 fewer instructions, but a 1.9 KB copy of the inputs in DDR, 117 cache lines missed every block. `fm_smooth` stays in the blob and in the tests. The bus sums stay: −3 200 cycles per block.

## Why the output is the same

- Sums: a zero gain gives a zero product. The accumulator adds integers with 8 guard bits, so skipping a channel or reordering does not change it. Same saved registers, `acc1`–`acc3`, MACSR mode. Only the N/Z/V/EV flags of the last EMAC operation differ: the OS never reads them.
- Smoothing: `C + K = 1` in Q15, so `s = x << 16` (or up to 33 below, truncation) is a fixed point. There the OS rewrites the same `s` and an output equal to `x`. The OS functions that write `s` directly (`0x40097766`, `0x400977AA`, `0x400977D8`, `0x4009787A`, `0x4009790C`, `0x4009792C`) write `x` too, with `s = x << 16`. The output is rewritten every block, as the OS does: LFOs and track code modify it afterwards.
- A different EMAC mode, or `acc0`/`acc1` not empty on entry, makes every group compute.

## Cost

Instructions per block, emulator ([tests/test_fastmix.py](../../tests/test_fastmix.py)).

| Part | Stock | fastmix |
|---|---|---|
| Sum, 10 ch, all gains | 811 | 509 |
| Sum, 10 ch, 2 gains (sends) | 811 | 296 |
| Sum, no gain (FX-track bus unused) | 811 | 76 |
| Sum, gains ramping | 811 | 827 |
| Smoothing, steady | 7 830 | 2 512 |
| Smoothing, all inputs changed | 7 830 | 8 205 (one block) |
| Smoothing, moving towards new values | 7 830 | 7 973 |

Whole interrupt with all mods: see [tests/test_cpu_budget.py](../../tests/test_cpu_budget.py).

## Layout

- Code and data at mod area `+0xF000` ([registry](../../docs/registry.md)), `.bss` zeroed by [modarea](../modarea).
- Hooks: `jmp` at the three sum entries, `jsr fm_smooth ; jmp 0x40097A2A` at `0x400979D6`.

## Tests

`tests/test_fastmix.py`: stock and patched routines in two emulators with the same data. Sums: 0–10 gains, steady and ramping, `acc0` not empty, saturation, four EMAC modes; bus, memory around it, gains, accumulators, saved registers. Smoothing: random state, settled state with words still moving, parameter changes, writers of the state, LFO writes on the output, `acc0`/`acc1` not empty, EMAC mode change. Cost ceilings.

`[!]` To check on the device: sound and CPU time (DTIM0) with and without it.
