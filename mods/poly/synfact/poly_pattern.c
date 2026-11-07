/* Laboratory-only wrappers. No physical storage allocation or firmware release. */
typedef unsigned int u32;
typedef unsigned char u8;
extern u32 stock_header_load(u8 *,const u8 *);
extern void stock_header_reset(u8 *,u32);

/* Express XOR through audited ADD/SUB/AND. Volatile keeps the compiler from
 * selecting an unaudited EOR form; this runs only on header load/reset. */
static u32 xor_bits(u32 a,u32 b)
{
    volatile u32 both=a&b;
    return (a+b)-(both+both);
}

static u32 legacy_valid(const volatile u8 *p)
{
    u32 crc=65535u,j,state,width,position=0;
    volatile u32 i,bits;
    if(p[0]!=0x50u || (p[1]!=0x51u && (p[1]&0xf8u)!=0x58u))return 0;
    if(p[1]!=0x51u && (((p[1]&2u) && !(p[1]&4u)) ||
                     ((p[1]&4u) && (p[1]&1u))))return 0;
    for(i=0;i<5;i++) {
        crc=xor_bits(crc,(u32)p[i]<<8);
        for(j=0;j<8;j++)crc=xor_bits(crc<<1,(crc&32768u)?0x1021u:0u)&65535u;
    }
    if(crc!=(((u32)p[5]<<8)+p[6]))return 0;
    bits=p[2];
    bits=(bits<<8)+p[3];
    bits=(bits<<8)+p[4];
    for(i=0;i<8;i++)if(((bits>>(21u-3u*i))&7u)>5u)return 0;
    while(position<8) {
        state=(bits>>(21u-3u*position))&7u;
        if(state<3u){position++;continue;}
        width=state-1;
        if(position+width>8u)return 0;
        for(j=1;j<width;j++)if(((bits>>(21u-3u*(position+j)))&7u)>=3u)return 0;
        position+=width;
    }
    return 1;
}

#include "poly_codec.c"

u32 poly_header_load(u8 *destination,const u8 *source)
{
    u32 result=stock_header_load(destination,source),i,ok;
    if(destination && source && (result&255u)) {
        ok=valid(source+0x21);
        for(i=0;i<7;i++)destination[0x21+i]=ok?source[0x21+i]:0;
    }
    return result;
}

void poly_header_reset(u8 *destination,u32 quiet)
{
    u32 i;
    stock_header_reset(destination,quiet);
    if(destination && (!quiet || !valid(destination+0x21)))
        for(i=0;i<7;i++)destination[0x21+i]=0;
}
