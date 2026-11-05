| SPDX-License-Identifier: GPL-2.0-or-later
| Drain stores, then invalidate the I-cache and branch cache with the native
| MAIN CACR value (as fast-main-st), after the render kernel is copied to SRAM.
| No RAMBAR, vector or D-cache change.
        .text
        .globl lfo3_sync
lfo3_sync:
        nop
        move.l #0xa40ce100,%d0
        movec %d0,%cacr
        rts
