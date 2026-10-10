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

### FX parameters as the DSP sees them

Engine copy of the kit (or global) blocks, base `0x800021B0`, written by `0x400A1D18`:

| Block | From kit L2 | Words |
|---|---|---|
| `0x80002896` delay | +34 | TIME · X · WID · FDBK · HPF · LPF · REV · VOL · routing |
| `0x800028AA` reverb | +54 | PRE · DEC · FREQ · GAIN · HPF · LPF · VOL · routing |
| `0x800028BA` external mixer | +70 | |
| `0x800028CC` FX track filter | +88 | |
| `0x800028E4` FX track amp | +112 | DRIVE at `0x800028F0` |

- HPF / LPF (delay and reverb): one-pole filters, pole `p = table[i]` at `0x4029BFFC` (Q31, 512 entries, 5 Hz × e^(0.0177·i) up to ~1 kHz, then warped). HPF `i = HPF>>6`, LPF `i = (HPF+LPF)>>6`.
- VOL (delay, reverb) and delay→reverb send: gain `(v/32768)²`.
- Reverb pre-delay: `(PRE² >> 16) + 37` samples, max 16384.

**The final mix is analog.** Digital buses go out through DACs (TDM, 8 slots, ring `0x80000000`) into the analog mixer; nothing digital sits after the master VCAs.

### Sends, returns and routing

- Per-track loop at `0x4008F21E` (t = 0–11, track struct `a3`): send targets = level/pan gain × (v/32768)² (DEL +118, REV +120), 0 if the track is muted (mask at `fp−508`). Ramp increments `(target − current) >> 5`, applied per sample.
- Summing routines `f(dst, src, gains, increments)`, 32 samples, `dst` step 8 B (one side of a stereo bus), EMAC *msac with load* (result = −Σ g·x): 10 ch `0x4008EF14`, 9 ch `0x4008EFAC`, 8 ch `0x4008F03E`, 6 ch `0x4008F0C6`, 4 ch `0x4008F13A`. Source channels at 128 B steps.
- Delay bus `0x8000DBD0` (digital + analog) → delay → `0x8000DCD0`. Reverb bus (tracks + delay→reverb) → reverb → `0x8000DDD0`.
- Returns are copied to channels 8/9 of the track buffer (`0x80004150`, `0x800041D0`) and summed with the tracks into **one** bus each: `0x8000DAD0` (direct) or `0x8000DFD0` (through the analog FX block) by their *FX Routing* flag (delay `a2+1782`, reverb `a2+1800`).
- Engine word **+106** (internal id 39, hidden param 72) is saved per track and unused by the OS: SND3 of [fx3](../mods/fx3).

### CPU load

- Everything above runs in the audio interrupt `0x400A3856` (`rte` at `0x400A54A8`), once per block. Free-running counter: DTIM0 `0xFC07000C`.
- Measured on the device (interrupt entry/exit with DTIM0): **~89 % of the CPU at rest**, sequencer stopped. The UI only gets what is left: a few % more per block is enough to make it lag.
- The DSPI wait at the start of the interrupt (`0x40102066`) is not idle time to reuse: the CV transfer (~500 frames of 16 bits at ~15.6 MHz, ~0.55 ms) starts early in the previous interrupt and is over before the next one.
- Reference costs per block (instructions, emulator): reverb ~8 200; our master compressor 100 off / ~2 000 on; fx3 ~40 idle, ~1 250 with one track sending, ~2 200 worst case.

## Track parameters, envelopes and filters

- Engine copy per track: `0x800021B0 + 142·t` (t = 0–11), word offset = **28 + 2 × internal id** (filter FREQ +84, ENV +88, amp ATK +108 … VOL +124). CPU #1 sends CPU #2 the shared block at `0x80002000` (0x1B0 B per interrupt).
- Track gain = velocity × (LEV × VOL)², VOL/LEV normalised to 127; sends (v/32768)²; pan constant-power (`0x400A171A`).
- Digital tracks: filter cutoff computed on CPU #1 (`0x400956BC`: FREQ + key track − env × ENV), filter and amp run on CPU #2. Biquad pole frequency f0 = 4.918 Hz · e^(0.065542·FREQ). BASE/WDTH use the delay pole table.
- Envelope tables (CPU #1 copies, 128 entries, index = value >> 8): filter env per block `0x401DEAC0` DEL (samples, max 3.0 s) / `0x401DEEC0` ATK / `0x401DECC0` DEC-REL; amp per sample `0x401DADDC` ATK (max 30 s) / `0x401DA9DC` HOLD (max 10 s) / `0x401DABDC` DEC-REL.
- Analog voices and the FX track drive a **hardware envelope generator** with 20-bit rate codes (amp: `0x401DC3E0`, `0x401DBFE0`, `0x401DC1E0`; FX filter: `0x401DE254`, `0x401DE054`). Measured: amp times ≈ digital × 1.05–1.52.
- Analog filter (tracks 9–12, FX track), measured from the resonance peak: f ≈ 14.645 Hz · e^(0.05741·FREQ).
- Tempo: `0x402D7010` = BPM × 120. Delay TIME = (TIME + 256)/1024 × 48000 × 900 / tempo samples (128 = one bar).

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
