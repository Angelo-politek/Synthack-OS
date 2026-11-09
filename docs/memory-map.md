# Memory map (CPU #1, section 3)

Two **ColdFire MCF5441x** (V4, EMAC, no FPU, ~250 MHz). 64 KB internal SRAM at `0x80000000`. Addresses: OS 1.42.

| Range | What |
|---|---|
| `0x40000400–0x40348B90` | section 3 image (code, data) |
| `0x40339740–0x4033A000` | linker fill, **free** (used by splash, dual-mono, mod-area loader) |
| `0x4033A000–0x40348B90` | initial SRAM content, copied at boot |
| `0x4033A000–0x45566490` | BSS, **zeroed at boot** |
| `0x444E48C0–0x454E48C0` | OS heap (buddy allocator `0x401036D0`, free `0x401038D6`, 16 MB, 16-byte units); first 512 KB block = **mod area** |
| `0x45566490–0x48000000` | no code or data reference, **but used at runtime** (sample loading writes all over it, #4) |
| `0x48000000` | boot stack top |
| `0x4D570000…`, `0x4FC00000…` | delay / reverb lines |
| `0x80000000–0x8000FFFF` | SRAM: audio buffers, DMA rings, engine parameter arrays |
| `0x10000000` | RAM shared with CPU #2, see [below](#shared-ram) |

## Boot

- `0x400004E8` entry. `0x4000045C` copies SRAM data, `0x400004B2` zeroes BSS (called once, from `0x40000542`). Caches are enabled after.
- Intro animation task `0x40087EE2` (~28 fps). The rest of boot waits for it: **don't make it longer**.
- Static constructors: loop `0x40082578`, count at `0x4033950C` (136), entries from `0x40339510`.
- Mods never add boot time: they set up from their hooks, or from a stub inside the OS page initializer (`0x40188796…`, one of the static constructors).

## Mod area

Mods larger than the free fill are **appended to section 3** at `0x40349000`, compressed (SHLZ, whitened), and linked at `0x444E48D0` (`tools/build/modarea_layout.py`): the first 512 KB block of the OS heap, + 0x10. A loader replacing the BSS clear (`0x400004B2`) unpacks them and zeroes the BSS around the area; a hook at the end of the heap initialization (`0x40103752`) asks the allocator for 512 KB before any other request, so the OS never hands that block out. Up to v0.8.1 the area was at `0x46000000`, above the BSS: RAM with no static reference that the OS still uses at runtime. See [mods/modarea](../mods/modarea); offsets in use: [registry](registry.md).

**Boot list**: 8 function pointers at mod area `+0x7400`. After unpacking and the BSS clear, the loader calls each non-zero one: C functions without arguments, caches off, boot stack, before the static constructors. A mod fills its slot with an appended patch at `IMG + 0x7400 + 4 × slot` (`modarea_layout.boot_slot`); slots are claimed in `BOOT_SLOTS` of `tools/build/registry.py`, or `"boot_slot"` in a new mod's `claims.json`. sy-fm4 fills its storage tables there; both machines register their SYN pages with [syn-pages](../mods/syn-pages). Keep these functions short: they run on every boot.

## Shared RAM

RAM seen by both CPUs: CPU #1 at `0x10000000 + offset`, CPU #2 at `offset`. Claims and the full map: [registry](registry.md#shared-ram-cpu-1-at-0x10000000--offset-cpu-2-at-offset).

| Offset | Owner | Content |
|---|---|---|
| `0x000–0x1B0` | OS | voice frames: CPU #1 copies `0x1B0` B from `0x80002000` every block (eDMA ch. 47, started at `0x400A4E44`) |
| `0x1B0–0x5B0` | OS | voice output: 8 × 32 × int32 |
| `0x5B0–0x630` | sampler | waveform: `+0x5B0` slot + 1 asked by CPU #1, `+0x5B4` slot + 1 being drawn, `+0x5B6` columns done (of 112), `+0x5B8` length, `+0x5BC` address, `+0x5C0` 112 peaks 0–127 |
| `0x700–0x780` | xparams | extra parameters of each digital track (sy-fm4 pages 2/3 and 3/3, sampler knob H), 8 words per track, locks applied; written by CPU #1 before each frame transfer, from a hook on the eDMA 47 wait (`0x400A20AE`) |
| `0x7F0–0x7F4` | sampler | tempo, BPM × 120, written by CPU #1 once per block |
| `0x800–0x1000` | OS | boot-time upload window |

## Screen

- 128×64, 1 bpp, double buffer; pointers at `0x402D7114` / `0x402D7110`.
- Bitmap is column-major: `byte = fb[x*8 + y/8]`, `bit = 7 - (y % 8)`, 1 = on.
- Frame loop `0x4000A0E6`: redraws only if the ViewController's dirty byte is set — `*(0x444E2334) + 96`.
