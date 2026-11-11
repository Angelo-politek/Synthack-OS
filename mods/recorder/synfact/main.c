/* Synfact recorder source port. UI/storage and PCM owned by this SMZ module;
 * the core owns the existing event bus, HZFS services and project/AUDIO pool.
 * Source origin/hashes and adaptations are recorded in provenance.json.
 */
#include <syntakt/modules.h>
#include <syntakt/host.h>
#include <syntakt/mix.h>
#include <syntakt/modal.h>
typedef st_u32 u32;typedef int s32;typedef unsigned short u16;typedef unsigned char u8;
#define DATA
static const struct st_machine_host_api *host;
static u32 recorder_last_paint;
static void normalize_fast(void);
static void recorder_prime(void),recorder_resume(void),recorder_draw_bridge(u8 *,void *);
static u32 recorder_save_acquire(void);static void recorder_save_release(void);
static volatile u32 recorder_transfer_active,recorder_save_lease;
void sampler_suspend(void);
extern u32 recorder_irq_lock(void);extern void recorder_irq_unlock(u32);
#ifndef REC_NATIVE
#define REC_NATIVE
#define MALLOC host->storage->alloc
#define FREE host->storage->free
#define MMC_READ host->storage->read
#define MMC_WRITE host->storage->write
#define CARD_SECTORS (host->storage->sectors())
#define UI_PUSH ((u32 (*)(void *,void *,u32))0x40100d86u)
#define UI_DROP ((void (*)(void *))0x4016dfacu)
#define UI_CLOSE ((void (*)(void *))0x400ffec6u)
#define UI_DIRTY ((void (*)(void *))0x400ffe22u)
#define UI_OPAQUE ((void (*)(void *,u32))0x400ffcb8u)
#define QSTR_INIT ((u32 (*)(void *,const char *,void *))0x401bf31eu)   /* SyntHack: OS results in d0 */
#define WAVE_FILL ((void (*)(void *,s32,s32,s32,s32,u32))0x400f7fb6u)
#define WAVE_PIXEL ((void (*)(void *,s32,s32,u32))0x400f7304u)
#define WAVE_TEXT ((void (*)(void *,void *,s32,s32,u32,const char *,...))0x400f8bd0u)
#define MAIN_BUS ((s32 *)ST_PREVIEW_BUS)
#endif
#include "native.h"
#define WORKING_PROJECT ((u8 *)0x40653514u)
#define SLOTS 128u
#define HZ_FLAG 0x8000u
#define HZ_BLOCK_SECTORS 1024u
#define HZ_INDEX_A (ST_HZ_FIRST*HZ_BLOCK_SECTORS)
#define HZ_INDEX_B ((ST_HZ_FIRST+1u)*HZ_BLOCK_SECTORS)
#define HZ_ENTRIES ST_HZ_ENTRIES
#define HZ_ENTRY ST_HZ_ENTRY
#define HZ_MAX_LEN ST_HZ_WINDOW
#define HZ_DATA_FIRST ST_HZ_DATA
/* SyntHack: sources 3..5 are named for what they hold, the FX track's bus (not the main output: the Syntakt sums
 * in analog and has no converter there; mods/recorder/README.md) */
#define SAMPLER_SOURCES {"IN L","IN R","IN L+R","FX L","FX R","FX L+R",\
    "TRK 1","TRK 2","TRK 3","TRK 4","TRK 5","TRK 6","TRK 7","TRK 8","TRK 9","TRK 10","TRK 11","TRK 12"}
/* Short fixed captions observed by Synfact sampling_resources; no donor
 * firmware or resource extractor is needed by this module's normal build. */
#define SAMPLER_LABELS {"RECORDER","Fn+YES: REC","YES: ARM","(E)RLEN","(F)THR","(G)SRC","(H)MON"}
struct fn_capture {void *data;u32 reserved;void *manager,*invoke;};
static u16 pool_now[SLOTS];
static u32 be32(const void *raw)
{const u8 *p=raw;return (u32)p[0]<<24|(u32)p[1]<<16|(u32)p[2]<<8|p[3];}
static void put32(void *raw,u32 n){u8 *p=raw;p[0]=n>>24;p[1]=n>>16;p[2]=n>>8;p[3]=n;}
static int heap_ok(const void *p){return (u32)p>=0x40000000u;}
static void text_set(char *d,const char *s,u32 n){u32 i;for(i=0;i<n && s[i];i++)d[i]=s[i];d[i]=0;}
static void number3(char *d,u32 n){d[0]='0'+n/100%10;d[1]='0'+n/10%10;d[2]='0'+n%10;}
static u32 crc_update(u32 crc,const u8 *p,u32 n){return host->crc_update(crc,p,n);}
static u32 crc32(const u8 *p,u32 n){return ~crc_update(0,p,n);}
#define pool_read host->pool_read
#define pool_write host->pool_write
#define pool_live_ready host->pool_ready
#define pool_live_sync host->pool_apply
static void preview_stop(void){host->preview_stop();}
static void preview_mix_frame(u32 frame,s32 x){st_preview_mix_frame(MAIN_BUS,frame,x);}
#include "recorder.c"
/* The optimized MAIN specialization uses the unchanged general source for
 * external inputs and individual tracks. Both are native integer C. */
void ui_sampler_native_tick(void){sampler_base_tick();}
#include "capture.c"
#include "normalize.c"
static void recorder_prime(void)
{
    u32 sr=recorder_irq_lock();
    if(sam_source>=3 && sam_source<6)sam_returns();
    recorder_irq_unlock(sr);headroom_meter_phase=23;
}
static void recorder_resume(void)
{recorder_prime();sam_peak=0;sam_last_source=18;}
static void recorder_draw(void *view,void *bitmap,u32 unused)
{(void)unused;if(view==sam_view && sam_view)sampler_draw(view,bitmap);}
static int recorder_key(void *brain,void *event)
{
    int taken=sampler_pre_event(brain,event);
    if(taken || be32((u8 *)event+12)==11)return taken; /* native STOP, also while SAVING */
    /* SyntHack: on top, the recorder owns the keys it does not use too (syntakt/modal.h), but not the trig keys:
     * they play the sounds to record. Under its naming and track popups the keys are the popup's. */
    if(sam_foreground() && sam_tail_is_recorder()){
        if(sampler_key(sam_view,event))return 1;
        return st_modal_key(be32((u8 *)event+12),be32((u8 *)event+16),1,0,1);
    }
    return st_modal_key(be32((u8 *)event+12),be32((u8 *)event+16),0,0,0);
}
static int recorder_encoder(void *brain,void *event)
{(void)brain;return sam_foreground() && sam_tail_is_recorder()?sampler_encoder(sam_view+4,event):0;}
static void recorder_audio(void)
{headroom_tick();sampler_playback_mix();}
/* Serialize the bounded save job with native high-zone Data uploads using
 * the existing FS events. The tiny check/publication is atomic across tasks;
 * no IRQ exclusion surrounds storage, allocation or normalization. */
static u32 recorder_save_acquire(void)
{
    u32 sr=recorder_irq_lock(),ok;
    ok=recorder_save_lease || !recorder_transfer_active;
    if(ok)recorder_save_lease=1;
    recorder_irq_unlock(sr);return ok;
}
static void recorder_save_release(void)
{u32 sr=recorder_irq_lock();recorder_save_lease=0;recorder_irq_unlock(sr);}
static int recorder_fs_write(void *router,const void *info,void *out)
{
    u32 sr,busy,i;u8 allocator=0;(void)router;
    if(((const u32 *)info)[3]<0x30000000u)return 0;
    sr=recorder_irq_lock();busy=recorder_save_lease;
    if(!busy)recorder_transfer_active=1;
    recorder_irq_unlock(sr);
    if(!busy)return 0;
    for(i=0;i<16;i++)((u8 *)out)[i]=0;
    QSTR_INIT((u8 *)out+4,"Recorder is saving",&allocator);return 1;
}
static void recorder_fs_written(const void *capture,const u8 *header,const u8 *status)
{
    u32 id,sr;(void)capture;
    if(!header || !status[0] || be32(header+13)!=8)return;
    id=be32(header+21);
    if(id<ST_HZ_RAW_FIRST+ST_HZ_FIRST || id>=ST_HZ_RAW_FIRST+0x2000u)return;
    sr=recorder_irq_lock();recorder_transfer_active=0;recorder_irq_unlock(sr);
}
static int initialize(const struct st_smz_api *api)
{
    if(!api || !api->ui || api->ui->version<6 || !api->ui->host || api->ui->host->version<2)return 1;
    host=api->ui->host;return 0;
}
static const struct st_smz_subscription subscriptions[]={
    {ST_EV_KEY,(void (*)(void))recorder_key},
    {ST_EV_ENC,(void (*)(void))recorder_encoder},
    {ST_EV_TICK,(void (*)(void))recorder_ui_tick},
    {ST_EV_DRAW|ST_EV_VIEW,(void (*)(void))recorder_draw},
    {ST_EV_MAIN_MIX,(void (*)(void))recorder_audio},
    {ST_EV_FS_WRITE,(void (*)(void))recorder_fs_write},
    {ST_EV_FS_WRITTEN,(void (*)(void))recorder_fs_written}};
const struct st_smz_module recorder_module={"AUDIO RECORDER",initialize,subscriptions,7};
