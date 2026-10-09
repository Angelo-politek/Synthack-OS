# dual-mono

With **SETTINGS → AUDIO ROUTING → EXTERNAL IN = mono**, the two inputs get independent levels.

- External Mixer page: `IN L · IN R · – · –` / `DEL · REV · – · FX` (sends stay shared).
- In stereo mode everything is **identical to stock** (verified bit-for-bit in emulation).

## How it works

- Two hooks around the **original** external-input block of the gain function (`0x40090872–0x400908FC`); no Elektron code is copied.
- Stereo: the block runs once, unchanged. Mono (`0x80003146` = 0): it runs twice with the balance centred — pass 1 with IN LR (→ left VCA), pass 2 with BAL (→ right VCA) — then the original parameters are restored.
- IN R is the hidden alias 125 turned into a BAL alias (internal id + two jump-table entries), so it draws as a bar. Long/short names switch to *Input Left/Right*, *IN L/IN R* and back.
- Code at `0x40338BE0` (free fill). Per-input pan isn't possible: the input has only two VCAs.

Test: `tests/test_dual_mono.py`.
