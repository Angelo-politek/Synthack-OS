# modarea

Gives mods **32 KB of RAM** at `0x46000000`.

The OS image has only ~2 KB of free space, and everything after it is zeroed at boot. So larger mods are appended to section 3 (from `0x40348000`, patch entries with `"append": true`) and this 42-byte loader copies them to `0x46000000` right before the OS clears its BSS.

- Hook: `jmp` at the start of `0x400004B2` (BSS clear, called once at boot), original instructions replayed.
- Destination: RAM between end of BSS and the boot stack, never referenced by the OS.
- Mods using it declare `"requires": ["modarea"]` and link their code at `0x46000000 + offset`.

Test: `tests/test_modarea.py` (boot hook in emulation, section grows only by the mod area).
