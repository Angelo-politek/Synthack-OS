/* SPDX-License-Identifier: GPL-2.0-or-later
 * Native Data RPC high windows and independent stock-slot write guard.
 */
#include "file-info.h"
#include "hzfs.h"
#define RAW_FIRST ST_HZ_RAW_FIRST
#define STOCK_FIRST 0x00400000u
#define STOCK_END 0x02400000u
#define STOCK_BODY (64u+48000u*5u*2u)
extern u32 fw_mmc_ready[],fw_mmc_sectors[],fw_empty_string[];
extern int fw_mmc_read(u32,u32,void *),fw_mmc_write(u32,u32,const void *);
extern void *fw_malloc(u32);
extern void fw_free(void *),fw_info_copy(void *,const void *);
extern void fw_string_ctor(void *,const char *,void *),core_fn_manager(void);
extern void core_high_validate(void);
/* Native DataWriteClose calls its completion event only when this capture
 * is present. A non-owning no-op enables the existing ev_fs_written for high
 * windows too; no additional hook or storage mutation is introduced. */
void core_high_written(const struct fn *fn,const u8 *header){(void)fn;(void)header;}
static u32 card_sectors(void){return fw_mmc_ready[0]?fw_mmc_sectors[0]:0;}
const struct st_storage_io core_hzfs_native_io={fw_mmc_read,fw_mmc_write,card_sectors,fw_malloc,fw_free};
int core_hzfs_status;
void core_hzfs_startup(void){core_hzfs_status=core_hzfs_ensure(&core_hzfs_native_io);}
static void zero(void *p,u32 n){u8 *q=p;while(n--)*q++=0;}
static u32 rd(const u8 *p){return (u32)p[0]<<24|(u32)p[1]<<16|(u32)p[2]<<8|p[3];}
static void error(void *out,const char *s,u32 n)
{u8 a=0;zero(out,n);fw_string_ctor((u8 *)out+4,s,&a);}
static u32 remaining(u32 k)
{
    u32 sectors=card_sectors(),lba=k<<10;
    if(sectors>0x800000u)sectors=0x800000u;
    if(k<ST_HZ_FIRST || k>=0x2000 || lba>=sectors)return 0;
    return (sectors-lba)<<9; /* <= 0xd0000000, no byte-address wrap */
}
static int span(u32 k,u32 bytes){return bytes && bytes<=remaining(k);}
static int path_window(const char *s,u32 *out)
{
    const char *prefix="/samples/";u32 n=0,i;
    for(i=0;prefix[i];i++)if(!s[i] || s[i]!=prefix[i])return 0;
    s+=i;if(*s<'1' || *s>'9')return 0;
    do{if(n>1637)return 0;n=n*10+(u32)(*s++-'0');}while(*s>='0' && *s<='9');
    if(*s || n<RAW_FIRST+ST_HZ_FIRST || n>=RAW_FIRST+0x2000)return 0;
    *out=n-RAW_FIRST;return 1;
}
void core_high_check_header(void *out,const struct fn *fn,const u8 *h)
{
    u8 *r=out;
    if(!h || rd(h+13)!=8 || rd(h+21)!=RAW_FIRST+fn->data || !span(fn->data,rd(h+25))){
        error(out,"High-zone object exceeds destination or card",12);return;
    }
    zero(out,12);r[0]=1;*(void **)(r+4)=fw_empty_string;r[8]=1;
}
int core_high_route(void *router,const char *const *path,void *out)
{
    struct info info;u32 k,n;u8 *r=out;(void)router;
    if(!path || !*path || !path_window(*path,&k))return 0;
    if(!card_sectors()){error(out,"eMMC unavailable",0x84);return 1;}
    n=remaining(k);zero(&info,sizeof(info));info.type=8;info.kind=2;
    info.permissions=n?6:2;info.address=k<<19;info.bytes=n<ST_HZ_WINDOW?n:ST_HZ_WINDOW;
    info.id=RAW_FIRST+k;info.tag=0xffffffffu;
    info.validate.data=k;info.validate.manager=core_fn_manager;info.validate.invoke=core_high_validate;
    info.written.manager=core_fn_manager;info.written.invoke=core_high_written;
    zero(out,8);r[0]=1;*(void **)(r+4)=fw_empty_string;
    fw_info_copy(r+8,&info);return 1;
}
int core_sample_write_guard(void *router,const struct info *info,void *out)
{
    u32 address=info->address,k;(void)router;
    /* Header length has ALREADY replaced info.bytes, before writer creation.
     * Never silently truncate a Data object here: its CRC would no longer match.
     * The host trims audio and rebuilds the complete object before sending it. */
    if(address>=STOCK_FIRST && address<STOCK_END){
        if((address&(ST_HZ_WINDOW-1)) || info->bytes>STOCK_BODY ||
           info->bytes>STOCK_END-address){
            error(out,"Stock sample exceeds 5 seconds / one slot",16);return 1;
        }return 0;
    }
    if(info->validate.manager!=(void *)core_fn_manager ||
       info->validate.invoke!=(void *)core_high_validate)return 0;
    k=info->validate.data;
    if(info->type!=8 || info->kind!=2 || info->id!=RAW_FIRST+k ||
       address!=(k<<19) || !span(k,info->bytes)){
        error(out,"High-zone write outside destination or card",16);return 1;
    }
    return 0;
}
