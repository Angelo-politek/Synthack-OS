/* SPDX-License-Identifier: GPL-2.0-or-later */
#ifndef SYNFACT_ST_ARP_LENGTH_H
#define SYNFACT_ST_ARP_LENGTH_H
#include "arp.h"
/* DN 1.44 gate producer 4009e78a..4009e79c and native countdown. Gate
 * units are the same on Syntakt: BPM*120 decrements per MAIN block.
 * LEN 127 has an anomalous finite lookup in that OS, retained for parity;
 * it is not an infinity sentinel. Invalid settings return zero. */
arp_u32 arp_note_gate(unsigned int length);
/* Original displayed length, including 1/64 through 1/2 aliases.
 * Caller supplies at least 12 writable bytes; no retained pointers/heap. */
char *arp_format_note_length(char *out,unsigned int length);
#endif
