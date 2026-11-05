| SPDX-License-Identifier: GPL-2.0-or-later
| sfcore adapters, OS 1.42. From Synfact mods/core (core.s: tick, draw, key, enc), mods/core-st (accounting.s:
| render_in, sample-ui.s: main_mix, files.s: fs_write/fs_written, native.s and note-events.s: native transactions),
| GSM1980 and contributors, on elekloader by irpina. Addresses translated from 1.41 with tools/build/osmap.py and
| the stock bytes checked by make_patch.py (comments give the 1.41 site).
|
| Ours: where a SyntHack mod already owns Synfact's site, the adapter sits on the next instruction, so both run,
| the existing mod first (build.py refuses two patches on the same bytes):
|   key       KEYDISP entry 0x4000839E, not its call 0x4000B420 (perf-fx: pf_ev, then jmp 0x4000839E)
|   render_in 0x400A38D6, after the prologue 0x400A38CE (cpu-meter: its time includes the subscribers)
|   main_mix  0x4008FB86, after 0x4008FB7C (fx3's mix hook: subscribers see the bus after fx3)
|   fs_write  0x400B620C, after the prologue 0x400B6204 (long-samples: subscribers see the writes it declines)
|   machine   0x4002559C, after the prologue 0x40025594 (sampler: its front half runs, then the guard)
| Every adapter tests its list or interest byte first and replays the displaced stock instructions.

        .text
| ---- IRQ mask for the binder (C)
        .globl  sfcore_irq_off, sfcore_irq_on
sfcore_irq_off:
        moveq   #0,%d0
        move.w  %sr,%d0
        move.w  #0x2700,%sr
        rts
sfcore_irq_on:
        move.l  4(%sp),%d0
        move.w  %d0,%sr
        rts

| ---- ev_tick: 0x4000A220 (1.41 same), was jsr 0x4010095C (returns ctrl->dirty, byte +0x20). (sp) ret, 4(sp) ctrl.
| Handlers f(ctrl); one that wants the frame recomposed sets ctrl+0x20. The first tick binds the modules.
        .globl  core_tick
core_tick:
        tst.l   sfcore_bound
        bne.s   0f
        jsr     sfcore_bind
0:      move.l  %a2,-(%sp)
        lea     ev_tick,%a2
1:      move.l  (%a2)+,%d0
        beq.s   2f
        move.l  8(%sp),-(%sp)
        movea.l %d0,%a0
        jsr     (%a0)
        addq.l  #4,%sp
        bra.s   1b
2:      movea.l (%sp)+,%a2
        movea.l 4(%sp),%a0
        move.b  0x20(%a0),%d0
        rts

| ---- ev_draw: 0x4000A286 (1.41 same), was jsr 0x40100992 (drawAll(ctrl, bmp)). Handlers f(bmp, ctrl).
        .globl  core_draw
core_draw:
        move.l  8(%sp),-(%sp)
        move.l  8(%sp),-(%sp)
        jsr     0x40100992
        addq.l  #8,%sp
        move.l  %a2,-(%sp)
        lea     ev_draw,%a2
1:      move.l  (%a2)+,%d0
        beq.s   2f
        move.l  8(%sp),-(%sp)
        move.l  16(%sp),-(%sp)
        movea.l %d0,%a0
        jsr     (%a0)
        addq.l  #8,%sp
        bra.s   1b
2:      movea.l (%sp)+,%a2
        rts

| ---- ev_key: at KEYDISP 0x4000839E (Synfact: its call 0x4000B420), lea -16(sp),sp; movem.l d2-d3/a2-a3,(sp)
| moved here. (sp) ret, 4 brain, 8 event. Handlers f(brain, event) -> nonzero consumes (no stock after it).
        .globl  core_key
core_key:
        move.l  %a2,-(%sp)
        lea     ev_key,%a2
        bsr.s   dispatch
        movea.l (%sp)+,%a2
        tst.l   %d0
        bne.s   1f
        lea     -16(%sp),%sp
        movem.l %d2-%d3/%a2-%a3,(%sp)
        jmp     0x400083A6
1:      rts

| ---- ev_enc: 0x4000B468 (1.41 same), was jsr 0x400083F0 (ENCDISP). Same convention as ev_key.
        .globl  core_enc
core_enc:
        move.l  %a2,-(%sp)
        lea     ev_enc,%a2
        bsr.s   dispatch
        movea.l (%sp)+,%a2
        tst.l   %d0
        bne.s   1f
        jmp     0x400083F0
1:      rts

| a2 = list; 12(sp) brain, 16(sp) event -> d0 = the first nonzero result, or 0
dispatch:
1:      move.l  (%a2)+,%d0
        beq.s   2f
        move.l  16(%sp),-(%sp)
        move.l  16(%sp),-(%sp)
        movea.l %d0,%a0
        jsr     (%a0)
        addq.l  #8,%sp
        tst.l   %d0
        beq.s   1b
2:      rts

| ---- ev_render_in: 0x400A38D6 (Synfact 0x400A3856, the prologue), move.l #0x7FFFFFFF,d0 moved here. The audio
| interrupt has saved d0-a5 in its frame: handlers f(void) may use the C scratch registers; a2 is saved here.
        .globl  core_render_in
core_render_in:
        move.l  %a2,-(%sp)
        lea     ev_render_in,%a2
1:      move.l  (%a2)+,%d0
        beq.s   2f
        movea.l %d0,%a0
        jsr     (%a0)
        bra.s   1b
2:      movea.l (%sp)+,%a2
        move.l  #0x7FFFFFFF,%d0
        jmp     0x400A38DC

| ---- ev_main_mix: jsr at 0x4008FB86 (Synfact 0x4008FB04 in 1.41, the two instructions before), pea 0x80003950
| moved here: below the return address. Handlers f(void), MAIN audio IRQ, buses in SRAM.
        .globl  core_main_mix
core_main_mix:
        move.l  (%sp),-(%sp)                    | return, then the pushed operand under it
        lea     -20(%sp),%sp
        movem.l %d0-%d1/%a0-%a2,(%sp)
        move.l  #0x80003950,%d0
        move.l  %d0,24(%sp)
        lea     ev_main_mix,%a2
1:      move.l  (%a2)+,%d0
        beq.s   2f
        movea.l %d0,%a0
        jsr     (%a0)
        bra.s   1b
2:      movem.l (%sp),%d0-%d1/%a0-%a2
        lea     20(%sp),%sp
        rts

| ---- ev_fs_write: 0x400B620C (Synfact 0x400B618C, the prologue), after link a6,#-76; movem.l d2-d5/a2-a4,(sp).
| Handlers int f(router, FileInfo *info, Result<Writer> *out); out is the hidden A0 result. Nonzero: complete
| result, return it (d0 = out) through the stock epilogue. movea.l 12(a6),a3; move.l a6,d4 moved here.
        .globl  core_fs_write
core_fs_write:
        movea.l %a0,%a2                         | d2-d5/a2-a4 are saved and not yet set by the body
        lea     ev_fs_write,%a4
1:      move.l  (%a4)+,%d0
        beq.s   3f
        move.l  %a2,-(%sp)
        move.l  12(%a6),-(%sp)
        move.l  8(%a6),-(%sp)
        movea.l %d0,%a1
        jsr     (%a1)
        lea     12(%sp),%sp
        tst.l   %d0
        beq.s   1b
        move.l  %a2,%d0
        movem.l (%sp),%d2-%d5/%a2-%a4
        unlk    %a6
        rts
3:      movea.l %a2,%a0
        movea.l 12(%a6),%a3
        move.l  %a6,%d4
        jmp     0x400B6212

| ---- ev_fs_written: 0x4010BA9E (Synfact 0x4010B8DA), was jsr 0x4019C5CE (DataWriteClose completion).
| Handlers f(capture, header, Status *status = -88(a6)); status +0 success byte: only turn success into error.
        .globl  core_fs_written
core_fs_written:
        lea     -12(%sp),%sp
        movem.l %a2-%a4,(%sp)
        movea.l 16(%sp),%a2
        movea.l 20(%sp),%a3
        move.l  %a3,-(%sp)
        move.l  %a2,-(%sp)
        jsr     0x4019C5CE
        addq.l  #8,%sp
        lea     ev_fs_written,%a4
1:      move.l  (%a4)+,%d0
        beq.s   2f
        pea     -88(%a6)
        move.l  %a3,-(%sp)
        move.l  %a2,-(%sp)
        movea.l %d0,%a0
        jsr     (%a0)
        lea     12(%sp),%sp
        bra.s   1b
2:      movem.l (%sp),%a2-%a4
        lea     12(%sp),%sp
        rts

| ================= native transactions (Synfact native.s, note-events.s). Interest bytes: sfcore.c.
        .macro  ENTRY name,op
        .globl  core_native_\name,core_stock_\name
core_native_\name:
        tst.b   core_native_interest+\op
        beq.w   core_stock_\name
        lea     4(%sp),%a0
        move.l  %a0,-(%sp)
        pea     \op
        jsr     core_native
        addq.l  #8,%sp
        rts
core_stock_\name:
        .endm
| TRIG 0x4008B8FA (1.41 0x4008B882)
        ENTRY   trig,0
        lea     -56(%sp),%sp
        movem.l %d2-%d7/%a2-%a6,(%sp)
        jmp     0x4008B902
| ENQUEUE: jsr at 0x4008D03C (1.41 0x4008CFC4), was jsr 0x4011A80C
        ENTRY   enqueue,1
        jmp     0x4011A80C
| HEADER_LOAD 0x400A7A44 (1.41 0x400A79CC)
        ENTRY   header_load,5
        lea     -12(%sp),%sp
        movem.l %d2/%a2-%a3,(%sp)
        jmp     0x400A7A4C
| HEADER_RESET 0x400B3746 (1.41 0x400B36CE)
        ENTRY   header_reset,6
        movea.l 4(%sp),%a0
        tst.l   %a0
        jmp     0x400B374C

| PUBLISH 0x400A4B56 (1.41 0x400A4ADE): observe a2, then lea 0x80004688,a4; clr.l d5
        .globl  core_native_publish
core_native_publish:
        tst.b   core_native_interest+3
        beq.s   9f
        lea     -20(%sp),%sp
        movem.l %d0-%d1/%a0-%a1,(%sp)
        move.l  %a2,16(%sp)
        pea     16(%sp)
        pea     3
        jsr     core_native
        addq.l  #8,%sp
        movem.l (%sp),%d0-%d1/%a0-%a1
        lea     20(%sp),%sp
9:      lea     0x80004688,%a4
        clr.l   %d5
        jmp     0x400A4B5E

| IMMEDIATE 0x4011A8F8 (1.41 0x4011A734): event in d2. Stock: movea.l 0x444DF434,a2; tst.l a2
        .globl  core_native_immediate
core_native_immediate:
        tst.b   core_native_interest+2
        beq.s   8f
        lea     -16(%sp),%sp
        movem.l %d1/%a0-%a1,(%sp)
        move.l  %d2,12(%sp)
        pea     12(%sp)
        pea     2
        jsr     core_native
        addq.l  #8,%sp
        movem.l (%sp),%d1/%a0-%a1
        lea     16(%sp),%sp
        tst.l   %d0
        bne.s   1f
8:      movea.l 0x444DF434,%a2
        tst.l   %a2
        jmp     0x4011A900
1:      jmp     0x4011A944

| TYPE 0x400A4C46 (1.41 0x400A4BCE), SRC_TYPE 0x400A4D0E (1.41 0x400A4C96). Bytes 18/19: subscribed digital
| tracks / every cursor.
        .globl  core_native_type,core_native_src_type
core_native_type:
        tst.b   core_native_interest+4
        beq.s   7f
        tst.b   core_native_interest+19
        bne.s   8f
        move.l  %a1,%d0
        subi.l  #0x80002F50,%d0
        cmpi.l  #8,%d0
        bcc.s   7f
        btst    %d0,core_native_interest+18
        bne.s   8f
7:      .byte   0x71,0x19,0xe1,0x88,0x31,0x40,0x00,0x3e    | mvs.b (a1)+,d0; lsl.l #8,d0; move.w d0,62(a0)
        jmp     0x400A4C4E
8:      lea     -16(%sp),%sp
        movem.l %d1/%a0-%a1,(%sp)
        move.l  %a1,12(%sp)
        pea     12(%sp)
        pea     4
        jsr     core_native
        addq.l  #8,%sp
        movem.l (%sp),%d1/%a0-%a1
        lea     16(%sp),%sp
        lea     1(%a1),%a1
        lsl.l   #8,%d0
        move.w  %d0,62(%a0)
        jmp     0x400A4C4E
core_native_src_type:
        tst.b   core_native_interest+4
        beq.s   7f
        tst.b   core_native_interest+19
        bne.s   8f
        move.l  %a3,%d0
        subi.l  #0x80002F50-0xDA0,%d0
        cmpi.l  #8,%d0
        bcc.s   7f
        btst    %d0,core_native_interest+18
        bne.s   8f
7:      .byte   0x71,0x2b,0x0d,0xa0,0x72,0x25,0xb2,0x80    | mvs.b 3488(a3),d0; moveq #37,d1; cmp.l d0,d1
        jmp     0x400A4D16
8:      lea     -16(%sp),%sp
        movem.l %d1/%a0-%a1,(%sp)
        lea     0xDA0(%a3),%a0
        move.l  %a0,12(%sp)
        pea     12(%sp)
        pea     4
        jsr     core_native
        addq.l  #8,%sp
        movem.l (%sp),%d1/%a0-%a1
        lea     16(%sp),%sp
        moveq   #0x25,%d1
        cmp.l   %d0,%d1
        jmp     0x400A4D16

| SOUND_ALLOWED 0x40013304 (1.41 same); stores of the LFO3 engine IDs 0x3D9..0x3F8 go to the parameter provider
| (query 24, original arguments; nonzero = stored).
        .globl  core_native_sound_set
core_native_sound_set:
        tst.b   core_native_interest+7
        beq.s   8f
        pea     0
        move.l  20(%sp),-(%sp)
        pea     7
        jsr     core_native_view
        lea     12(%sp),%sp
        tst.l   %d0
        beq.s   2f
8:      move.l  8(%sp),%d0
        subi.l  #0x3D9,%d0
        cmpi.l  #32,%d0
        bcc.s   9f
        move.l  core_parameter_provider,%d0
        beq.s   9f
        movea.l %d0,%a0
        clr.l   -(%sp)
        clr.l   -(%sp)
        pea     12(%sp)
        pea     24
        jsr     (%a0)
        lea     16(%sp),%sp
        tst.l   %d0
        bne.s   2f
9:      link    %a6,#-40
        movem.l %d2-%d7/%a2,(%sp)
        jmp     0x4001330C
2:      rts

| MACHINE_ALLOWED at 0x4002559C (Synfact: the entry 0x40025594, sampler's here): after the prologue, so 40 bytes
| of saved registers: 44 sound, 48 machine, 52 track. A refusal returns 0 through the stock epilogue.
        .globl  core_native_machine_select
core_native_machine_select:
        tst.b   core_native_interest+8
        beq.s   8f
        pea     0
        move.l  56(%sp),-(%sp)
        pea     8
        jsr     core_native_view
        lea     12(%sp),%sp
        tst.l   %d0
        bne.s   8f
        movem.l (%sp),%d2-%d6/%a2-%a6
        lea     40(%sp),%sp
        rts
8:      movea.l 44(%sp),%a2
        move.l  48(%sp),%d2
        jmp     0x400255A4

| MODULATION 0x40097B74 (1.41 0x40097AFC): a subscriber may supply a replacement entry. The stock replay jumps to
| 0x40097B7C, where modulation-skip sits when it is in the build.
        .globl  core_native_modulation,core_native_lfo
core_native_modulation:
        tst.b   core_native_interest+16
        beq.s   3f
        clr.l   -(%sp)
        pea     16
        jsr     core_native
        addq.l  #8,%sp
        tst.l   %d0
        beq.s   3f
        movea.l %d0,%a0
        jmp     (%a0)
3:      lea     -60(%sp),%sp
        movem.l %d2-%d7/%a2-%a6,(%sp)
        jmp     0x40097B7C
| LFO 0x4011942A (1.41 0x40119266): subscribers receive {working, tempo, trigs}.
core_native_lfo:
        tst.b   core_native_interest+17
        beq.s   4f
        pea     4(%sp)
        pea     17
        jsr     core_native
        addq.l  #8,%sp
        tst.l   %d0
        beq.s   4f
        movea.l %d0,%a0
        jmp     (%a0)
4:      lea     -64(%sp),%sp
        movem.l %d2-%d7/%a2-%a6,(%sp)
        jmp     0x40119432

| NOTE_ACCEPT 0x400A42B6 (1.41 0x400A423E): A2 event, A4 Sound, A3 queue bucket, A6 the IRQ frame.
| Decline replays move.l 36(a2),d0; moveq #1,d1. Consume reaches 0x400A4796 (the same event release).
        .globl  core_native_note_accept
core_native_note_accept:
        tst.b   core_native_interest+20
        beq.s   note_stock
        lea     -32(%sp),%sp
        movem.l %d1/%a0-%a1,(%sp)
        move.w  %sr,%d1
        move.w  %d1,12(%sp)
        move.l  %a2,16(%sp)
        move.l  %a4,20(%sp)
        move.l  0x800046EC,%d0
        tst.l   (%a3)
        bne.s   note_immediate
        move.l  4(%a3),%d0
note_immediate:
        move.l  %d0,24(%sp)
        move.l  -64(%a6),28(%sp)
        pea     16(%sp)
        pea     20
        jsr     core_native
        addq.l  #8,%sp
        move.w  12(%sp),%d1
        move.w  %d1,%ccr
        movem.l (%sp),%d1/%a0-%a1
        lea     32(%sp),%sp
        tst.l   %d0
        bne.s   note_consumed
note_stock:
        move.l  36(%a2),%d0
        moveq   #1,%d1
        jmp     0x400A42BC
note_consumed:
        jmp     0x400A4796
