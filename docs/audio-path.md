# Audio path

Blocks of **32 frames at 48 kHz** (0.67 ms).

## CPU #2 — voice engine (section 7)

- Main `0x40000DB4`; all work in the audio interrupt `0x40000934` (vector 96, DMA timer 0 capture).
- Per block: copies `0x1B0` B of parameters from shared RAM, renders **8 digital voices** with `0x40004324`, sends 8 × 32 × int32 (1 KB) back via **eDMA ch. 47**. No mixing here.
- 12 engines: tables at `0x400148F0` (render), `0x40014920` (update), `0x40014950` (machine ID → engine).
  0 BD MODERN · 1 SD BASIC · 2 CY ALLOY · 3 PC CARBON · 4 SY TONE · 5 SY CHORD · 6 SD VINTAGE · 7 CP VINTAGE · 8 SY TOY · 9 SY BITS · 10 SY SWARM · 11 SP TWINSHOT.
- SY CHORD reads a 512 × int32 single-cycle wave at `0x4001A300`.

## CPU #1 — mix and output (section 3)

Per-block routine `0x400A3856` calls, in order: CV/gain function `0x400903CA` → ADC deinterleave → master/FX function `0x4008F1CA`.

| Buffer | Content |
|---|---|
| `0x80003D50` | 8 digital tracks from CPU #2 (8 × 128 B) |
| `0x80003950` | 8 **ADC** channels (ring `0x80001800`, 8 slots/frame, phase-inverted): 0–3 analog tracks · 4–5 external in · **6–7 analog mix bus L/R, before the master VCAs** |
| `0x8000DAD0` | digital bus to the analog mixer (tracks not routed to the FX track + delay/reverb returns) |
| `0x8000DFD0` | digital tracks routed to the FX track |
| `0x80004760` | Overbridge/USB, 20 ch/frame: 0–1 main, 2–9 digital tracks, 10–13 analog tracks, 14–15 ADC 6/7, 16–17 FX |

Delay `0x40096890` and reverb `0x40096E3C` run on CPU #1 (same code as Digitakt mk1).

**The final mix is analog.** Digital buses go out through DACs (TDM, 8 slots, ring `0x80000000`) into the analog mixer; nothing digital sits after the master VCAs.

## Analog mixer control voltages

40 CVs in a 1000-byte struct (live copy `0x4029A040`, per-block copy in SRAM), sent over DSPI1 with eDMA ch. 15.

| CV | Name |
|---|---|
| 0–3 / 5–8 | voice 1–4 left / right |
| 4 / 9 | external in left / right (`hw+0x08`, `hw+0x12`) |
| 10–33 | voice cutoff, resonance, tune, levels |
| **35 / 36** | **master left / right** (`hw+70`, `hw+72`) — recomputed every block in `0x400904B2–0x4009055E` |
| 37 / 38 | master filter cutoff |

- External-in gains: block `0x40090872–0x400908F8`; constant-power balance law `0x400A171A`.
- EXTERNAL IN mode flag: byte `0x80003146`, **0 = mono**.
