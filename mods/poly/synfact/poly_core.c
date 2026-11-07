/*  common state. File-owned heap storage, supplied by the existing plugin
 * image allocation. No fixed SRAM reservation or owning Sound copies. */
#define DATA __attribute__((section(".data")))
#include "poly_event.c"
#include "poly_groups.c"
#include "poly_pattern.c"
static u8 poly_modes[8],poly_next_modes[8];
static void poly_play_maps(const volatile u8 *);
static void poly_copy_group(u32,u32);
#include "poly_sequence.c"
#include "poly_publication.c"
#include "poly_play.c"
#include "poly_copy.c"
#include "poly_type.c"
/* Generic core parameter transport owns all machine frames. */

volatile struct config poly_seq_config DATA={1,0,{0,0,0,0,0,0,0,0,0,0,0,0},
    {0,1,2,3,4,5,6,7,8,9,10,11},{{0,0,0,0}}};
#ifndef POLY_HOST_TEST
__asm__(".globl poly_owner_map\n.set poly_owner_map,poly_seq_config+20");
#else
__asm__(".globl _poly_owner_map\n.set _poly_owner_map,_poly_seq_config+20");
#endif
static u8 record_cache[7] DATA={0};
/* SyntHack: the record's bytes 1..2 and 3..6 as an aligned word and long (sequence+0x21382/+0x21384), so the
 * per-block fast path of poly_sync compares three values instead of looping over seven bytes. */
static u16 cache_word DATA=0;
static u32 cache_long DATA=0;
static u32 cache_sequence DATA=0;
static u32 cache_midi_mask DATA=0xffffffffu;
static u32 preview_notes[12][4] DATA={{0}};
static u32 preview_generation[12] DATA={0};
static u32 preview_depth DATA=0;

u32 poly_effective_owner(u32 track) {return track<12?poly_owner_map[track]:track;}

/* Called at the early MAIN frame boundary and before sequencer construction.
 * UI edits are committed under the same native interrupt exclusion. */
static u32 poly_sync_locked(void)
{
    volatile u32 i,changed=0,midi_bit;
    u32 kit=*(volatile u32 *)0x43bd843cu,midi_mask,j,width;
    u8 states[12];
    const volatile u8 *sequence=*(const volatile u8 **)0x43bd8430u;
    const volatile u8 *record;
    if(!sequence)return 0;
    midi_mask=kit?*(volatile u16 *)(kit+0x1550u):0xffffu;
    record=sequence+0x21381u;
    if((u32)sequence!=cache_sequence)changed=1;
    if(midi_mask!=cache_midi_mask)changed=1;
    for(i=0;i<7;i++)if(record[i]!=record_cache[i])changed=1;
    if(!changed)return 1;
    poly_decode(record,states,poly_next_modes);
    /* A saved group can be loaded with a KIT whose member is now MIDI.
     * Suspend only that group; retain its recorded topology for audio mode. */
    for(i=0;i<12;i++)if(states[i]>=3u) {
        width=states[i]-1u;
        for(j=i;j<i+width;j++) {
            midi_bit=(midi_mask>>j)&1u;
            if(midi_bit){states[i]-=3u;break;}
        }
        i+=width-1u;
    }
    if(!poly_commit((u32)sequence,states))return 0;
    for(i=0;i<7;i++)record_cache[i]=record[i];
    cache_word=(u16)(record[1]<<8|record[2]);
    cache_long=(u32)record[3]<<24|(u32)record[4]<<16|(u32)record[5]<<8|record[6];
    cache_sequence=(u32)sequence;
    cache_midi_mask=midi_mask;
    return 1;
}

static u32 poly_record_settings_locked(u32 track,u32 enabled,u32 voices,u32 mode)
{
    u8 states[12],owners[12],raw[7],modes[8];
    volatile u32 i,midi_bit;
    volatile u8 *sequence=*(volatile u8 **)0x43bd8430u;
    u32 kit=*(volatile u32 *)0x43bd843cu;
    if(!sequence || !kit || voices<2 || voices>poly_max_voices(track))return 0;
    poly_sync_locked();
    if(poly_seq_config.owners[track]!=track)return 0;
    /* Keep suspended groups in the persistent record when another master is
     * edited. Runtime states can differ only because of the current MIDI KIT. */
    poly_decode(sequence+0x21381u,states,modes);
    if(track<8 && mode<2)modes[track]=(u8)mode;
    states[track]=(u8)(voices-2u+(enabled?3u:0u));
    if(!poly_resolve(states,owners))return 0;
    /* Do not silently convert existing MIDI tracks into digital voices. */
    if(enabled)for(i=track;i<track+voices;i++) {
        midi_bit=(*(volatile u16 *)(kit+0x1550u)>>i)&1u;
        if(midi_bit)return 0;
    }
    poly_encode(raw,states,modes);
    for(i=0;i<7;i++)sequence[0x21381u+i]=raw[i];
    return poly_sync_locked();
}

static u32 poly_record_write_locked(u32 track,u32 enabled,u32 voices)
{return poly_record_settings_locked(track,enabled,voices,4);}

static u32 poly_mode_write(u32 track,u32 mode)
{
    u32 command[6]={0x504f4c59u,0x43464732u,track,mode,0,0};
    native_immediate(command);return command[5];
}

/* Only UI reads machine IDs: never scan them from the audio fast path. */
static void poly_analog_publish_locked(void)
{
    u32 t,i,kit=*(volatile u32 *)0x43bd843cu;
    if(!kit)return;
    for(t=8;t<10;t++)if(poly_seq_config.states[t]>=3) {
        u8 type=*(volatile u8 *)(0x80002f50u+t);
        if(type==poly_analog_type[t-8])continue;
        for(i=t+1;i<t+poly_seq_config.states[t]-1u;i++)
            native_publish_sound((const volatile u8 *)(kit+0x2au+t*0x123u),i);
        poly_analog_type[t-8]=type;
    }
}

static void poly_analog_ui(void)
{
    u32 t;
    if(!poly_analog_active)return;
    for(t=8;t<10;t++)if(poly_seq_config.states[t]>=3 &&
        *(volatile u8 *)(0x80002f50u+t)!=poly_analog_type[t-8]) {
        u32 command[6]={0x504f4c59u,0x414e4c47u,0,0,0,0};
        native_immediate(command);break;
    }
}

/* The existing native immediate queue entry supplies its SR save/mask/restore
 * around a private stack command. The hook consumes the command before the
 * stock queue sees any fields; no event/lock/bucket is allocated or enqueued.
 * This keeps multi-byte pattern writes and config publication atomic without
 * injecting new privileged instructions or changing native lock routines. */
u32 poly_sync(void)
{
    u32 command[6],kit,i;
    const u8 *sequence=*(const u8 *const volatile *)0x43bd8430u;
    /* : called on every published block (1500/s), Sound write and draw.
     * Read-only fast path: when the sequence, MIDI mask and topology record
     * still equal the last committed ones and no recording fixup is pending,
     * the locked pass would change nothing. Any difference takes it. */
    if(sequence && (u32)sequence==cache_sequence) {
        kit=*(volatile u32 *)0x43bd843cu;
        if((kit?*(volatile u16 *)(kit+0x1550u):0xffffu)==cache_midi_mask) {
            /* SyntHack: aligned compares when the sequence is (pattern objects are) */
            if(!((u32)sequence&3u)) {
                if(sequence[0x21381u]==record_cache[0] && *(const u16 *)(sequence+0x21382u)==cache_word &&
                   *(const u32 *)(sequence+0x21384u)==cache_long)return 1;
            }else {
                for(i=0;i<7;i++)if(sequence[0x21381u+i]!=record_cache[i])break;
                if(i==7)return 1;
            }
        }
    }
    command[0]=0x504f4c59u;command[1]=0x53594e43u;
    command[2]=0;command[3]=0;command[4]=0;
    command[5]=0;native_immediate(command);return command[5];
}

u32 poly_record_write(u32 track,u32 enabled,u32 voices)
{
    u32 command[6];
    command[0]=0x504f4c59u;command[1]=0x43464731u;
    command[2]=track;command[3]=enabled;command[4]=voices;
    command[5]=0;native_immediate(command);return command[5];
}

void poly_preview(u32 *event)
{
    u32 track=event[2],step,count=0,i;
    u32 *batch[4];
    if(track>=12 || event[3]!=1 || event[11]){native_immediate(event);return;}
    poly_sync();
    if(poly_seq_config.owners[track]<track) {
        if(!event[0])native_event_free(event);
        return;
    }
    /* CHORUS_CODEC: native long (401055be/cmp.l), -1 = none; the .. byte read
     * took its high byte, i.e. step 0 for any held step. */
    step=*(volatile u32 *)0x402d5aacu;
    if(event[1]==1 && poly_seq_config.states[track]>=3 && step<64) {
        count=poly_prepare(event,(const volatile u8 *)poly_seq_config.sequence,step,
                           poly_seq_config.states[track]-1u,batch);
        if(count && poly_submit(batch,count,0,1)) {
            for(i=0;i<4;i++)preview_notes[track][i]=128;
            for(i=0;i<count;i++)preview_notes[track][batch[i][2]-track]=batch[i][6];
            preview_generation[track]=poly_seq_config.generation;
            if(!event[0])native_event_free(event);
            return;
        }
        while(count)native_event_free(batch[--count]);
    }else if(event[1]!=1 && preview_generation[track]==poly_seq_config.generation) {
        for(i=0;i<4;i++)if(preview_notes[track][i]<128) {
            batch[count]=copy_event(event);
            if(!batch[count])break;
            poly_voice_target(batch[count],track,i);
            batch[count][6]=preview_notes[track][i];count++;
        }
        if(i==4 && count && poly_submit(batch,count,0,1)) {
            preview_generation[track]=0;
            if(!event[0])native_event_free(event);
            return;
        }
        while(count)native_event_free(batch[--count]);
    }
    native_immediate(event);
}

/* Live notes (internal keyboard, TRIG keys, step preview, MIDI note input)
 * reach the native immediate queue from 40119684 with kind 2; +4 is 1 for on
 * and 2 for off, after that function's per-track note priority.
 *
 * : the origin decides the POLY behavior. Keys of the KEYBOARD mode and
 * MIDI note input play one voice per key; everything else (a track's TRIG
 * key, a held step's preview) plays the chord. The origin is the native
 * caller still on the stack: KEYBOARD press 4002e850 (returns to 4002ed0a)
 * and its release callback 4002d5f2 (4002d602); MIDI channel input 401052da
 * (40105408) and its release loop 401051ae (401052c4). Only live frames
 * above this function are read, never written. */
static u32 poly_live_from_keys(void)
{
#ifdef POLY_HOST_TEST
    return poly_test_origin;
#else
    const volatile u16 *stack;
    u32 i,word,sp;
    __asm__ volatile("move.l %%sp,%0":"=d"(sp));
    stack=(const volatile u16 *)sp;
    for(i=0;i<1024;i++) {
        word=((u32)stack[i]<<16)|stack[i+1];
        /* 2 = a key press (recorded by the native recorder); 1 = a release,
         * whose native last-note re-send is not a new key. */
        if(word==0x4002ed0au || word==0x401055CCu)return 2;
        if(word==0x4002d602u || word==0x40105488u)return 1;
    }
    return 0;
#endif
}

/*  live recording of played chords. The native live recorder 4001ecb6
 * runs in the UI loop from the note message of 40104c02; on an audio track it
 * keeps one note per step (NOTE = played note, NOT2..NOT4 = FFh = inherit the
 * track defaults) in the UI pattern model. The sequencer reads its own copy
 * (43bd7430), refreshed from that model, so the  fixup of that copy alone
 * was lost. : a chord is the set of keys held together that fall on the
 * same recorder step. Each key press while live recording (same test as
 * 400087d6 -> 400c2f6a) notes the step the recorder will use (4008da6e on the
 * same clock, clamp, 4002a3b6 remap). In the UI loop (draw dispatch), once the
 * recorder has written that step for the newest note (NOTE = note, NOT2..NOT4
 * = FFh), the step gets the played chord as its own trig values, in the model
 * and in the sequencer copy: NOTE = first key, NOT2..NOT4 = the other keys as
 * intervals, unused ones OFF (64). Existing step values and track defaults
 * are not used. */
struct rec_chord {u32 sequence,age;u8 dirty,step,count,notes[4];};
static struct rec_chord rec_chords[12] DATA={{0}};

static u32 poly_rec_active(void)
{
    u32 state=*(volatile u32 *)0x43bd8424u|*(volatile u32 *)0x43bd83bcu;
    u32 object=*(volatile u32 *)0x444e23ecu;
    return state==1 && object && *(volatile u8 *)(object+0x169u);
}

static void poly_rec_note(u32 track,u32 note,u32 held)
{
    u8 position[4];
    s32 step;
    const volatile u8 *data;
    struct rec_chord *chord=&rec_chords[track];
    u32 length;
    if(!poly_seq_config.sequence || !poly_rec_active())return;
    data=(const volatile u8 *)poly_seq_config.sequence+track*0x499u;
    POLY_CALL(0x4008dae6u,void (*)(u32,u32,u8 *))(*(volatile u32 *)0x800046ecu,track,position);
    step=(s32)(signed char)position[0];
    if(step<0)step=0;
    if(step>63)step=63;
    length=data[0x458];
    if(length) {
        step=(s32)(signed char)data[0x459u+(u32)step%length];
        if(step<0)step=0;
        if(step>63)step=63;
    }
    if(held && chord->count && chord->step==(u8)step && chord->sequence==poly_seq_config.sequence) {
        if(chord->count>=4)return;
        chord->notes[chord->count++]=(u8)note;
    }else {
        chord->sequence=poly_seq_config.sequence;chord->step=(u8)step;
        chord->notes[0]=(u8)note;chord->count=1;
    }
    chord->age=0;
    chord->dirty=1;
}

/* UI loop only (draw dispatch): the same context as the native recorder. */
void poly_rec_ui(void)
{
    u32 t,k,interval,app,pattern,trk;
    volatile u8 *model,*mirror;
    struct rec_chord *chord;
    u8 lanes[4];
    for(t=0;t<12;t++) {
        chord=&rec_chords[t];
        if(!chord->dirty)continue;
        if(chord->sequence!=poly_seq_config.sequence || ++chord->age>2000u){chord->dirty=0;continue;}
        app=*(volatile u32 *)0x444e23f4u;
        if(!app)continue;
        pattern=POLY_CALL(0x40019000u,u32 (*)(u32))(app);
        if(!pattern)continue;
        trk=pattern+(t+1u)*0x70u;
        model=(volatile u8 *)((u32 (*)(u32))(*(u32 **)trk)[0x28/4])(trk);   /* SyntHack: pointer in d0 */
        if(!model)continue;
        model+=chord->step;
        /* The recorder has not written the newest key of this step yet. */
        if(model[0x2c0]!=chord->notes[chord->count-1u] || model[0x300]!=255u || model[0x340]!=255u ||
           model[0x380]!=255u)continue;
        lanes[0]=chord->notes[0];
        for(k=1;k<4;k++) {
            lanes[k]=64;
            if(k<chord->count) {
                interval=(u32)chord->notes[k]+64u-chord->notes[0];
                if(interval<=127u)lanes[k]=(u8)interval;
            }
        }
        mirror=(volatile u8 *)poly_seq_config.sequence+t*0x499u+chord->step;
        for(k=0;k<4;k++){model[0x2c0u+k*0x40u]=lanes[k];mirror[0x2c0u+k*0x40u]=lanes[k];}
        chord->dirty=0;
    }
}

/* FM_LAYOUT: each held key takes one voice of the group, like a polyphonic synth:
 * a press goes to a free voice (round robin after the last one used, else the
 * oldest note is stolen) and its release to the voice that holds it. The
 * event itself is retargeted to that voice and continues on the native path;
 * nothing is allocated. Releasing the current note makes the native last-note
 * priority re-send the newest held key: if that key still sounds on its voice
 * the repeat is absorbed, if it was stolen it takes a voice again. A release
 * of a stolen key is absorbed. */
static u8 live_notes[12][4] DATA={{0}};
static u32 live_age[12][4] DATA={{0}};
static u32 live_clock DATA=0;
static u32 live_next[12] DATA={0};
static u32 live_generation[12] DATA={0};

static u32 poly_live_keys(u32 *event,u32 track,u32 voices,u32 press)
{
    u32 note=event[6],i,v,voice=4,oldest=0xffffffffu,held=0;
    if(live_generation[track]!=poly_seq_config.generation) {
        /* A release from before a group change keeps the native path. */
        if(event[1]!=1)return 0;
        for(i=0;i<4;i++)live_notes[track][i]=128;
        live_next[track]=0;
        live_generation[track]=poly_seq_config.generation;
    }
    for(i=0;i<voices;i++)if(live_notes[track][i]==note){voice=i;break;}
    if(event[1]==1) {
        if(voice<4) {
            if(!event[0])native_event_free(event);
            return 1;
        }
        for(i=0;i<voices;i++)if(live_notes[track][i]<128)held=1;
        for(i=0;i<voices;i++) {
            v=live_next[track]+i;
            if(v>=voices)v-=voices;
            if(live_notes[track][v]>127){voice=v;break;}
        }
        if(voice>=4)for(i=0;i<voices;i++)if(live_age[track][i]<oldest) {
            oldest=live_age[track][i];voice=i;
        }
        live_notes[track][voice]=(u8)note;
        live_age[track][voice]=++live_clock;
        live_next[track]=voice+1u<voices?voice+1u:0;
        if(press==2)poly_rec_note(track,note,held);
    }else {
        if(voice>=4) {
            if(!event[0])native_event_free(event);
            return 1;
        }
        live_notes[track][voice]=128;
    }
    /* Voice 0 is the master's own event, untouched; SLAVE fields as FM_FAST. */
    if(voice)poly_voice_target(event,track,voice);
    return 0;
}

/* FM_FAST chord (restored in  for TRIG keys and step preview): the master's
 * note also plays NOT2..NOT4 (held step lane, else the defaults) on its SLAVE
 * voices. A note-off repeats each voice's offset, so the native handling of
 * a non-current note is mirrored, not reinterpreted. */
static u32 chord_root[12] DATA={0};
static u8 chord_notes[12][4] DATA={{0}};
static u32 chord_generation[12] DATA={0};

static u32 poly_live_chord(u32 *event,u32 track,u32 voices)
{
    u32 root=event[6],i,count=1,step;
    u32 *batch[4];
    s32 note;
    batch[0]=event;
    if(event[1]==1) {
        step=*(volatile u32 *)0x402d5aacu;
        for(i=1;i<4;i++)chord_notes[track][i]=128;
        for(i=1;i<voices;i++) {
            note=poly_chord_note((const volatile u8 *)poly_seq_config.sequence,track,step,i,root);
            if(note<0)continue;
            chord_notes[track][i]=(u8)note;
        }
    }else if(chord_generation[track]!=poly_seq_config.generation)return 0;
    for(i=1;i<voices;i++) {
        if(chord_notes[track][i]>127)continue;
        note=(s32)chord_notes[track][i]+(s32)root-(s32)chord_root[track];
        if(event[1]==1)note=chord_notes[track][i];
        if(note<0 || note>(track<8?127:84))continue;
        batch[count]=copy_event(event);
        if(!batch[count])break;
        poly_voice_target(batch[count],track,i);
        batch[count][6]=(u32)note;count++;
    }
    if(i<voices || !poly_submit(batch,count,0,1)) {
        /* Never a partial chord; the master keeps its native behavior. */
        while(count>1)native_event_free(batch[--count]);
        if(event[1]==1)chord_generation[track]=0;
        return 0;
    }
    if(event[1]==1) {
        chord_root[track]=root;
        chord_generation[track]=poly_seq_config.generation;
    }else if(root==chord_root[track])chord_generation[track]=0;
    return 1;
}

static u32 poly_live_locked(u32 *event)
{
    u32 track=event[2],note=event[6],voices,i,origin;
    if(event[1]!=1 && event[1]!=2)return 0;
    poly_sync_locked();
    if(poly_seq_config.owners[track]<track) {
        /* A SLAVE plays only through its master. */
        if(!event[0])native_event_free(event);
        return 1;
    }
    if(poly_seq_config.states[track]<3 || note>127)return 0;
    voices=poly_seq_config.states[track]-1u;
    if(event[1]==2 && live_generation[track]==poly_seq_config.generation)
        for(i=0;i<voices;i++)if(live_notes[track][i]==note)return poly_live_keys(event,track,voices,0);
    origin=poly_live_from_keys();
    if(origin)return poly_live_keys(event,track,voices,origin);
    return poly_live_chord(event,track,voices);
}

/* This hook runs after the original native function has saved SR and raised
 * its IRQ mask. Recursive submissions take its original continuation only. */
u32 poly_preview_locked(u32 *event)
{
    u32 track=event[2];
    if(event[0]==0x504f4c59u) {
        if(event[1]==0x434f5059u) {
            event[5]=poly_copy_pending;poly_copy_pending=0;return 1;
        }
        if(event[1]==0x43464731u) {
            event[5]=poly_record_write_locked(event[2],event[3],event[4]);return 1;
        }
        if(event[1]==0x43464732u) {
            if(event[2]<8 && event[3]<2 && poly_seq_config.states[event[2]]>=3)
                event[5]=poly_record_settings_locked(event[2],1,poly_seq_config.states[event[2]]-1,event[3]);
            return 1;
        }
        if(event[1]==0x414e4c47u) {poly_analog_publish_locked();return 1;}
        if(event[1]==0x53594e43u) {event[5]=poly_sync_locked();return 1;}
    }
    if(preview_depth || track>=12)return 0;
    if(event[3]==2) {
        u32 handled;
        preview_depth=1;
        handled=poly_live_locked(event);
        preview_depth=0;
        return handled;
    }
    if(event[3]!=1 || event[11])return 0;
    poly_sync_locked();
    if(poly_seq_config.owners[track]==track &&
       (poly_seq_config.states[track]<3 ||
        (*(volatile u32 *)0x402d5aacu>=64 &&
         preview_generation[track]!=poly_seq_config.generation)))return 0;
    preview_depth=1;
    poly_preview(event);
    preview_depth=0;
    return 1;
}

u32 poly_sound_write_allowed(u32 track)
{
    volatile u32 allowed=0;
    poly_sync();
    if(track>=12)return 1;
    if(poly_seq_config.owners[track]==track) {
        allowed=1;
        if(track<8 && poly_seq_config.states[track]>=3)poly_copy_mark(track);
    }
    return allowed;
}

#include "poly_ui.c"
