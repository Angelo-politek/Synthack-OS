/* SPDX-License-Identifier: GPL-2.0-or-later
 * Shared MAIN native-bus mono audition primitive. Inverted Q31, stereo,
 * 32 frames; caller owns its IRQ PCM publication. No IO/heap/EMAC state.
 */
#ifndef ELEKLOADER_ST_MIX_H
#define ELEKLOADER_ST_MIX_H
static __inline__ void st_main_mix_frame(int *bus,unsigned int frame,int x)
{
    int y;unsigned int a,b,r;
    for(b=0;b<2;b++){
        y=bus[2*frame+b];a=(unsigned int)y;r=a-(unsigned int)x;
        if(((a^(unsigned int)x)&(a^r))&0x80000000u)r=y<0?0x80000000u:0x7fffffffu;
        bus[2*frame+b]=(int)r;
    }
}
/* Preview/monitor bus: 8000dfd0 reaches MAIN without the FX track's analog
 * block, unlike 8000dad0 (device report 2026-10-28; USB MAIN = 8 x (ADC sum
 * 8000ded0 + 8000dfd0), 8000dad0 absent). Its 4008eeca stage is x8 instead
 * of x10: x+x/4 keeps the previous digital level (10/32 for full PCM16). */
#define ST_PREVIEW_BUS ((int *)0x8000dfd0u)
static __inline__ void st_preview_mix_frame(int *bus,unsigned int frame,int x)
{
    st_main_mix_frame(bus,frame,x+(x>>2));
}
#endif
