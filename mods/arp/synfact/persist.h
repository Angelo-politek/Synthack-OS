/* SPDX-License-Identifier: GPL-2.0-or-later */
#ifndef ARP_PERSIST_H
#define ARP_PERSIST_H
#include "arp.h"
/* SyntHack: the settings of each audio track are saved with the project (mods/projstore, glue.c), not with the
 * Sound (Synfact's SOUND_META side storage). */
void arp_track_read(arp_u32 track,struct arp_settings *);
int arp_track_store(arp_u32 track,const struct arp_settings *);
/* Note LEN steps through 56 values (the packed lock's room: glue.c) */
unsigned int arp_len_step(unsigned int n,int delta);
/* Locks of the active pattern's lock model: a field's value or -1; set, or clear with -1. */
int arp_lock_get(void *model,arp_u32 track,arp_u32 step,arp_u32 field);
arp_u32 arp_lock_set(void *model,arp_u32 track,arp_u32 step,arp_u32 field,int value);
/* MAIN blocks since boot (counted by arp_frame): Synfact's machine_telemetry[0] */
extern volatile arp_u32 arp_blocks;
#endif
