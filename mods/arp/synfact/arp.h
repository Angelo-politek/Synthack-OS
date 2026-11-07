/* SPDX-License-Identifier: GPL-2.0-or-later */
#ifndef SYNFACT_ST_ARP_H
#define SYNFACT_ST_ARP_H
typedef unsigned int arp_u32;
/* Native audio tracks only; 12 is the FX track and has no Sound ARP. */
#define ARP_TRACKS 12u
/* Sound-independent selector. All storage belongs to the caller. No firmware
 * addresses, allocations, UI calls, timers or floating point in this layer. */
struct arp_settings {
    unsigned char mode, speed, range, note_length, length;
    unsigned short enabled;
    signed char offset[16];
};
void arp_activate(struct arp_settings *);
struct arp_selector {
    arp_u32 mask[4];
    unsigned char order[128];
    arp_u32 count, generation;
    int step, word, ascending, last, cursor, octave;
    arp_u32 remaining;
};
void arp_reset(struct arp_selector *,arp_u32 generation);
int arp_hold(struct arp_selector *,unsigned int note);
int arp_release(struct arp_selector *,unsigned int note);
/* Donor result convention: -2 = stale generation/no held notes; -1 = rest.
 * A nonnegative result still needs the native scale/transpose/range policy. */
int arp_next(struct arp_selector *,const struct arp_settings *,arp_u32 generation);

/* UI-only recognizer. TRIG is the parameter-page button, key 0x13, rather
 * than the sixteen sequencer keys. Clock unit is a 32-frame MAIN block. */
struct arp_double_tap {arp_u32 at, track;unsigned int pending,down,consume_release;};
enum {ARP_TAP_PASS,ARP_TAP_CONSUME,ARP_TAP_OPEN};
int arp_trig_tap(struct arp_double_tap *,arp_u32 key,arp_u32 flags,
                 arp_u32 track,arp_u32 blocks,int main_screen);
#endif
