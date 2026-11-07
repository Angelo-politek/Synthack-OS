/* PR: retain the experimental four-code rank geometry, including OFF voice
 * preferences, inside the existing 24-bit PQ payload. Only codes 0/1 remain active.
 * No adjacent native header byte is used. PQ still decodes as shared LFO. */
static const u32 poly_counts[9]={1,3,21,135,873,5319,33561,210519,1320057};
static const u32 poly_pow3[4]={1,3,9,27};

static u32 poly_crc(const volatile u8 *p)
{
    u32 crc=65535u,i,j;
    for(i=0;i<5;i++) {
        crc=xor_bits(crc,(u32)p[i]<<8);
        for(j=0;j<8;j++)crc=xor_bits(crc<<1,(crc&32768u)?0x1021u:0u)&65535u;
    }
    return crc;
}

static u32 poly_decode_record(const volatile u8 *p,u8 *states,u8 *modes)
{
    u32 i,rank,n,w,block,code,j,analog=0;
    for(i=0;i<12;i++)states[i]=0;
    for(i=0;i<8;i++)modes[i]=0;
    if(p[0]!=0x50)return 0;
    rank=((u32)p[2]<<16)+((u32)p[3]<<8)+p[4];
    if(p[1]==0x51 || (p[1]&0xf8u)==0x58u) {
        if(!legacy_valid(p))return 0;
        for(i=0;i<8;i++)states[i]=(u8)((rank>>(21-3*i))&7u);
        if(p[1]!=0x51) {
            if(p[1]&4u)states[8]=(p[1]&2u)?4:3;
            if(p[1]&1u)states[9]=3;
        }
        return 1;
    }
    if(p[1]==0x53){analog=rank&3u;rank>>=2;}
    if((p[1]!=0x52 && p[1]!=0x53) || poly_crc(p)!=(((u32)p[5]<<8)+p[6]) || rank>=poly_counts[8])return 0;
    if(analog==1)states[8]=3;
    if(analog==2)states[8]=4;
    if(analog==3)states[9]=3;
    i=0;
    while(i<8) {
        n=8-i;block=3*poly_counts[n-1];
        if(rank<block) {
            states[i]=(u8)(rank/poly_counts[n-1]);
            rank%=poly_counts[n-1];i++;continue;
        }
        rank-=block;
        for(w=2;w<=4 && w<=n;w++) {
            block=4*poly_pow3[w-1]*poly_counts[n-w];
            if(rank>=block){rank-=block;continue;}
            states[i]=(u8)(w+1);
            code=rank/poly_counts[n-w];rank%=poly_counts[n-w];
            modes[i]=(u8)(code/poly_pow3[w-1]);code%=poly_pow3[w-1];
            for(j=1;j<w;j++){states[i+j]=(u8)(code%3);code/=3;}
            break;
        }
        if(w>4 || w>n)return 0;
        i+=w;
    }
    return rank==0;
}

/* Keep the experimental PR geometry readable. Retired mono/legato values
 * migrate to M.LFO, retaining the group and every OFF voice preference. */
static u32 poly_decode(const volatile u8 *p,u8 *states,u8 *modes)
{
    u32 ok=poly_decode_record(p,states,modes),i;
    for(i=0;i<8;i++)if(modes[i]>1)modes[i]=0;
    for(i=8;i<12;i++)states[i]=0;   /* SyntHack: a saved analog group is ignored (analog POLY not ported) */
    return ok;
}

static u32 poly_rank(const u8 *states,const u8 *modes,u32 i)
{
    u32 n=8-i,w,j,rank,code=0;
    if(!n)return 0;
    if(states[i]<3)return states[i]*poly_counts[n-1]+poly_rank(states,modes,i+1);
    w=states[i]-1;
    rank=3*poly_counts[n-1];
    for(j=2;j<w;j++)rank+=4*poly_pow3[j-1]*poly_counts[n-j];
    for(j=1;j<w;j++)code+=states[i+j]*poly_pow3[j-1];
    code+=modes[i]*poly_pow3[w-1];
    return rank+code*poly_counts[n-w]+poly_rank(states,modes,i+w);
}

static void poly_encode(u8 *p,const u8 *states,const u8 *modes)
{
    u32 i,bits=0,extended=0,crc,analog=states[8]>=3?(states[8]==4?2u:1u):states[9]>=3?3u:0u;
    for(i=0;i<8;i++) {
        bits=(bits<<3)+states[i];
        if(states[i]>=3 && modes[i])extended=1;
    }
    if(extended)bits=poly_rank(states,modes,0);
    p[0]=0x50;p[1]=(u8)(extended?0x52:0x51);
    if(analog) {
        if(extended){bits=(bits<<2)|analog;p[1]=0x53;}
        else p[1]=(u8)(analog==1?0x5c:analog==2?0x5e:0x59);
    }
    p[2]=(u8)(bits>>16);p[3]=(u8)(bits>>8);p[4]=(u8)bits;
    crc=poly_crc(p);p[5]=(u8)(crc>>8);p[6]=(u8)crc;
}

static u32 valid(const volatile u8 *p)
{u8 states[12],modes[8];return poly_decode(p,states,modes);}

/* Legacy analog callers retain the same PQ/PX serialization. */
static void record_states(const volatile u8 *p,u8 *states)
{u8 modes[8];poly_decode(p,states,modes);}
static void record_encode(const u8 *states,u8 *p)
{const u8 modes[8]={0};poly_encode(p,states,modes);}
