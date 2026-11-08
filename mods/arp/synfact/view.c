/* SPDX-License-Identifier: GPL-2.0-or-later
 * OS 1.41 plain IView, using the Recorder's native shared-owner lifecycle.
 * Included by module.c; no private code patches or parameter-provider claim.
 */
#include "ui.h"
#include "length.h"
#include <syntakt/pattern.h>
typedef unsigned char arp_u8;
#define UI_CALL(a,t) ((t)(a))
#define ARP_DIRTY UI_CALL(0x400ffe22u,void (*)(void *))
#define ARP_CLOSE UI_CALL(0x400ffec6u,void (*)(void *))
#define ARP_FILLRECT UI_CALL(0x400f7fb6u,void (*)(void *,int,int,int,int,arp_u32))
static arp_u8 *arp_view DATA=0,*arp_manager DATA=0;
static arp_u8 *arp_main DATA=0;
static arp_u32 arp_vtable[19] DATA={0};
static struct arp_double_tap arp_taps DATA={0};
static unsigned int arp_selected DATA=0;
static arp_u32 arp_length_until DATA=0;
static unsigned int arp_length_show DATA=0;
static void *arp_proxy DATA=0;
static arp_u32 arp_ui_sound DATA=0;
static struct arp_settings arp_ui_parameters DATA=ARP_DEFAULT;
static unsigned int arp_lock_mode DATA=0,arp_lock_step DATA=0,arp_lock_shown DATA=0;
static arp_u32 arp_held[2] DATA={0,0};
/* Arp steps held on the trig keys outside REC (bit k = key k = arp step k),
 * and whether an encoder edited them during this hold. */
static arp_u32 arp_steps_held DATA=0;
static unsigned int arp_steps_edited DATA=0;
/* SyntHack: the locks are one packed native lock (locks.h, glue.c), not LFO3's shared service */
/* The application (4016e804) and its active track model (40019036), as
 * 400c34d6, 40019150 and the core's lock preview take them. The lock setter
 * 40017602 (LFO3's lfo3_pattern_set) and getter 4001722a take the active
 * pattern's (40019000) lock model at +620h (40016062), as 4001ef50 passes it;
 * not the pattern itself, nor anything from the parameter view's +68h. */
static void *arp_app(void)
{return (void *)UI_CALL(0x4016e9c8u,arp_u32 (*)(void))();}   /* SyntHack: OS pointers come back in d0 */
static void *arp_pattern_model(void)
{
    void *app=arp_app(),*pattern=app?(void *)UI_CALL(0x40019000u,arp_u32 (*)(void *))(app):0;
    return pattern?(void *)UI_CALL(0x40016062u,arp_u32 (*)(void *))(pattern):0;
}
static void arp_lock_read(void)
{
    unsigned short values[ARP_LOCK_SLOTS];unsigned int i,mask=0;int n;void *model=arp_pattern_model();
    arp_track_read(arp_track,&arp_ui_parameters);arp_lock_shown=0;
    if(!model)return;
    for(i=0;i<ARP_LOCK_SLOTS;i++){
        n=arp_lock_get(model,arp_track,arp_lock_step,i);
        values[i]=n<0?0:(unsigned short)n;if(n>=0)mask|=1u<<i;
    }
    arp_locks_apply(&arp_ui_parameters,mask,values);arp_lock_shown=mask;
}
/* The sequencer's UI state (singleton 4016e8aa), as the parameter view sees it. */
static void *arp_selection(void)
{
    arp_u8 *parameter=arp_main?*(arp_u8 **)(arp_main+0xc0):0;
    return parameter?*(void **)(parameter+0x6c):0;
}
/* Grid REC (400c2e56, +168h, toggled by REC) or live REC (400c2fb6, +16Ah,
 * REC+PLAY). Either way the trig keys belong to the sequencer. */
static int arp_recording(void)
{
    void *selection=arp_selection();
    return selection && ((unsigned char)UI_CALL(0x400c2f02u,arp_u32 (*)(void *))(selection) ||
                         (unsigned char)UI_CALL(0x400c3062u,arp_u32 (*)(void *))(selection));
}
/* The native lock editor's test (40038e42, and the lock preview after
 * 400391a8): trigs selected within the track length (400c34d6), then the
 * 64-step selection itself. The app keeps that selection from the trig keys
 * whichever view is on top; never maintain another mask from key codes or
 * guess the current sequencer page. */
static void arp_lock_sync(void)
{
    void *selection=arp_selection();
    unsigned int i,first=64,previous=arp_lock_mode;
    arp_held[0]=arp_held[1]=0;
    if(selection && (unsigned char)UI_CALL(0x400c3582u,arp_u32 (*)(void *))(selection)){
        for(i=0;i<64;i++)if((unsigned char)UI_CALL(0x400c2e40u,arp_u32 (*)(void *,arp_u32))(selection,i)){
            arp_held[i>>5]|=1u<<(i&31);if(first==64)first=i;
        }
    }
    arp_lock_mode=first<64;
    if(arp_lock_mode){arp_lock_step=first;arp_lock_read();}
    else if(previous)arp_track_read(arp_track,&arp_ui_parameters);
}
/* As the native editor after a lock edit (40038e66): mark the held trigs as
 * locked, so that their release does not toggle them. */
static void arp_lock_mark(void)
{
    void *selection=arp_selection();
    if(selection)UI_CALL(0x400c2de0u,void (*)(void *,arp_u32))(selection,1);
}
static int arp_lock_write(unsigned int slot,unsigned int value)
{
    void *app=arp_app(),*model=arp_pattern_model(),*track=app?st_pattern_active_track(app):0;
    if(slot>=ARP_LOCK_SLOTS || !model || !track || arp_lock_step>=st_pattern_track_length(track) ||
       !arp_lock_set(model,arp_track,arp_lock_step,slot,(int)value))return 0;
    if(!st_pattern_step_present(track,arp_lock_step))
        UI_CALL(0x40029faau,void (*)(void *,arp_u32,arp_u32))(track,arp_lock_step,1);
    arp_lock_read();return 1;
}
/* Encoder push with trigs held: clear that lock on every held step, as the
 * native pages do. -1 deletes (lfo3_pattern_delete's own call). */
static void arp_lock_clear(unsigned int slot)
{
    void *model=arp_pattern_model();unsigned int i,first=arp_lock_step,done=0;
    if(!model || slot>=ARP_LOCK_SLOTS)return;
    for(i=0;i<64;i++)if(arp_held[i>>5]&(1u<<(i&31)))
        if(arp_lock_get(model,arp_track,i,slot)>=0)
            done|=arp_lock_set(model,arp_track,i,slot,-1);
    if(done)arp_lock_mark();
    arp_lock_step=first;arp_lock_read();ARP_DIRTY(arp_view);
}
static arp_u32 proxy_sound(void *proxy)
{
    arp_u32 *vt,*inner;
    if(!proxy || !(vt=*(arp_u32 **)proxy) || vt[0x28/4]!=0x40012986u)return 0;
    inner=*(arp_u32 **)((arp_u8 *)proxy+0x10);
    if(!inner || !*inner)return 0;
    return ((arp_u32 (*)(void *))(*(arp_u32 **)inner)[0x28/4])(inner);
}
static int save_ui_settings(const struct arp_settings *p)
{
    if(proxy_sound(arp_proxy)!=arp_ui_sound || !arp_ui_sound || !eligible(arp_track))return 0;
    if(!arp_track_store(arp_track,p))return 0;
    arp_track_configure(arp_track,p);
    /* Same native model notification as a Sound parameter edit (task only). */
    UI_CALL(0x40013084u,void (*)(void *))(arp_proxy);
    arp_track_read(arp_track,&arp_ui_parameters);return 1;
}
/* Resource descriptors have identical glyph metrics/maps/pixels to DN 1.44.
 * The vtable belongs to Syntakt. These are borrowed ROM fonts, not owning
 * native objects copied from another view. */
static const arp_u32 arp_fonts[2][2]={{0x40240f74u,0x402a76a4u},{0x40240f74u,0x402aa114u}};
static const char *arp_speeds[]={"1/1","1/2","1/3","1/4","1/5","1/6","1/8","1/10","1/12",
    "1/16","1/20","1/24","1/32","1/40","1/48","1/64","1/80","1/96"};
static arp_u32 view_word(const void *v,unsigned int off)
{return *(const arp_u32 *)((const arp_u8 *)v+off);}
static arp_u8 *arp_top(void *app)
{
    arp_u8 *m=(arp_u8 *)app+0x40,*n=*(arp_u8 **)(m+0x1c);
    return n && n!=m+0x14?*(arp_u8 **)(n+8):0;
}
static int arp_foreground(void)
{
    arp_u8 *n;
    if(!arp_view || !arp_manager || arp_view[0x30])return 0;
    n=*(arp_u8 **)(arp_manager+0x1c);
    return n && n!=arp_manager+0x14 && *(arp_u8 **)(n+8)==arp_view;
}
static void arp_dispose(void *v)
{
    if(v==arp_view){arp_view=arp_manager=arp_main=0;arp_proxy=0;arp_ui_sound=0;arp_taps.pending=0;arp_length_show=0;arp_lock_mode=0;
        arp_steps_held=0;arp_steps_edited=0;}
    UI_CALL(0x400fffc0u,void (*)(void *))(v);
}
/* Key LEDs. Each UI frame (400094f4) clears the LEDs, then the view stack
 * (40100856) offers them from the top down to each view that is a
 * LedHandler (dynamic_cast from View 40241b9c to LedHandler 401c7104, then
 * its vtable +8): the first setter of an LED wins (40008220). The view is
 * a View followed by a LedHandler (vptr and a 64-bit claim mask) at +50h,
 * described by its own __vmi_class_type_info (vtable 4024947c), as
 * TrackSelect's (401d42ec) describes its LedHandler at +78h. */
#define ARP_VIEW_BYTES 0x50u
#define ARP_LED_BYTES 12u
/* Palettes as the stock trig LEDs use them: 3 a note trig, 2 unlit (mode 1
 * forces it). ARP_LED_ACTIVE is a guess that needs the hardware. */
#define ARP_LED_ACTIVE 9u
#define ARP_LED_INACTIVE 3u
static const char arp_type_name[]="10ArpSeqView";
static const arp_u32 arp_type[8]={0x4024979cu,(arp_u32)arp_type_name,0,2,
    0x40241ebcu,2u,0x401c73a4u,(ARP_VIEW_BYTES<<8)|2u};
static void arp_led_nothing(void *handler){(void)handler;}
static void arp_view_leds(void *handler,void *claimed,void *offered)
{
    struct arp_settings *p=&arp_ui_parameters;
    unsigned int k,mode,palette;void *mgr;(void)claimed;(void)offered;
    if(!arp_view || handler!=arp_view+ARP_VIEW_BYTES || arp_lock_mode || arp_recording())return;
    mgr=(void *)UI_CALL(0x4016efa4u,arp_u32 (*)(void))();
    for(k=0;k<16;k++){
        if(k>p->length){mode=1;palette=2;}
        else{mode=2;palette=p->enabled&(1u<<k)?ARP_LED_ACTIVE:ARP_LED_INACTIVE;}
        UI_CALL(0x40008220u,void (*)(void *,arp_u32,arp_u32,arp_u32))(mgr,k+1,mode,palette);
    }
}
static const arp_u32 arp_led_vtable[5]={(arp_u32)-(int)ARP_VIEW_BYTES,(arp_u32)arp_type,
    (arp_u32)arp_led_nothing,(arp_u32)arp_led_nothing,(arp_u32)arp_view_leds};
static void arp_text(void *bmp,unsigned int font,int x,int y,unsigned int align,const char *s)
{
    if(font){
        const char *erase=x==14?"ARP XX":y==9?"OFS":y==26?"LEN":"XXX";
        /* Small labels use the native framed-text renderer: its alignment 1
         * means centered, and it takes a font descriptor rather than IFont. */
        UI_CALL(0x400f8ddcu,void (*)(void *,const void *,int,int,arp_u32,arp_u32,const char *,const char *,const char *))
            (bmp,(const void *)arp_fonts[1][1],x,y,align,0,erase,"%s",s);return;
    }
    UI_CALL(0x400f8bd0u,void (*)(void *,const void *,int,int,arp_u32,const char *,const char *))
        (bmp,arp_fonts[0],x,y,align,"%s",s);
}
static void arp_shape(void *bmp,unsigned int kind,int x,int y,int x2,int y2,unsigned int col)
{
    if(kind==ARP_RECT)
        UI_CALL(0x400f7d9au,void (*)(void *,int,int,int,int,arp_u32))(bmp,x,y,x2,y2,col);
    else ARP_FILLRECT(bmp,x,y,x2,y2,col);
}
/* Negative of a p-locked length marker: its colour plane inverted, its mask
 * shared. The blit writes the colour only where the mask is set, so the
 * marker's own silhouette comes out inverted. Rows are one long each (27 px). */
#define ARP_NEGATIVE_LONGS 32u
static arp_u32 arp_negative_plane[ARP_NEGATIVE_LONGS] DATA={0};
static void arp_bitmap(void *bmp,unsigned int resource,int x,int y,unsigned int mode)
{
    arp_u32 rail[7],negative[7];const arp_u32 *entry=(const arp_u32 *)resource;const void *p=(const void *)resource;
    arp_u32 i,n;
    if(resource==0xffffffffu){
        /* Same 27x27 image and mask as DN 40255b58/40255aec; constructed by
         * the native bitmap constructor, then destroyed on the UI task. */
        UI_CALL(0x400f72beu,void (*)(void *,arp_u32,arp_u32,const void *,const void *))
            (rail,27,27,(const void *)0x402eae24u,(const void *)0x402d76bcu);
        p=rail;
    }else if(mode&2){
        /* entry: +4 width, +8 height, +12 stride (longs), +16 colour, +20 mask */
        n=entry[2]*entry[3];
        if(entry[3]==1 && n>0 && n<=ARP_NEGATIVE_LONGS){
            const arp_u32 *colour=(const arp_u32 *)entry[4];
            for(i=0;i<n;i++)arp_negative_plane[i]=~colour[i];
            UI_CALL(0x400f72beu,void (*)(void *,arp_u32,arp_u32,const void *,const void *))
                (negative,entry[1],entry[2],arp_negative_plane,(const void *)entry[5]);
            UI_CALL(0x400f8f70u,void (*)(void *,const void *,int,int,arp_u32))(bmp,negative,x,y,mode);
            UI_CALL(0x400f71f0u,void (*)(void *))(negative);
            return;
        }
    }
    UI_CALL(0x400f8f70u,void (*)(void *,const void *,int,int,arp_u32))(bmp,p,x,y,mode);
    if(resource==0xffffffffu)UI_CALL(0x400f71f0u,void (*)(void *))(rail);
}
static void arp_view_draw(void *v,void *bmp,arp_u32 phase)
{
    struct arp_canvas c={bmp,arp_text,arp_shape,arp_bitmap};
    struct arp_screen s;arp_u32 first,last,count,index;char length[12];(void)phase;
    if(v!=arp_view || !arp_view)return;
    first=*(const volatile arp_u32 *)0x444e0618u;last=*(const volatile arp_u32 *)0x444e061cu;
    count=(last-first)/28u;if(count<24 || count>128)return;
    index=12u+((count-23u)*arp_ui_parameters.note_length>>7);
    s.settings=&arp_ui_parameters;s.track=arp_track;s.selected=arp_selected;
    s.show_length=arp_length_show && (int)(arp_length_until-arp_blocks)>0;
    s.speed_text=arp_speeds[arp_ui_parameters.speed];s.length_text=arp_format_note_length(length,arp_ui_parameters.note_length);
    s.length_bitmap=first+28u*index;
    s.locked=arp_lock_mode?arp_lock_shown:0;
    ARP_FILLRECT(bmp,0,0,127,63,0);arp_draw(&s,&c);
}
static void arp_enc_reset(void);
static int arp_open(void *app,arp_u32 track)
{
    arp_u8 *root,*v,*main,*parameter;void *pair[2],*proxy;arp_u32 sound;
    unsigned int i;struct arp_settings p;
    if(track>=ARP_TRACKS || !eligible(track))return 0;
    main=arp_top(app);if(!main || view_word(main,0)!=0x401c849cu)return 0;
    parameter=*(arp_u8 **)(main+0xc0);if(!parameter || view_word(parameter,0)!=0x401c9a9cu)return 0;
    proxy=(void *)((arp_u32 (*)(void *,arp_u32,int))(*(arp_u32 **)parameter)[0xc4/4])(parameter,0x60u,-1);
    sound=proxy_sound(proxy);if(!sound)return 0;
    arp_track_read(track,&p);
    if(arp_view)return 0;
    root=(arp_u8 *)UI_CALL(0x401036d0u,arp_u32 (*)(arp_u32))(16+ARP_VIEW_BYTES+ARP_LED_BYTES);   /* SyntHack: OS malloc */if((arp_u32)root<0x40000000u)return 0;
    *(arp_u32 *)root=0x401c9910u;*(arp_u32 *)(root+4)=1;*(arp_u32 *)(root+8)=1;
    v=root+16;*(void **)(root+12)=v;
    UI_CALL(0x400ffd6au,void (*)(void *,const char *))(v,"ARPEGGIATOR");
    arp_activate(&p);
    for(i=0;i<sizeof(p);i++)((volatile arp_u8 *)&arp_ui_parameters)[i]=((const arp_u8 *)&p)[i];
    UI_CALL(0x400ffcb8u,void (*)(void *,arp_u32))(v,1);
    for(i=0;i<19;i++)arp_vtable[i]=((const arp_u32 *)0x40241ef4u)[i];
    arp_vtable[1]=(arp_u32)arp_type;arp_vtable[2]=(arp_u32)arp_dispose;*(arp_u32 **)v=arp_vtable+2;
    *(const arp_u32 **)(v+ARP_VIEW_BYTES)=arp_led_vtable+2;
    *(arp_u32 *)(v+ARP_VIEW_BYTES+4)=0;*(arp_u32 *)(v+ARP_VIEW_BYTES+8)=0;
    arp_track=track;arp_proxy=proxy;arp_ui_sound=sound;arp_view=v;arp_main=main;arp_manager=(arp_u8 *)app+0x40;arp_selected=0;
    arp_steps_held=0;arp_steps_edited=0;arp_enc_reset();
    pair[0]=v;pair[1]=root;
    UI_CALL(0x40100d86u,arp_u32 (*)(void *,void *,arp_u32))(arp_manager,pair,0);
    UI_CALL(0x4016dfacu,void (*)(void *))(pair+1);ARP_DIRTY(v);return 1;
}
/* Encoder A..F turns use the stock increment (400f68d2) with control 0x13's
 * policy, as POLY and FM TONE do. The routine keeps one 20-byte record per
 * position p at base+20*p+20, so the block holds six fields from base+20. Its
 * sub-step travel is per field and is cleared when the view opens or the
 * track changes. */
#define ARP_ENC_FIELDS 6
static arp_u8 arp_enc_state[20*(ARP_ENC_FIELDS+1)] DATA={0};
static void arp_enc_reset(void)
{
    unsigned int i;
    for(i=0;i<sizeof(arp_enc_state);i++)((volatile arp_u8 *)arp_enc_state)[i]=0;
}
static int arp_encoder_steps(unsigned int field,const void *event)
{
    arp_u32 policy,increment[7],pressed,i;int delta;
    policy=UI_CALL(0x4007ba2au,arp_u32 (*)(arp_u32))(0x13);
    for(i=0;i<7;i++)increment[i]=((const arp_u32 *)*(const arp_u32 *)(policy+16))[i];
    delta=UI_CALL(0x400f6866u,int (*)(const void *,arp_u32,arp_u32))(event,*(const arp_u32 *)(policy+4),*(const arp_u32 *)(policy+8));
    pressed=UI_CALL(0x400f6884u,arp_u32 (*)(const void *))(event);
    delta=UI_CALL(0x400f6a96u,int (*)(void *,arp_u32,int,void *,arp_u32))(arp_enc_state,field,delta,increment,pressed);
    if(!delta)return 0;
    return delta/256?delta/256:(delta<0?-1:1);
}
static int arp_edit(unsigned int field,int delta)
{
    struct arp_settings p=arp_ui_parameters;int n,limit;
    if(field>5 || !delta || (arp_lock_mode && field>=ARP_LOCK_SLOTS))return 0;
    if(delta>127)delta=127;if(delta< -127)delta=-127;
    n=field==0?p.mode:field==1?p.speed:field==2?p.range:field==3?p.note_length:
        field==4?p.offset[arp_selected]:p.length;
    limit=field==0?4:field==1?17:field==2?3:field==3?127:field==4?24:15;
    if(field==3)n=(int)arp_len_step((unsigned int)n,delta);   /* SyntHack: 56 values (glue.c) */
    else{n+=delta;if(n<(field==4?-24:0))n=field==4?-24:0;if(n>limit)n=limit;}
    if(field==0)p.mode=n;else if(field==1)p.speed=n;else if(field==2)p.range=n;
    else if(field==3)p.note_length=n;else if(field==4)p.offset[arp_selected]=n;else p.length=n;
    if(arp_lock_mode){if(!arp_lock_write(field,(unsigned int)n))return 0;}
    else if(!save_ui_settings(&p))return 0;
    if(field==3){arp_length_until=arp_blocks+1500u;arp_length_show=1;}
    ARP_DIRTY(arp_view);return 1;
}
static void arp_view_tick(void *controller)
{
    arp_u32 now=arp_blocks;(void)controller;
    if(arp_foreground() && arp_main && view_word(arp_main,0xa4)){
        arp_u32 track=UI_CALL(0x4001ff74u,arp_u32 (*)(void *))(*(void **)(arp_main+0xa4));
        if(track!=arp_track){
            arp_u8 *parameter=*(arp_u8 **)(arp_main+0xc0);void *proxy=0;arp_u32 sound=0;
            if(track<ARP_TRACKS && eligible(track) && parameter && view_word(parameter,0)==0x401c9a9cu){
                proxy=(void *)((arp_u32 (*)(void *,arp_u32,int))(*(arp_u32 **)parameter)[0xc4/4])(parameter,0x60u,-1);
                sound=proxy_sound(proxy);
            }
            if(!sound){ARP_CLOSE(arp_view);return;}
            arp_track=track;arp_proxy=proxy;arp_ui_sound=sound;arp_enc_reset();
            arp_track_read(track,&arp_ui_parameters);arp_length_show=0;ARP_DIRTY(arp_view);
            if(arp_lock_mode)arp_lock_read();
        }
    }
    if(arp_foreground()){
        unsigned int before=arp_lock_mode,step=arp_lock_step;
        arp_lock_sync();
        if(before!=arp_lock_mode || (arp_lock_mode && step!=arp_lock_step))ARP_DIRTY(arp_view);
    }
    if(arp_length_show && (int)(now-arp_length_until)>=0){
        arp_length_show=0;if(arp_view)ARP_DIRTY(arp_view);
    }
}
static int arp_view_encoder(void *app,const void *event)
{
    arp_u32 knob=view_word(event,12);(void)app;
    int steps;
    if(!arp_foreground())return 0;
    arp_lock_sync();
    if(knob>=1 && knob<=6){
        /* One native increment per turn: held steps and locks all take it. */
        steps=arp_encoder_steps(knob-1,event);
        if(!steps)return 1;
        if(arp_lock_mode){
            unsigned int i,first=arp_lock_step,done=0;
            for(i=0;i<64;i++)if(arp_held[i>>5]&(1u<<(i&31))){
                arp_lock_step=i;arp_lock_read();done|=arp_edit(knob-1,steps);
            }
            if(done)arp_lock_mark();
            arp_lock_step=first;arp_lock_read();
        }else if(arp_steps_held){
            /* Held arp steps: any of A..F edits each one's note (OFS). */
            unsigned int i,first=arp_selected;
            for(i=0;i<16;i++)if(arp_steps_held&(1u<<i)){arp_selected=i;arp_edit(4,steps);}
            arp_selected=first;arp_steps_edited=1;
        }else arp_edit(knob-1,steps);
    }
    return 1;
}
/* Trig keys 24..39 outside REC are the arp's sixteen steps: a press selects
 * the step, a release without an encoder edit toggles it. With REC, or with
 * FUNC (1), key 2 or key 12h held, they stay the sequencer's: the native
 * selection then drives the p-lock editing above. A release whose press
 * went to the sequencer goes there too. */
static int arp_step_key(arp_u32 key,arp_u32 flags)
{
    unsigned int k=key-24,bit=1u<<k;
    if(!(flags&1)){
        if(!(arp_steps_held&bit))return 0;
        arp_steps_held&=~bit;
        if(!arp_steps_edited && k<=arp_ui_parameters.length){
            struct arp_settings p=arp_ui_parameters;p.enabled^=bit;save_ui_settings(&p);
        }
        if(!arp_steps_held)arp_steps_edited=0;
        ARP_DIRTY(arp_view);return 1;
    }
    if(arp_recording() || UI_CALL(0x40102f40u,arp_u32 (*)(arp_u32))(1) ||
       UI_CALL(0x40102f40u,arp_u32 (*)(arp_u32))(2) || UI_CALL(0x40102f40u,arp_u32 (*)(arp_u32))(0x12)){
        arp_steps_held=0;arp_steps_edited=0;return 0;
    }
    if(!(flags&8)){
        if(!arp_steps_held)arp_steps_edited=0;
        arp_steps_held|=bit;arp_selected=k;ARP_DIRTY(arp_view);
    }
    return 1;
}
static int arp_view_key(void *app,const void *event)
{
    arp_u32 key=view_word(event,12),flags=view_word(event,16),track=0xffffffffu;
    arp_u8 *top=arp_top(app);int action,main=top && view_word(top,0)==0x401c849cu;
    if(main && view_word(top,0xa4))track=UI_CALL(0x4001ff74u,arp_u32 (*)(void *))(*(void **)(top+0xa4));
    action=arp_trig_tap(&arp_taps,key,flags,track,arp_blocks,main);
    if(action==ARP_TAP_OPEN){
        if(arp_open(app,track))return 1;
        arp_taps.consume_release=0;return 0;
    }
    if(action==ARP_TAP_CONSUME)return 1;
    if(!arp_foreground())return 0;
    if(key>=24 && key<=39)return arp_step_key(key,flags);
    arp_lock_sync();
    if(key==13){if(flags&1)ARP_CLOSE(arp_view);return 1;}
    if(arp_lock_mode && key>=40 && key<40+ARP_LOCK_SLOTS){
        if((flags&1) && !(flags&8))arp_lock_clear(key-40);
        return 1;
    }
    if(key==12){
        if((flags&1) && !(flags&8) && !arp_lock_mode){
            struct arp_settings p=arp_ui_parameters;p.enabled^=1u<<arp_selected;
            save_ui_settings(&p);ARP_DIRTY(arp_view);
        }
        return 1;
    }
    if(key>=14 && key<=17){
        if(flags&1){
            if(key==16 && arp_selected)arp_selected--;
            if(key==17 && arp_selected<15)arp_selected++;
            if(key==14 || key==15)arp_edit(4,key==14?1:-1);
            ARP_DIRTY(arp_view);
        }
        return 1;
    }
    /* Transport and track selection keep their native app handling. */
    return 0;
}
