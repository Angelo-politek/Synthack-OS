# modarea

Gives mods **64 KB of RAM** at `0x46000000`, loaded compressed.

The OS image has only ~2 KB of free space, and everything after it is zeroed at boot. So larger mods are appended to section 3 (patch entries with `"append": true`, at `0x40348000 + offset`). The build compresses that area (SHLZ, `tools/build/lz.py`) and this 138-byte loader unpacks it to `0x46000000` right before the OS clears its BSS, then zeroes the rest of the 64 KB.

- Compressed, the mods barely touch the bootstrap's [decompression margin](../../docs/firmware-format.md#boot-decompression-limit-%EF%B8%8F) (v0.8.0: 18 KB left).
- Hook: `jmp` at the start of `0x400004B2` (BSS clear, called once at boot), original instructions replayed. Cost: ~0.1 M instructions.
- Destination: RAM between end of BSS and the boot stack, never referenced by the OS.
- Mods using it declare `"requires": ["modarea"]` and link their code at `0x46000000 + offset`.

SHLZ: `"SHLZ"`, unpacked length, stream length, then tokens `0xxxxxxx` (x+1 literals) or `1lllllll hi lo` (copy l+3 bytes from distance hi·256+lo).

Test: `tests/test_modarea.py` (boot hook in emulation on the real build: RAM equals the uncompressed area), `tests/test_lz.py`.
