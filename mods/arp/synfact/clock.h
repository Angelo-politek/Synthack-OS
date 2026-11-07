/* SPDX-License-Identifier: GPL-2.0-or-later */
#ifndef SYNFACT_ST_ARP_CLOCK_H
#define SYNFACT_ST_ARP_CLOCK_H
#include "arp.h"
/* Native MAIN musical time, not UI ticks or elapsed wall-clock time.
 * Callers supply the actual frame [begin,end), including external tempo sync.
 * A discontinuity/STOP/pattern replacement must stop or rearm this timeline. */
struct arp_clock {arp_u32 next,period,generation,armed,late;};
int arp_clock_arm(struct arp_clock *,arp_u32 when,unsigned int speed,arp_u32 generation);
void arp_clock_stop(struct arp_clock *);
int arp_clock_poll(struct arp_clock *,arp_u32 begin,arp_u32 end,
                   arp_u32 generation,arp_u32 *due);
#endif
