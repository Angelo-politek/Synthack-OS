# Emulation

`tools/emu` runs original Syntakt code on the PC with [Unicorn](https://www.unicorn-engine.org/) (installed separately, GPL-2.0).

```sh
pip install unicorn
python tools/emu/cli.py render --machine 5 --note 60 --seconds 0.5 -o out/emu/chord.wav
python tools/emu/cli.py survey --seconds 0.5 -o out/emu      # one WAV per engine
```

| File | Role |
|---|---|
| `memmap.py` | shared RAM, DDR `0x40000000`, SRAM `0x80000000`, peripherals |
| `periph.py` | behavioural PIT, eDMA, timers |
| `engine.py` | boots section 7 (simulated CPU #1 handshake), one interrupt = one block |
| `emac.py` | **EMAC** (multiply-accumulate unit) in Python, hooked via `ILLEGAL` breakpoints |
| `gen_emac_sites.py` | exact list of EMAC instruction addresses (GNU objdump) |

## Why a custom EMAC

Stock Unicorn gets signed fractional EMAC wrong, so audio comes out silent. We trap each EMAC instruction and execute it in Python from the NXP reference manual. Use CPU model "ANY" (the code needs FF1, MVS/MVZ, SATS) and set `SR` before `A7`.

## How mods are tested

Each mod's test loads the stock section 3 or 7, applies the patch, and runs the **original** function and the patched one side by side (e.g. `tests/test_dual_mono.py`, `tests/test_master_comp.py`). ~400× slower than real time for section 7.
