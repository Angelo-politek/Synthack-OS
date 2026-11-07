/* Native sequencer binding prototype; storage is supplied by the laboratory.
 * Configuration is published only under the existing sequencer exclusion. */
typedef unsigned int u32;
typedef unsigned char u8;
struct pending {u32 event,sequence,step,generation;};
struct config {u32 generation,sequence;u8 states[12],owners[12];struct pending pending[13];};
extern volatile struct config poly_seq_config;
extern void native_event_free(u32 *);
extern u32 poly_prepare(const u32 *,const volatile u8 *,u32,u32,u32 **);
extern u32 poly_submit(u32 **,u32,u32,u32);
extern u32 poly_resolve(const volatile u8 *,volatile u8 *);
extern void native_cancel_track(u32 *,u32);
extern void native_release_track(u32,u32);
extern u32 poly_sync(void);
extern void native_publish_sound(const volatile u8 *,u32);

/* First step after STOP/pattern load. 4008c0b0 prepares one static
 * event per track at 444e2438+t*50h (time 444e2848+t*4); the native start
 * routines 4008b1ac/4008b008 copy and enqueue those directly, bypassing the
 * 4008cfc4 chord expansion. SLAVE statics are filled from their master. */
#define PREP_EVENT(t) ((volatile u32 *)(0x444e3438u+(t)*0x50u))
#define PREP_TIME(t) (*(volatile s32 *)(0x444e3848u+(t)*4u))
static u8 prep_step[12] DATA={0};
static u32 prep_generation[12] DATA={0};

/* Interval lane of one chord voice: step value, default when inherited. */
static s32 poly_chord_note(const volatile u8 *sequence,u32 track,u32 step,u32 voice,volatile u32 root)
{
    volatile u32 raw=255;
    s32 note;
    if(step<64)raw=sequence[track*0x499u+0x2c0u+voice*0x40u+step];
    if(raw==255)raw=sequence[track*0x499u+0x3c5u+voice];
    if(root>127)return -1;
    if(raw==64 || raw>127)return -1;
    note=(s32)root+(s32)raw-64;
    return note>=0 && note<=(track<8?127:84)?note:-1;
}

/* Delay the native start adds when a track starts inside its own step. */
/* Native signed bytes, widened without MVS (not in the audited forms). */
static s32 signed_byte(volatile u32 value)
{
    value&=255u;
    return value>127u?(s32)value-256:(s32)value;
}

static s32 prep_delay(const volatile u8 *sequence,u32 track)
{
    s32 rem=signed_byte(*(volatile u8 *)(0x43bd84fcu+track)),speed,scale;
    if(rem<1)return 0;
    scale=signed_byte(sequence[0x2137au]);
    if(sequence[0x21379u]==1)scale=signed_byte(sequence[track*0x499u+0x3ccu]);
    speed=*(volatile s32 *)(0x401dac58u+(u32)(scale*4));
    return (speed-rem)*900000;
}

/* Copy the prepared master trig to one SLAVE static, same start instant. */
static u32 prep_fill(const volatile u8 *sequence,u32 master,u32 voice,s32 time)
{
    volatile u32 *source=PREP_EVENT(master),*target=PREP_EVENT(master+voice);
    volatile u32 i;
    s32 note;
    target[1]=0;
    if(!source[1] || source[2]!=master)return 0;
    note=poly_chord_note(sequence,master,prep_step[master],voice,source[6]);
    if(note<0)return 0;
    time+=prep_delay(sequence,master)-prep_delay(sequence,master+voice);
    if(time<0)return 0;
    for(i=0;i<20;i++)target[i]=source[i];
    poly_voice_target(target,master,voice);target[6]=(u32)note;
    PREP_TIME(master+voice)=time;
    return 1;
}

static void prep_fill_group(const volatile u8 *sequence,u32 master,s32 time)
{
    u32 voice;
    for(voice=1;voice+1u<poly_seq_config.states[master];voice++)prep_fill(sequence,master,voice,time);
}

/* Native per-track preparation, as 4008c0b0 does for one audio track. */
static void prep_rebuild(const volatile u8 *sequence,u32 track)
{
    u32 kit=*(volatile u32 *)0x43bd843cu,step;
    volatile u32 midi_bit;
    s32 time=0;
    volatile u32 *event=PREP_EVENT(track);
    if(!kit || *(volatile u32 *)(0x43bd83c8u+track*4u)==1)return;
    midi_bit=(*(volatile u16 *)(kit+0x1550u)>>track)&1u;
    if(midi_bit)return;
    if(poly_seq_config.owners[track]<track)return;
    step=(u32)signed_byte(*(volatile u8 *)(0x43bd84efu+track));
    event[17]=*(volatile u32 *)(0x444e4884u+track*4u);
    if(stock_trig(track,sequence,kit,step,(u32 *)event,(u32 *)&time))PREP_TIME(track)=time;
    else event[1]=0;
    if(PREP_TIME(track)<0)event[1]=0;
    prep_step[track]=(u8)step;
    prep_generation[track]=poly_seq_config.generation;
    if(poly_seq_config.states[track]>=3)prep_fill_group(sequence,track,PREP_TIME(track));
}

/* Published together with owners under the native IRQ exclusion. */
volatile u8 poly_has_groups DATA=0;
volatile u8 poly_analog_active DATA=0;
u32 poly_publish_end DATA=1;
u32 poly_publish_first DATA=1;
u32 poly_slave_mask DATA=0;
static u8 poly_analog_type[2] DATA={0,0};

extern void poly_native_interest(void);
u32 poly_commit(u32 sequence,const volatile u8 *states)
{
    u8 owners[12],old_roots[12],new_roots[12],affected[12];
    volatile u32 i,changed=0,on;
    u32 old;
    volatile u32 *bucket;
    u32 *event;
    if(!poly_resolve(states,owners))return 0;
    if(sequence!=poly_seq_config.sequence)changed=1;
    for(i=0;i<12;i++) {
        old_roots[i]=0;new_roots[i]=0;
        if(states[i]!=poly_seq_config.states[i] || (i<8 && poly_modes[i]!=poly_next_modes[i]))changed=1;
    }
    if(!changed)return 1;
    for(i=0;i<12;i++) {
        old=poly_seq_config.owners[i];
        if(old>i)return 0; /* Caller must initialize an identity map. */
        on=0;
        if(states[i]>=3)on=1;
        if(poly_seq_config.states[i]>=3)on=1;
        if((sequence!=poly_seq_config.sequence && (on || old!=i || owners[i]!=i)) || old!=owners[i] ||
           (on && (states[i]!=poly_seq_config.states[i] || (i<8 && poly_modes[i]!=poly_next_modes[i])))) {
            old_roots[old]=1;new_roots[owners[i]]=1;
        }
    }
    for(i=0;i<12;i++) {
        affected[i]=0;
        if(!old_roots[poly_seq_config.owners[i]] && !new_roots[owners[i]])continue;
        affected[i]=1;
        bucket=*(volatile u32 **)0x444df434u;
        while(bucket) {
            event=(u32 *)bucket[2];
            while(event) {native_cancel_track(event,i);event=(u32 *)event[19];}
            bucket=(volatile u32 *)bucket[4];
        }
        /* Same release request as a native machine change. The next MAIN
         * render consumes these countdowns, preserving its gate semantics. */
        native_release_track(i,0x7fffu);
        /* Destructive setup: copy new voices, never restore removed voices.
         * A PLAY-only change or a decrease makes no new base Sound copy. */
        if(i<8) {
            if(owners[i]<i && (owners[i]!=poly_seq_config.owners[i] || sequence!=poly_seq_config.sequence))
                poly_copy_group(i,owners[i]);
        }else if(poly_seq_config.owners[i]<i && owners[i]==i) {
            u32 kit=*(volatile u32 *)0x43bd843cu;
            if(kit)native_publish_sound((const volatile u8 *)(kit+0x2au+i*0x123u),i);
        }
    }
    for(i=0;i<12;i++)poly_seq_config.states[i]=states[i];
    for(i=0;i<12;i++)poly_seq_config.owners[i]=owners[i];
    for(i=0;i<8;i++)poly_modes[i]=poly_next_modes[i];
    poly_play_maps(poly_seq_config.owners);
    poly_has_groups=0;poly_analog_active=0;poly_publish_end=1;poly_slave_mask=0;
    for(i=1;i<12;i++)if(owners[i]<i) {
        if(!poly_has_groups)poly_publish_first=i;
        poly_has_groups=1;poly_publish_end=i+1;
        if(i>=8)poly_slave_mask|=1u<<i;
        if(i>=8)poly_analog_active=1;
    }
    /* Analog TYPE is native, so publish its master's Sound at group apply. */
    for(i=8;i<12;i++)if(owners[i]<i) {
        u32 kit=*(volatile u32 *)0x43bd843cu;
        if(kit)native_publish_sound((const volatile u8 *)(kit+0x2au+owners[i]*0x123u),i);
    }
    for(i=8;i<10;i++)poly_analog_type[i-8]=*(volatile u8 *)(0x80002f50u+i);
    poly_native_interest();
    poly_seq_config.sequence=sequence;
    poly_seq_config.generation++;
    if(!poly_seq_config.generation)poly_seq_config.generation=1;
    /* A group edited while stopped must not start from statics prepared
     * under the previous topology. Only the same sequence is rebuilt: a new
     * pattern is prepared by its own native 4008c0b0 pass. */
    if(sequence==*(volatile u32 *)0x43bd8430u) {
        for(i=0;i<12;i++)
            if(affected[i] && owners[i]<i && *(volatile u32 *)(0x43bd83c8u+i*4u)!=1)PREP_EVENT(i)[1]=0;
        for(i=0;i<12;i++)
            if(affected[i] && owners[i]==i)prep_rebuild((const volatile u8 *)sequence,i);
    }
    return 1;
}

static u32 *poly_trig_synced(u32 track,const volatile u8 *seq,u32 kit,u32 step,u32 *event,u32 *time)
{
    u32 generation,i;
    u32 *result;
    generation=poly_seq_config.generation;
    if(track<13)poly_seq_config.pending[track].event=0;
    if(track<12 && poly_seq_config.sequence==(u32)seq && poly_seq_config.owners[track]<track) {
        u32 master=poly_seq_config.owners[track];
        /* Static first-step preparation of a SLAVE: take the master's. */
        if(event==(u32 *)PREP_EVENT(track) && time && prep_generation[master]==generation &&
           prep_fill(seq,master,track-master,PREP_TIME(master))) {
            *time=(u32)PREP_TIME(track);
            return event;
        }
        if(event)event[1]=0;
        return (u32 *)0;
    }
    result=stock_trig(track,seq,kit,step,event,time);
    if(track<12 && event==(u32 *)PREP_EVENT(track) && poly_seq_config.sequence==(u32)seq &&
       generation==poly_seq_config.generation && poly_seq_config.states[track]>=3) {
        /* Master preparation: 4008c0b0 has not yet published its time. */
        prep_step[track]=(u8)step;
        prep_generation[track]=generation;
        if(result && time)prep_fill_group(seq,track,(s32)*time);
        else for(i=1;i+1u<poly_seq_config.states[track];i++)PREP_EVENT(track+i)[1]=0;
    }
    if(!result)return result;
    if(track>=12)return result;
    if(poly_seq_config.sequence!=(u32)seq)return result;
    if(generation!=poly_seq_config.generation)return result;
    if(poly_seq_config.states[track]<3)return result;
    poly_seq_config.pending[track].sequence=(u32)seq;
    poly_seq_config.pending[track].step=step;
    poly_seq_config.pending[track].generation=generation;
    poly_seq_config.pending[track].event=(u32)result;
    return result;
}

u32 *poly_trig(u32 track,const volatile u8 *seq,u32 kit,u32 step,u32 *event,u32 *time)
{
    poly_sync();
    return poly_trig_synced(track,seq,kit,step,event,time);
}

/* Bound specifically to the main sequencer's enqueue call at 4008cfc4.
 * Other enqueue callers retain the original function and ABI unchanged. */
u32 poly_sequence_enqueue(u32 *event,u32 time)
{
    u32 track=event[2],count,i;
    u32 *batch[4];
    volatile struct pending *pending;
    if(track>=12)return stock_enqueue(event,time);
    pending=&poly_seq_config.pending[track];
    if(pending->event!=(u32)event)return stock_enqueue(event,time);
    pending->event=0;
    if(pending->generation!=poly_seq_config.generation || pending->sequence!=poly_seq_config.sequence) {
        if(!event[0])native_event_free(event);
        return 0;
    }
    count=poly_prepare(event,(const volatile u8 *)pending->sequence,pending->step,
                           poly_seq_config.states[track]-1u,batch);
    if(!count) {
        /* A failed reservation has rolled back all child refs. Keep the
         * original master behavior when the native queue can accept it. */
        batch[0]=event;
        if(poly_submit(batch,1,time,0))return 1;
        if(!event[0])native_event_free(event);
        return 0;
    }
    if(poly_submit(batch,count,time,0)) {
        if(!event[0])native_event_free(event);
        return 1;
    }
    for(i=0;i<count;i++)native_event_free(batch[i]);
    if(!event[0])native_event_free(event);
    return 0;
}
