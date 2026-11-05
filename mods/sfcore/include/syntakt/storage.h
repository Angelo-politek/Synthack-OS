/* SPDX-License-Identifier: GPL-2.0-or-later
 * HZFS v1. Task context only; serialize calls with Data RPC transfers.
 * Every operation mounts fresh metadata; no index survives a Data RPC edit.
 */
#ifndef ELEKLOADER_ST_LONG_STORAGE_H
#define ELEKLOADER_ST_LONG_STORAGE_H
#define ST_HZ_WINDOW 0x80000u
#define ST_HZ_RAW_FIRST 8185u /* native Data /samples/<base + window> ID */
#define ST_HZ_FIRST 0x600u
#define ST_HZ_DATA 0x602u
#define ST_HZ_ENTRY 64u
#define ST_HZ_ENTRIES 0x140u
/* V2 appends folder memberships and 48-byte folder records after samples.
 * Header +40: folder count, +44: next folder ID. Root is ID zero. */
#define ST_HZ_FOLDER_BYTES 48u
#define ST_HZ_MAX_FOLDERS 1024u
static __inline__ unsigned int st_hz_word(const unsigned char *p)
{return (unsigned int)p[0]<<24|(unsigned int)p[1]<<16|(unsigned int)p[2]<<8|p[3];}
static __inline__ unsigned int st_hz_folder_count(const unsigned char *p)
{return st_hz_word(p+4)==2?st_hz_word(p+40):0;}
static __inline__ unsigned int st_hz_member(const unsigned char *p,unsigned int i)
{return st_hz_word(p+4)==2?st_hz_word(p+ST_HZ_ENTRIES+64*st_hz_word(p+12)+4*i):0;}
static __inline__ const unsigned char *st_hz_folder_record(const unsigned char *p,unsigned int i)
{return p+ST_HZ_ENTRIES+68*st_hz_word(p+12)+ST_HZ_FOLDER_BYTES*i;}
static __inline__ unsigned int st_hz_length(unsigned int version,unsigned int n,unsigned int f)
{return ST_HZ_ENTRIES+n*64+(version==2?n*4+f*ST_HZ_FOLDER_BYTES:0);}
#define ST_HZ_MAX_ENTRIES ((ST_HZ_WINDOW-ST_HZ_ENTRIES)/ST_HZ_ENTRY)
enum {ST_HZ_OK=1,ST_HZ_ABSENT=0,ST_HZ_IO=-1,ST_HZ_CORRUPT=-2,
      ST_HZ_MEMORY=-3,ST_HZ_CAPACITY=-4,ST_HZ_ARGUMENT=-5,ST_HZ_FULL=-6,
      ST_HZ_EXISTS=-7,ST_HZ_NOT_FOUND=-8};
struct st_storage_io {
    int (*read)(unsigned int lba,unsigned int bytes,void *);
    int (*write)(unsigned int lba,unsigned int bytes,const void *);
    unsigned int (*sectors)(void);
    void *(*alloc)(unsigned int);
    void (*free)(void *);
};
struct st_hzfs {
    const struct st_storage_io *io;
    unsigned char *copy[2];
    unsigned int length[2],best,windows;
};
struct st_sample_entry {
    unsigned int id,first,blocks,bytes,frames,crc,created,flags;
    char name[33];
};
/* Open frees everything on error. Close every successful open. */
int core_hzfs_open(struct st_hzfs *,const struct st_storage_io *);
void core_hzfs_close(struct st_hzfs *);
/* Create empty indices only if BOTH entire index windows contain 00/FF.
 * Valid metadata is retained; unknown/corrupt data is never formatted. */
int core_hzfs_ensure(const struct st_storage_io *);
unsigned int core_hzfs_count(const struct st_hzfs *);
int core_hzfs_entry(const struct st_hzfs *,unsigned int,struct st_sample_entry *);
/* Stream a complete SAMP body: 64-byte header + PCM16BE mono at 48 kHz.
 * callback returns zero on success; offsets/sizes are logical bytes.
 * put reads its source twice (write, verify), with bounded scratch RAM.
 * get validates CRC/header before emitting bytes, then streams a second pass.
 */
typedef int (*st_sample_stream)(void *,unsigned int,unsigned int,void *);
int core_hzfs_put(const struct st_storage_io *,const char *,unsigned int bytes,
                 unsigned int created,st_sample_stream,void *,unsigned int *id);
int core_hzfs_get(const struct st_storage_io *,unsigned int id,st_sample_stream,void *);
int core_hzfs_remove(const struct st_storage_io *,unsigned int id);
extern const struct st_storage_io core_hzfs_native_io;
extern int core_hzfs_status;
#endif
