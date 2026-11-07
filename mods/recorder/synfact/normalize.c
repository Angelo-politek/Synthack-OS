/* UI-owned bounded normalization. Same Q16 PCM and zero-inclusive envelopes.
 * Split only at existing 256-frame detail / 126-column wave boundaries.
 * Each inner run needs two extrema in registers, not four indexed arrays and
 * absolute peak / boundary bookkeeping per sample. No second PCM or new RAM. */
typedef unsigned int u32;
typedef int s32;
extern volatile u32 sam_state,sam_frames,sam_enabled;
extern short *sam_pcm;
extern u32 sam_pcm_peak,sam_norm_pos,sam_norm_gain,sam_norm_init,sam_norm_shown;
extern u32 sam_norm_bin,sam_norm_next,sam_display_peak,sam_detail_frames;
extern u32 sam_wave_ready,sam_trim_valid,sam_focus;
extern short sam_wave_low[],sam_wave_high[],sam_detail_low[],sam_detail_high[];
extern void sam_trim_init(void);
#ifndef NORM_QUOTA
#define NORM_QUOTA 3072u
#endif
void normalize_fast(void)
{
    u32 n=sam_frames,p=sam_norm_pos,end,stop,detail,bin,next,i,peak,mag;
    short *pcm=sam_pcm,*at,*limit;
    s32 gain,lo,hi,value;
    if(sam_state!=4 || (sam_enabled && !sam_norm_shown))return;
    if(!pcm || !n || n>2880000u){sam_state=0;return;}
    if(!sam_norm_init) {
        sam_norm_gain=sam_pcm_peak?(29204u*65536u)/sam_pcm_peak:65536u;
        sam_norm_bin=0;sam_norm_next=(n+125u)/126u;
        sam_display_peak=1;sam_detail_frames=0;
        for(i=0;i<126;i++){sam_wave_low[i]=0;sam_wave_high[i]=0;}
        sam_norm_init=1;
    }
    gain=(s32)sam_norm_gain;bin=sam_norm_bin;next=sam_norm_next;
    peak=sam_display_peak;end=p+NORM_QUOTA;if(end>n)end=n;
    while(p<end) {
        while(p>=next && bin<125){bin++;next=((bin+1u)*n+125u)/126u;}
        detail=p>>8;
        if(!(p&255u)){sam_detail_low[detail]=0;sam_detail_high[detail]=0;}
        stop=(p|255u)+1u;if(stop>end)stop=end;
        if(bin<125 && next<stop)stop=next;
        at=pcm+p;limit=pcm+stop;lo=0;hi=0;
        /* MULS.L gives the same modulo-32 product as the parent. SWAP puts
         * its signed high word in the low word. Store and compare that word
         * directly; extend just the final extrema, once per run. Compact
         * scalar loop: no unrolling, saturation, EMAC or FPU state. */
#ifdef __m68k__
        __asm__ volatile(
            "1:\n\tmvs.w (%0),%3\n\tmuls.l %4,%3\n\tswap %3\n\t"
            "move.w %3,(%0)+\n\tcmp.w %1,%3\n\tbge 2f\n\tmove.w %3,%1\n"
            "2:\n\tcmp.w %2,%3\n\tble 3f\n\tmove.w %3,%2\n"
            "3:\n\tcmp.l %5,%0\n\tbcs 1b\n\text.l %1\n\text.l %2"
            : "+&a"(at),"+&d"(lo),"+&d"(hi),"=&d"(value)
            : "d"(gain),"a"(limit) : "cc","memory");
#else
        do {
            value=(s32)(short)(((u32)(s32)*at*(u32)gain)>>16);
            *at++=(short)value;if(value<lo)lo=value;if(value>hi)hi=value;
        }while(at<limit);
#endif
        if(lo<sam_detail_low[detail])sam_detail_low[detail]=(short)lo;
        if(hi>sam_detail_high[detail])sam_detail_high[detail]=(short)hi;
        if(lo<sam_wave_low[bin])sam_wave_low[bin]=(short)lo;
        if(hi>sam_wave_high[bin])sam_wave_high[bin]=(short)hi;
        mag=(u32)-lo;if(mag>peak)peak=mag;
        if((u32)hi>peak)peak=(u32)hi;
        p=stop;
    }
    sam_norm_pos=p;sam_norm_bin=bin;sam_norm_next=next;sam_display_peak=peak;
    if(p==n) {
        sam_detail_frames=n;sam_wave_ready=1;sam_trim_valid=0;
        sam_trim_init();sam_focus=0;sam_state=3;
    }
}
