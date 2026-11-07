/* SPDX-License-Identifier: GPL-2.0-or-later
 * sfcore: the part of Synfact's Syntakt core (mods/core-st, GSM1980 and contributors, on elekloader by irpina) that
 * its modules need, for SyntHack on OS 1.42. From modules.c (event lists, native interest), native.c (native
 * transactions, stock replays), machine-host.c (host API 12). Not here: SMZ banks, machines, project pool, Sample
 * Manager, telemetry. Ours: a fixed module table filled by the build instead of an SMZ file, static event lists,
 * binding at the first UI tick, storage and CRC borrowed from long-samples when it is in the build.
 *
 * Modules are Synfact `struct st_smz_module` descriptors. Each port writes the address of its descriptor into its
 * slot of sfcore_modules (tools/build/registry.py, SFCORE_SLOTS). At the first tick sfcore calls their init with
 * the usual st_smz_api (ui->host = host API 12) and appends their subscriptions to the event lists, in slot order.
 */
#include <syntakt/modules.h>
#include <syntakt/native.h>
#include <syntakt/host.h>
typedef unsigned int u32;typedef unsigned short u16;typedef unsigned char u8;

#define SLOTS 8u
#define CAP 8u                                  /* entries per event list, the terminating zero included */
extern const struct st_smz_module *const sfcore_modules[SLOTS];  /* registry: SFCORE_TABLE */

/* ---- event lists, read by the adapters (adapters.S). Zero-terminated. */
u32 ev_tick[CAP],ev_draw[CAP],ev_key[CAP],ev_enc[CAP],ev_render_in[CAP],ev_main_mix[CAP],ev_fs_write[CAP],
    ev_fs_written[CAP],ev_native[CAP],ev_view_draw[CAP];    /* ev_view_draw: ST_EV_DRAW | ST_EV_VIEW */
static u32 *const lists[ST_EV_COUNT]={ev_tick,ev_draw,ev_key,ev_enc,0,ev_render_in,0,0,ev_fs_write,ev_fs_written,
    ev_main_mix,ev_native};

/* 1 per slot: bound; 2: init refused; 3: an event sfcore does not provide (or a context it does not have yet);
 * 4: a list is full. Read by the tests and by modules that show a status. */
u32 sfcore_status[SLOTS],sfcore_bound,sfcore_subscriptions;

extern u32 sfcore_irq_off(void);
extern void sfcore_irq_on(u32);

/* ---- native transactions (Synfact native.c, modules.c) */
#define NATIVE_WORDS ((ST_NATIVE_OPERATION_LIMIT+3)/4)
#define NATIVE_TYPE_TRACKS ST_NATIVE_OPERATION_COUNT
/* One byte per operation: nonzero sends it through core_native; zero: the adapter replays stock at once. All zero
 * until a module subscribes to ev_native (Synfact starts open because its lists exist before the bank loads). */
u8 core_native_interest[4*NATIVE_WORDS] __attribute__((aligned(4)));
u32 core_native_page_view;
#define NATIVE_SLOTS 4
#define NATIVE_PAGE_OPS ((1u<<ST_NATIVE_PAGE_SYNC)|(1u<<ST_NATIVE_PAGE_NAV))
static struct {u32 fn,mask,view;} native_masks[NATIVE_SLOTS];

__attribute__((noinline)) static u32 native_fill(u8 *out,const u32 *list)
{
    u32 fn,m=0,t=0,i,own,view,pv=0,any=0;
    while((fn=*list++)){
        own=~0u;view=0;
        for(i=0;i<NATIVE_SLOTS;i++)if(native_masks[i].fn==fn){own=native_masks[i].mask;view=native_masks[i].view;break;}
        m|=own;
        if(own>>ST_NATIVE_TYPE&1u)t|=own>>24 && own>>24!=0xffu?own>>24:0x100u;
        if(own&NATIVE_PAGE_OPS){if(!view || (pv && pv!=view))any=1;pv=view;}
    }
    for(i=0;i<4*NATIVE_WORDS;i++,m>>=1)out[i]=(u8)(m&1u);
    out[NATIVE_TYPE_TRACKS]=(u8)t;out[NATIVE_TYPE_TRACKS+1]=(u8)(t>>8);
    return any?0:pv;
}
static void native_publish(void)
{
    union {u8 b[4*NATIVE_WORDS];u32 w[NATIVE_WORDS];} next;u32 i,sr,view=native_fill(next.b,ev_native);
    sr=sfcore_irq_off();
    for(i=0;i<NATIVE_WORDS;i++)((u32 *)core_native_interest)[i]=next.w[i];
    core_native_page_view=view;
    sfcore_irq_on(sr);
}
__attribute__((noinline)) static void native_set(void (*callback)(void),u32 value,u32 field)
{
    u32 i,*e=0,*slot=0;
    for(i=0;i<NATIVE_SLOTS;i++){
        u32 *x=&native_masks[i].fn;
        if(*x==(u32)callback){e=x;break;}
        if(!*x && !slot)slot=x;
    }
    if(!e){if(!slot)return;e=slot;e[0]=(u32)callback;e[1]=~0u;e[2]=0;}
    e[field]=value;
    native_publish();
}
void core_native_interest_set(void (*callback)(void),u32 mask){native_set(callback,mask,1);}
void core_native_page_view_set(void (*callback)(void),u32 vtable){native_set(callback,vtable,2);}
int core_event_native(u32 operation,const u32 *args,u32 *result)
{
    const u32 *p=ev_native;u32 fn;
    while((fn=*p++))if(((int (*)(u32,const u32 *,u32 *))fn)(operation,args,result))return 1;
    return 0;
}
extern u32 core_stock_trig(u32,u32,u32,u32,u32,u32);
extern u32 core_stock_enqueue(u32,u32);
extern u32 core_stock_header_load(u32,u32);
extern void core_stock_header_reset(u32,u32);
/* PAGE_LAYOUT has no adapter yet (LFO3/POLY pages): no override. */
__attribute__((noinline)) u32 core_native_original(u32 op,const u32 *a)
{
    switch(op){
    case ST_NATIVE_TRIG:return core_stock_trig(a[0],a[1],a[2],a[3],a[4],a[5]);
    case ST_NATIVE_ENQUEUE:return core_stock_enqueue(a[0],a[1]);
    case ST_NATIVE_TYPE:return (u32)(int)*(const signed char *)a[0];
    case ST_NATIVE_HEADER_LOAD:return core_stock_header_load(a[0],a[1]);
    case ST_NATIVE_HEADER_RESET:core_stock_header_reset(a[0],a[1]);return 0;
    case ST_NATIVE_SOUND_ALLOWED:case ST_NATIVE_MACHINE_ALLOWED:return 1;
    case ST_NATIVE_PAGE_NAV:return 0xffffffffu;
    default:return 0;
    }
}
#define CORE_NATIVE_TIMER() (*(const volatile u32 *)0xfc07000cu)
static u32 *native_profile;
void core_native_profile(u32 *buffer){native_profile=buffer;}
__attribute__((noinline)) u32 core_native(u32 op,const u32 *a)
{
    u32 *p=native_profile,start=0,result=0;
    if(p)start=CORE_NATIVE_TIMER();
    if(op>=ST_NATIVE_OPERATION_LIMIT || !core_native_interest[op] || !core_event_native(op,a,&result))
        result=core_native_original(op,a);
    if(p && op<ST_NATIVE_OPERATION_COUNT){p[op]+=CORE_NATIVE_TIMER()-start;p[ST_NATIVE_OPERATION_COUNT+op]++;}
    return result;
}
u32 core_native_view(u32 op,void *view,u32 other)
{
    u32 a[2]={(u32)view,other},v=core_native_page_view;
    if(v && (op==ST_NATIVE_PAGE_SYNC || op==ST_NATIVE_PAGE_NAV) && *(u32 *)view!=v)
        return core_native_original(op,a);
    return core_native(op,a);
}

/* ---- parameter provider (host API 7). Called by the Sound setter adapter (query 24) for the LFO3 engine IDs.
 * The metadata lookups (queries 0..23, notifications 25..27) come with LFO3, which is their only user. */
int (*core_parameter_provider)(u32,u32 *,void *,u32 *);
void core_parameter_provider_set(int (*provider)(u32,u32 *,void *,u32 *)){core_parameter_provider=provider;}

/* ---- host API 12 (Synfact machine-host.c). Storage, HZFS and CRC are long-samples' (the same Synfact code), when
 * long-samples is in the build: its header word 'LSHD' says so. Pool, preview and telemetry: no such services in
 * SyntHack (one list of samples, no Sample Manager), stubs that refuse. */
#define LS_MAGIC 0x4c534844u
extern const u32 ls_header_at[];                /* make_patch: long-samples' ls_header */
extern const struct st_storage_io ls_native_io; /* and its symbols, used only when the magic is there */
extern int ls_hz_open(struct st_hzfs *,const struct st_storage_io *);
extern void ls_hz_close(struct st_hzfs *);
extern u32 ls_crc_update(u32,const u8 *,u32);
/* Without long-samples: the same reflected CRC32 register, a bit at a time (no 1 KB table twice). */
static u32 crc_bits(u32 crc,const u8 *p,u32 n)
{
    u32 k;
    while(n--){crc^=*p++;for(k=0;k<8;k++)crc=crc>>1^(0xedb88320u&-(crc&1u));}
    return crc;
}
static void pool_read(const u8 *in,u16 *out){(void)in;(void)out;}
static void pool_write(u8 *out,const u16 *in){(void)out;(void)in;}
static int pool_ready(void){return 0;}
static int pool_apply(const u16 *before){(void)before;return -1;}
static void preview_stop(void){}
static int view_event(u32 event,void *view,void *data,u32 id){(void)event;(void)view;(void)data;(void)id;return 0;}
static void clock_snapshot(u32 *out){out[0]=CORE_NATIVE_TIMER();out[1]=out[2]=0;}
static void additem(void *menu,const void *item){(void)menu;(void)item;}
static const u32 zero[8];
static u32 query_owner;
static const u8 core_info[40+1]={'s','f','c','o','r','e'};   /* one record: id "sfcore", version "1.0" */
static const u8 *const bank_info=0;
static struct st_machine_host_api host={
    12,0,0,0,crc_bits,pool_read,pool_write,pool_ready,pool_apply,preview_stop,view_event,clock_snapshot,additem,
    zero,&query_owner,core_native_original,(const volatile u32 *)zero,core_native_profile,core_native_interest_set,
    core_native_page_view_set,core_parameter_provider_set,{core_native},0,core_info,&bank_info};
const struct st_machine_host_api *const sfcore_host=&host;

/* ---- UI API 7 (Synfact machines.h): no machine bank, so wave/cursor/sample/edit services answer "none". */
static const struct st_machine_wave *wave(u32 slot){(void)slot;return 0;}
static void wave_idle(u32 slot,u32 budget){(void)slot;(void)budget;}
static int sample_name(u32 slot,char *out){(void)slot;out[0]=0;return 0;}
static const struct st_machine_cursor *cursor(u32 track,u32 slot){(void)track;(void)slot;return 0;}
static void edit(void *view,u32 id,int delta,u32 knob){(void)view;(void)id;(void)delta;(void)knob;}
static void clear(void *view,u32 id,u32 whole,u32 knob){(void)view;(void)id;(void)whole;(void)knob;}
static int bind_input(u32 t,int (*e)(void *,void *,u32),void (*k)(void *,void *)){(void)t;(void)e;(void)k;return 1;}
static int bind_codec(const struct st_machine_action_codec *c){(void)c;return 1;}
static const struct st_machine_ui_api ui={7,wave,wave_idle,sample_name,cursor,0,edit,clear,bind_input,bind_codec,&host};

/* ---- binding (Synfact modules.c core_modules_bind, one module at a time into static lists) */
static u32 length(const u32 *l){u32 n=0;while(l[n])n++;return n;}
static u32 bind(const struct st_smz_module *m)
{
    u32 j,e,add[ST_EV_COUNT],sr;struct st_smz_api api={1,&ui};
    for(e=0;e<ST_EV_COUNT;e++)add[e]=0;
    for(j=0;j<m->count;j++){
        u32 ev=m->subscriptions[j].event;e=ST_EV_INDEX(ev);
        if(ev==(ST_EV_DRAW|ST_EV_VIEW))continue;     /* view draw: its own list (ev_view_draw) */
        if(e>=ST_EV_COUNT || !lists[e] || ev&(ST_EV_VIEW|ST_EV_PRE))return 3;   /* other contexts: not yet */
        add[e]++;
        if(e==ST_EV_NATIVE)api.version=3;
    }
    for(e=0;e<ST_EV_COUNT;e++)if(add[e] && length(lists[e])+add[e]>=CAP)return 4;
    if(m->init && (u32)m->init!=0xffffffffu && m->init(&api))return 2;
    for(j=0;j<m->count;j++){
        u32 *l=m->subscriptions[j].event==(ST_EV_DRAW|ST_EV_VIEW)?ev_view_draw:lists[ST_EV_INDEX(m->subscriptions[j].event)],
            n=length(l);
        if(n+1>=CAP)return 4;
        sr=sfcore_irq_off();                    /* the zero after it is already there: one aligned store */
        l[n]=(u32)m->subscriptions[j].callback;
        sfcore_irq_on(sr);
        sfcore_subscriptions++;
    }
    return 1;
}
/* At the first ev_tick (UI task, OS up: heap, views). Before it every list is empty and every adapter replays
 * stock. Called by core_tick (adapters.S). */
void sfcore_bind(void)
{
    u32 i;
    if(sfcore_bound)return;
    sfcore_bound=1;
    if(ls_header_at[0]==LS_MAGIC){
        host.storage=&ls_native_io;host.hz_open=ls_hz_open;host.hz_close=ls_hz_close;host.crc_update=ls_crc_update;
    }
    for(i=0;i<SLOTS;i++)if(sfcore_modules[i])sfcore_status[i]=bind(sfcore_modules[i]);
    native_publish();
}
/* Boot list slot 3 (after unpacking, before the OS starts): nothing to do yet, the lists are in the area's zeros. */
void sfcore_boot(void){}
