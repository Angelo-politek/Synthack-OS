/* SPDX-License-Identifier: GPL-2.0-or-later */
#include "arp.h"
/* Opening only displays the Sound's settings, including MODE OFF. */
void arp_activate(struct arp_settings *p){(void)p;}
int arp_trig_tap(struct arp_double_tap *s,arp_u32 key,arp_u32 flags,
                 arp_u32 track,arp_u32 blocks,int main_screen)
{
    int open;
    if(key!=0x13){
        if(flags&1)s->pending=0;
        return ARP_TAP_PASS;
    }
    if(!(flags&1)){
        s->down=0;
        if(s->consume_release){s->consume_release=0;return ARP_TAP_CONSUME;}
        return ARP_TAP_PASS;
    }
    if(s->down || flags&8)return s->consume_release?ARP_TAP_CONSUME:ARP_TAP_PASS;
    s->down=1;
    if(!main_screen || track>=12 || flags&2){s->pending=0;return ARP_TAP_PASS;}
    open=s->pending && s->track==track && blocks-s->at<=525u;
    s->pending=!open;s->track=track;s->at=blocks;
    if(open){s->consume_release=1;return ARP_TAP_OPEN;}
    return ARP_TAP_PASS;
}
