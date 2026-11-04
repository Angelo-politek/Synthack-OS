/* SPDX-License-Identifier: GPL-2.0-or-later
 * HZFS v1, source implementation. No firmware blobs or runtime patch plans.
 * Sector IO is confined to the high zone. Both valid catalogues reserve data
 * until a new verified catalogue replaces the older one.
 */
#include "hzfs.h"
#include "crc.h"
typedef unsigned int u32;typedef unsigned char u8;
#define CHUNK 4096u
static u32 rd(const u8 *p){return (u32)p[0]<<24|(u32)p[1]<<16|(u32)p[2]<<8|p[3];}
static void wr(u8 *p,u32 n){p[0]=n>>24;p[1]=n>>16;p[2]=n>>8;p[3]=n;}
static void zero(void *p,u32 n){u8 *q=p;while(n--)*q++=0;}
static void cp(void *d,const void *s,u32 n){u8 *a=d;const u8 *b=s;while(n--)*a++=*b++;}
static int eq(const void *a,const void *b,u32 n)
{const u8 *p=a,*q=b;while(n--)if(*p++!=*q++)return 0;return 1;}
/* zlib.crc32(bytes, 0xffffffff): internal register begins at zero. */
#define crc_step core_crc_update
static u32 checksum(u8 *p,u32 n)
{u32 saved=rd(p+32),c;wr(p+32,0);c=~crc_step(0,p,n);wr(p+32,saved);return c;}
static u32 windows(const struct st_storage_io *io)
{u32 n=io->sectors();if(n>0x800000u)n=0x800000u;return n>>10;}
static int transfer(const struct st_storage_io *io,int writing,u32 lba,u32 n,void *p)
{
    u32 card=io->sectors();
    if(lba<(ST_HZ_FIRST<<10) || lba>=0x800000u || !n || (n&511) ||
       n>CHUNK || lba>=card || (n>>9)>card-lba || (n>>9)>0x800000u-lba)return ST_HZ_CAPACITY;
    return (writing?io->write(lba,n,p):io->read(lba,n,p))?ST_HZ_IO:ST_HZ_OK;
}
static const u8 *entry(const u8 *p,u32 i){return p+ST_HZ_ENTRIES+64*i;}
static int compare(const u8 *p,u32 a,u32 b,u32 mode)
{
    const u8 *x=entry(p,a),*y=entry(p,b);u32 i,l,r;
    if(mode==2){l=st_hz_member(p,a);r=st_hz_member(p,b);if(l!=r)return l<r?-1:1;}
    if(mode<2){l=rd(x+4*mode);r=rd(y+4*mode);return l<r?-1:l>r;}
    for(i=32;i<64;i++){if(x[i]!=y[i])return x[i]<y[i]?-1:1;if(!x[i])return 0;}return 0;
}
/* Heapsort a bounded array of entry indices: no recursion or quadratic scan
 * of the maximum-size catalogue during boot. */
static void sift(u32 *a,u32 root,u32 n,const u8 *p,u32 mode)
{
    u32 child,t;while((child=2*root+1)<n){
        if(child+1<n && compare(p,a[child],a[child+1],mode)<0)child++;
        if(compare(p,a[root],a[child],mode)>=0)return;
        t=a[root];a[root]=a[child];a[child]=t;root=child;
    }
}
static void sort(u32 *a,u32 n,const u8 *p,u32 mode)
{u32 i,t;for(i=0;i<n;i++)a[i]=i;for(i=n/2;i;i--)sift(a,i-1,n,p,mode);
 for(i=n;i>1;i--){t=a[0];a[0]=a[i-1];a[i-1]=t;sift(a,0,i-1,p,mode);}}
/* Task-only validation; all pointers are bounded by the checked catalogue
 * length before this traversal. Folders consume no PCM extents or pool IDs. */
static int folders_valid(const u8 *p)
{
    u32 n=rd(p+12),f=st_hz_folder_count(p),i,j,k,parent,depth,next=rd(p+44);
    const u8 *d,*other;
    if(rd(p+4)!=2)return 1;
    if(!next)return 0;
    for(i=0;i<f;i++) {
        d=st_hz_folder_record(p,i);
        if(!rd(d) || rd(d)>=32767 || rd(d)>=next || !d[8] || rd(d+40) || rd(d+44))return 0;
        for(k=8;k<40 && d[k];k++)if(d[k]<32 || d[k]=='/' || d[k]=='\\')return 0;
        if((d[8]=='.' && !d[9]) || (d[8]=='.' && d[9]=='.' && !d[10]))return 0;
        for(j=0;j<i;j++) {
            other=st_hz_folder_record(p,j);
            if(rd(d)==rd(other) || (rd(d+4)==rd(other+4) && eq(d+8,other+8,32)))return 0;
        }
        parent=rd(d+4);depth=1;
        while(parent) {
            if(++depth>16 || parent==rd(d))return 0;
            for(j=0;j<f && rd(st_hz_folder_record(p,j))!=parent;j++){}
            if(j==f)return 0;
            parent=rd(st_hz_folder_record(p,j)+4);
        }
    }
    for(i=0;i<n;i++)if((parent=st_hz_member(p,i))) {
        for(j=0;j<f && rd(st_hz_folder_record(p,j))!=parent;j++){}
        if(j==f)return 0;
    }
    return 1;
}
static int valid(const struct st_storage_io *io,u8 *p,u32 length,u32 capacity)
{
    u32 f=st_hz_folder_count(p),version=rd(p+4),count=rd(p+12),next=rd(p+28),n=rd(p+24),i,j,id,first,blocks,bytes,frames;
    u32 *order;const u8 *e,*prev;
    if(rd(p)!=0x485a4653u || (version!=1 && version!=2) || !rd(p+8) ||
       count>ST_HZ_MAX_ENTRIES || f>ST_HZ_MAX_FOLDERS || length>ST_HZ_WINDOW || length!=st_hz_length(version,count,f) || rd(p+36)!=length ||
       rd(p+16)!=ST_HZ_WINDOW || rd(p+20)!=ST_HZ_DATA ||
       n<=ST_HZ_DATA || n>capacity || !next || checksum(p,length)!=rd(p+32))return ST_HZ_CORRUPT;
    if(!folders_valid(p))return ST_HZ_CORRUPT;
    for(i=0;i<count;i++){
        e=entry(p,i);id=rd(e);first=rd(e+4);blocks=rd(e+8);bytes=rd(e+12);frames=rd(e+16);
        if(!id || id>=next || first<ST_HZ_DATA || first>=n || !blocks || blocks>n-first ||
           bytes<64 || frames>(0xffffffffu-64)/2 || bytes!=64+2*frames ||
           blocks!=1+(bytes-1)/ST_HZ_WINDOW || !e[32])return ST_HZ_CORRUPT;
    }
    order=count?io->alloc(4*count):0;if(count && !order)return ST_HZ_MEMORY;
    for(j=0;j<3;j++){
        sort(order,count,p,j);
        for(i=1;i<count;i++){
            prev=entry(p,order[i-1]);e=entry(p,order[i]);
            if((j==1 && rd(e+4)<rd(prev+4)+rd(prev+8)) ||
               (j!=1 && !compare(p,order[i-1],order[i],j))){io->free(order);return ST_HZ_CORRUPT;}
        }
    }
    if(order)io->free(order);
    for(i=0;i<64;i++)if((id=rd(p+64+4*i))){
        for(j=0;j<count && rd(entry(p,j))!=id;j++){}
        if(j==count)return ST_HZ_CORRUPT;
    }
    return ST_HZ_OK;
}
static int load(const struct st_storage_io *io,u32 k,u32 capacity,u8 **out,u32 *length)
{
    u8 head[512],*p;u32 len,off,bytes;int r;
    *out=0;*length=0;r=transfer(io,0,k<<10,512,head);if(r<0)return r;
    len=rd(head+36);
    if(rd(head)!=0x485a4653u)return ST_HZ_ABSENT;
    /* Validate CRC before classifying a recognizable newer/malformed header.
     * Never silently use a stale copy's allocation map for such metadata. */
    if(len<ST_HZ_ENTRIES || len>ST_HZ_WINDOW)return ST_HZ_CORRUPT;
    bytes=(len+511)&~511u;p=io->alloc(bytes);if(!p)return ST_HZ_MEMORY;
    for(off=0;off<bytes;off+=CHUNK){
        r=transfer(io,0,(k<<10)+(off>>9),bytes-off>CHUNK?CHUNK:bytes-off,p+off);
        if(r<0){io->free(p);return r;}
    }
    if(checksum(p,len)!=rd(p+32)){io->free(p);return ST_HZ_ABSENT;}
    r=valid(io,p,len,capacity);
    if(r!=ST_HZ_OK){io->free(p);return r;}
    *out=p;*length=len;return ST_HZ_OK;
}
void core_hzfs_close(struct st_hzfs *fs)
{u32 i;for(i=0;i<2;i++)if(fs->copy[i]){fs->io->free(fs->copy[i]);fs->copy[i]=0;}}
int core_hzfs_open(struct st_hzfs *fs,const struct st_storage_io *io)
{
    int r;u32 i;zero(fs,sizeof(*fs));fs->io=io;fs->windows=windows(io);
    if(fs->windows<=ST_HZ_DATA)return ST_HZ_CAPACITY;
    for(i=0;i<2;i++){
        r=load(io,ST_HZ_FIRST+i,fs->windows,&fs->copy[i],&fs->length[i]);
        if(r<0){core_hzfs_close(fs);return r;}
    }
    if(!fs->copy[0] && !fs->copy[1])return ST_HZ_ABSENT;
    fs->best=!fs->copy[0] || (fs->copy[1] && rd(fs->copy[1]+8)>rd(fs->copy[0]+8));
    /* Equal sequences must describe exactly the same state. */
    if(fs->copy[0] && fs->copy[1] && rd(fs->copy[0]+8)==rd(fs->copy[1]+8) &&
       (fs->length[0]!=fs->length[1] || !eq(fs->copy[0],fs->copy[1],fs->length[0]))){
        core_hzfs_close(fs);return ST_HZ_CORRUPT;
    }
    return ST_HZ_OK;
}
static int write_verify(const struct st_storage_io *io,u32 lba,u8 *p,u32 n)
{
    u8 back[512];u32 off;int r;
    for(off=0;off<n;off+=512){
        r=transfer(io,1,lba+(off>>9),512,p+off);if(r<0)return r;
        r=transfer(io,0,lba+(off>>9),512,back);if(r<0)return r;
        if(!eq(back,p+off,512))return ST_HZ_IO;
    }return ST_HZ_OK;
}
int core_hzfs_ensure(const struct st_storage_io *io)
{
    struct st_hzfs fs;u8 buf[512],*scan;u32 k,off,i;int r=core_hzfs_open(&fs,io);
    if(r==ST_HZ_OK){core_hzfs_close(&fs);return r;}if(r!=ST_HZ_ABSENT)return r;
    /* Scan both COMPLETE index windows before the first write. */
    scan=io->alloc(CHUNK);if(!scan)return ST_HZ_MEMORY;
    for(k=ST_HZ_FIRST;k<ST_HZ_DATA;k++)for(off=0;off<ST_HZ_WINDOW;off+=CHUNK){
        r=transfer(io,0,(k<<10)+(off>>9),CHUNK,scan);if(r<0){io->free(scan);return r;}
        for(i=0;i<CHUNK;i++)if(scan[i]!=0 && scan[i]!=255){io->free(scan);return ST_HZ_CORRUPT;}
    }
    io->free(scan);
    zero(buf,512);wr(buf,0x485a4653);wr(buf+4,1);wr(buf+8,1);
    wr(buf+16,ST_HZ_WINDOW);wr(buf+20,ST_HZ_DATA);wr(buf+24,windows(io));
    wr(buf+28,1);wr(buf+36,ST_HZ_ENTRIES);wr(buf+32,checksum(buf,ST_HZ_ENTRIES));
    for(k=ST_HZ_FIRST;k<ST_HZ_DATA;k++){
        r=write_verify(io,k<<10,buf,512);if(r<0)return r;
    }return ST_HZ_OK;
}
u32 core_hzfs_count(const struct st_hzfs *fs){return rd(fs->copy[fs->best]+12);}
int core_hzfs_entry(const struct st_hzfs *fs,u32 n,struct st_sample_entry *out)
{
    const u8 *e;if(n>=core_hzfs_count(fs))return ST_HZ_NOT_FOUND;
    e=entry(fs->copy[fs->best],n);
    out->id=rd(e);out->first=rd(e+4);out->blocks=rd(e+8);out->bytes=rd(e+12);
    out->frames=rd(e+16);out->crc=rd(e+20);out->created=rd(e+24);out->flags=rd(e+28);
    cp(out->name,e+32,32);out->name[32]=0;return ST_HZ_OK;
}
static int commit(struct st_hzfs *fs,u8 *p,u32 len)
{
    u32 seq=rd(fs->copy[fs->best]+8),target=1-fs->best;
    if(seq==0xffffffffu)return ST_HZ_FULL;
    wr(p+8,seq+1);wr(p+36,len);wr(p+32,checksum(p,len));
    return write_verify(fs->io,(ST_HZ_FIRST+target)<<10,p,(len+511)&~511u);
}
static u32 find(const struct st_hzfs *fs,u32 id)
{u32 i,n=core_hzfs_count(fs);for(i=0;i<n && rd(entry(fs->copy[fs->best],i))!=id;i++){}return i;}
int core_hzfs_remove(const struct st_storage_io *io,u32 id)
{
    struct st_hzfs fs;u8 *p,*next;u32 i,n,len;int r=core_hzfs_open(&fs,io);if(r!=1)return r;
    n=core_hzfs_count(&fs);i=find(&fs,id);if(i==n){r=ST_HZ_NOT_FOUND;goto done;}
    p=fs.copy[fs.best];len=fs.length[fs.best]-(rd(p+4)==2?68u:64u);
    next=io->alloc((len+511)&~511u);if(!next){r=ST_HZ_MEMORY;goto done;}
    zero(next,(len+511)&~511u);cp(next,p,ST_HZ_ENTRIES+64*i);
    cp(next+ST_HZ_ENTRIES+64*i,entry(p,i+1),64*(n-i-1));
    if(rd(p+4)==2){
        u32 dst=ST_HZ_ENTRIES+64*(n-1),src=ST_HZ_ENTRIES+64*n;
        cp(next+dst,p+src,4*i);cp(next+dst+4*i,p+src+4*(i+1),4*(n-i-1));
        cp(next+dst+4*(n-1),p+src+4*n,ST_HZ_FOLDER_BYTES*st_hz_folder_count(p));
    }
    wr(next+12,n-1);
    for(i=0;i<64;i++)if(rd(next+64+4*i)==id)wr(next+64+4*i,0);
    r=commit(&fs,next,len);io->free(next);
done:core_hzfs_close(&fs);return r;
}
static int samp(const u8 *p,u32 bytes)
{return rd(p)==0x53414d50u && bytes>=64 && rd(p+8)==(bytes-64)/2 && !(bytes&1);}
int core_hzfs_put(const struct st_storage_io *io,const char *name,u32 bytes,u32 created,
                  st_sample_stream source,void *opaque,u32 *id_out)
{
    struct st_hzfs fs;u8 *index=0,*buf=0,*back=0,*e;const u8 *old;
    u32 n,len,i,j,k,first=ST_HZ_DATA,blocks,limit,off,take,physical,again,end,c=0,name_len=0,id;
    int r;
    if(!name || !source || !id_out || bytes<64 || (bytes&1))return ST_HZ_ARGUMENT;
    while(name[name_len] && name_len<33)name_len++;
    if(!name_len || name_len>32)return ST_HZ_ARGUMENT;
    r=core_hzfs_ensure(io);if(r!=1)return r;r=core_hzfs_open(&fs,io);if(r!=1)return r;
    old=fs.copy[fs.best];len=fs.length[fs.best];n=core_hzfs_count(&fs);id=rd(old+28);limit=rd(old+24);
    if(len>ST_HZ_WINDOW-(rd(old+4)==2?68u:64u) || n==ST_HZ_MAX_ENTRIES || id==0xffffffffu || rd(old+8)==0xffffffffu){r=ST_HZ_FULL;goto done;}
    for(i=0;i<n;i++){
        e=(u8 *)entry(old,i);for(j=0;j<32 && e[32+j] && j<name_len && e[32+j]==(u8)name[j];j++){}
        if(!st_hz_member(old,i) && j==name_len && (j==32 || !e[32+j])){r=ST_HZ_EXISTS;goto done;}
    }
    blocks=1+(bytes-1)/ST_HZ_WINDOW;
    /* First fit over the union, not just the selected catalogue. */
    do{
        again=0;if(first>=limit || blocks>limit-first){r=ST_HZ_FULL;goto done;}
        for(k=0;k<2;k++)if(fs.copy[k])for(i=0;i<rd(fs.copy[k]+12);i++){
            e=(u8 *)entry(fs.copy[k],i);end=rd(e+4)+rd(e+8);
            if(first<end && rd(e+4)<first+blocks){first=end;again=1;}
        }
    }while(again);
    index=io->alloc((len+(rd(old+4)==2?68u:64u)+511)&~511u);buf=io->alloc(CHUNK);back=io->alloc(CHUNK);
    if(!index || !buf || !back){r=ST_HZ_MEMORY;goto done;}
    zero(index,(len+(rd(old+4)==2?68u:64u)+511)&~511u);cp(index,old,ST_HZ_ENTRIES+64*n);
    if(rd(old+4)==2){
        cp(index+ST_HZ_ENTRIES+64*(n+1),old+ST_HZ_ENTRIES+64*n,4*n);
        cp(index+ST_HZ_ENTRIES+68*(n+1),old+ST_HZ_ENTRIES+68*n,ST_HZ_FOLDER_BYTES*st_hz_folder_count(old));
    }
    for(off=0;off<bytes;off+=take){
        take=bytes-off>CHUNK?CHUNK:bytes-off;physical=(take+511)&~511u;zero(buf,physical);
        if(source(opaque,off,take,buf)){r=ST_HZ_IO;goto done;}
        if(!off && !samp(buf,bytes)){r=ST_HZ_ARGUMENT;goto done;}
        r=transfer(io,1,(first<<10)+(off>>9),physical,buf);if(r<0)goto done;
        c=crc_step(c,buf,take);
    }
    /* Full readback compared with the original source before publication. */
    for(off=0;off<bytes;off+=take){
        take=bytes-off>CHUNK?CHUNK:bytes-off;physical=(take+511)&~511u;
        r=transfer(io,0,(first<<10)+(off>>9),physical,back);if(r<0)goto done;
        if(source(opaque,off,take,buf) || !eq(buf,back,take)){r=ST_HZ_IO;goto done;}
    }
    e=index+ST_HZ_ENTRIES+64*n;wr(e,id);wr(e+4,first);wr(e+8,blocks);wr(e+12,bytes);wr(e+16,(bytes-64)/2);
    wr(e+20,~c);wr(e+24,created);cp(e+32,name,name_len);wr(index+12,n+1);wr(index+28,id+1);
    r=commit(&fs,index,len+(rd(old+4)==2?68u:64u));if(r==1)*id_out=id;
done:if(index)io->free(index);if(buf)io->free(buf);if(back)io->free(back);core_hzfs_close(&fs);return r;
}
int core_hzfs_get(const struct st_storage_io *io,u32 id,st_sample_stream sink,void *opaque)
{
    struct st_hzfs fs;u8 *buf=0;const u8 *e;u32 i,pass,bytes,off,take,c=0,first;int r;
    if(!sink)return ST_HZ_ARGUMENT;r=core_hzfs_open(&fs,io);if(r!=1)return r;
    i=find(&fs,id);if(i==core_hzfs_count(&fs)){r=ST_HZ_NOT_FOUND;goto done;}
    e=entry(fs.copy[fs.best],i);bytes=rd(e+12);first=rd(e+4);
    buf=io->alloc(CHUNK);if(!buf){r=ST_HZ_MEMORY;goto done;}
    for(pass=0;pass<2;pass++){
        for(off=0;off<bytes;off+=take){
            take=bytes-off>CHUNK?CHUNK:bytes-off;
            r=transfer(io,0,(first<<10)+(off>>9),(take+511)&~511u,buf);if(r<0)goto done;
            if(!off && !samp(buf,bytes)){r=ST_HZ_CORRUPT;goto done;}
            if(!pass)c=crc_step(c,buf,take);else if(sink(opaque,off,take,buf)){r=ST_HZ_IO;goto done;}
        }
        if(!pass && ~c!=rd(e+20)){r=ST_HZ_CORRUPT;goto done;}
    }r=ST_HZ_OK;
done:if(buf)io->free(buf);core_hzfs_close(&fs);return r;
}
