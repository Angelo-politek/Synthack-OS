/* SPDX-License-Identifier: GPL-2.0-or-later
 * SyntHack: a mod view that is on top owns the keys. Synfact's views return 0 for the keys they do not use, and
 * the OS then acts under the view (device: FUNC+BANK muted parts under the arpeggiator, a second SYN opened the
 * machine menu over it). st_modal_key is the answer for such a key:
 *   - transport (keys 9, 10, 11: the app's own switch at 0x40046BB0) and the keys in `pass` go to the OS;
 *   - any other press is consumed, and so is its release, also after the view has closed;
 *   - the release of a key pressed before the view opened goes to the OS, which saw its press.
 * Call it for every key event the view does not handle, with foreground = the view is on top.
 * One mask per module: include this header once in the module (plain static data, zero at start).
 */
#ifndef ST_MODAL_H
#define ST_MODAL_H
#ifndef ST_MODAL_DATA
#define ST_MODAL_DATA
#endif
static unsigned int st_modal_held[2] ST_MODAL_DATA = {0, 0};

/* key: event +12; flags: event +16 (bit 0 = press); pass: bit k = key k (< 32) goes to the OS; pass_trigs: the
 * 16 trig keys (24..39) go to the OS */
static int st_modal_key(unsigned int key, unsigned int flags, int foreground, unsigned int pass, int pass_trigs)
{
    unsigned int bit;
    if (key >= 64)
        return 0;
    bit = 1u << (key & 31);
    if (!(flags & 1u)) {                            /* release: ours only if we took the press */
        if (!(st_modal_held[key >> 5] & bit))
            return 0;
        st_modal_held[key >> 5] &= ~bit;
        return 1;
    }
    if (!foreground || (key >= 9 && key <= 11) || (key < 32 && (pass >> key & 1u)) ||
        (pass_trigs && key >= 24 && key <= 39))
        return 0;
    st_modal_held[key >> 5] |= bit;
    return 1;
}
#endif
