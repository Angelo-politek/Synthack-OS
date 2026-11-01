# sy-fm4

SY TONE becomes a 4-operator FM machine. By **Rxuting** ([Rxuting/sy-fm4](https://github.com/Rxuting/sy-fm4), MIT, see `LICENSE`). Ported to OS 1.42 for SyntHack.

## Use

1. Pick **SY FM4** as the machine of a digital track (it replaces SY TONE in the list).
2. **SYN 1/2**: SY TONE's page, unchanged: `TUNE RATIO PNCH DEC` / `FDBK MOD MENV OVER`.
3. Press **SYN** again for **SYN 2/2**: `ALGO RAT3 LEV3 DEC3` / `DET RAT4 LEV4 DEC4`.

| Control | Values |
|---|---|
| `ALGO` | 0 = SY TONE (same sound), 1–8 classic 4-operator set, 9 tree, 10 diamond, 11 ring |
| `RAT3`, `RAT4` | ratio of operators 3 and 4 (SY TONE's RATIO table) |
| `LEV3`, `LEV4` | level of operators 3 and 4 |
| `DEC3`, `DEC4` | decay of operators 3 and 4 |
| `DET` | detune of operators 2–4, ±16 semitones, fine steps |

- Page 2/2 is saved with the sound and p-lockable.
- Sounds and projects from SY TONE open as SY FM4, ALGO 0: they sound the same.

`[!]` A project with page 2/2 p-locks opened on a stock OS loses those locks.

`[!]` Page 2/2 has no MIDI CC.

## How it works

| Part | Detail |
|---|---|
| CPU #2 | `engine/syn`, `engine/fm4.c`. Engine 4 (SY TONE) prep/render → SY FM4, in the [modarea7](../modarea7) engine area. SY TONE's prep always runs; ALGO 0 is SY TONE's render. Section 7 is the same in 1.40A, 1.41 and 1.42. |
| CPU #1 | `engine/main/main_fm4.c`, mod area `+0x8180`. SourcePageView slots 47/19: two pages for machine 4. |
| Parameters | Descriptors 254–261 (Digitakt MIDI-track "CC1–CC8 Value", no page on the Syntakt), logical indices `0x36–0x3D`. The original uses the MIDI CC placeholders 1–5 and 12–14: on 1.42 they carry CC 1, 2, 6, 7, 10, 120, 121, 123. |
| Storage | Sound slots `0x36–0x3D` (72 slots, 54 used). P-lock lanes `0x50–0x57`. Tables filled by `fm4m_boot` from the mod area boot list. |
| To CPU #2 | `fm4m_dma_wait` replaces the render's eDMA 47 wait and copies page 2/2 (locks applied) to shared RAM `0x700`. |
| Port | Addresses moved with `tools/build/osmap.py`. With the 1.40A addresses put back, every patched site has the hash of the original patcher (`tests/test_sy_fm4.py`). |

## Test

`tests/test_sy_fm4.py`: sites against the original patcher's hashes; page 2/2 descriptors; boot list fills the storage tables on the real build; on the section 7 emulator (cold boot of the real compressed build) ALGO 0 equals stock SY TONE sample by sample, ALGO 1–11 sound and differ, SP TWINSHOT unchanged.

Original tests by Rxuting on 1.40A hardware: install, every parameter, p-locks, 8 voices for 47 s recorded clean. On 1.42 hardware: `[wip]`, not tested yet.
