/* Native views retain their vtables and owning models. All POLY dispatch lives
 * in the existing file-owned hook table, so replacing the machine file leaves
 * no callbacks or data pointers inside native views. */
#define UI_GET POLY_CALL(0x40039160u,u32 (*)(void *,u32,u8 *))
#define UI_TEXT POLY_CALL(0x400f8bd0u,void (*)(void *,void *,s32,s32,u32,const char *,const char *))
#define UI_FILL POLY_CALL(0x400f7fb6u,void (*)(void *,s32,s32,s32,s32,u32))
#define UI_RECT POLY_CALL(0x400f7d9au,void (*)(void *,s32,s32,s32,s32,u32))
#define UI_TOGGLE POLY_CALL(0x400703DAu,void (*)(void *,u32,void *,s32,s32,u32))
static u32 poly_layout_view DATA=0;
static u32 poly_trig_layout[11] DATA={0};
/*  page, as the native MIDI TRIG page (40041076..40041530): positions
 * 0..3 are the top row (encoders A..D), 4..7 the bottom row (E..H).
 * Top: POLY, VOICES. Bottom: NOTE, then NOT2/NOT3/NOT4 under the keyboard.
 * POLY OFF leaves only POLY: the other controls are neither drawn nor edited. */
static const u32 poly_control_ids[9]={0,0,0,0,0x15,0x1e,0x1f,0x20,10};
static const u32 poly_analog_ids[9]={0,0,0,0,0x14,0x1e,0x1f,0x20,10};
static const u32 poly_off_ids[9]={0,0,0,0,0,0,0,0,10};

u32 poly_ui_parameter_view(u8 *view)
{
    u32 vt=*(u32 *)view;
    volatile u32 qualified=0;
    /* SyntHack: 1.41 0x40338600 (end of code) is unmapped; on 1.42 the zero fill starts at 0x40339740 */
    if(vt<0x40000408u || vt>=0x40339740u)return 0;
    if(((const u32 *)vt)[0x88/4]==0x4003792cu)qualified=1;
    return qualified;
}

u32 poly_ui_track(u8 *view)
{
    u32 model=*(u32 *)(view+0x74);
    if(!model)return 0xffffffffu;
    return POLY_CALL(0x4001ff74u,u32 (*)(u32))(model);
}

u32 poly_ui_slave(u8 *view)
{
    u32 track;
    volatile u32 answer=0;
    if(!poly_ui_parameter_view(view))return 0;
    track=poly_ui_track(view);
    if(track>=12)return 0;
    poly_sync();
    if(poly_seq_config.owners[track]<track)answer=1;
    return answer;
}

void poly_ui_sync(u8 *view)
{
    u32 key,vt=*(u32 *)view,track;
    u32 *pages,*replacement,count;
    /* The draw queue also contains small, unrelated widgets. Qualify the
     * immutable ParameterView vtable before reading any derived fields. */
    if(!poly_ui_parameter_view(view))return;
    key=*(u32 *)(view+0x88);
    if(key<0x12 || key>0x18)return;
    track=poly_ui_track(view);if(track>=13)return;
    if(vt!=0x401c9a9cu)return;
    pages=*(u32 **)(view+0x7c);
    if(!pages)return;
    count=(*(u32 *)(view+0x80)-(u32)pages)/4u;
    /* MainScreen 4003209c selects bank +140h for digital tracks 0..7:
     * ROM 401c7f84 [2,3]. Analog is +f8h / 401c7fcc [1,3];
     * MIDI is +188h / 401c7f74 [26,3]. All share this TRIG vtable. */
    /* SyntHack: no third TRIG page on analog tracks (analog POLY not ported) */
    if(track>=8 || pages[0]!=(track<8?2u:1u)) {
        if(count==3 && pages[2]==3u) {
            *(u32 *)(view+0x80)=(u32)(pages+2);
            if(*(u32 *)(view+0x90)>1)*(u32 *)(view+0x90)=0;
        }
        return;
    }
    if(count!=2)return;
    if(*(u32 *)(view+0x84)-(u32)pages<12u) {
        replacement=(u32 *)POLY_CALL(0x4010394Cu,u32 (*)(u32))(12);   /* SyntHack: pointer in d0 */
        if(!replacement)return;
        replacement[0]=pages[0];replacement[1]=pages[1];replacement[2]=3;
        POLY_CALL(0x40103958u,void (*)(void *))(pages);
        pages=replacement;
        *(u32 *)(view+0x7c)=(u32)pages;
        *(u32 *)(view+0x84)=(u32)(pages+3);
    }else pages[2]=3;
    *(u32 *)(view+0x80)=(u32)(pages+3);
}

u32 poly_ui_third(u8 *view)
{
    volatile u32 answer=0;
    if(*(u32 *)view!=0x401c9a9cu)return 0;
    if(poly_ui_track(view)>=8)return 0;   /* SyntHack: digital tracks only */
    if(*(u32 *)(view+0x90)==2)answer=1;
    return answer;
}

/* The effective state, after poly_sync suspends groups containing MIDI. */
static u32 poly_ui_on(u8 *view)
{
    u32 track=poly_ui_track(view);
    volatile u32 answer=0;
    if(track>=12)return 0;
    poly_sync();
    if(poly_seq_config.states[track]>=3)answer=1;
    return answer;
}

static const u32 *poly_ui_ids(u8 *view)
{
    if(poly_ui_on(view))return poly_ui_track(view)<8?poly_control_ids:poly_analog_ids;
    return poly_off_ids;
}

u32 poly_ui_layout(u32 page)
{
    u32 i;u8 *view=(u8 *)poly_layout_view;const u32 *native,*ids;
    if(page!=3 || !view || !poly_ui_third(view))return 0;
    native=stock_page_layout(3);ids=poly_ui_ids(view);
    poly_trig_layout[0]=native[0];poly_trig_layout[1]=native[1];
    for(i=0;i<9;i++)poly_trig_layout[i+2]=ids[i];
    return (u32)poly_trig_layout;
}

u32 poly_ui_control(u8 *view,u32 position)
{
    poly_ui_sync(view);
    if(!poly_ui_third(view))return 0xffffffffu;
    if(position>8)return 0;
    return poly_ui_ids(view)[position];
}

u32 poly_ui_action_begin(u8 *view)
{
    u32 previous=poly_layout_view;
    poly_layout_view=(u32)view;poly_ui_sync(view);return previous;
}
void poly_ui_action_end(u32 previous){poly_layout_view=previous;}

/* UI owns the PatternSettings backing record; the sequencer owns its mirror.
 * Notify through the same virtual method as native settings setters, so later
 * updateMirror/save operations retain the seven-byte topology record. */
static u32 poly_ui_settings_write(u8 *view,u32 track,u32 enabled,u32 voices,u32 mode)
{
    u32 app=*(u32 *)(view+0x68),pattern,i;
    u8 *model,*header;
    const volatile u8 *sequence;
    if(!app)return 0;
    pattern=POLY_CALL(0x40019000u,u32 (*)(u32))(app);
    if(!pattern)return 0;
    model=(u8 *)(pattern+0x2cu);
    header=(u8 *)((u32 (*)(void *))(*(u32 **)model)[0x28/4])(model);   /* SyntHack: pointer in d0 */
    if(!header)return 0;
    if(!(mode<2?poly_mode_write(track,mode):poly_record_write(track,enabled,voices)))return 0;
    poly_copy_ui();
    sequence=*(const volatile u8 **)0x43bd8430u;
    for(i=0;i<7;i++)header[0x21+i]=sequence[0x21381+i];
    ((void (*)(void *,u32))(*(u32 **)model)[0x10/4])(model,0);
    return 1;
}

u32 poly_ui_record_write(u8 *view,u32 track,u32 enabled,u32 voices)
{return poly_ui_settings_write(view,track,enabled,voices,4);}

u32 poly_ui_encoder(u8 *view,void *event)
{
    u32 position,policy,pressed,increment[7],track,state,voices;
    volatile u32 i,enabled;
    s32 delta;
    poly_ui_sync(view);
    /* Shared core editor gate checks slave ownership before subscribers. */
    if(!poly_ui_third(view))return 0;
    if(!POLY_CALL(0x400f67ceu,u32 (*)(void *,u32))(event,0xfffffffdu))return 0;
    position=POLY_CALL(0x400f67f6u,u32 (*)(void *))(event);
    if(position>7)return 0;
    /* Hidden controls are inert; NOTE and NOT2..NOT4 use the native editor. */
    if(position && !poly_ui_on(view))return 1;
    if(position>=4)return 0;
    if(position==3)return 1;
    policy=POLY_CALL(0x4007ba2au,u32 (*)(u32))(0x13);
    for(i=0;i<7;i++)increment[i]=((u32 *)*(u32 *)(policy+16))[i];
    delta=POLY_CALL(0x400f6866u,s32 (*)(void *,u32,u32))(event,*(u32 *)(policy+4),*(u32 *)(policy+8));
    pressed=POLY_CALL(0x400f6884u,u32 (*)(void *))(event);
    delta=POLY_CALL(0x400f6a96u,s32 (*)(void *,u32,s32,void *,u32))(view+0x94,position,delta,increment,pressed);
    if(!delta)return 1;
    track=poly_ui_track(view);poly_sync();state=poly_seq_config.states[track];
    enabled=0;voices=state+2;
    if(state>=3){enabled=1;voices=state-1;}
    if(position==2 && track>=8)return 1;
    if(position==2) {
        /* UI order: POLY, M.LFO; one bounded selection per native increment. */
        poly_ui_settings_write(view,track,enabled,voices,delta>0?0:1);
    }else {
    if(position==0) {if(delta>0)enabled=1;else enabled=0;}
    else if(delta>0){if(voices<poly_max_voices(track))voices++;}
    else if(voices>2)voices--;
    poly_ui_record_write(view,track,enabled,voices);
    }
    POLY_CALL(0x400ffe22u,void (*)(void *))(view);
    return 1;
}

/* Port of the native MIDI TRIG keyboard (40041340..40041530): fifteen
 * 5-pixel white keys at x 48..126, rows 7..23, black keys in rows 14..23,
 * window centred on the chord (native tables 401c979c note->white key and
 * 401c97cc white key->semitone). Notes are native Q8 intervals around NOTE;
 * OFF (interval 0 or >127) and voices beyond VOICES are not marked, exactly
 * as poly_sequence never fires them. Divisions are done by counting. */
#define UI_PATTERN POLY_CALL(0x400f82c8u,void (*)(void *,s32,s32,s32,s32,u32))
static u32 poly_ui_pitch(s32 note)
{
    while(note>=12)note-=12;
    return (u32)note;
}

static u32 poly_ui_black(s32 note)
{
    volatile u32 black=(0x54au>>poly_ui_pitch(note))&1u;
    return black;
}

static u32 poly_ui_marked(const s32 *notes,s32 note)
{
    volatile u32 i,marked=0;
    for(i=0;i<4;i++)if(notes[i]==note)marked=1;
    return marked;
}

void poly_ui_keyboard(void *ctx,const u32 *values,u32 voices)
{
    const s32 *white_of=(const s32 *)0x401c9a3cu,*semitone=(const s32 *)0x401c9a6cu;
    s32 notes[4],low,high,base,start,key,octave,note,x;
    u32 i,interval;
    notes[0]=(s32)(values[0]>>8);low=notes[0];high=notes[0];
    for(i=1;i<4;i++) {
        notes[i]=notes[0];interval=values[i]>>8;
        if(i<voices && interval!=64u && interval<=127u)notes[i]=notes[0]+(s32)interval-64;
        if(notes[i]<low)low=notes[i];
        if(notes[i]>high)high=notes[i];
    }
    base=low+high;if(base<0)base++;
    base=(base>>1)-12;
    if(base>notes[0])base=notes[0];
    if(base<notes[0]-23)base=notes[0]-23;
    if(base<0)base=0;
    else {
        if(poly_ui_black(base))base--;
        if(base>102)base=103;
    }
    start=white_of[poly_ui_pitch(base)];
    key=start;octave=0;
    for(x=51;x!=126;x+=5) {
        note=base+semitone[key]-semitone[start]+octave;
        if(!poly_ui_black(note)) {
            if(poly_ui_marked(notes,note))UI_PATTERN(ctx,x-3,7,x,23,1);
            else UI_FILL(ctx,x-3,7,x,23,1);
        }
        key++;if(key==7){key=0;octave+=12;}
    }
    key=start;octave=0;
    for(x=53;x!=123;x+=5) {
        note=base+semitone[key]-semitone[start]+octave+1;
        if(poly_ui_black(note)) {
            if(poly_ui_marked(notes,note)) {
                UI_FILL(ctx,x-3,13,x+1,24,0);
                UI_PATTERN(ctx,x-2,14,x,23,1);
            }else UI_FILL(ctx,x-2,14,x,23,0);
        }
        key++;if(key==7){key=0;octave+=12;}
    }
}

/* Native ParameterView widget 0xb4 with the MIDI page's arguments: encoder
 * state 400f68aa, lock byte, turning flag 400f6abc. hide=1 keeps only the
 * label (NOT2..NOT4 under the keyboard). */
static void poly_ui_widget(u8 *view,void *ctx,u32 position,u32 id,u32 value,u8 locked,u32 hide)
{
    s32 x=24+26*(s32)(position&3u),y=position<4?27:0;
    u32 state=POLY_CALL(0x400f6a6eu,u32 (*)(void *,u32))(view+0x94,position);
    u32 turning=POLY_CALL(0x400f6c80u,u32 (*)(void *,u32))(view+0x94,position);
    ((void (*)(void *,void *,s32,s32,u32,u32,u32,u32,u32,u32))(*(u32 **)(view))[0xb4/4])
        (view,ctx,x,y,id,value,state,locked,turning,hide);
}

u32 poly_ui_draw(u8 *view,void *ctx)
{
    u32 i,track,state,voices,on=0,id,value,notes[4];u8 locked;
    char number[2];
    /* : UI-loop point after the native live recorder (any view). */
    poly_rec_ui();
    if(!poly_ui_parameter_view(view))return 0;
    poly_ui_sync(view);
    if(poly_ui_slave(view)) {
        UI_FILL(ctx,20,0,127,53,0);
        /* Frame y grows up: TRACK IN on the upper line, SLAVE MODE below. */
        UI_TEXT(ctx,(void *)0x443db230u,74,32,2,"%s","TRACK IN");
        UI_TEXT(ctx,(void *)0x443db230u,74,22,2,"%s","SLAVE MODE");
        return 1;
    }
    if(!poly_ui_third(view))return 0;
    track=poly_ui_track(view);poly_sync();state=poly_seq_config.states[track];
    voices=state+2;if(state>=3){on=1;voices=state-1;}
    UI_FILL(ctx,20,0,127,53,0);
    /* A: POLY, top row. */
    UI_TEXT(ctx,(void *)0x443db230u,33,27,2,"%s","POLY");
    UI_TOGGLE(view,on?256u:0u,ctx,24,34,0);
    if(on) {
        /* B: VOICES, top row. */
        UI_TEXT(ctx,(void *)0x443db230u,59,27,2,"%s","VOICES");
        UI_RECT(ctx,50,34,68,50,1);
        number[0]=(char)('0'+voices);number[1]=0;
        UI_TEXT(ctx,(void *)0x443db210u,59,39,2,"%s",number);
        if(track<8) {
        /* C: PLAY; D: native empty-position bitmap, no control. */
        UI_TEXT(ctx,(void *)0x443db230u,85,27,2,"%s","PLAY");
        UI_TEXT(ctx,(void *)0x443db230u,85,39,2,"%s",
            poly_modes[track]?"POLY":"M.LFO");
        POLY_CALL(0x400f8f70u,void (*)(void *,void *,s32,s32,u32))(ctx,(void *)0x444e00b4u,103,34,0);
        }
        /* E: NOTE; F..H: NOT2..NOT4 labels, then the keyboard over F..H. */
        for(i=0;i<4;i++) {
            id=i?0x1du+i:(track<8?0x15u:0x14u);locked=0;
            value=UI_GET(view,id,&locked);
            notes[i]=value;
            poly_ui_widget(view,ctx,4+i,id,value,locked,i?1:0);
        }
        poly_ui_keyboard(ctx,notes,voices);
    }
    ((void (*)(void *,void *,u32))(*(u32 **)(view))[0xb8/4])(view,ctx,0);
    POLY_CALL(0x4003a1c2u,void (*)(void *,void *,u32,u32,u32))(view,ctx,3,2,7);
    return 1;
}

u32 poly_ui_block_key(u8 *view,void *event)
{
    volatile u32 blocked=0;
    u32 key=POLY_CALL(0x400f978cu,u32 (*)(void *))(event);
    poly_ui_sync(view);
    /* A slave track blocks only the other parameter pages (TRIG 19, SYN 20,
     * FLTR 21, AMP 22, LFO 23); FUNC, TRK, the trigs and the rest pass, so
     * TRK + trig still selects another track with the keyboard open. */
    if(poly_ui_slave(view) && key>=19 && key<=23 && key!=*(u32 *)(view+0x88))blocked=1;
    return blocked;
}
