# modarea

**256 KB of RAM** for mod code (64 KB until 2026-11-04, 128 KB until 2026-11-05). Stored compressed. Unpacked at boot into a block of the OS heap that nothing else gets.

| Item | Value |
|---|---|
| Why | The OS image has ~2 KB of free space. Everything after it is zeroed at boot. |
| Image | appended to section 3 at `0x40349000 + offset` (`"append": true`), compressed by the build (SHLZ, `tools/build/lz.py`) |
| RAM | first 256 KB block of the OS heap (buddy allocator `0x401036D0`, 16 MB pool at `0x444E48C0`), from `+0x10` |
| Layout | `tools/build/modarea_layout.py` |
| Boot hook | `jmp` at the start of `0x400004B2` (BSS clear, called once) |
| Reservation hook | `jsr` at the end of the heap initialization (`0x40103752`) |
| Cost | 256 KB of the 16 MB heap. Boot time unchanged. After boot with a new project (emulator): largest free block 8 MB, 13.3 MB free in all. |
| Tests | `tests/test_modarea.py`, `tests/test_lz.py` (SHLZ) |

Boot:

1. The loader unpacks the area and zeroes the rest of it.
2. It zeroes the BSS **around** the area and returns.

Reservation:

1. Before any other request, the loader asks the allocator for 256 KB. It always gets index 0.
2. The heap lock is recursive. From then on the OS never hands that block out.
3. The heap initialization writes 12 bytes at the block start: the area starts at `+0x10`.

Use: declare `"requires": ["modarea"]`, link at `modarea_layout.RAM + offset`, claim the offset in `tools/build/registry.py`.

SHLZ format: `"SHLZ"`, unpacked length, stream length, then tokens `0xxxxxxx` (x+1 literals) or `1lllllll hi lo` (copy l+3 bytes from distance hi·256+lo).

Tests: boot on the real build (area equals the uncompressed patches, whole BSS zero around it, registers and return); real allocator (reservation at index 0; 1,500 random allocations and frees never inside or writing to the area; 8 MB still available).

`[!]` Up to v0.8.1 the area was at `0x46000000`, above the BSS. No code references that RAM, but the OS writes over it when it loads samples ([#4](https://github.com/Angelo-politek/Synthack-OS/issues/4)).
