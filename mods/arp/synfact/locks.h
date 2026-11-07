/* SPDX-License-Identifier: GPL-2.0-or-later */
#include "arp.h"
/* SyntHack: MODE, SPEED, RANGE and note LEN (the encoders A..D) lock as one native pattern lock on the Sound's
 * spare logical index 0x46 (lane 0x60 in the file, mods/xparams), packed by arp_lock_pack (glue.c), instead of
 * Synfact's shared lock service on lanes 0x60..0x63. The OS saves, copies, pastes and clears it as any lock. */
#define ARP_LOCK_SLOTS 4u
extern arp_u32 synfact_extra_locks(arp_u32,arp_u32,unsigned short *);
static void arp_locks_apply(struct arp_settings *p,arp_u32 mask,const unsigned short *v)
{
    if((mask&1) && v[0]<=4)p->mode=v[0];
    if((mask&2) && v[1]<18)p->speed=v[1];
    if((mask&4) && v[2]<=3)p->range=v[2];
    if((mask&8) && v[3]<128)p->note_length=v[3];
}
/* The locks of the trig that started each track's arp, captured at
 * NOTE_ACCEPT, plus those of trigless trigs that pass while it plays. The
 * running arp uses them every frame: the root is consumed before the native
 * effects, so the track's published active locks never carry them. */
struct arp_root_locks {arp_u32 mask;unsigned short v[8];};
static struct arp_root_locks arp_root_lock[ARP_TRACKS] DATA={{0}};
static void arp_root_capture(unsigned int track,arp_u32 lock,int merge)
{
    unsigned short v[8];unsigned int i;arp_u32 mask=synfact_extra_locks(track,lock,v);
    struct arp_root_locks *r=&arp_root_lock[track];
    if(!merge)r->mask=0;
    for(i=0;i<8;i++)if(mask&(1u<<i))r->v[i]=v[i];
    r->mask|=mask;
    arp_dirty|=1u<<track;      /* SyntHack: arp_frame re-derives the rate */
}
static void arp_effective(unsigned int track,struct arp_settings *p)
{
    *p=arp_parameters[track];arp_locks_apply(p,arp_root_lock[track].mask,arp_root_lock[track].v);
}
