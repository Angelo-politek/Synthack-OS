| Synfact native services retain their original ownership and queue semantics.
        .text
        .globl native_event_alloc,native_event_copy,native_event_free
        .globl native_enqueue,native_immediate,native_cancel_track
        .globl native_release_track,native_publish_sound
        .set native_event_alloc,0x4011a686
        .set native_event_copy,0x4011a6f0
        .set native_event_free,0x4011a6bc
        .set native_enqueue,0x4011a80c
        .set native_immediate,0x4011a8e6
        .set native_cancel_track,0x4008aa28
        .set native_release_track,0x400a5780
        .set native_publish_sound,0x400a321a
        | Exact native replays for groups with no shared LFO voices. The core
        | owns both entry hooks; these only replay their stock continuations.
        .globl poly_mod_all,poly_native_all
poly_mod_all:
        lea -60(%sp),%sp
        movem.l %d2-%d7/%a2-%a6,(%sp)
        jmp 0x40097b7c
poly_native_all:
        lea -64(%sp),%sp
        movem.l %d2-%d7/%a2-%a6,(%sp)
        jmp 0x40119432
        | SyntHack: no imported analog kernels (analog POLY not ported)
