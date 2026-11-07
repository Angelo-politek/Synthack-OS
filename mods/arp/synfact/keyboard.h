/* SPDX-License-Identifier: GPL-2.0-or-later */
#ifndef SYNFACT_ST_ARP_KEYBOARD_H
#define SYNFACT_ST_ARP_KEYBOARD_H
#include "arp.h"
/* Read-only snapshot of OS 1.41's held-note bitmap and insertion list.
 * Caller holds native exclusion. Returns held count, or -1 without mutation
 * for an inconsistent list. No keyboard/voice allocator module is required. */
int arp_keyboard_sync(struct arp_selector *,const volatile arp_u32 *native);
#endif
