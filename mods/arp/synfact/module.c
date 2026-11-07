/* SPDX-License-Identifier: GPL-2.0-or-later
 * Sound-owned monophonic ARP. Task-side metadata uses the shared lifecycle bus.
 * Twelve independent audio tracks; OFF at startup. Native events retain ownership.
 * SyntHack: settings per track saved with the project (persist.h), no SOUND_META; MAIN blocks counted here
 * (arp_blocks) for the host's machine telemetry, which sfcore does not have; view memory from the OS heap.
 */
#include <syntakt/native.h>
#include <syntakt/host.h>
#include "runtime.h"
#include "native-st.h"
#include "keyboard.h"
#include "persist.h"
#define DATA
#define ARP_COMMAND 0x41525031u
#define ARP_CONFIG 0x43464731u
#define ARP_STOP 0x53544f50u
static const struct st_machine_host_api *arp_host DATA=0;
static struct arp_runtime arp_voice[ARP_TRACKS] DATA={{0}};
#define ARP_DEFAULT {0,9,1,30,15,0xffff,{0}}
static struct arp_settings arp_parameters[ARP_TRACKS] DATA={ARP_DEFAULT,ARP_DEFAULT,ARP_DEFAULT,ARP_DEFAULT,
    ARP_DEFAULT,ARP_DEFAULT,ARP_DEFAULT,ARP_DEFAULT,ARP_DEFAULT,ARP_DEFAULT,ARP_DEFAULT,ARP_DEFAULT};
static arp_u32 arp_track DATA=0,arp_running DATA=0;
static arp_u32 arp_generation[ARP_TRACKS] DATA={1,1,1,1,1,1,1,1,1,1,1,1},arp_sequence[ARP_TRACKS] DATA={0},arp_kit[ARP_TRACKS] DATA={0};
static unsigned int arp_live[ARP_TRACKS] DATA={0};
static unsigned char arp_lab_override[ARP_TRACKS] DATA={0};
/* SyntHack: tracks whose rate or locks may have changed since their last full frame (arp_frame) */
static arp_u32 arp_dirty DATA=0;
#include "locks.h"
static const volatile arp_u32 *held_notes(unsigned int track)
{return (const volatile arp_u32 *)(0x455406e0u+track*0x2e18u);}
static int arp_native(arp_u32,const arp_u32 *,arp_u32 *);
static int queue(arp_u32 *e,arp_u32 time)
{
    const volatile arp_u32 *b=*(const volatile arp_u32 **)0x444df434u;
    if(!*(const volatile arp_u32 *)0x444df43cu){
        /* Native allocation spins on exhaustion: never call it without a
         * free bucket or an existing non-immediate bucket at this timestamp. */
        while(b && (b[0] || b[1]!=time))b=(const volatile arp_u32 *)b[4];
        if(!b)return 0;
    }
    ARP_ENQUEUE(e,time);return 1;
}
static arp_u32 *allocate(void){return ARP_EVENT_ALLOC();}
static void copy(arp_u32 *d,const arp_u32 *s){ARP_EVENT_COPY(d,s);}
static void release(arp_u32 *e){ARP_EVENT_FREE(e);}
static const struct arp_runtime_api arp_native_api={allocate,copy,release,queue};
static int eligible(arp_u32 track)
{
    arp_u32 kit=*(const volatile arp_u32 *)0x43bd843cu;
    const unsigned char *owner;unsigned int i;
    if(track>=ARP_TRACKS || !kit || (*(const volatile unsigned short *)(kit+0x1550u)&(1u<<track)))return 0;
    owner=(const unsigned char *)arp_host->native_dispatch(ST_NATIVE_OWNERS,0);
    if(owner){if(owner[track]!=track)return 0;for(i=track+1;i<ARP_TRACKS;i++)if(owner[i]==track)return 0;}
    return 1;
}
static void stop_quiet(unsigned int track)
{
    arp_live[track]=0;arp_running&=~(1u<<track);
    arp_runtime_stop(&arp_voice[track]);if(!++arp_generation[track])arp_generation[track]=1;
}
static void stop_locked(unsigned int track)
{
    if(arp_voice[track].source)ARP_RELEASE(track,0x7fffu);
    stop_quiet(track);
}
static void interest(void)
{
    /* A newly loaded Sound can enable ARP before any page has been opened. */
    arp_u32 mask=(1u<<ST_NATIVE_IMMEDIATE)|(1u<<ST_NATIVE_HEADER_LOAD)|(1u<<ST_NATIVE_HEADER_RESET)|
        (1u<<ST_NATIVE_NOTE_ACCEPT);
    arp_host->native_interest((void (*)(void))arp_native,mask);
}
/* UI/test entry. Publication uses the existing native exclusion and private
 * command pattern already used by POLY. No native object is reinterpreted. */
int arp_experiment_configure(arp_u32 track,const struct arp_settings *p)
{
    arp_u32 command[6]={ARP_COMMAND,ARP_CONFIG,track,(arp_u32)p,0,0};
    ARP_IMMEDIATE(command);return (int)command[5];
}
/* SyntHack: from the track's saved settings (e[4] = 1: superseded if they changed since) */
static int arp_track_configure(arp_u32 track,const struct arp_settings *p)
{
    arp_u32 command[6]={ARP_COMMAND,ARP_CONFIG,track,(arp_u32)p,1,0};
    ARP_IMMEDIATE(command);return (int)command[5];
}
static void restore_track(unsigned int track)
{
    struct arp_settings p;unsigned int i;int different=0;
    if(arp_lab_override[track] || !arp_track_changed(track))return;   /* SyntHack: per note, a quick compare */
    arp_track_read(track,&p);
    for(i=0;i<sizeof(p);i++)if(i!=5 && ((const unsigned char *)&p)[i]!=((const unsigned char *)&arp_parameters[track])[i]){different=1;break;}
    if(different && (p.mode!=arp_parameters[track].mode || p.speed!=arp_parameters[track].speed))stop_locked(track);
    if(different){
        for(i=0;i<sizeof(p);i++)((volatile unsigned char *)&arp_parameters[track])[i]=((const unsigned char *)&p)[i];
        arp_dirty|=1u<<track;
    }
}
static void stop_command(void)
{arp_u32 c[6]={ARP_COMMAND,ARP_STOP,0,0,0,0};ARP_IMMEDIATE(c);}
static void arp_frame(void)
{
    arp_u32 begin,tempo,sequence,kit,pending=arp_running;unsigned int track;
    arp_blocks++;
    if(!pending)return;
    sequence=*(const volatile arp_u32 *)0x43bd8430u;kit=*(const volatile arp_u32 *)0x43bd843cu;
    begin=*(const volatile arp_u32 *)0x800046ecu;tempo=*(const volatile arp_u32 *)0x402d7360u;
    while(pending){
        track=31-__builtin_clz(pending&-pending);pending&=pending-1;
        if(sequence!=arp_sequence[track] || kit!=arp_kit[track] || tempo<3600 || tempo>36000 ||
           (!arp_live[track] && *(const volatile arp_u32 *)0x43bd83bcu!=1)) {stop_locked(track);continue;}
        if(arp_live[track] && arp_keyboard_sync(&arp_voice[track].selector,held_notes(track))<=0){stop_locked(track);continue;}
        {
            /* SyntHack: between two beats, with the same rate and locks, there is nothing else to do (Synfact
             * re-derived the rate every block: ~7 % of the block for 12 running arps, emulator) */
            const struct arp_runtime *r=&arp_voice[track];
            if(!(arp_dirty&(1u<<track)) && r->source && r->clock.armed && (int)(r->clock.next-(begin+2*tempo))>=0 &&
               !(r->finite && (int)(begin-r->until)>=0))continue;
            arp_dirty&=~(1u<<track);
        }
        if((int)(arp_voice[track].clock.next-(begin+2*tempo))<0 && !eligible(track)){stop_locked(track);continue;}
        {
            struct arp_settings effective;struct arp_clock desired;
            arp_effective(track,&effective);
            arp_clock_arm(&desired,begin,effective.speed,arp_generation[track]);
            if(arp_voice[track].clock.period!=desired.period){
                /* A new rate keeps the phase of the last emitted beat. */
                struct arp_clock *c=&arp_voice[track].clock;
                c->next=c->next-c->period+desired.period;c->period=desired.period;
                if((int)(c->next-begin)<0)c->next=begin;
            }
            arp_runtime_frame(&arp_voice[track],&effective,begin,begin+2*tempo,arp_generation[track]);
        }
        if(!arp_voice[track].source)arp_running&=~(1u<<track);
    }
}
static int arp_native(arp_u32 op,const arp_u32 *a,arp_u32 *result)
{
    arp_u32 *e,before;const struct arp_settings *p;unsigned int i,track;
    if(op==ST_NATIVE_IMMEDIATE){
        e=(arp_u32 *)a[0];if(e[0]!=ARP_COMMAND){
            int held;
            track=e[2];
            if(track>=ARP_TRACKS || e[0]>1 || e[3]!=2 ||
               (e[1]!=1 && e[1]!=2) || !eligible(track))return 0;
            restore_track(track);
            if(!arp_parameters[track].mode)return 0;
            if(arp_live[track]) {
                held=arp_keyboard_sync(&arp_voice[track].selector,held_notes(track));
                if(held<0 || (e[1]==1 &&
                   ((e[11] && e[11]!=*(const volatile arp_u32 *)0x444852d0u) ||
                    (e[9]&0x30201u)!=0x10201u))) {stop_locked(track);return 0;}
                if(!held) {
                    stop_locked(track);
                    if(held<0 || e[1]==1)return 0;
                }
            }else {
                /* Check the whole set, before retaining or consuming anything.
                 * Native priority may enqueue only the most recent key. */
                struct arp_selector keys;arp_reset(&keys,arp_generation[track]);
                held=arp_keyboard_sync(&keys,held_notes(track));
                if(held<=0 || e[1]!=1 || (e[11] && e[11]!=*(const volatile arp_u32 *)0x444852d0u))return 0;
                if(!arp_runtime_live_start(&arp_voice[track],&arp_parameters[track],e,
                    *(const volatile arp_u32 *)0x800046ecu,arp_generation[track])) {
                    if(arp_voice[track].source)stop_locked(track);return 0;
                }
                for(i=0;i<sizeof(keys);i++)
                    ((volatile unsigned char *)&arp_voice[track].selector)[i]=((const volatile unsigned char *)&keys)[i];
                arp_live[track]=1;arp_running|=1u<<track;arp_root_lock[track].mask=0;
                arp_sequence[track]=*(const volatile arp_u32 *)0x43bd8430u;arp_kit[track]=*(const volatile arp_u32 *)0x43bd843cu;
            }
            /* IMMEDIATE owns a pooled input. As for POLY's consuming handler,
             * release it exactly once; outputs use ENQUEUE, avoiding recursion. */
            if(!e[0])ARP_EVENT_FREE(e);
            *result=1;return 1;
        }
        if(e[1]==ARP_STOP){for(i=0;i<ARP_TRACKS;i++)if(arp_voice[i].source)stop_locked(i);*result=1;return 1;}
        if(e[1]!=ARP_CONFIG){*result=1;return 1;}
        p=(const struct arp_settings *)e[3];track=e[2];e[5]=0;
        if(p && p->mode<=4 && p->speed<18 && p->range<=3 && p->note_length<128 && p->length<16 && e[2]<ARP_TRACKS &&
           (!p->mode || eligible(e[2]))){
            if(e[4]){
                struct arp_settings current;arp_track_read(track,&current);
                for(i=0;i<sizeof(*p);i++)if(i!=5 && ((const unsigned char *)&current)[i]!=((const unsigned char *)p)[i])break;
                if(i<sizeof(*p)){*result=1;return 1;} /* task snapshot was superseded */
            }
            /* Preserve the root when changing mode or rate. Retiming uses the
             * last emitted beat as the phase origin and never queues in the past. */
            if(!p->mode || (arp_voice[track].source &&
               (arp_sequence[track]!=*(const volatile arp_u32 *)0x43bd8430u ||
                arp_kit[track]!=*(const volatile arp_u32 *)0x43bd843cu ||
                (!arp_live[track] && *(const volatile arp_u32 *)0x43bd83bcu!=1))))stop_locked(track);
            else if(arp_voice[track].source && p->speed!=arp_parameters[track].speed){
                struct arp_clock *c=&arp_voice[track].clock;
                arp_u32 last=c->next-c->period,now=*(const volatile arp_u32 *)0x800046ecu;
                arp_clock_arm(c,last,p->speed,arp_generation[track]);c->next+=c->period;
                if((int)(c->next-now)<0)c->next=now;
            }
            for(i=0;i<sizeof(*p);i++)
                ((volatile unsigned char *)&arp_parameters[track])[i]=((const volatile unsigned char *)p)[i];
            arp_dirty|=1u<<track;
            arp_lab_override[track]=!e[4];
            arp_sequence[track]=*(const volatile arp_u32 *)0x43bd8430u;arp_kit[track]=*(const volatile arp_u32 *)0x43bd843cu;
            interest();
            e[5]=1;
        }
        *result=1;return 1;
    }
    if(op==ST_NATIVE_HEADER_LOAD || op==ST_NATIVE_HEADER_RESET){
        if(arp_running)stop_command();return 0;
    }
    if(op!=ST_NATIVE_NOTE_ACCEPT)return 0;
    e=(arp_u32 *)a[0];track=e[2];
    if(track>=ARP_TRACKS || e[3]!=1)return 0;
    /* Our own output: play it, or drop one a newer root has superseded. */
    switch(arp_runtime_owns(&arp_voice[track],e)){case 1:return 0;case 2:*result=1;return 1;}
    restore_track(track);
    /* The step's locks precede native effect application at NOTE_ACCEPT. */
    struct arp_settings effective;
    /* A trigless lock trig passing a running sequence arp adds its locks to
     * it, as a lock trig changes the sounding note; the native applies the
     * rest. It neither restarts nor stops the arp. */
    if(e[1]==1 && (e[9]&0x10201u)!=0x10201u){
        if(arp_voice[track].source && !arp_live[track] && e[17])arp_root_capture(track,e[17],1);
        return 0;
    }
    arp_root_capture(track,e[17],0);
    arp_effective(track,&effective);
    if(!effective.mode)return 0;
    if(arp_live[track]){*result=1;return 1;}
    /* Stopped/held-step preview is not a running sequence root. Held keyboard
     * input has its own IMMEDIATE lifecycle above. */
    if(*(const volatile arp_u32 *)0x43bd83bcu!=1){
        if(arp_voice[track].source)stop_locked(track);return 0;
    }
    if(e[1]!=1 || !eligible(track)){
        stop_locked(track);return 0;
    }
    /* A new root replaces the running one: its first output retriggers the
     * track. The native gate release (400a5708) is applied by the audio
     * engine after that output and silenced the new root (LEN = the loop). */
    if(arp_voice[track].source)stop_quiet(track);
    i=arp_runtime_start(&arp_voice[track],&effective,e,a[2],arp_generation[track],0,0);
    if(!i)return 0;
    arp_sequence[track]=*(const volatile arp_u32 *)0x43bd8430u;arp_kit[track]=*(const volatile arp_u32 *)0x43bd843cu;
    arp_running|=1u<<track;before=arp_voice[track].dropped;
    arp_runtime_frame(&arp_voice[track],&effective,a[2],a[3],arp_generation[track]);
    /* Pool pressure on the very first output retains the original note. */
    if(arp_voice[track].dropped!=before){stop_locked(track);return 0;}
    *result=1;return 1;
}
#include "view.c"
static int arp_initialize(const struct st_smz_api *a)
{
    unsigned int i;
    if(!a || a->version<3 || !a->ui || !a->ui->host || a->ui->host->version<10 ||
       !a->ui->host->native_dispatch)return 1;
    arp_host=a->ui->host;for(i=0;i<ARP_TRACKS;i++)arp_runtime_init(&arp_voice[i],&arp_native_api);interest();return 0;
}
static const struct st_smz_subscription subscriptions[]={
    {ST_EV_KEY,(void (*)(void))arp_view_key},
    {ST_EV_ENC,(void (*)(void))arp_view_encoder},
    {ST_EV_DRAW|ST_EV_VIEW,(void (*)(void))arp_view_draw},
    {ST_EV_TICK,(void (*)(void))arp_view_tick},
    {ST_EV_RENDER_IN,(void (*)(void))arp_frame},
    {ST_EV_NATIVE,(void (*)(void))arp_native}};
const struct st_smz_module arp_module={"ARP EXPERIMENT",arp_initialize,subscriptions,6};
