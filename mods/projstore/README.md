# projstore

256 bytes for mods, **saved with the project**. Same value on every pattern. Kept across power cycles and project reloads.

| Item | Value |
|---|---|
| Writer / reader | `0x400A9134` / `0x400A84F0`, 1024-byte project settings block |
| Free bytes | `+0x227…+0x3FF`: zeroed by the writer, ignored by the reader |
| Our data | marker (`SH`, version, length) at `+0x228`, then the bytes |
| RAM | `ps_data`, mod area `+0x7000` |
| Slices | `tools/build/projstore_layout.py` |
| Test | `tests/test_projstore.py` |

- Two hooks, one at the start of each function. The OS fields are untouched.
- Projects from the stock OS or older versions have no marker. The bytes load as zero: zero must mean "default".
- The test runs the real writer and reader with and without the hooks: same block and settings as stock apart from our bytes; our bytes round-trip; old projects load zeros; failures pass through.
