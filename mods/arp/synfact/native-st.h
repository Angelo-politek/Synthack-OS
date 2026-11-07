/* SPDX-License-Identifier: GPL-2.0-or-later
 * OS 1.41 event-pool services, also used by POLY. No runtime patch installer.
 * Event/bucket allocators are bounded pools, not the general heap. */
#ifndef ARP_ST_CALL
#define ARP_ST_CALL(a,t) ((t)(a))
#endif
#define ARP_EVENT_ALLOC ARP_ST_CALL(0x4011a686u,arp_u32 *(*)(void))
#define ARP_EVENT_COPY ARP_ST_CALL(0x4011a6f0u,void (*)(arp_u32 *,const arp_u32 *))
#define ARP_EVENT_FREE ARP_ST_CALL(0x4011a6bcu,void (*)(arp_u32 *))
#define ARP_ENQUEUE ARP_ST_CALL(0x4011a80cu,void (*)(arp_u32 *,arp_u32))
#define ARP_IMMEDIATE ARP_ST_CALL(0x4011a8e6u,void (*)(arp_u32 *))
#define ARP_RELEASE ARP_ST_CALL(0x400a5780u,void (*)(arp_u32,arp_u32))
