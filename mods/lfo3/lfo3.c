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
/* ---- the LFO3 page (idspace page 38, third page of the LFO tab, ids 530..537). The LFO tab is the same for every
 * track: on the FX track the page is empty (its indices 0x3e..0x45 are the FX amp block). UI task only. */
#define PAGE38_SLOTS ((volatile u32 *)(IDS_PAGE38 + 8))
#define XSTR_(x) #x
#define XSTR(x) XSTR_(x)
#define PROJECT ((u32 (*)(void))0x4016E9C8u)
#define ACTIVE_TRACK ((u32 (*)(u32))0x4001FF74u)
struct rep { u32 len, cap; int ref; char s[8]; };      /* static COW std::string: -1 = leaked, never freed */
const struct rep lfo3_page_s = {4, 4, -1, "LFO3"};
const struct rep lfo3_page_l = {5, 5, -1, "LFO 3"};
const u32 lfo3_lfo_pages[3] = {4, 5, 38};               /* the LFO tab's pages */
void lfo3_page_slots(void)
{
    u32 fx=ACTIVE_TRACK(PROJECT()+0x30u)==12u,k;
    if((PAGE38_SLOTS[0]==0)==fx)return;
    for(k=0;k<8;k++)PAGE38_SLOTS[k]=fx?0:530u+k;
}
/* The LFO tab's draw (0x400F3824) draws the waveform box of LFO1 on page 0 of the tab and of LFO2 on page 1, from
 * the values of WAVE, SPH, MODE, SPD and DEP (ids 90 92 93 86 94, +10 for LFO2), with 0x400F33F2; any other page got
 * none, so LFO3 looked like a plain eight-knob page (device, RC1). Its page test at 0x400F3A0C (moveq #1,d1 ;
 * cmp.l d0,d1 ; bne.s 0x400F3A84, d0 = page of the tab) comes here: page 2 with LFO3's parameters on it (not the
 * FX track, where the page is empty) reads 534 535 536 530 537 the same way and joins the OS code at 0x400F3A5A. */
__asm__(
    "        .text\n"
    "        .globl  lfo3_wave_hook\n"
    "lfo3_wave_hook:\n"
    "        moveq   #1,%d1\n"
    "        cmp.l   %d0,%d1\n"
    "        bne.s   1f\n"
    "        jmp     0x400F3A12\n"                      /* LFO2, as the OS */
    "1:      moveq   #2,%d1\n"
    "        cmp.l   %d0,%d1\n"
    "        bne.s   9f\n"
    "        tst.l   " XSTR(IDS_PAGE38_E) "\n"       /* slot E of page 38: empty on the FX track */
    "        beq.s   9f\n"
    "        move.l  %sp,%d3\n"
    "        addi.l  #75,%d3\n"
    "        move.l  %d3,-(%sp)\n"
    "        pea     534\n"                             /* WAVE */
    "        move.l  %a2,-(%sp)\n"
    "        lea     0x40039160,%a3\n"
    "        jsr     (%a3)\n"
    "        move.l  %d3,-(%sp)\n"
    "        pea     535\n"                             /* SPH */
    "        move.l  %a2,-(%sp)\n"
    "        move.l  %d0,%d4\n"
    "        jsr     (%a3)\n"
    "        move.l  %d3,-(%sp)\n"
    "        pea     536\n"                             /* MODE */
    "        move.l  %a2,-(%sp)\n"
    "        move.l  %d0,%d5\n"
    "        jsr     (%a3)\n"
    "        lea     32(%sp),%sp\n"
    "        move.l  %d3,(%sp)\n"
    "        pea     530\n"                             /* SPD */
    "        move.l  %a2,-(%sp)\n"
    "        move.l  %d0,%d6\n"
    "        jsr     (%a3)\n"
    "        move.l  %d3,-(%sp)\n"
    "        pea     537\n"                             /* DEP */
    "        move.l  %d0,%d7\n"
    "        jmp     0x400F3A5A\n"
    "9:      jmp     0x400F3A84\n");

/* LFO3's DEST (id 533) is a DEST like LFO1's (89) and LFO2's (99) where the OS tells them apart by id: popup
 * (0x4003B11A, id in d3), randomize (0x400149E2, d2), relative step (0x40014C5E / 0x40014E48, d0). Each site's
 * compare chain becomes jsr here: Z = 1 for 89, 99, 533; the site's own bne follows. Only flags change. */
__asm__(
    "        .text\n"
    "        .globl  lfo3_dest_d0, lfo3_dest_d2, lfo3_dest_d3\n"
    "lfo3_dest_d0:\n"
    "        cmpi.l  #89,%d0\n"
    "        beq.s   1f\n"
    "        cmpi.l  #99,%d0\n"
    "        beq.s   1f\n"
    "        cmpi.l  #533,%d0\n"
    "1:      rts\n"
    "lfo3_dest_d2:\n"
    "        cmpi.l  #89,%d2\n"
    "        beq.s   1f\n"
    "        cmpi.l  #99,%d2\n"
    "        beq.s   1f\n"
    "        cmpi.l  #533,%d2\n"
    "1:      rts\n"
    "lfo3_dest_d3:\n"
    "        cmpi.l  #89,%d3\n"
    "        beq.s   1f\n"
    "        cmpi.l  #99,%d3\n"
    "        beq.s   1f\n"
    "        cmpi.l  #533,%d3\n"
    "1:      rts\n");

static void lfo3_tick(void *controller)
{
    lfo3_page_slots();
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
/* a new Sound takes each logical index's default from the descriptor these tables name (FUN_400a5490; sy-fm4 does
 * the same for 0x36..0x3d): LFO3's indices get LFO1's defaults (SPD, MULT...) instead of zeros */
#define LIX_TABLE_A ((volatile u32 *)0x43bdf7fcu)
#define LIX_TABLE_B ((volatile u32 *)0x43bdf6e0u)
static void defaults_for_new_sounds(void)
{
    u32 k;
    for(k=0;k<8;k++){LIX_TABLE_A[LFO3_LIX+k]=530u+k;LIX_TABLE_B[LFO3_LIX+k]=530u+k;}
}
static int initialize(const struct st_smz_api *api)
{
    defaults_for_new_sounds();
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
