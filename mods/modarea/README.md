# modarea

Gives mods **64 KB of RAM**, loaded compressed, in a block of the OS heap that nobody else can get.

The OS image has only ~2 KB of free space, and everything after it is zeroed at boot. So larger mods are appended to section 3 (patch entries with `"append": true`, at `0x40348000 + offset`). The build compresses that area (SHLZ, `tools/build/lz.py`).

- **Where:** the first 64 KB block of the OS heap (buddy allocator `0x4010350C`, 16 MB pool at `0x444E38C0`), from `+0x10` (the heap initialization writes 12 bytes at its start). Addresses in `tools/build/modarea_layout.py`.
- **Boot:** `jmp` at the start of `0x400004B2` (BSS clear, called once): the loader unpacks the area, zeroes the rest of it, then zeroes the BSS **around** it and returns.
- **Reservation:** `jsr` at the end of the heap initialization (`0x4010358E`): before any other request the loader asks the allocator for 64 KB and always gets index 0. The heap lock is recursive. From then on the OS never hands that block out.
- **Why not above the BSS** (v0.8.1 and earlier, `0x46000000`): that RAM has no code or data reference, but the OS writes all over it at runtime when it loads samples ([#4](https://github.com/Angelo-politek/Synthack-OS/issues/4)).
- Cost: 64 KB of the 16 MB heap; boot time unchanged.
- Mods using it declare `"requires": ["modarea"]` and link their code at `modarea_layout.RAM + offset`.

SHLZ: `"SHLZ"`, unpacked length, stream length, then tokens `0xxxxxxx` (x+1 literals) or `1lllllll hi lo` (copy l+3 bytes from distance hi·256+lo).

Test: `tests/test_modarea.py`. It covers boot on the real build (area equals the uncompressed patches, whole BSS zero around it, registers and return), and the real allocator: reservation at index 0, 1 500 random allocations and frees never inside or writing to the area, 8 MB still available. `tests/test_lz.py` covers SHLZ.
