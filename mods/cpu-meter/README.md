# cpu-meter

Diagnostic. Shows the load of the audio interrupt measured on the device. Not for builds you play with.

## Use

1. Build with it: `python tools/build/build.py --stock firmware/Syntakt_OS1.42.syx mods/cpu-meter <mods to measure> -o out/meter.syx`.
2. Open any parameter page (SRC, FLTR, AMP, the FX3 page).
3. Read the box left of the tempo, top right: `93 97` = average and peak load of the last ~0.34 s, in percent of the audio block. Stock at rest: ~89.
4. Above ~95: the UI lags. 100: the interrupt runs late.

The first value after power-on is wrong (no previous block). The page redraws ~3 times per second to refresh it.

## How it works

| Part | Detail |
|---|---|
| Entry | `0x400A38CE`: `jmp cm_entry`. The stub redoes `link` and `movem`, reads DTCN0 (`0xFC07000C`, DTIM0's free-running counter, also read by the OS at `0x400822B4`). Period = entry − previous entry |
| Exit | `0x400A5518`: `jmp cm_exit`. Duration = exit − entry, sums and peak. Then the OS's `movem`, `unlk`, `rte` (`0x400A551E`) |
| Window | 512 blocks: sums published, root view byte 96 set (redraw) |
| Text | ParameterPageView vtable `0x401C84AC`: the OS draw (`0x40032692`), then `"%s"` with the 4×6 font in a 7-character box at (74, 56) |
| Cost | ~25 instructions per block in the interrupt; one redraw every 0.34 s |

The ratio duration / period doesn't depend on the counter's clock.

## Test

`tests/test_cpu_meter.py`: the interrupt with both hooks against stock (same output, ≤ 40 instructions more), sums with a simulated DTCN0, the text drawn on the page and the stock page without measurements.
