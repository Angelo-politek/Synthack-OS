# projstore

256 bytes for mods, **saved with the project**: the same value on every pattern, kept across power cycles and project reloads.

- **Where in the file:** the project settings are written by `0x400A90BC` into a 1024-byte block and read back by `0x400A8478`. The writer zeroes bytes `+0x227…+0x3FF` and the reader ignores them. projstore puts a marker (`SH`, version, length) at `+0x228` followed by its bytes.
- **In RAM:** `ps_data`, in the mod area (offset `+0x7000`). Each mod gets its own slice, listed in `tools/build/projstore_layout.py`.
- **Projects saved by the stock OS or older versions** have no marker: the bytes load as zero, so zero must mean "default".
- Two hooks, one at the start of each function. The OS fields are untouched.

Test: `tests/test_projstore.py`. It runs the real writer and reader with and without the hooks: same block and same settings as the stock OS apart from our bytes, our bytes round-trip, old projects load zeros, failures pass through.
