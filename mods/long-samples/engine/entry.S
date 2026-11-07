| SPDX-License-Identifier: GPL-2.0-or-later
| long-samples on the voice CPU: at the end of the audio interrupt (0x40000b04, Synfact's audio_machine_exit site),
| the runtime receiver (rx.c), then the instruction it replaces: tst.l 0x40040050 (its flags go to the beq after).
        .text
        .globl ls_rx_exit
ls_rx_exit:
        move.l 0x800,%d0                    | 'LSRX': nothing to do otherwise (a few instructions a block); d0-d1,
        cmpi.l #0x4C535258,%d0              | a0-a1: the interrupt restores them after (0x40000b16)
        bne.s 1f
        jsr ls_rx
1:      tst.l 0x40040050
        rts
