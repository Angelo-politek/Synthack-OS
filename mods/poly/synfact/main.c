/* Synfact digital POLY, integrated through existing UI events and core-owned
 * native transactions. Authored source provenance is pinned beside this file.
 */
#include <syntakt/native.h>
#include <syntakt/host.h>
typedef unsigned int u32;typedef unsigned char u8;
#ifndef POLY_CALL
#define POLY_CALL(address,type) ((type)(address))
#endif
static const struct st_machine_host_api *poly_host;
static u32 *stock_trig(u32 t,const volatile u8 *s,u32 k,u32 p,u32 *e,u32 *when)
{u32 a[]={t,(u32)s,k,p,(u32)e,(u32)when};return (u32 *)poly_host->native_original(ST_NATIVE_TRIG,a);}
static u32 stock_enqueue(u32 *event,u32 time)
{u32 a[]={(u32)event,time};return poly_host->native_original(ST_NATIVE_ENQUEUE,a);}
static u32 stock_header_load(u8 *d,const u8 *s)
{u32 a[]={(u32)d,(u32)s};return poly_host->native_original(ST_NATIVE_HEADER_LOAD,a);}
static void stock_header_reset(u8 *d,u32 quiet)
{u32 a[]={(u32)d,quiet};poly_host->native_original(ST_NATIVE_HEADER_RESET,a);}
static const u32 *stock_page_layout(u32 page)
{return (const u32 *)poly_host->native_original(ST_NATIVE_PAGE_LAYOUT,&page);}
#include "poly_core.c"
extern void poly_fast_publish(u8 *,const volatile u8 *);
/* SyntHack: no analog guard kernels (poly_mod_shared, poly_native_shared): analog POLY not ported. */
static u32 poly_grouped(void)
{
    return poly_has_groups;
}
static void poly_frame(void){poly_sync();}
static int poly_native(u32 op,const u32 *a,u32 *result);
/* Host API 5: without groups only the operations POLY always needs reach its
 * handler (its own private IMMEDIATE commands, trig cleanup, pattern header,
 * the POLY page); every other one replays stock without the C dispatcher.
 * Groups add the voice-routing operations. Called at init and from
 * poly_commit, the only writer of the owner map (an IRQ-masked section). */
#define POLY_NATIVE_ALWAYS ((1u<<ST_NATIVE_TRIG)|(1u<<ST_NATIVE_IMMEDIATE)| \
    (1u<<ST_NATIVE_HEADER_LOAD)|(1u<<ST_NATIVE_HEADER_RESET)|(1u<<ST_NATIVE_PAGE_SYNC)| \
    (1u<<ST_NATIVE_PAGE_NAV)|(1u<<ST_NATIVE_PAGE_LAYOUT)|(1u<<ST_NATIVE_PAGE_BEGIN)|(1u<<ST_NATIVE_PAGE_END))
#define POLY_NATIVE_GROUPED ((1u<<ST_NATIVE_ENQUEUE)|(1u<<ST_NATIVE_PUBLISH)| \
    (1u<<ST_NATIVE_SOUND_ALLOWED)|(1u<<ST_NATIVE_MACHINE_ALLOWED)|(1u<<ST_NATIVE_PAGE_GUARD)| \
    (1u<<ST_NATIVE_OWNERS))
static u32 poly_interest;
void poly_native_interest(void)
{
    u32 mask=POLY_NATIVE_ALWAYS;
    if(poly_grouped()){
        mask|=POLY_NATIVE_GROUPED;
        if(!poly_shared_mask)mask&=~((1u<<ST_NATIVE_PUBLISH)|(1u<<ST_NATIVE_MODULATION)|
            (1u<<ST_NATIVE_LFO)|(1u<<ST_NATIVE_OWNERS));
        if(poly_analog_active)mask|=(1u<<ST_NATIVE_MODULATION)|(1u<<ST_NATIVE_LFO);
        /* New voices already own a native Sound/type; no TYPE dispatcher. */
    }
    if(mask==poly_interest || !poly_host || poly_host->version<5)return;
    poly_interest=mask;poly_host->native_interest((void (*)(void))poly_native,mask);
}
static void poly_draw(void *view,void *bitmap,u32 phase)
{(void)phase;poly_ui_draw(view,bitmap);}
static int poly_encoder(void *view,void *event,u32 id)
{(void)id;return poly_ui_encoder(view,event);}
static int poly_key(void *view,void *event,u32 phase)
{
    u32 track;(void)phase;
    /* Reload/paste/Sound selection finishes in the same UI task before tick. */
    if(poly_ui_parameter_view(view)) {
        track=poly_ui_track(view);
        if(track<8 && poly_seq_config.states[track]>=3)poly_copy_mark(track);
    }
    return poly_ui_block_key(view,event);
}
static void poly_tick(void *ctrl){(void)ctrl;poly_copy_ui();poly_rec_ui();poly_analog_ui();}
static u32 poly_context[16],poly_depth;
static int poly_native(u32 op,const u32 *a,u32 *result)
{
    u32 v;
    switch(op){
    case ST_NATIVE_TRIG:
        poly_sync();if(!poly_grouped()){
            if(a[0]<13)poly_seq_config.pending[a[0]].event=0;
            return 0;
        }
        *result=(u32)poly_trig_synced(a[0],(const volatile u8 *)a[1],a[2],a[3],(u32 *)a[4],(u32 *)a[5]);return 1;
    case ST_NATIVE_ENQUEUE:
        if(!poly_grouped())return 0;
        *result=poly_sequence_enqueue((u32 *)a[0],a[1]);return 1;
    case ST_NATIVE_IMMEDIATE:*result=poly_preview_locked((u32 *)a[0]);return 1;
    case ST_NATIVE_PUBLISH:
        if(poly_shared_mask)poly_publish_entry((u8 *)a[0],poly_post_map,poly_publish_span);return 0;
    case ST_NATIVE_TYPE:
        v=a[0]-0x80002f50u;if(v>=8 || poly_owner_map[v]>=v)return 0;
        *result=poly_effective_type((const volatile u8 *)a[0]);return 1;
    case ST_NATIVE_HEADER_LOAD:*result=poly_header_load((u8 *)a[0],(const u8 *)a[1]);return 1;
    case ST_NATIVE_HEADER_RESET:poly_header_reset((u8 *)a[0],a[1]);*result=0;return 1;
    case ST_NATIVE_SOUND_ALLOWED:case ST_NATIVE_MACHINE_ALLOWED:
        if(poly_sound_write_allowed(a[0]))return 0;*result=0;return 1;
    case ST_NATIVE_PAGE_SYNC:poly_ui_sync((u8 *)a[0]);break;
    case ST_NATIVE_PAGE_NAV:v=poly_ui_control((u8 *)a[0],a[1]);if(v==0xffffffffu)return 0;*result=v;return 1;
    case ST_NATIVE_PAGE_LAYOUT:v=poly_ui_layout(a[0]);if(!v)return 0;*result=v;return 1;
    case ST_NATIVE_PAGE_BEGIN:
        if(poly_depth<16)poly_context[poly_depth]=poly_ui_action_begin((u8 *)a[0]);
        poly_depth++;break;
    case ST_NATIVE_PAGE_END:
        if(poly_depth && --poly_depth<16)poly_ui_action_end(poly_context[poly_depth]);break;
    case ST_NATIVE_PAGE_GUARD:if(!poly_ui_slave((u8 *)a[0]))return 0;*result=1;return 1;
    case ST_NATIVE_OWNERS:
        if(!poly_shared_mask)return 0;
        *result=(u32)(a && a[0]==1?poly_lfo_map:poly_post_map);return 1;
    case ST_NATIVE_MODULATION:case ST_NATIVE_LFO:
        /* Preserve the validated analog skip kernels. Their bitmap excludes
         * digital voices, which keep native per-track modulation in either PLAY. */
        return 0;   /* SyntHack: poly_analog_active is never set (analog POLY not ported) */
    default:return 0;
    }
    return 0; /* Notifications continue to later native subscribers. */
}
static int poly_initialize(const struct st_smz_api *api)
{
    if(!api || api->version<3 || !api->ui || api->ui->version<7 ||
       !api->ui->host || api->ui->host->version<2)return 1;
    poly_host=api->ui->host;poly_native_interest();
    /* Host API 6: POLY's page handlers act only on the TRIG ParameterView. */
    if(poly_host->version>=6)poly_host->native_page_view((void (*)(void))poly_native,0x401c9a9cu);
    return 0;
}
static const struct st_smz_subscription poly_subscriptions[]={
    {ST_EV_RENDER_IN,(void (*)(void))poly_frame},
    {ST_EV_DRAW|ST_EV_VIEW,(void (*)(void))poly_draw},
    {ST_EV_ENC|ST_EV_VIEW,(void (*)(void))poly_encoder},
    {ST_EV_KEY|ST_EV_VIEW|ST_EV_PRE,(void (*)(void))poly_key},
    {ST_EV_TICK,(void (*)(void))poly_tick},
    {ST_EV_NATIVE,(void (*)(void))poly_native}};
const struct st_smz_module poly_module={"POLY",poly_initialize,poly_subscriptions,6};
