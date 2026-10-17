# kitstore

36 words for mods, **saved with the kit**: they follow pattern changes, kit copy/paste and FUNC+YES/NO like any kit parameter.

- **Where:** the kit has 12 per-track blocks of 148 bytes (`kit + 0xE5C + 148·t`). They hold the Digitakt MIDI-track data, 71 words each.
  - The OS saves words 0–40 (MIDI parameters, internal ids 17–40) with `0x400A6E6E` and reads them back with `0x400A6E02`.
  - Words 41–70 are never saved, read back or used: they are only copied to `0x444B4B48`.
  - In the file, bytes `+150…+155` of each block are zeroed by the writer and ignored by the reader.
- **What kitstore does:** words 41–43 of each block (RAM `+82…+87`) go into those 6 file bytes and come back on load. Slices per mod: `tools/build/kitstore_layout.py`.
- **Defaults:** new kits, and kits saved by the stock OS or older versions, load these words as zero. Zero must mean "default".

Test: `tests/test_kitstore.py`. It runs the real writer and reader with and without the hooks: same file and same block as the stock OS apart from our words, which round-trip; old kits load zeros; failures pass through.
