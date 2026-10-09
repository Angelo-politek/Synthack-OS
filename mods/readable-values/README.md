# readable-values

Shows parameters in real units instead of 0–127. Every value comes from the same OS data the DSP uses; parameters without a physical unit (PNCH, OVER, COL…) keep their numbers.

| Parameter | Text | Source |
|---|---|---|
| Filter FREQ (tracks 1–8) | `4.9Hz` … `20.3k` | pole frequency of the engine biquad: 4.918 Hz · e^(0.065542·FREQ), measured in emulation (< 0.1 %) |
| Filter BASE / WDTH (tracks 1–8) | `5.0Hz` … `24.0k` | one-pole HP/LP, OS table `0x4029BFFC`; WDTH starts at BASE |
| Filter env DEL / ATK / DEC / REL (tracks 1–8) | `0.7ms` … `10.0s`, `INF` | OS tables; ATK = full ramp, DEC/REL = time to −60 dB |
| Amp ATK / DEC / REL (tracks 1–8), HOLD (all) | `0.1ms` … `30.0s`, `INF` | engine tables (identical copy in CPU #1 memory) |
| SUS (filter, amp) | `0%` … `100%` | |
| LEV, VOL, IN | `-inf` … `0.0dB` | gain (v/127)² |
| Sends DEL / REV (tracks, FX track, external in) | `-inf` … `-0.1dB` | gain (v/32768)² |
| Delay HPF / LPF, Reverb HPF / LPF | `5.0Hz` … `24.0k` | −3 dB of the one-pole filters; LPF starts at HPF |
| Delay REV / VOL, Reverb VOL | dB | gain (v/32768)² |
| Reverb PRE | `0.8ms` … `337ms` | (v² >> 16) + 37 samples |
| Reverb shelving FREQ / GAIN | `974Hz` … `14.0k` / dB | first-order bilinear high shelf |

| Analog filter FREQ (tracks 9–12, FX track) | `15Hz` … `21.5k` | measured on the device: 14.645 Hz · e^(0.05741·FREQ), within 1.4 % |
| Analog amp ATK / DEC / REL (tracks 9–12, FX track) | `~275ms`, `~7.58s` | digital times × measured factor (1.05–1.52); `~` = estimate, ±10–20 % |

Still numbers: filter envelope and BASE/WDTH on analog tracks and the FX track, LFOs, RESO and parameters without a unit.
Measurements: `tools/measure/analog.py` on recordings of the main out.

## How it works

- `rv.c` (C, `m68k-linux-gnu-gcc -mcpu=54418`, no FPU, no libgcc) at `0x46002000` in the [mod area](../modarea).
- At boot the OS copies each parameter's formatter (`std::function`, object `+20`) from a prototype; we patch the prototype operand of each handled id to `rv_proto`. One invoker finds the id from the object address.
- Track parameters (58–85) are shared by all tracks: the formatter asks the OS for the active track the same way the parameter pages do (`0x4001FF74(project + 48)`, project = `*0x444E13F4`).

Test: `tests/test_readable_values.py` runs the original CPU #1 and CPU #2 code in the emulator and checks every text against it.
