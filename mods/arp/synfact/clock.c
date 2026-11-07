/* SPDX-License-Identifier: GPL-2.0-or-later */
#include "clock.h"
void arp_clock_stop(struct arp_clock *c){c->armed=0;}
int arp_clock_arm(struct arp_clock *c,arp_u32 when,unsigned int speed,arp_u32 generation)
{
    static const unsigned char denominator[]={1,2,3,4,5,6,8,10,12,16,20,24,32,40,48,64,80,96};
    c->armed=0;
    if(speed>=18 || !generation)return 0;
    c->next=when;c->period=86400000u/denominator[speed];
    c->generation=generation;c->late=0;c->armed=1;return 1;
}
int arp_clock_poll(struct arp_clock *c,arp_u32 begin,arp_u32 end,arp_u32 generation,arp_u32 *due)
{
    if(!c->armed)return 0;
    if(c->generation!=generation){c->armed=0;return 0;}
    if((int)(end-begin)<=0)return 0;
    /* Bounded recovery: one trigger maximum; never replay a missed backlog. */
    if((int)(c->next-begin)<0){c->next=begin;c->late++;}
    if((int)(c->next-end)>=0)return 0;
    *due=c->next;c->next+=c->period;
    if((int)(c->next-end)<0){c->next=end;c->late++;}
    return 1;
}
