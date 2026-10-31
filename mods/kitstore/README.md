# kitstore

36 words for mods, **saved with the kit**. They follow pattern changes, kit copy/paste and FUNC+YES/NO like any kit parameter.

| Item | Value |
|---|---|
| Kit blocks | 12 per-track blocks of 148 bytes at `kit + 0xE5C + 148·t`: Digitakt MIDI-track data, 71 words each |
| OS writer / reader | `0x400A6EE6` / `0x400A6E7A`: words 0–40 (MIDI parameters, internal ids 17–40) |
| Unused words | 41–70: never saved, read back or used; only copied to `0x444B5B48` |
| Free file bytes | `+150…+155` of each block: zeroed by the writer, ignored by the reader |
| Ours | words 41–43 of each block (RAM `+82…+87`) → those 6 file bytes |
| Slices | `tools/build/kitstore_layout.py` |
| Test | `tests/test_kitstore.py` |

- New kits, and kits from the stock OS or older versions, load these words as zero. Zero must mean "default".
- The test runs the real writer and reader with and without the hooks: same file and block as stock apart from our words; our words round-trip; old kits load zeros; failures pass through.
