# Memory map (CPU #1, section 3)

Two **ColdFire MCF5441x** (V4, EMAC, no FPU, ~250 MHz). 64 KB internal SRAM at `0x80000000`.

| Range | What |
|---|---|
| `0x40000400–0x40347B90` | section 3 image (code, data) |
| `0x40338740–0x40339000` | linker fill, **free** (used by splash, dual-mono, mod-area loader) |
| `0x40339000–0x40347B90` | initial SRAM content, copied at boot |
| `0x40339000–0x45565490` | BSS, **zeroed at boot** |
| `0x444E38C0–0x454E38C0` | OS heap (buddy allocator `0x4010350C`, free `0x40103712`, 16 MB, 16-byte units); first 64 KB block = **mod area** |
| `0x45565490–0x48000000` | no code or data reference, **but used at runtime** (sample loading writes all over it, #4) |
| `0x48000000` | boot stack top |
| `0x4D570000…`, `0x4FC00000…` | delay / reverb lines |
| `0x80000000–0x8000FFFF` | SRAM: audio buffers, DMA rings, engine parameter arrays |
| `0x10000000` | RAM shared with CPU #2 |

## Boot

- `0x400004E8` entry. `0x4000045C` copies SRAM data, `0x400004B2` zeroes BSS (called once, from `0x40000542`). Caches are enabled after.
- Intro animation task `0x40087E6A` (~28 fps). The rest of boot waits for it: **don't make it longer**.
- Static constructors: loop `0x40082500`, count at `0x4033850C` (136), entries from `0x40338510`.
- Mods never add boot time: they set up from their hooks, or from a stub inside the OS page initializer (`0x401885D2…`, one of the static constructors).

## Mod area

Mods larger than the free fill are **appended to section 3** at `0x40348000`, compressed (SHLZ), and linked at `0x444E38D0` (`tools/build/modarea_layout.py`): the first 64 KB block of the OS heap, + 0x10. A loader replacing the BSS clear (`0x400004B2`) unpacks them and zeroes the BSS around the area; a hook at the end of the heap initialization (`0x4010358E`) asks the allocator for 64 KB before any other request, so the OS never hands that block out. Up to v0.8.1 the area was at `0x46000000`, above the BSS: RAM with no static reference that the OS still uses at runtime. See [mods/modarea](../mods/modarea); offsets in use: [modding guide](modding-guide.md#1-workflow).

## Screen

- 128×64, 1 bpp, double buffer; pointers at `0x402D6DC4` / `0x402D6DC0`.
- Bitmap is column-major: `byte = fb[x*8 + y/8]`, `bit = 7 - (y % 8)`, 1 = on.
- Frame loop `0x4000A0E6`: redraws only if the ViewController's dirty byte is set — `*(0x444E1334) + 96`.
