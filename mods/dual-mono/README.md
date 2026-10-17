# dual-mono

With **SETTINGS → AUDIO ROUTING → EXTERNAL IN = mono**, the two inputs become two separate mono inputs.

- **External Mixer** page = IN L: `IN L · – · – · –` / `DEL · REV · FX3 · FX`.
- **IN R** page (MIXER tab, 4th page, only in mono): `IN R · – · – · –` / `DEL · REV · FX3 · –`. FX3 sits next to the reverb on both pages; in stereo it goes back to slot C, with BAL in G. Its DEL, REV and FX3 are the sends of IN R, saved with the kit ([kitstore](../kitstore), block 0). Kits from older versions start with them at 0.
- Each input goes to the delay, the reverb, FX3 and the FX track (routing: FUNC+FX, trig 16) centred, with its own level and sends.
- In stereo everything is **identical to stock** (verified in emulation), and the MIXER tab has its 3 pages.

## How it works

- **Analog levels** (`dualmono.S`, section 3 free fill): two hooks around the original external-input block of the gain function (`0x40090872–0x400908FC`). Mono (`0x80003146` = 0): it runs twice with the balance centred, pass 1 with IN LR (left VCA), pass 2 with BAL (right VCA). IN R is the hidden alias 125 turned into a BAL alias (internal id + two jump-table entries), drawn as a bar; names switch to *IN L / IN R*.
- **Sends** (`dualmono2.c`, mod area `+0x5000`): the same trick on the input-send block of the mix function (`0x4008F478–0x4008F5F2`). Mono: pass 1 with IN L, centre, DEL/REV of IN L keeps channel 12 (ADC 4); pass 2 with IN R, centre and the R sends keeps channel 13 (ADC 5). Same volume law as the OS. Stock mono instead sums the inputs and pans them with BAL, so with v1 IN R moved the balance of the sends.
- **IN R page**: page 27 (Digitakt "MIDI Source", never shown on the Syntakt). The MIXER page list becomes `{22, 23, 24, 27}`; the view's vector holds 4 pages in mono and 3 in stereo, updated when the view is built (`0x40035914`) and when the setting reaches the engine (`0x400A3404`).
- **Same ids on both pages** (no free ids left): DEL 129, REV 130 and FX3 269 show their usual icons. 129/130 go through [vparams](../vparams); while the IN R page is the current MIXER page they read and write the R sends, otherwise the OS code runs. fx3 does the same for 269 and, in the audio pass 2, uses FX3 R: it reads pass and page from the header at `+0x5000`. A MIDI CC for the input DEL/REV received while the IN R page is open goes to IN R.

Test: `tests/test_dual_mono.py` (analog levels), `tests/test_dual_mono_v2.py` (the OS send block run in the emulator: each channel equals the stock block with that input's level and sends; stereo identical; FX3 per side; tab size; page-aware get/set; page slots).
