/* SPDX-License-Identifier: GPL-2.0-or-later
 * SyntHack SDK: names for what mods use most in Syntakt OS 1.42 (main CPU, section 3).
 *
 *     #include "synthack.h"        // tools/build/modkit.py puts it next to your sources
 *
 * Only addresses that mods in this repository already use and test are listed here.
 * More: docs/modding-guide.md, docs/audio-path.md, docs/ui-parameters.md.
 *
 * Rules the compiler does not check (docs/modding-guide.md, section 1):
 * - variables go in .data, not .bss: write `static u32 n DATA = 0;`
 * - no libgcc: no 64-bit multiply or divide, no float;
 * - an OS function returns every result in d0, pointers too, and gcc reads pointer results from a0:
 *   declare OS functions with an integer result and cast it (tests/test_os_abi.py rejects the other form).
 */
#ifndef SYNTHACK_H
#define SYNTHACK_H

typedef unsigned char u8;
typedef unsigned short u16;
typedef unsigned int u32;
typedef signed char s8;
typedef short s16;
typedef int s32;

#define DATA __attribute__((section(".data")))

/* ---- memory (UI task only: never from the audio interrupt) */
#define FW_MALLOC ((u32 (*)(u32))0x4010394Cu)              /* (size) -> address, 0 if none */
#define FW_FREE   ((void (*)(void *))0x40103958u)

/* ---- screen: 128 x 64, 1 bit per pixel. Draw only from a draw function the OS calls, on the context it gives. */
#define UI_ROOT     (*(char *const volatile *)0x444E2334u) /* the view controller */
#define UI_REDRAW() (UI_ROOT[96] = 1)                      /* ask for a redraw of the current page */
#define FONT_4X6    ((const void *)0x402A9510u)
/* (ctx, font, x, y, centred, 0, width_template, fmt, ...): printf-like; the template sets the width, e.g. "XXXX" */
#define DRAW_TEXT ((void (*)(void *, const void *, s32, s32, s32, s32, const char *, const char *, ...))0x400F8DDCu)

/* ---- time */
#define TEMPO_X120 (*(const volatile u32 *)0x402D7360u)    /* BPM x 120 */

/* ---- audio, in the audio interrupt: blocks of 32 frames at 48 kHz, s32 samples (docs/audio-path.md).
 * The stock OS uses ~89 % of each block. Count what you add (tests/test_cpu_budget.py, tools/emu/cycles.py). */
#define BLOCK_FRAMES 32
#define AUDIO_DIGITAL(t) ((volatile s32 *)(0x80003D50u + 128u * (t)))  /* tracks 1-8 from the voice CPU, t = 0..7 */
#define AUDIO_ADC(c)     ((volatile s32 *)(0x80003950u + 128u * (c)))  /* 0-3 analog tracks, 4-5 inputs, 6-7 FX track bus */
#define BUS_DIRECT       ((volatile s32 *)0x8000DAD0u)     /* to the analog mixer, L/R interleaved */
#define BUS_FX_TRACK     ((volatile s32 *)0x8000DFD0u)     /* digital tracks routed to the FX track, L/R interleaved */
#define DELAY_OUT        ((volatile s32 *)0x8000DCD0u)     /* delay return, L/R interleaved */
#define REVERB_OUT       ((volatile s32 *)0x8000DDD0u)     /* reverb return, L/R interleaved */
/* engine copy of a track's parameters: word of internal id i at TRACK_PARAMS(t)[14 + i], t = 0..11 */
#define TRACK_PARAMS(t)  ((volatile s16 *)(0x800021B0u + 142u * (t)))

#endif
