/* SPDX-License-Identifier: GPL-2.0-or-later
 * modulation-skip: skips the stock modulation 0x40097B74 (OS 1.42; 0x40097AFC in 1.41), the velocity/modulation
 * matrix of the MAIN audio IRQ, in blocks where it would write exactly what it wrote last time.
 * From Synfact mods/modulation-skip-st/main.c (GSM1980 and contributors, on elekloader by irpina).
 *
 * The stock body writes, per track t, working[t] + 2*index for 4 entries of 12 velocity groups and 13x5 source
 * groups; entry = {amount, index} longs of the track's unsmoothed machine data. Its output depends only on the
 * velocity and source tables (45 longs), the machine data it reads (13 x 24 longs) and the values of its
 * destination words on entry. When all of them equal the last real run's, it would write the same: write those
 * final values and return.
 *
 * Changes for SyntHack:
 * - sites patched by the build (patch.json, stock bytes checked there), not at run time;
 * - hot data in the CPU's internal SRAM (registry: SRAM), so a skipped block reads no DDR line: destinations as
 *   {offset, before, after} halfwords, the input tables, the state, a bitmap of the destination words; only the
 *   copy of the machine data (read when it may have changed, and every 64 blocks) stays in the mod area;
 * - one pass over the destinations: compare and write; a difference puts the written ones back and runs stock;
 * - the destination list depends only on the indices in the machine data: rebuilt only when that changes;
 * - SRAM starts zeroed by the stock boot: mode 0 = not started = stock. The sfcore init sets ON (or VERIFY);
 * - a destination outside the SRAM (index far out of range): that configuration always runs stock.
 * Modes: VERIFY (built with MODULATION_SKIP_VERIFY=1) never skips, runs stock and compares every block;
 * ON skips, and every 64th would-skip block runs stock and compares; the first difference turns it OFF (stock for
 * the rest of the session). Header line (sfcore ev_draw) on a difference, OFF or VERIFY:
 * `MSKIP ON  H99 S98 E000` = mode, % of blocks whose inputs matched, % skipped, differences.
 */
#include <syntakt/modules.h>
typedef unsigned int u32;typedef unsigned short u16;typedef unsigned char u8;typedef short s16;typedef int s32;
#ifndef MODULATION_SKIP_VERIFY
#define MODULATION_SKIP_VERIFY 0
#endif
#define R32(a) (*(const volatile u32 *)(a))
#define R16(a) (*(volatile u16 *)(a))
#define FILL ((void (*)(void *,int,int,int,int,u32))0x400f7fb6u)          /* 1.41 0x400f7df2 */
#define TEXT ((void (*)(void *,void *,int,int,u32,const char *,const char *))0x400f8bd0u)  /* 1.41 0x400f8a0c */
#define FONT ((void *)0x443db230u)                                          /* 1.41 0x443da230 */
#define WORKING 0x80006348u
#define TRACK(t) (WORKING+0x1cu+0x8eu*(t))
#define RAW(t) (WORKING+0x754u+0x7cu*(t))
#define DESTS (12*4+13*5*4)
#define MACHINE (13*24)
#define CHECK_EVERY 64u
enum {OFF_STOCK,VERIFY,ON,OFF};                   /* 0: SRAM as the boot left it, before init */
enum {RUN_STOCK,SKIPPED,RUN_AND_CHECK};

/* ---- SRAM (registry): state, tables and bitmap in the second tail, destinations in the first */
struct state {
    u32 mode,valid,n,ticks,count,writes,seen,capture,outside;
    u32 blocks,hits,skips,errors;
};
struct entry {u16 off,pre,post;};
#define ST ((struct state *)0x8000fc20u)
#define TABLES ((u32 *)0x8000fc60u)                /* 45 longs */
#define MAP ((u32 *)0x8000fd20u)                   /* 1024 bits: words WORKING..WORKING+0x800 */
#define MAP_WORDS 1024u
#define ENT ((struct entry *)0x80007780u)          /* DESTS x 6 B, to 0x80007eb8 */
static u32 machine[MACHINE];                       /* DDR: read only when it may have changed */

static const u32 ranges[3][2]={{0x80004670u,0x80004688u},{0x800046b8u,0x800046ecu},{0x800046f8u,0x80004760u}};
static u32 tables_equal(void)
{
    u32 *s=TABLES,a,v,eq=1,i;
    for(i=0;i<3;i++)for(a=ranges[i][0];a<ranges[i][1];a+=4){v=R32(a);if(*s!=v){eq=0;*s=v;}s++;}
    return eq;
}
static u32 machine_equal(void)
{
    u32 *s=machine,a,v,t,eq=1;
    for(t=0;t<13;t++)for(a=RAW(t);a<RAW(t)+0x60u;a+=4){v=R32(a);if(*s!=v){eq=0;*s=v;}s++;}
    return eq;
}
static void add(u32 at)
{
    struct state *st=ST;u32 i,w,n=st->n;
    if(at-0x80000000u>=0x10000u || at&1u){st->outside=1;return;}
    w=(at-WORKING)>>1;
    if(at>=WORKING && w<MAP_WORDS){
        if(MAP[w>>5]&1u<<(w&31))return;
        MAP[w>>5]|=1u<<(w&31);
    }else for(i=0;i<n;i++)if(ENT[i].off==(u16)at)return;
    ENT[n].off=(u16)at;st->n=n+1;
}
/* The destination words, as the stock body computes them (MVS.W of each entry's low word), each once. */
static void build(void)
{
    u32 t,g,k;
    for(k=0;k<MAP_WORDS/32;k++)MAP[k]=0;
    ST->n=0;ST->outside=0;
    for(t=0;t<12;t++)for(k=0;k<4;k++)add(TRACK(t)+2u*(u32)(s32)(s16)R32(RAW(t)+4u*k));
    for(t=0;t<13;t++)for(g=1;g<=5;g++)for(k=0;k<4;k++)add(TRACK(t)+2u*(u32)(s32)(s16)R32(RAW(t)+0x10u*g+4u*k));
}
#define AT(e) ((volatile u16 *)(0x80000000u|(e)->off))
static u32 entries_equal(void)
{struct entry *e=ENT,*end=ENT+ST->n;for(;e<end;e++)if(*AT(e)!=e->pre)return 0;return 1;}
static void capture(void)
{struct entry *e=ENT,*end=ENT+ST->n;for(;e<end;e++)e->pre=*AT(e);ST->capture=1;}
/* Compare and write in one pass; on a difference put back what was written. 1: skipped. */
static u32 skip(void)
{
    struct entry *e=ENT,*end=ENT+ST->n,*b;
    for(;e<end;e++){
        if(*AT(e)!=e->pre){for(b=ENT;b<e;b++)*AT(b)=b->pre;return 0;}
        *AT(e)=e->post;
    }
    return 1;
}
/* IRQ, at the stock body: RUN_STOCK, SKIPPED (outputs written) or RUN_AND_CHECK (run stock, then _after). */
u32 modulation_skip_decide(u32 working)
{
    struct state *st=ST;u32 same,writes,written,periodic,changed=0;
    if(st->mode!=VERIFY && st->mode!=ON)return RUN_STOCK;
    if(working!=WORKING){st->valid=0;return RUN_STOCK;}
    st->blocks++;
    writes=st->writes;written=writes!=st->seen;st->seen=writes;
    periodic=!(++st->ticks%CHECK_EVERY);
    same=tables_equal();
    if(written || periodic || st->mode==VERIFY){
        if(!machine_equal()){
            changed=1;same=0;
            if(!written && st->valid){                 /* changed with no write seen: an unknown writer */
                st->errors++;
                if(st->mode==ON){st->mode=OFF;st->valid=0;return RUN_STOCK;}
            }
        }
    }
    if(changed || !st->n){build();st->valid=0;}
    if(st->outside)return RUN_STOCK;
    if(same && st->valid){
        st->hits++;
        if(st->mode==ON && ++st->count%CHECK_EVERY){
            if(skip()){st->skips++;return SKIPPED;}
        }else if(entries_equal()){st->capture=0;return RUN_AND_CHECK;}
    }
    capture();st->valid=0;
    return RUN_AND_CHECK;
}
void modulation_skip_after(u32 working)
{
    struct state *st=ST;struct entry *e=ENT,*end=ENT+st->n;u32 bad=0,v;(void)working;
    for(;e<end;e++){v=*AT(e);if(!st->capture && v!=e->post)bad=1;e->post=(u16)v;}
    st->valid=1;
    if(bad){st->errors++;if(st->mode==ON){st->mode=OFF;st->valid=0;}}
}

/* ---- trampolines. 0x40097B7C: the stock body after its prologue (11 registers in 60 bytes, return at 60,
 * argument at 64), its two instructions moved here. RUN_AND_CHECK calls the stock body as a subroutine with a second
 * identical frame. 0x400A313C (machine-data writer, 1.41 0x400A30C4): one write counted before and one after. */
__asm__(
"        .text\n"
"        .globl modulation_skip_entry\n"
"modulation_skip_entry:\n"
"        move.l 64(%sp),-(%sp)\n"
"        jsr modulation_skip_decide\n"
"        addq.l #4,%sp\n"
"        tst.l %d0\n"
"        bne.s 1f\n"
"        movea.l 64(%sp),%a2\n"
"        move.l %a2,%d3\n"
"        jmp 0x40097b82\n"
"1:      subq.l #1,%d0\n"
"        beq.s 3f\n"
"        move.l 64(%sp),-(%sp)\n"
"        jsr 2f\n"
"        jsr modulation_skip_after\n"
"        addq.l #4,%sp\n"
"3:      movem.l (%sp),%d2-%d7/%a2-%a6\n"
"        lea 60(%sp),%sp\n"
"        rts\n"
"2:      lea -60(%sp),%sp\n"
"        movem.l %d2-%d7/%a2-%a6,(%sp)\n"
"        movea.l 64(%sp),%a2\n"
"        move.l %a2,%d3\n"
"        jmp 0x40097b82\n"
"        .globl modulation_skip_machine_entry\n"
"modulation_skip_machine_entry:\n"
"        addq.l #1,0x8000fc34\n"                 /* ST->writes */
"        move.l 8(%sp),-(%sp)\n"
"        move.l 8(%sp),-(%sp)\n"
"        jsr 4f\n"
"        addq.l #8,%sp\n"
"        addq.l #1,0x8000fc34\n"
"        rts\n"
"4:      lea -12(%sp),%sp\n"
"        movem.l %d2/%a2-%a3,(%sp)\n"
"        jmp 0x400a3144\n");
typedef char writes_offset[__builtin_offsetof(struct state,writes)==0x14?1:-1];

/* ---- sfcore module: init and header line */
static u32 ticks,seen_blocks,seen_hits,seen_skips;
static char line[24]="MSKIP --- H-- S-- E000";
static u32 shown(void){return MODULATION_SKIP_VERIFY || ST->errors || ST->mode==OFF;}
static void digits(char *at,u32 value,u32 k){while(k--){at[k]=(char)('0'+value%10u);value/=10u;}}
static void percent(char *at,u32 part,u32 whole)
{u32 v;if(!whole){at[0]=at[1]='-';return;}v=100u*part/whole;if(v>99u){at[0]=at[1]='!';}else digits(at,v,2);}
static void update(void)
{
    static const char tag[4][4]={"---","VER","ON ","OFF"};
    struct state *st=ST;u32 b=st->blocks,h=st->hits,s=st->skips,e=st->errors,i;
    for(i=0;i<3;i++)line[6+i]=tag[st->mode&3][i];
    percent(line+11,h-seen_hits,b-seen_blocks);percent(line+15,s-seen_skips,b-seen_blocks);
    digits(line+19,e>999u?999u:e,3);
    seen_blocks=b;seen_hits=h;seen_skips=s;
}
static void skip_tick(void *controller)
{ticks++;if(ticks%30u==0){update();if(shown())((u8 *)controller)[0x20]=1;}}
static void skip_draw(void *bitmap,void *controller)
{
    (void)controller;
    if(ticks/120u%2u!=1u || !shown())return;
    FILL(bitmap,18,54,127,63,0);
    TEXT(bitmap,FONT,20,55,0,"%s",line);
}
static int initialize(const struct st_smz_api *api)
{
    if(!api || !api->ui || api->ui->version<7)return 1;
    ST->mode=MODULATION_SKIP_VERIFY?VERIFY:ON;
    update();
    return 0;
}
static const struct st_smz_subscription subscriptions[]={
    {ST_EV_TICK,(void (*)(void))skip_tick},
    {ST_EV_DRAW,(void (*)(void))skip_draw}};
const struct st_smz_module modulation_skip_module={"MODULATION SKIP",initialize,subscriptions,2};
