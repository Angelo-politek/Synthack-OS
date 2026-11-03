/* xparams: eight extra logical indices for every track (0x36..0x3d), shared by the machines that use them (OS 1.42).
 *
 * A machine reads and writes them like its own (descriptors with these logical indices); xparams saves them with
 * the sound, takes them through p-locks, and copies them, locks applied, to the voice CPU's shared RAM every audio
 * block: XP_SHARED + 16 * voice + 2 * (index - XP_FIRST). It also copies each track's machine words as set
 * (XP_RAW). Indices are per track: a track has one machine, so two machines can give the same index different
 * meanings.
 *
 * A sound saved by a stock OS has zeros there. A machine can register what to write instead (xp_on_empty, from the
 * mod area's boot list); it gets the sound's values, word per logical index.
 */
#ifndef XPARAMS_H
#define XPARAMS_H

#include <stdint.h>

#define XP_FIRST 0x36
#define XP_N 8
#define XP_SHARED 0x700                 /* voice CPU address; the main CPU sees it at 0x10000000 + XP_SHARED */

/* The machine words (logical indices 0x11..0x1a) as set, with this block's locks: the voice frames carry them
 * smoothed (0x400979CA moves them a little every block), which suits sounds, not choices (a slice, a grid, a mode).
 * XP_RAW + 20 * voice + 2 * (index - XP_RAW_FIRST). */
#define XP_RAW 0x640
#define XP_RAW_FIRST 0x11
#define XP_RAW_N 10

typedef struct {
    void (*empty)(volatile uint16_t *lix);
} xp_table_t;

#ifdef XP_TABLE
static inline void xp_on_empty(void (*fn)(volatile uint16_t *lix)) {
    ((volatile xp_table_t *)XP_TABLE)->empty = fn;
}
#endif

#endif
