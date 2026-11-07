/* SPDX-License-Identifier: GPL-2.0-or-later */
#include "runtime.h"
#include "length.h"
static arp_u32 *retain(struct arp_runtime *r,const arp_u32 *source)
{
    arp_u32 *e=r->api->alloc();
    if(!e)return 0;
    r->api->copy(e,source);
    /* Borrowed/static native sources do not increment their lock refs in
     * event_copy. A newly pooled copy must acquire that reference as POLY does. */
    if(source[0] && source[17])(*(arp_u32 *)source[17])++;
    e[0]=0;e[19]=0;return e;
}
void arp_runtime_init(struct arp_runtime *r,const struct arp_runtime_api *api)
{
    unsigned int i;
    r->api=api;r->source=0;r->clock.armed=0;r->emitted=0;r->dropped=0;
    r->generation=0;r->kind=1;r->queued_next=0;
    for(i=0;i<8;i++)r->queued[i]=0;
}
int arp_runtime_owns(struct arp_runtime *r,const arp_u32 *e)
{
    unsigned int i;
    for(i=0;i<8;i++)if(r->queued[i]==e && r->queued_note[i]==e[6]){
        r->queued[i]=0;return r->source && r->queued_generation[i]==r->generation?1:2;
    }
    return 0;
}
void arp_runtime_stop(struct arp_runtime *r)
{
    arp_u32 *e=r->source;
    r->source=0;arp_clock_stop(&r->clock);
    if(e)r->api->free(e);
}
int arp_runtime_start(struct arp_runtime *r,const struct arp_settings *p,
                      const arp_u32 *e,arp_u32 when,arp_u32 generation,
                      const int *chord,unsigned int count)
{
    arp_u32 *saved;unsigned int i;int note;
    /* A pooled Sound pointer may have a different owner than the lock block.
     * Fail through to native behavior until its lifetime is separately bound. */
    if(!p->mode || p->mode>4 || p->speed>=18 || p->note_length>=128 || p->length>=16 || !generation ||
       e[0]>1 || e[1]!=1 || e[2]>=ARP_TRACKS || e[3]!=1 || e[6]>127 || e[11] || count>3 ||
       (count && !chord) || (e[9]&0x30201u)!=0x10201u){
        arp_runtime_stop(r);return 0;
    }
    saved=retain(r,e);
    if(!saved){arp_runtime_stop(r);r->dropped++;return 0;}
    arp_runtime_stop(r);r->source=saved;r->track=e[2];r->generation=generation;
    /* Native zero disables the gate countdown (e.g. infinite TRIG length).
     * Keep accepting the explicit -1 sentinel used by existing event callers. */
    r->finite=e[12] && e[12]!=0xffffffffu;
    /* Native gate counters decrement by BPM*120, musical time by twice that. */
    r->until=when+2u*e[12];
    if(r->finite && e[12]>=0x40000000u){
        arp_runtime_stop(r);return 0;
    }
    arp_reset(&r->selector,generation);arp_hold(&r->selector,e[6]);
    for(i=0;i<count;i++)if(chord[i]){
        note=(int)e[6]+chord[i];if(note>=0 && note<=127)arp_hold(&r->selector,(unsigned int)note);
    }
    r->kind=1;arp_clock_arm(&r->clock,when,p->speed,generation);
    return 1;
}
int arp_runtime_live_start(struct arp_runtime *r,const struct arp_settings *p,
                           const arp_u32 *e,arp_u32 when,arp_u32 generation)
{
    arp_u32 *saved;unsigned int i;
    if(!p->mode || p->mode>4 || p->speed>=18 || p->note_length>=128 || p->length>=16 ||
       !generation || e[0]>1 || e[1]!=1 || e[2]>=ARP_TRACKS || e[3]!=2 || e[6]>127 ||
       (e[9]&0x30201u)!=0x10201u)return 0;
    saved=retain(r,e);if(!saved){r->dropped++;return 0;}
    arp_runtime_stop(r);r->source=saved;r->track=e[2];r->generation=generation;r->kind=2;
    /* event_free/copy own only lock +44h, never Sound +2ch. The UI source
     * borrows a mutable preview record. Capture its flat 123h bytes and keep
     * +2ch semantics (forced native Sound publication), rather than keeping
     * the UI pointer or aliasing the kit Sound. No Sound allocator is needed.
     * All generated outputs are enqueued for this MAIN frame, then consumed
     * under the same native exclusion before a UI template can replace it. */
    if(e[11]) {
        for(i=0;i<sizeof(r->live_sound);i++)
            ((volatile unsigned char *)r->live_sound)[i]=((const volatile unsigned char *)e[11])[i];
        saved[11]=(arp_u32)r->live_sound;
    }
    r->finite=0;r->until=0;arp_reset(&r->selector,generation);
    arp_clock_arm(&r->clock,when,p->speed,generation);return 1;
}
int arp_runtime_frame(struct arp_runtime *r,const struct arp_settings *p,
                      arp_u32 begin,arp_u32 end,arp_u32 generation)
{
    arp_u32 due,gate,*e;int note;unsigned int i;
    if(!r->source)return 0;
    if(generation!=r->generation || !p->mode ||
       (r->finite && (int)(begin-r->until)>=0)){
        arp_runtime_stop(r);return 0;
    }
    if(!arp_clock_poll(&r->clock,begin,end,generation,&due))return 0;
    if(r->finite && (int)(due-r->until)>=0){arp_runtime_stop(r);return 0;}
    note=arp_next(&r->selector,p,generation);
    if(note<0 || note>127)return 0;
    e=retain(r,r->source);
    if(!e){r->dropped++;return 0;}
    e[3]=r->kind;e[6]=(arp_u32)note;e[12]=arp_note_gate(p->note_length);
    /* One generated note, not a second native retrigger generator. Keep
     * trig/lock/gate flags, remove the native retrigger bit and its counters. */
    e[9]&=~0x48000u;e[13]=0;e[14]=0;e[15]=0;
    if(r->finite){gate=(r->until-due)/2u;if(e[12]>gate)e[12]=gate;}
    if(!e[12]){r->api->free(e);return 0;}
    if(!r->api->queue(e,due)){r->api->free(e);r->dropped++;return 0;}
    /* A reused event block makes any older entry for it stale. */
    for(i=0;i<8;i++)if(r->queued[i]==e)r->queued[i]=0;
    r->queued[r->queued_next&7]=e;r->queued_note[r->queued_next&7]=(arp_u32)note;
    r->queued_generation[r->queued_next&7]=generation;r->queued_next++;
    r->emitted++;return 1;
}
