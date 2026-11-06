# idspace

Parameter ids above 504 for the mods. The OS has 505 parameter ids, and every one of them belongs to an OS parameter, even the hidden ones: the MIDI machine's pages use 246–269, for example. A mod that needs its own parameters takes ids from 505 on.

## How it works

| Part | Detail |
|---|---|
| Descriptors | At boot (modarea's boot list, before the static constructors) the OS's 505 descriptors (`0x4022D83C`, 52 B) are copied to a table of 537 in the mod area, followed by the mods' own. Every OS reference to the table (68) points to the copy. |
| Bounds | The OS maps an id ≥ 505 to id 0 before each access (`cmpi.l #0x1F9` / `#0x1F8`, 61 sites): raised to 537. The three boot loops that build the reverse maps (group/internal id → id, MIDI CC) stay at 505: the mods' ids never receive MIDI CCs. |
| Parameter objects | The two lookups (`0x4007BA2A` object, `0x4007BBE2` text) go through idspace. A mod's object is built at the first lookup from a template id, with the mod's std::function prototypes for text (+20), graphic (+36) and style (+68). |
| Pages | Page indices 37–40 are the mods' (`0x4007BA48`). |
| Memory | Mod area: code and the mods' definitions at `+0x3E000`, descriptor table and objects at `+0x40000` (runtime RAM). |

A mod writes, with appended patches: its descriptors, object definitions and pages at the addresses of [tools/build/idspace_layout.py](../../tools/build/idspace_layout.py). Kit or virtual values still go through [vparams](../vparams).

## Test

`tests/test_idspace.py`: stock pages drawn the same with idspace (12 tabs), descriptor copy, bounds, objects, pages.
