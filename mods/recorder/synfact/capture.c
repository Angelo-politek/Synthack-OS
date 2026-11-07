/* Recorder audio IRQ extension; inherited key handling and UI cadence remain. */
typedef unsigned int u32;
typedef int s32;
typedef unsigned char u8;
extern volatile u32 sam_clock,sam_enabled,sam_source,sam_state,sam_post;
extern volatile u32 sam_mon,sam_peak;
extern volatile u32 sam_frames,sam_take_post;
extern u8 *sam_view,*sam_manager;
extern u32 sam_take_source,sam_limit,sam_trigger,sam_pcm_peak;
extern short *sam_pcm;
extern u32 sam_last_source,sam_ret_clock,sam_report[8];
extern s32 sam_ret[2][64];
extern void ui_sampler_native_tick(void);
u32 headroom_normalizing_skips DATA=0,headroom_ready_skips DATA=0;
u32 headroom_armed_quiet_blocks DATA=0;
u32 headroom_ui_meter_skipped_blocks DATA=0,headroom_ui_meter_samples DATA=0;
static u32 headroom_meter_phase DATA=23,headroom_meter_signature DATA=0xffffffffu;
/* MAIN PRE/POST keeps its existing one-block alignment and exact integer
 * arithmetic. A bus whose four return gains are zero needs only zero stores.
 * Process stereo pairs explicitly, avoiding dynamic gain indexing. */
#define RETURN_BANK(name,convert) \
static void __attribute__((noinline)) name(s32 *out,s32 gd0,s32 gr0,s32 gd1,s32 gr1) \
{ \
    const volatile s32 *del=(const volatile s32 *)0x8000dcd0u; \
    const volatile s32 *rev=(const volatile s32 *)0x8000ddd0u; \
    s32 c,d,r;u32 i; \
    __asm__("" : "+r"(del),"+r"(rev)); \
    if(!(gd0|gr0|gd1|gr1)) {for(i=0;i<64;i++)out[i]=0;return;} \
    for(i=0;i<64;i+=2) { \
        d=((del[i]>>15)+1)>>1;r=((rev[i]>>15)+1)>>1; \
        c=-(((gd0*d)>>1)+((gr0*r)>>1));out[i]=(convert); \
        d=((del[i+1]>>15)+1)>>1;r=((rev[i+1]>>15)+1)>>1; \
        c=-(((gd1*d)>>1)+((gr1*r)>>1));out[i+1]=(convert); \
    } \
}
RETURN_BANK(headroom_fx_bank,c>>11)
RETURN_BANK(headroom_direct_bank,(c>>13)*5)
/* Rounded return inputs are exactly zero in [-32768,32767]. Usually the
 * first active sample exits this scan. Quiet FX need no gain products, even
 * when their routing gains are active. This does not skip MAIN input frames. */
static u32 __attribute__((noinline)) headroom_quiet_returns(void)
{
    const volatile s32 *del=(const volatile s32 *)0x8000dcd0u;
    const volatile s32 *rev=(const volatile s32 *)0x8000ddd0u;
    u32 i;
    for(i=0;i<64;i++)
        if((((u32)del[i]+32768u)|((u32)rev[i]+32768u))&0xffff0000u)return 0;
    return 1;
}
/* Only the frozen take's correction bank is consumed. EMPTY changes prime
 * the requested bank on the preceding block; the original key handler primes
 * BOTH banks before publishing a new take. Other sources retain their native
 * tick. No consumer may use the other bank with this shared clock alone. */
static void __attribute__((noinline)) headroom_returns(u32 mode)
{
    const volatile s32 *left=(const volatile s32 *)(mode?0x8000e188u:0x8000e138u);
    const volatile s32 *right=(const volatile s32 *)(mode?0x8000e160u:0x8000e110u);
    s32 d0=((left[8]>>15)+1)>>1,r0=((left[9]>>15)+1)>>1;
    s32 d1=((right[8]>>15)+1)>>1,r1=((right[9]>>15)+1)>>1;
    if((d0|r0|d1|r1) && headroom_quiet_returns())d0=r0=d1=r1=0;
    if(mode)headroom_direct_bank(sam_ret[1],d0,r0,d1,r1);
    else headroom_fx_bank(sam_ret[0],d0,r0,d1,r1);
    sam_ret_clock=sam_clock;
}
static s32 headroom_side(s32 value,s32 correction)
{
    s32 x=(value>>16)+correction;
    if(x>32767)x=32767;
    if(x< -32768)x=-32768;
    return (s32)((u32)x<<16);
}
/* IRQ-owned scratch, initialized DATA in the loaded file. No allocation or
 * physical RAM reservation. Separating headroom_capture from bus conversion keeps the
 * per-frame loop free of source/state/limit checks and register spills. */
static s32 headroom_capture_block[32] DATA={0};
#define SCAN_MAIN(expr,store) \
    for(i=0;i<32;i++) { \
        value=(expr);store; \
        mag=value<0?0u-(u32)value:(u32)value; \
        if(mag>peak)peak=mag; \
    }
#define MAIN_BLOCK(name,setup,store,finish) \
static u32 __attribute__((noinline)) name(u32 source,u32 mode,u32 ready) \
{ \
    const volatile s32 *usb=(const volatile s32 *)0x80004760u; \
    const s32 *ret=sam_ret[mode?1:0]; \
    u32 i,peak=0,mag;s32 value;setup; \
    if(source==5) { \
        if(!ready) {SCAN_MAIN((usb[20*i]>>1)+(usb[20*i+1]>>1),store)} \
        else if(mode) {SCAN_MAIN((headroom_side(usb[20*i],ret[2*i])>>1)+(headroom_side(usb[20*i+1],ret[2*i+1])>>1),store)} \
        else {SCAN_MAIN((headroom_side(usb[20*i],-ret[2*i])>>1)+(headroom_side(usb[20*i+1],-ret[2*i+1])>>1),store)} \
    } else { \
        usb+=source==4;ret+=source==4; \
        if(!ready) {SCAN_MAIN(usb[20*i],store)} \
        else if(mode) {SCAN_MAIN(headroom_side(usb[20*i],ret[2*i]),store)} \
        else {SCAN_MAIN(headroom_side(usb[20*i],-ret[2*i]),store)} \
    } \
    finish;return peak; \
}
MAIN_BLOCK(headroom_main_meter,(void)0,(void)0,(void)0)
MAIN_BLOCK(headroom_main_capture,(void)0,headroom_capture_block[i]=value,(void)0)
/* The common RECORDING path owns a complete 32-frame slice. Convert straight
 * to PCM instead of storing/reloading scratch and rechecking capacity per
 * sample. Partial tails and the exact ARMED threshold retain the scratch path. */
#define RECORD_SETUP short *pcm=sam_pcm+sam_frames;u32 pcm_peak=sam_pcm_peak,pcm_mag;s32 pcm_value
#define RECORD_STORE \
    pcm_value=value>>16;pcm[i]=(short)pcm_value; \
    pcm_mag=pcm_value<0?0u-(u32)pcm_value:(u32)pcm_value; \
    if(pcm_mag>pcm_peak)pcm_peak=pcm_mag
#define RECORD_FINISH \
    if(sam_state==1 || sam_state==2) { \
        sam_frames+=32;sam_pcm_peak=pcm_peak; \
        __asm__ volatile("" ::: "memory"); \
        if(sam_frames==sam_limit || sam_frames==2880000u)sam_state=4; \
    }
MAIN_BLOCK(headroom_record_block,RECORD_SETUP,RECORD_STORE,RECORD_FINISH)

static void __attribute__((noinline)) headroom_capture(u32 state)
{
    u32 i=0,p=sam_frames,peak=sam_pcm_peak,limit=sam_limit,mag;
    short *pcm=sam_pcm;s32 value;
    if(state==1) {
        for(;i<32;i++) {
            value=headroom_capture_block[i];mag=value<0?0u-(u32)value:(u32)value;
            if(mag>sam_trigger){state=2;break;}
        }
    }
    if(state==2) {
        if(limit>2880000u)limit=2880000u;
        if(!pcm || p>=limit)state=p?4:0;
        else {
            for(;i<32 && p<limit;i++) {
                value=headroom_capture_block[i]>>16;pcm[p++]=(short)value;
                mag=value<0?0u-(u32)value:(u32)value;
                if(mag>peak)peak=mag;
            }
            if(p==limit)state=4;
        }
    }
    if(sam_state==1 || sam_state==2) {
        sam_frames=p;sam_pcm_peak=peak;
        __asm__ volatile("" ::: "memory");
        sam_state=state;
    }
}

/* MAIN PRE/POST, including armed/recording. Freeze source/mode for a take,
 * exactly as the native routine. Other sources use its original body.
 * No decimation: every frame contributes to peak and capture at 48 kHz. */
void headroom_tick(void)
{
    u32 source=sam_source,mode=sam_post,state=sam_state,ready,peak,old,take,meter=0,signature,limit,full;
    u8 *view=sam_view,*manager=sam_manager,*node;
    /* Closing is synchronous at the view flag; destruction/idle may occur
     * later. Do not leave an enabled meter behind a retired/covered view. */
    if(sam_enabled && view && manager) {
        node=*(u8 **)(manager+0x1c);
        if(view[0x30] || !node || node==manager+0x14 || *(u8 **)(node+8)!=view)sam_enabled=0;
    }
    if(!sam_enabled || source>=18) {sam_clock+=32;headroom_meter_phase=23;return;}
    /* NORMALIZING and READY own a closed take. Audition mixes independently
     * in sampler_playback_mix; input meters/monitor/returns have no consumer.
     * Keep the clock for screen/play-cursor cadence, including wraparound. */
    if(state==4 || (state==3 && sam_frames)) {
        sam_clock+=32;
        if(state==4)headroom_normalizing_skips++;else headroom_ready_skips++;
        return;
    }
    take=state==1 || state==2;
    if(take){source=sam_take_source;mode=sam_take_post;}
    /* The standby meter has no capture/threshold consumer. Sample at 60 Hz;
     * MAIN primes the PRE/POST correction on the preceding audio block.
     * Live input monitoring, ARMED and RECORDING always run every block. */
    if(state==0 && (!sam_mon || (source>=3 && source<6))) {
        signature=source|(mode<<8);
        if(signature!=headroom_meter_signature){headroom_meter_signature=signature;headroom_meter_phase=23;}
        if(headroom_meter_phase!=24) {
            sam_clock+=32;
            if(headroom_meter_phase==23 && source>=3 && source<6)headroom_returns(mode);
            headroom_meter_phase++;
            old=sam_peak;sam_peak=old-(old?(old>>9)+1u:0);
            headroom_ui_meter_skipped_blocks++;return;
        }
        headroom_meter_phase=0;meter=1;headroom_ui_meter_samples++;
    } else headroom_meter_phase=23;
    if(source<3 || source>=6) {
        ui_sampler_native_tick();return;
    }
    sam_clock+=32;ready=sam_ret_clock==sam_clock-32u;
    limit=sam_limit<2880000u?sam_limit:2880000u;
    full=state==2 && sam_pcm && sam_frames<=limit && limit-sam_frames>=32;
    peak=full?headroom_record_block(source,mode,ready):
        take?headroom_main_capture(source,mode,ready):headroom_main_meter(source,mode,ready);
    if(!meter)headroom_returns(mode);
    if(take && !full) {
        if(state==2 || peak>sam_trigger)headroom_capture(state);
        else headroom_armed_quiet_blocks++;
    }
    old=sam_last_source==source?sam_peak:0;
    old-=old?(old>>9)+1u:0;
    sam_peak=peak>old?peak:old;sam_last_source=source;
    sam_report[1]++;sam_report[5]=source;sam_report[6]=peak;
}

