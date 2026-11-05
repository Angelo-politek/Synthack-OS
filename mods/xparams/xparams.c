/* xparams on the main CPU (OS 1.42): logical indices 0x36..0x3d of every track saved, p-locked and sent to the voice
 * CPU. From SY FM4 (Rxuting, MIT), where they held its second SYN page; here for any machine (xparams.h).
 *
 * FUN_xxxxxxxx names below are the 1.40A functions of the original notes.
 */
#include "xparams.h"

typedef uint32_t u32;

/* first in the blob: xparams_layout.TABLE */
__attribute__((section(".entries"), used)) xp_table_t xp_table = {0};

/* ---- storage: logical index <-> storage slot ------------------------------
 *
 * MAIN OS maps a track's logical indices 0..0x35 to storage slots through
 * 0x40234344 (54 entries) and back through 0x4023441c, which follows it, so
 * neither can grow in place. These copies run to 0x46: the extra indices
 * map to themselves for sounds (soundStorage has 72 slots, 54 used, so slots
 * 0x36..0x3d are spare and a stock OS skips them), and to lock lane ids
 * 0x50..0x57 for pattern locks: a stock OS drops lanes above 0x46, where an
 * id of 0x36 would have loaded as a lock on logical index 0 (trig note).
 * Filled at boot, before MAIN OS reads anything (xp_boot, from the mod area's boot list).
 */
#define LIX2PHYS ((const u32 *)0x40234344)
#define PHYS2LIX ((const u32 *)0x4023441c)
#define FX_PHYS2LIX ((const u32 *)0x40234230)
#define STOCK_LIX 0x36
#define ALL_LIX 0x47
#define LANE_FIRST 0x50

u32 xp_sound_l2p[ALL_LIX];
u32 xp_sound_p2l[ALL_LIX];
u32 xp_lane_of_lix[ALL_LIX];

void xp_boot(void) {
    for (int i = 0; i < ALL_LIX; i++) {
        int stock = i < STOCK_LIX;
        xp_sound_l2p[i] = stock ? LIX2PHYS[i] : (u32)i;
        xp_sound_p2l[i] = stock ? PHYS2LIX[i] : (u32)i;
        if (stock)
            xp_lane_of_lix[i] = LIX2PHYS[i];
        else if (i < XP_FIRST + XP_N)
            xp_lane_of_lix[i] = LANE_FIRST + (i - XP_FIRST);
        else
            xp_lane_of_lix[i] = 0xff;
    }
}

/* Replaces FUN_400a5d5e (storage slot / lock lane id -> logical index, per
 * track; 12 is the FX track). Same answers for every id it took before. */
u32 xp_phys_to_lix(u32 track, u32 phys) {
    if (track > 12)
        return 0;
    if (track == 12)
        return phys < 0x45 ? FX_PHYS2LIX[phys] : 0;
    if (phys < STOCK_LIX)
        return PHYS2LIX[phys];
    if (phys >= LANE_FIRST && phys < LANE_FIRST + XP_N)
        return XP_FIRST + (phys - LANE_FIRST);
    return 0;
}

/* Replaces the deserialiser's slot loop (0x400a706a..0x400a708c in
 * FUN_400a6022, called through xp_load_shim with its a2/a3): storage
 * slots 0..0x3d to the sound's logical indices. A sound saved by a stock OS
 * has zeros in the extra slots: the registered machine's values go there. */
void xp_load_params(uint8_t *sound, const uint8_t *storage) {
    volatile uint16_t *lix = (volatile uint16_t *)(sound + 10 * 2);
    const uint16_t *slot = (const uint16_t *)(storage + 0x1c);
    for (int p = 0; p < XP_FIRST + XP_N; p++)
        lix[xp_sound_p2l[p]] = slot[p];
    int empty = 1;
    for (int k = 0; k < XP_N; k++)
        if (lix[XP_FIRST + k])
            empty = 0;
    if (empty && xp_table.empty)
        xp_table.empty(lix);
}

__asm__(
    "    .text\n"
    "    .globl xp_load_shim\n"
    "xp_load_shim:\n"
    "    move.l %a3,-(%sp)\n"
    "    move.l %a2,-(%sp)\n"
    "    jsr xp_load_params\n"
    "    addq.l #8,%sp\n"
    "    rts\n");

/* ---- the extra indices to the second CPU ------------------------------------
 *
 * Replaces FUN_400a10da, the render's wait for eDMA 47 before it starts the
 * frame transfer (and the voice transfer). After the wait it copies each
 * synth track's extra values, with this block's locks applied, from the
 * sequencer's per-track values (0x800021b0 + (0xe + track * 0x47 + lix) * 2,
 * where FUN_40096958 writes locks and FUN_40096804 restores them) to the
 * shared RAM at XP_SHARED: 16 bytes a voice, which the voice engines read; and the machine words
 * at XP_RAW (20 bytes a voice).
 * 0x5b0..0x800 is past the frame (0x1b0) and the voice output (0x400) and
 * below the boot-time upload window (0x800..0x1000).
 */
#define SEQ_VALUES ((volatile uint16_t *)0x800021b0)
#define SHARED_MAIN ((volatile uint16_t *)(0x10000000 + XP_SHARED))
#define SHARED_RAW ((volatile uint16_t *)(0x10000000 + XP_RAW))
#define DMA_PENDING (*(volatile uint8_t *)0x43bde73c)
#define TCD47_CSR (*(volatile uint16_t *)0xfc0455fe)
/* The audio interrupt calls the wait twice: before the frame transfer (return to 0x400a4e34) and at its end
 * (0x400a54fc). The values are copied with the frame, at the first call: nothing in the interrupt writes them in
 * between, so the second copy only repeated the first (144 shared-RAM writes a block, outside the cache). */
#define FRAME_CALL ((void *)0x400a4e34)

__attribute__((optimize("O2"), noinline)) static void xp_copy(void) {
    /* One move.l (a0)+,(a1)+ per two words, the words of a track unrolled, the tracks in a loop: ~120 instructions in
     * ~60 bytes of code. The audio interrupt does not fit the 8 KB instruction cache, so every 16 bytes of code
     * it runs cost a line fill each block: the fully unrolled copy (144 move.w d16(An),d16(An), 870 bytes) ran
     * fewer instructions and cost more time (tools/emu/cycles.py). Long words halve the accesses to the shared
     * RAM, which is outside the cache; the source of odd tracks is 2-aligned (the V4 core reads it in two). */
    volatile uint32_t *dst = (volatile uint32_t *)SHARED_MAIN, *raw = (volatile uint32_t *)SHARED_RAW;
    for (int t = 0; t < 8; t++) {
        volatile const uint32_t *src = (volatile const uint32_t *)(SEQ_VALUES + 0xe + t * 0x47 + XP_FIRST);
#pragma GCC unroll 4
        for (int k = 0; k < XP_N / 2; k++)
            *dst++ = *src++;
        /* the machine words as set: the voice frames carry them smoothed */
        src = (volatile const uint32_t *)(SEQ_VALUES + 0xe + t * 0x47 + XP_RAW_FIRST);
#pragma GCC unroll 5
        for (int k = 0; k < XP_RAW_N / 2; k++)
            *raw++ = *src++;
    }
}

__attribute__((optimize("O2"))) void xp_dma_wait(void) {
    if (DMA_PENDING) {
        while (!(TCD47_CSR & 0x80))     /* DONE */
            ;
        DMA_PENDING = 0;
    }
    if (__builtin_return_address(0) == FRAME_CALL)
        xp_copy();
}
