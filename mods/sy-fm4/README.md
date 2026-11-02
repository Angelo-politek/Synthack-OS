# sy-fm4

SY TONE becomes a 4-operator FM machine. By **Rxuting** ([Rxuting/sy-fm4](https://github.com/Rxuting/sy-fm4), MIT, see `LICENSE`). Ported to OS 1.42 for SyntHack.

## Use

1. Pick **SY FM4** as the machine of a digital track (it replaces SY TONE in the list).
2. **SYN 1/3**: SY TONE's parameters as FM controls: `TUNE RAT2 LEV2 DEC2` / `PNCH FDBK OVER DEC1`.
3. Press **SYN** again for **SYN 2/3**: `RAT3 LEV3 DEC3` / `DET RAT4 LEV4 DEC4`.
4. **SYN 3/3**: `ALGO` on knob A, its number in the box; the algorithm drawn on the right.

On pages 1/3 and 2/3 a column is one kind: ratio, level, decay. Operator 1 is the carrier, operator 2 SY TONE's modulator.

| Control | Values |
|---|---|
| `RAT2`, `LEV2`, `DEC2` | operator 2: SY TONE's RATIO, MOD, MENV |
| `DEC1` | operator 1 (carrier): SY TONE's DEC |
| `FDBK`, `PNCH`, `OVER`, `TUNE` | as on SY TONE |
| `ALGO` | 0 = SY TONE (same sound), 1–8 classic 4-operator set, 9 tree, 10 diamond, 11 ring |
| `RAT3`, `RAT4` | ratio of operators 3 and 4 (SY TONE's RATIO table) |
| `LEV3`, `LEV4` | level of operators 3 and 4 |
| `DEC3`, `DEC4` | decay of operators 3 and 4 |
| `DET` | detune of operators 2–4, ±16 semitones, fine steps |

- Pages 2/3 and 3/3 are saved with the sound and p-lockable.
- The algorithm drawing: operators in boxes, modulation as lines, carriers dotted up to the output, feedback as a loop on the right of operator 4 (ALGO 11: the ring back from 1 to 4). Our drawings, in the style of the Digitone's.
- Sounds and projects from SY TONE open as SY FM4, ALGO 0: they sound the same.

`[!]` A project with p-locks of pages 2/3 and 3/3 opened on a stock OS loses those locks.

`[!]` Pages 2/3 and 3/3 have no MIDI CC.

## How it works

| Part | Detail |
|---|---|
| CPU #2 | `engine/syn`, `engine/fm4.c`. Engine 4 (SY TONE) prep/render → SY FM4, in the [modarea7](../modarea7) engine area. SY TONE's prep always runs; ALGO 0 is SY TONE's render. Section 7 is the same in 1.40A, 1.41 and 1.42. |
| CPU #1 | `engine/main/main_fm4.c`, mod area `+0x5800`. Three pages for machine 4 through [syn-pages](../syn-pages); descriptors 190–197 renamed; the algorithm drawn on page 3/3 under row 13 (above it the OS writes a turned value); turning `ALGO` leaves its name under the box (knob A not highlighted). |
| Parameters | Descriptors 254–261 (Digitakt MIDI-track "CC1–CC8 Value", no page on the Syntakt), logical indices `0x36–0x3D`. The original uses the MIDI CC placeholders 1–5 and 12–14: on 1.42 they carry CC 1, 2, 6, 7, 10, 120, 121, 123. |
| Storage | Sound slots `0x36–0x3D` (72 slots, 54 used). P-lock lanes `0x50–0x57`. Tables filled by `fm4m_boot` from the mod area boot list. |
| To CPU #2 | `fm4m_dma_wait` replaces the render's eDMA 47 wait and copies the eight parameters of pages 2/3 and 3/3 (locks applied) to shared RAM `0x700`. |
| Port | Addresses moved with `tools/build/osmap.py`. With the 1.40A addresses put back, every patched site has the hash of the original patcher (`tests/test_sy_fm4.py`). |

## Test

`tests/test_sy_fm4.py`: sites against the original patcher's hashes; descriptors 254–261; the three pages, names and the 12 algorithm drawings on the main CPU emulator; boot list fills the storage tables on the real build; on the section 7 emulator (cold boot of the real compressed build) ALGO 0 equals stock SY TONE sample by sample, ALGO 1–11 sound and differ, SP TWINSHOT unchanged.

Original tests by Rxuting on 1.40A hardware: install, every parameter, p-locks, 8 voices for 47 s recorded clean. On 1.42 hardware: `[wip]`, not tested yet.
