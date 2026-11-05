| Fused 13-track LFO3 render. Imported from Synfact src/features/lfo3/throughput/render.s
| (sha256 65110d2a...), derived from the native OS 1.41 LFO kernel. Position independent:
| it runs from a MAIN SRAM copy; native helpers/tables are absolute. Same EMAC contract.
.text
.globl lfo3_render,lfo3_step_body
lfo3_render:
 lea -96(%sp),%sp
 movem.l %d2-%d7/%a2-%a6,(%sp)
 movea.l 100(%sp),%a5
 lea 28(%a5),%a5
 movea.l 112(%sp),%a3
 addq.l #6,%a3
 movea.l 116(%sp),%a2
 lea 4(%a2),%a4
 lea 36(%a2),%a2
 move.l 104(%sp),%d0
 move.l %d0,68(%sp)
 move.l 108(%sp),%d0
 move.l %d0,52(%sp)
 move.l 120(%sp),%d0
 move.l %d0,76(%sp)
 moveq #13,%d0
 move.l %d0,80(%sp)
lfo3_step_body:
 | Common initial LFO3 record. Preserve the full general kernel otherwise.
 mvs.w -6(%a3),%d0
 cmpi.l #0x7000,%d0
 bne.s lfo3_full_step
 mvs.w -4(%a3),%d0
 cmpi.l #0x0300,%d0
 bne.s lfo3_full_step
 mvs.w -2(%a3),%d0
 cmpi.l #0x4000,%d0
 bne.s lfo3_full_step
 mvs.w (%a3),%d0
 beq.s default_destination_checked
 cmpi.l #0x7f00,%d0
 bne.s lfo3_full_step
default_destination_checked:
 tst.w 2(%a3)
 bne.s lfo3_full_step
 tst.w 4(%a3)
 bne.s lfo3_full_step
 tst.w 6(%a3)
 bne.s lfo3_full_step
 mvs.w 8(%a3),%d0
 cmpi.l #0x4000,%d0
 bne.s lfo3_full_step
 move.l -20(%a2),%d0
 cmpi.l #0x3fffffff,%d0
 bhi.s lfo3_full_step
 move.l %macsr,%d0
 andi.l #0xf0,%d0
 cmpi.l #0x20,%d0
 bne.s lfo3_full_step
 bra.w lfo3_default_step
lfo3_full_step:
        mvs.w -6(%a3),%d5
        mvs.b -4(%a3),%d0
        addi.l #-16384,%d5
        add.l %d5,%d5
        tst.l %d0
        bge.s mult_nonnegative
        clr.l %d0
        bra.s tempo_external
mult_nonnegative:
        moveq #23,%d1
        cmp.l %d0,%d1
        bge.s mult_in_range
        moveq #23,%d0
        bra.s tempo_fixed
mult_in_range:
        moveq #11,%d2
        cmp.l %d0,%d2
        bge.s tempo_external
tempo_fixed:
        addi.l #-12,%d0
        move.l #0x3840,%d1
        bra.s tempo_ready
tempo_external:
        move.l 68(%sp),%d1
tempo_ready:
        mvs.b 2(%a3),%d3
        bge.s wave_nonnegative
        clr.l %d3
        bra.s wave_ready
wave_nonnegative:
        moveq #6,%d7
        cmp.l %d3,%d7
        bge.s wave_ready
        moveq #6,%d3
wave_ready:
        muls.l %d1,%d5
        moveq #11,%d7
        mvs.w 4(%a3),%d2
        sub.l %d0,%d7
        mvs.w -2(%a3),%d0
        move.l %d2,44(%sp)
        asr.l %d7,%d5
        move.l %d0,-(%sp)
        jsr 0x40118e38
        addq.l #4,%sp
        mvs.b 6(%a3),%d1
        move.l %d5,%d2
        movea.l -36(%a2),%a0
        add.l %a0,%d2
        movea.l %d2,%a1
        adda.l #0xd6cd2000,%a0
        mvs.w %d1,%d4
        adda.l #0xd6cd2000,%a1
        movea.l %d1,%a6
        move.l %a1,%d7
        move.l %a0,%d1
        eor.l %d1,%d7
        add.l -20(%a2),%d0
        tst.l %d7
        bge.s wrap_phase
        tst.b 1(%a2)
        bne.s wrap_phase
        tst.b (%a2)
        bne.s wrap_phase
        moveq #4,%d7
        cmp.l %d4,%d7
        bne.s wrap_phase
        lea 0x40245b04,%a0
        move.l (%a0,%d3.l*4),(%a4)
        move.b #1,(%a2)
wrap_phase:
        cmpi.l #0x5265bfff,%d2
        bls.s mode_flags
        tst.b 1(%a2)
        bne.s wrap_now
        tst.b (%a2)
        bne.s wrap_now
        moveq #3,%d1
        cmp.l %d4,%d1
        bne.s wrap_now
        lea 0x40245b3c,%a1
        tst.l %d5
        blt.s wrap_latch
        lea 0x40245B20,%a1
wrap_latch:
        movea.l (%a1,%d3.l*4),%a0
        move.l %a0,(%a4)
        move.b #1,(%a2)
wrap_now:
        tst.l %d5
        blt.s wrap_backward
        addi.l #0xad9a4000,%d2
        bra.s mode_flags
wrap_backward:
        addi.l #0x5265c000,%d2
mode_flags:
        moveq #1,%d1
        cmp.l %d4,%d1
        bcs.s mode_started
        clr.b (%a2)
mode_started:
        clr.b 1(%a2)
        btst #0,55(%sp)
        beq.s no_reset
        moveq #1,%d1
        cmp.l %d4,%d1
        beq.s reset_phase
        move.l %a6,%d1
        subq.l #3,%d1
        mvz.w %d1,%d1
        moveq #1,%d7
        cmp.l %d1,%d7
        bcs.s trig_other_mode
reset_phase:
        moveq #6,%d0
        cmp.l %d3,%d0
        beq.s reset_random_phase
        move.l 44(%sp),%d2
        move.l #0x5265c000,%d0
        swap %d2
        clr.w %d2
        .word 0xa400,0x0800,0xa1c2
        bra.s reset_fade
reset_random_phase:
        clr.l %d2
reset_fade:
        moveq #1,%d7
        mvs.w -2(%a3),%d1
        move.l %d1,-(%sp)
        jsr 0x40118eb4
        clr.b (%a2)
        addq.l #4,%sp
        move.b %d7,1(%a2)
trig_other_mode:
        tst.l %d4
        bne.s trig_mode_two
        clr.b (%a2)
        mvs.w -2(%a3),%d0
        move.l %d0,-(%sp)
        jsr 0x40118eb4
        addq.l #4,%sp
        bra.s no_reset
trig_mode_two:
        moveq #2,%d1
        cmp.l %d4,%d1
        bne.s no_reset
        move.b #1,(%a2)
        move.b #1,%d1
        bra.s save_phase
no_reset:
        clr.l %d1
save_phase:
        move.l %d2,-36(%a2)
        movea.l %d0,%a6
        tst.l %d0
        bge.s fade_upper
        suba.l %a6,%a6
        bra.s fade_ready
fade_upper:
        cmpi.l #0x3fffffff,%d0
        ble.s fade_ready
        movea.l #0x3fffffff,%a6
fade_ready:
        move.l %a6,-20(%a2)
        move.l (%a4),%d0
        tst.b (%a2)
        beq.s calculate_wave
        tst.l %d1
        beq.s held_wave
calculate_wave:
        moveq #6,%d7
        cmp.l %d3,%d7
        beq.s random_wave
        move.l #0x636ba875,%d0
        .word 0xa400,0x0800,0xa1c2
        lsl.l #2,%d2
        lea 0x40245B58,%a1
        movea.l (%a1,%d3.l*4),%a1
        move.l %d2,-(%sp)
        move.l %d1,52(%sp)
        jsr (%a1)
        addq.l #4,%sp
        move.l 48(%sp),%d1
        bra.w wave_ready_output
random_wave:
        tst.l %d5
        blt.s random_backward
        move.l %d2,%d0
        sub.l -16(%a2),%d0
        bra.s random_threshold
random_backward:
        move.l -16(%a2),%d0
        sub.l %d2,%d0
random_threshold:
        cmpi.l #0x05265bff,%d0
        bhi.s random_next
        tst.l %d4
        beq.s random_slew
        btst #0,55(%sp)
        beq.s random_slew
random_next:
        move.l %d2,-16(%a2)
        move.l %d1,48(%sp)
        movea.l 76(%sp),%a0
        bsr.w lfo3_random
        move.l %d0,-28(%a2)
        move.l 48(%sp),%d1
        bra.s random_slew
held_wave:
        moveq #6,%d2
        cmp.l %d3,%d2
        bne.s wave_ready_output
random_slew:
        move.l 44(%sp),%d7
        asr.l #8,%d7
        lea 0x40245B70,%a0
        move.l -28(%a2),%d2
        move.l #0x7fffffff,%d0
        move.l -24(%a2),%d3
        movea.l (%a0,%d7.l*4),%a1
        sub.l %a1,%d0
        .word 0xa002,0x0800,0xa243,0x0800,0xa1c0
        move.l %d0,(%a4)
wave_ready_output:
        move.l %d0,-24(%a2)
        tst.b (%a2)
        beq.s apply_fade
        tst.l %d1
        beq.s destination
apply_fade:
        .word 0xa00e,0x0800,0xa1c0
        add.l %d0,%d0
        move.l %d0,(%a4)
destination:
        mvs.b (%a3),%d1
        moveq #70,%d7
        mvs.w %d1,%d2
        move.l %d2,-12(%a2)
        cmp.l %d2,%d7
        bcs.s phase_copy
        mvs.w 8(%a3),%d2
        lea (%a5,%d1.l*2),%a0
        addi.l #-16384,%d2
        add.l %d2,%d2
        .word 0xa002,0x0800,0xa1c0
        move.l %d0,-8(%a2)
        mvs.w (%a0),%d2
        add.l %d2,%d0
        bpl.s clamp_max
        clr.l %d0
        bra.s write_value
clamp_max:
        cmpi.l #0x7f00,%d0
        ble.s write_value
        move.l #0x7f00,%d0
write_value:
        move.w %d0,(%a0)
phase_copy:
        tst.b (%a2)
        beq.s running_phase
        clr.l -4(%a2)
        bra.s step_return
running_phase:
        move.l -36(%a2),-4(%a2)
step_return:
 subq.l #1,80(%sp)
 beq.s render_return
 lea 142(%a5),%a5
 lea 16(%a3),%a3
 lea 40(%a2),%a2
 lea 40(%a4),%a4
 move.l 52(%sp),%d0
 lsr.l #1,%d0
 move.l %d0,52(%sp)
 bra.w lfo3_step_body
render_return:
 movem.l (%sp),%d2-%d7/%a2-%a6
 lea 96(%sp),%sp
 rts
| Exact specialization of SPD=7000, MULT=0300, FADE=4000, zero-depth DEST 0 or invalid 7f,
| WAVE/SPH/MODE=0, DEP=4000, with valid fade state. Native fade increment
| is 40000000 and trigger reset is 3fffffff, so both paths saturate to max.
| Keep the same phase normalization, waveform helper and fractional EMAC.
lfo3_default_step:
 move.l #0x6000,%d5
 move.l 68(%sp),%d1
 muls.l %d1,%d5
 asr.l #8,%d5
 move.l -36(%a2),%d2
 add.l %d5,%d2
 cmpi.l #0x5265bfff,%d2
 bls.s default_phase_ready
 tst.l %d5
 blt.s default_phase_backward
 addi.l #0xad9a4000,%d2
 bra.s default_phase_ready
default_phase_backward:
 addi.l #0x5265c000,%d2
default_phase_ready:
 move.l %d2,-36(%a2)
 move.l %d2,-4(%a2)
 clr.w (%a2)
 movea.l #0x3fffffff,%a6
 move.l %a6,-20(%a2)
 move.l #0x636ba875,%d0
 .word 0xa400,0x0800,0xa1c2
 lsl.l #2,%d2
 lea 0x40245B58,%a1
 movea.l (%a1),%a1
 move.l %d2,-(%sp)
 jsr (%a1)
 addq.l #4,%sp
 move.l %d0,-24(%a2)
 .word 0xa00e,0x0800,0xa1c0
 add.l %d0,%d0
 move.l %d0,(%a4)
 mvs.b (%a3),%d1
 move.l %d1,-12(%a2)
 tst.l %d1
 bne.w step_return
 clr.l %d2
 .word 0xa002,0x0800,0xa1c0
 move.l %d0,-8(%a2)
 mvs.w (%a5),%d2
 add.l %d2,%d0
 bpl.s default_clamp_max
 clr.l %d0
 bra.s default_write_value
default_clamp_max:
 cmpi.l #0x7f00,%d0
 ble.s default_write_value
 move.l #0x7f00,%d0
default_write_value:
 move.w %d0,(%a5)
 bra.w step_return
lfo3_random:
 move.l 4(%a0),%d1
 move.l %d1,%d0
 add.l (%a0),%d0
 move.l %d1,(%a0)
 move.l %d0,4(%a0)
 rts

.globl lfo3_render_end
lfo3_render_end:
