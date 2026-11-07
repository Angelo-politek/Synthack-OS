/* Audited laboratory batch preparation; native event/lock pools stay native.

 * Caller supplies storage and the existing queue exclusion context. */

typedef unsigned int u32;

typedef unsigned char u8;

typedef signed int s32;

extern u32 native_event_alloc(void);   /* SyntHack: pointer in d0 */

extern void native_event_copy(u32 *,const u32 *);

extern void native_event_free(u32 *);

extern void native_enqueue(u32 *,u32);

extern void native_immediate(u32 *);



static u32 *copy_event(const u32 *source)

{

    u32 *event=(u32 *)native_event_alloc();

    if(!event)return (u32 *)0;

    native_event_copy(event,source);

    /* The native copy increments refs for pooled sources. Borrowed preview

     * sources also need a reference when converted to a pooled event. */

    if(source[0] && source[17])(*(u32 *)source[17])++;

    event[0]=0;

    event[19]=0;

    return event;

}

/* Keyboard/MIDI kind-2 events have Sound+28h == 0 (401196e2).
 * The native consumer then loads the destination track's own kit Sound
 * (400a464c), replacing an analog slave's machine. Bind the master's borrowed
 * kit Sound on retarget, exactly as sequencer events with an explicit Sound.
 * Keep pooled/locked Sounds and master/digital events unchanged. Event path
 * only: no extra work in the per-block publisher or subscription guards. */
static void poly_voice_target(volatile u32 *event,u32 master,u32 voice)
{
    if(voice && master>=8 && !event[10] && !event[11]) {
        u32 kit=*(volatile u32 *)0x43bd843cu;
        if(kit)event[10]=kit+0x2au+master*0x123u;
    }
    event[2]=master+voice;
    event[18]=master+voice;
}



u32 poly_prepare(const u32 *source,const volatile u8 *sequence,u32 step,

                     u32 voices,u32 **out)

{

    u32 i,count=0,track,raw,root;

    s32 note;

    for(i=0;i<4;i++)out[i]=(u32 *)0;

    if(!source || !sequence)return 0;

    if(source[3]!=1 || source[11])return 0;

    track=source[2];root=source[6];

    if(track>=12 || root>127 || step>=64 || voices<2 || voices>4 ||
       track+voices>(track<8?8u:11u) || (track>=8 && voices>(track==8?3u:track==9?2u:0u)))return 0;
    for(i=0;i<voices;i++) {

        if(i==0)note=(s32)root;

        else {

            raw=sequence[track*0x499u+0x2c0u+i*0x40u+step];

            if(raw==255)raw=sequence[track*0x499u+0x3c5u+i];

            if(raw==64 || raw>127)continue;

            note=(s32)root+(s32)raw-64;

            if(note<0 || note>(track<8?127:84))continue;
        }

        if(track>=8 && note>84)continue;
        out[count]=copy_event(source);

        if(!out[count]) {

            while(count) {count--;native_event_free(out[count]);out[count]=(u32 *)0;}

            return 0;

        }

        poly_voice_target(out[count],track,i);
        out[count][6]=(u32)note;

        count++;

    }

    return count;

}



/* Return without taking ownership if a new bucket would exhaust its pool.

 * Same-timestamp voices are enqueued separately so native tail stays correct.

 * No tagging or overlay of the native event's fields is introduced. */

u32 poly_submit(u32 **events,u32 count,u32 time,u32 immediate)

{

    volatile u32 *bucket=*(volatile u32 **)0x444df434u;

    u32 can_queue=*(volatile u32 *)0x444df43cu!=0,i;

    if(count<1 || count>4)return 0;

    if(immediate) {

        if(bucket && bucket[0])can_queue=1;

    }else {

        while(bucket) {

            if(!bucket[0] && bucket[1]==time){can_queue=1;break;}

            bucket=(volatile u32 *)bucket[4];

        }

    }

    if(!can_queue)return 0;

    for(i=0;i<count;i++) {

        if(immediate)native_immediate(events[i]);

        else native_enqueue(events[i],time);

    }

    return 1;

}



/* Sink for the actual native queue iterator, used only by the laboratory. */

void poly_capture(const u32 *event,u32 *sink)

{

    u32 index=sink[0];

    if(index<16) {

        sink[1+index*3]=event[2];

        sink[2+index*3]=event[6];

        sink[3+index*3]=event[10];

    }

    sink[0]=index+1;

}

