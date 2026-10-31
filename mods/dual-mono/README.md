# dual-mono

**SETTINGS → AUDIO ROUTING → EXTERNAL IN = mono**: the two inputs become two separate mono inputs.

## Use

| Page | Knobs (top / bottom row) | Saved |
|---|---|---|
| MIXER page 3, External Mixer = IN L | `IN L · – · – · –` / `DEL · REV · FX3 · FX` | kit |
| MIXER page 4, IN R (mono only) | `IN R · – · – · –` / `DEL · REV · FX3 · –` | kit: [kitstore](../kitstore), block 0 |

- Each input reaches delay, reverb, FX3 and the FX track (ROUTING: FUNC+FX, trig 16) centered, with its own level and sends.
- FX3 sits next to REV on both pages. In stereo it returns to knob C, with BAL in G.
- In stereo everything is **identical to stock** (verified in emulation). The MIXER tab has 3 pages.

`[!]` Kits from older versions start with the IN R sends at 0.

`[!]` A MIDI CC for the input DEL/REV received while the IN R page is open goes to IN R.

## How it works

| Part | Detail |
|---|---|
| Analog levels | `dualmono.S`, section 3 free fill. Two hooks around the external-input block of the gain function (`0x400908EA–0x40090974`). Mono (`0x80003146` = 0): the block runs twice with the balance centered: pass 1 with IN LR (left VCA), pass 2 with BAL (right VCA). |
| IN R parameter | Hidden alias 125 turned into a BAL alias (internal id + two jump-table entries), drawn as a bar. Names switch to *IN L / IN R*. |
| Sends | `dualmono2.c`, mod area `+0x5000`. Same trick on the input-send block of the mix function (`0x4008F4F0–0x4008F66A`). Pass 1: IN L, centered, IN L DEL/REV, channel 12 (ADC 4). Pass 2: IN R, centered, R sends, channel 13 (ADC 5). Same volume law as the OS. |
| IN R page | Page 27 (Digitakt "MIDI Source", never shown on the Syntakt). MIXER page list `{22, 23, 24, 27}`. The view holds 4 pages in mono, 3 in stereo; updated when the view is built (`0x40035914`) and when the setting reaches the engine (`0x400A347C`). |
| Shared ids | No free ids left: DEL 129, REV 130 and FX3 269 are on both pages. 129/130 go through [vparams](../vparams): while IN R is the current MIXER page they read and write the R sends; otherwise the OS code runs. fx3 does the same for 269 and uses FX3 R in audio pass 2. Pass and page are in the header at `+0x5000`. |

`[!]` Stock mono sums the inputs and pans them with BAL. With dual-mono v1, IN R moved the balance of the sends.

## Test

- `tests/test_dual_mono.py`: analog levels.
- `tests/test_dual_mono_v2.py`: the OS send block in the emulator. Each channel equals the stock block with that input's level and sends; stereo identical; FX3 per side; tab size; page-aware get/set; page slots.
