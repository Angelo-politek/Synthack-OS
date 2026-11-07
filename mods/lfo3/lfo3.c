/* SPDX-License-Identifier: GPL-2.0-or-later
 * lfo3: Synfact's third LFO (mods/lfo3-st, GSM1980 and contributors, on elekloader by irpina), OS 1.42.
 * Engine stage, from main.c: thirteen engines (12 tracks + FX) run the Synfact LFO3 kernel (synfact/render.s, the
 * native LFO algorithm, own state and RNG) before the two native LFOs, from sfcore's LFO operation, so LFO3 may
 * modulate LFO1/LFO2 parameters in the same block. Non-consuming: the native LFOs run after it unchanged.
 *
 * CPU #1 SRAM (tools/build/registry.py, SRAM): the kernel runs from a copy in the first tail and its state, RNG and
 * parameter bank live in the second tail (SRAM never misses the cache). Both must still be all zero as the stock
 * boot leaves them; otherwise, or if the copy's CRC ever changes, the same kernel and data run from DDR.
 *
 * Changes for SyntHack:
 * - a module of sfcore (slot 3 of its table) instead of an SMZ bank;
 * - nothing runs in the audio interrupt while no engine has a destination: the LFO interest byte of sfcore is set
 *   only while one does (checked at each UI tick), so an unused LFO3 costs one tst.b a block;
 * - the parameter record is the bank's (lfo3_params), written by the page (later steps); no locks yet.
 */
#include <syntakt/native.h>
#include <syntakt/host.h>
#include <syntakt/modules.h>
#include "lfo3.h"

#define LFO3_FILL ((void (*)(void *,int,int,int,int,u32))0x400f7fb6u)                         /* 1.41 0x400f7df2 */
#define LFO3_TEXT ((void (*)(void *,void *,int,int,u32,const char *,const char *))0x400f8bd0u) /* 1.41 0x400f8a0c */
#define LFO3_FONT ((void *)0x443db230u)                                                       /* 1.41 0x443da230 */
typedef void (*render_t)(u8 *,u32,u32,const u16 *,u8 *,u32 *);
extern void lfo3_render(u8 *,u32,u32,const u16 *,u8 *,u32 *);
extern const u8 lfo3_render_end[];
extern void lfo3_sync(void);
static const u16 defaults[8]={0x7000,0x300,0x4000,0x7f00,0,0,0,0x4000};
static const u32 tails[2][2]={{LFO3_SRAM_TAIL0,LFO3_SRAM_TAIL0_END},{LFO3_SRAM_TAIL1,LFO3_SRAM_TAIL1_END}};
static const struct st_machine_host_api *host;
static struct lfo3_bank ddr_bank;
struct lfo3_bank *lfo3_bank;
static render_t render;
/* diagnostics: kernel bytes and CRC, UI ticks, 1 = SRAM, refusal reason, engines with a destination */
u32 lfo3_code_bytes,lfo3_code_crc,lfo3_ticks,lfo3_in_sram,lfo3_refused,lfo3_active;

static u32 crc(u32 at,u32 n){return ~host->crc_update(~0u,(const u8 *)at,n);}
static void bank_reset(struct lfo3_bank *b)
{
    u32 t,i;
    for(t=0;t<LFO3_TRACKS;t++){
        for(i=0;i<40;i++)b->state[t][i]=0;
        *(u32 *)&b->state[t][16]=0x3fffffffu;
        for(i=0;i<8;i++)b->params[t][i]=b->overlay[t][i]=defaults[i];
    }
    b->rng[0]=0x12345678u;b->rng[1]=0x9abcdef0u;     /* Synfact seeds */
}
static void use_ddr(void)
{
    bank_reset(&ddr_bank);lfo3_bank=&ddr_bank;render=lfo3_render;lfo3_in_sram=0;
}
/* Returns 0 with the kernel and bank in SRAM, else the refusal reason. */
static u32 install(void)
{
    u32 i,at,n=(u32)lfo3_render_end-(u32)lfo3_render;
    if(LFO3_SRAM_CODE+n>tails[0][1] || LFO3_SRAM_BANK+sizeof(struct lfo3_bank)>tails[1][1])return 1;
    for(i=0;i<2;i++)for(at=tails[i][0];at<tails[i][1];at+=4)
        if(*(volatile u32 *)at)return 2;              /* not as the stock boot left it */
    for(i=0;i<n;i++)((volatile u8 *)LFO3_SRAM_CODE)[i]=((const u8 *)lfo3_render)[i];
    lfo3_code_bytes=n;lfo3_code_crc=crc((u32)lfo3_render,n);
    if(crc(LFO3_SRAM_CODE,n)!=lfo3_code_crc){for(i=0;i<n;i++)((volatile u8 *)LFO3_SRAM_CODE)[i]=0;return 3;}
    lfo3_sync();
    lfo3_bank=(struct lfo3_bank *)LFO3_SRAM_BANK;bank_reset(lfo3_bank);
    render=(render_t)LFO3_SRAM_CODE;lfo3_in_sram=1;
    return 0;
}
/* The record the kernel reads this block: the bank's parameters (p-locks come later). */
/* SyntHack: the 8 parameters are logical indices 0x3e..0x45 of each audio track's Sound (mods/xparams, second
 * group: saved, p-locked). The kernel reads them from the working copy of this block, locks applied: copied into the
 * bank's record before each render. The FX track has no LFO3 (its words 0x3e..0x45 are the FX amp block). */
#define LFO3_LIX 0x3Eu
#define WORK(t) ((volatile const u16 *)(0x800021B0u + 28u + 142u * (t) + 2u * LFO3_LIX))
const u16 *lfo3_events_bank(void)
{
    u32 t,*d=(u32 *)&lfo3_bank->params[0][0];        /* long words: odd tracks are 2-aligned (2 bus reads) */
    for(t=0;t<12u;t++,d+=4){
        volatile const u32 *w=(volatile const u32 *)WORK(t);
        d[0]=w[0];d[1]=w[1];d[2]=w[2];d[3]=w[3];
    }
    lfo3_bank->params[12][3]=0x7f00u;               /* FX track: none */
    return &lfo3_bank->params[0][0];
}
/* An engine matters when its destination is a Sound slot (1..70): 0 is the native None, 0x7f (and anything above
 * 70) is skipped by the kernel itself. Read from the working copy, in the UI task. */
static u32 active_mask(void)
{
    u32 t,m=0,slot;
    for(t=0;t<12u;t++){slot=WORK(t)[3]>>8;if(slot && slot<=70)m|=1u<<t;}
    return m;
}
int lfo3_native(u32 op,const u32 *a,u32 *result)
{
    (void)result;
    if(op==ST_NATIVE_LFO && a && render)
        render((u8 *)a[0],a[1],a[2],lfo3_events_bank(),&lfo3_bank->state[0][0],lfo3_bank->rng);
    return 0;                                     /* native LFO1/LFO2 continue */
}
/* Interest in the LFO operation only while an engine has a destination: otherwise the adapter replays stock. */
void lfo3_update(void)
{
    u32 m=render?active_mask():0;
    if(!host || (m!=0)==(lfo3_active!=0)){lfo3_active=m;return;}
    lfo3_active=m;
    host->native_interest((void (*)(void))lfo3_native,m?1u<<ST_NATIVE_LFO:0);
}
static void lfo3_tick(void *controller)
{
    lfo3_ticks++;
    if(lfo3_in_sram && lfo3_ticks%60u==0 && crc(LFO3_SRAM_CODE,lfo3_code_bytes)!=lfo3_code_crc){
        lfo3_refused=4;use_ddr();                      /* the copy changed: same kernel and data from DDR */
    }
    lfo3_update();
    if(lfo3_ticks<=300u && lfo3_ticks%30u==0)((u8 *)controller)[0x20]=1;
}
static void lfo3_draw(void *bitmap,void *controller)
{
    /* Only the DDR fallback is worth a notice; running from SRAM is normal. */
    static char line[]="LFO3 SRAM ON";
    (void)controller;if(lfo3_ticks>300u || lfo3_in_sram)return;
    line[5]='D';line[6]='D';line[7]='R';line[8]=' ';line[9]=(char)('0'+lfo3_refused);line[10]=line[11]=' ';
    LFO3_FILL(bitmap,18,54,127,63,0);
    LFO3_TEXT(bitmap,LFO3_FONT,20,55,0,"%s",line);
}
static int initialize(const struct st_smz_api *api)
{
    if(!api || api->version<3 || !api->ui || api->ui->version<7 || !api->ui->host)return 1;
    host=api->ui->host;
    lfo3_refused=install();if(lfo3_refused)use_ddr();
    host->native_interest((void (*)(void))lfo3_native,0);
    lfo3_update();
    return 0;
}
static const struct st_smz_subscription subscriptions[]={
    {ST_EV_NATIVE,(void (*)(void))lfo3_native},
    {ST_EV_TICK,(void (*)(void))lfo3_tick},
    {ST_EV_DRAW,(void (*)(void))lfo3_draw}};
const struct st_smz_module lfo3_module={"LFO3",initialize,subscriptions,3};
