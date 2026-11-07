/* Field map witnessed in native MAIN 400a31a2/400a30c4/40097952.
 * Parameters only: no Sound/model, filter/envelope state, note or LFO advance.
 *
 * : runs once per published block (1500/s). Plain copies: the former
 * volatile counters cost ~2200 instructions per SLAVE and block. The 142-byte
 * working block is copied as longs when source and destination share 4-byte
 * alignment (owner and SLAVE of equal parity), else as halfwords. */
typedef unsigned int u32;
typedef unsigned short u16;
typedef unsigned char u8;

/* Five words per iteration: both sizes used here are multiples of five. */
static void copy_longs5(u32 *d,const u32 *s,u32 groups)
{
    do {*d++=*s++;*d++=*s++;*d++=*s++;*d++=*s++;*d++=*s++;}while(--groups);
}

static void copy_halves5(u16 *d,const u16 *s,u32 groups)
{
    do {*d++=*s++;*d++=*s++;*d++=*s++;*d++=*s++;*d++=*s++;}while(--groups);
}

static void copy_working(u8 *dst,const u8 *src)
{
    if(!(((u32)dst|(u32)src)&3u))copy_longs5((u32 *)dst,(const u32 *)src,7);   /* 140 B */
    else copy_halves5((u16 *)dst,(const u16 *)src,14);                         /* 140 B */
    ((u16 *)dst)[70]=((const u16 *)src)[70];
}

void poly_publish(u8 *working,const volatile u8 *owners)
{
    u32 t,owner,j;
    u8 *dst;
    const u8 *src;
    for(t=1;t<poly_publish_end;t++) {
        owner=owners[t];
        if(owner>=t)continue;
        ((u16 *)working)[t]=((const u16 *)working)[owner];
        copy_working(working+0x1cu+t*0x8eu,working+0x1cu+owner*0x8eu);
        dst=working+0x754u+t*0x7cu;
        src=working+0x754u+owner*0x7cu;
        copy_longs5((u32 *)dst,(const u32 *)src,5);                                /* 100 B */
        dst[0x64]=src[0x64];
        for(j=0x68;j<0x78;j+=4)*(u32 *)(dst+j)=*(const u32 *)(src+j);
        for(j=0x78;j<0x7b;j++)dst[j]=src[j];
    }
}
