/* SPDX-License-Identifier: GPL-2.0-or-later
 * lfo3: shared definitions (Synfact mods/lfo3-st/main.c, OS 1.42). */
#ifndef SYNTHACK_LFO3_H
#define SYNTHACK_LFO3_H
typedef unsigned int u32;typedef unsigned short u16;typedef unsigned char u8;
#define LFO3_TRACKS 13u
/* CPU #1 SRAM, LFO3's parts of the tails the stock boot zeroes (tools/build/registry.py, SRAM) */
#define LFO3_SRAM_TAIL0 0x80007330u
#define LFO3_SRAM_TAIL0_END 0x80007780u
#define LFO3_SRAM_TAIL1 0x8000f860u
#define LFO3_SRAM_TAIL1_END 0x8000fc20u
#define LFO3_SRAM_CODE 0x80007340u
#define LFO3_SRAM_BANK 0x8000f870u
/* Parameter record per engine: SPD, MULT, FADE, DEST (slot<<8, 7f00 = none), WAVE, SPH/SLEW, MODE, DEP, in native
 * LFO units. state: the kernel's 40 bytes per engine (+28: this block's modulation, +24: the wave). */
struct lfo3_bank {u8 state[LFO3_TRACKS][40];u32 rng[2];u16 params[LFO3_TRACKS][8];u16 overlay[LFO3_TRACKS][8];};
extern struct lfo3_bank *lfo3_bank;
extern u32 lfo3_active;
void lfo3_update(void);
#endif
