# syn-pages

SYN pages of its own for a machine: more than one page, its own page names, its own drawing. Used by [sy-fm4](../sy-fm4) and [sampler](../sampler). No change for the other machines.

## How it works

| Part | Detail |
|---|---|
| SRC view | Three slots of SourcePageView's vtable (`0x401CA37C`) point to `synpages.c`: 47 knob → descriptor, 19 page name, 4 draw. |
| Pages | The page key already cycles the view's page list (`+0x90` = index). For a machine with two pages the list gets a second entry. |
| Page name | Slot 19 returns a `std::string` by value: built at the address in `a0` with the OS's constructor (`0x401BF31E`). |
| Machines | A table of 4 entries at the start of the blob (`tools/build/synpages_layout.py`). A machine writes its entry from the mod area's boot list (`sp_register` in `synpages.h`): the descriptor of knob A on its stock page as the key, the page count, and its callbacks. |
| Drawing | `synpages.h` has pixel and line helpers for the screen bitmap. Knob graphics get `x`, `y` from the bottom of the screen. |

## Test

`tests/test_sy_fm4.py`, `tests/test_sampler.py`: pages, descriptors, page names and drawing of each machine on the main CPU emulator; the stock name for the other machines.
