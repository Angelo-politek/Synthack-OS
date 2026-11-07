# poly

Synfact's POLY ([poly-st](https://github.com/GSM1980/synfact-dev), GPL-2.0-or-later) on OS 1.42, as an [sfcore](../sfcore) module.

## Use

Third TRIG page of a digital track (and of track 9 or 10): **A POLY, B VOICES, C PLAY, E NOTE, F/G/H NOT2–NOT4**.

| Item | Detail |
|---|---|
| VOICES | 2, 3 or 4 contiguous tracks: the first is the master, the others are slaves (TRACK IN / SLAVE MODE) |
| PLAY | POLY: one held key per voice, LFOs per voice. M.LFO: the master's modulation on every voice |
| Notes | keyboard and MIDI allocate one voice per held note (oldest stolen); trigs and held steps play the chord |
| Saved | with the pattern (7 bytes of PatternSettings) |

Groups never cross the digital/analog boundary (tracks 8/9); tracks 11 and 12 cannot be masters.

## SyntHack changes

| Synfact | Here |
|---|---|
| SMZ module | sfcore module, page services `sfcore:pages` |
| page layout hook at `0x4007BA48` | [idspace](../idspace) owns that site and asks sfcore first (hook slot), for page 3 only |

Cost per audio block (emulator): off ~0, POLY ~0, M.LFO +482 instructions.

## Test

`tests/test_poly.py`.
