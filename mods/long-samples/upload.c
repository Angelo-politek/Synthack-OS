/* SPDX-License-Identifier: GPL-2.0-or-later
 * long-samples: a long sample sent to the voice CPU while the Syntakt runs, playable at once (no reboot).
 * The sender side of engine/rx.c (after Synfact's core_pool_sync / send, mods/core-st/sample-pool.c): shared RAM
 * window 0x800, one request at a time, each acknowledged by the voice CPU at the end of its audio interrupt.
 *
 * A file goes after the last one on the voice CPU, laid out as at boot (SAMP header + PCM, from a page start), then
 * its table entry; the project's list gets it at its end (pool.c, ls_apply). Used by the recorder (the take, from
 * RAM) and after an upload from the web builder or Synfact's tool (the new files, from the eMMC: ls_refresh).
 * Task context only; it waits for each acknowledgement (one audio block, 0.67 ms, for 992 bytes).
 */
#include "synfact/hzfs.h"

typedef unsigned int u32;
typedef unsigned char u8;

#define WIN ((volatile u32 *)0x10000800u)
#define MAGIC 0x4C535258u                           /* 'LSRX' */
#define DATA_MAX 992u
#define WAIT 400000u                                /* polls for one answer (several audio blocks) */

extern int fw_mmc_read(u32 lba, u32 bytes, void *buf);
extern u32 ls_free_page(u32 pages);
extern int ls_file_add(u32 id, u32 ptr, u32 frames, u32 pages, u32 mmc, const char *name);
extern int ls_file_index(u32 id);
extern void ls_file_rename(u32 index, const char *name);
extern u32 ls_loaded;

static u32 seq;
u32 ls_up_fault;                                    /* a request went unanswered: no more until reboot */
u32 ls_up_bytes, ls_up_total;                       /* progress of the file being sent */

static int send(u32 cmd, u32 dst, u32 len, const u8 *data, u32 bytes)
{
    u32 i, v, sum, s, ack;
    if (ls_up_fault)
        return -1;
    s = seq = seq % 65535 + 1;
    sum = MAGIC + (s << 16 | cmd) + dst + len;
    for (i = 0; i < bytes / 4; i++) {
        v = (u32)data[4 * i] << 24 | (u32)data[4 * i + 1] << 16 | (u32)data[4 * i + 2] << 8 | data[4 * i + 3];
        WIN[8 + i] = v;
        sum += v;
    }
    WIN[0] = 0;
    WIN[2] = dst;
    WIN[3] = len;
    WIN[4] = sum;
    WIN[6] = 0;
    __asm__ volatile("" ::: "memory");
    WIN[1] = s << 16 | cmd;
    WIN[0] = MAGIC;
    for (i = 0; i < WAIT; i++) {
        ack = WIN[6];
        if (ack >> 16 == s)
            return (ack & 0xffffu) == 1 ? 1 : -1;
    }
    ls_up_fault = 1;
    return -1;
}

typedef int (*reader)(void *ctx, u32 off, u32 n, u8 *dst);

/* file = SAMP header (64 B, frames at +8) + PCM16BE: bytes in all, read by rd. Returns the loaded index, or < 0. */
int ls_hot_add(u32 id, u32 frames, const char *name, u32 bytes, reader rd, void *ctx, u32 mmc)
{
    static u8 buf[DATA_MAX] __attribute__((aligned(4)));
    u32 pages = (bytes + 2047) >> 11, page = ls_free_page(pages), at, n, i;
    int k;
    if (!page || bytes < 64 || ls_loaded >= 64 || ls_up_fault)
        return -1;
    at = 0x4004F750u + page * 2048;                 /* CPU #2 address of the page */
    ls_up_total = bytes;
    for (ls_up_bytes = 0; ls_up_bytes < bytes; ls_up_bytes += n) {
        n = bytes - ls_up_bytes < DATA_MAX ? bytes - ls_up_bytes : DATA_MAX;
        if (rd(ctx, ls_up_bytes, n, buf))
            return -2;
        for (i = n; i & 3; i++)
            buf[i] = 0;
        if (send(2, at + ls_up_bytes, i, buf, i) != 1)
            return -3;
    }
    k = ls_file_add(id, at + 64, frames, pages, mmc, name);
    if (k < 0)
        return -4;
    buf[0] = (u8)((at + 64) >> 24);
    buf[1] = (u8)((at + 64) >> 16);
    buf[2] = (u8)((at + 64) >> 8);
    buf[3] = (u8)(at + 64);
    if (send(3, (u32)k, frames, buf, 4) != 1)
        return -5;                                  /* the entry stays empty on the voice CPU */
    return k;
}

/* a file of the eMMC: whole 512-byte sectors through a 2 KB page */
struct mmc_src { u32 base, have; u8 page[2048 + 512]; };
static struct mmc_src src __attribute__((aligned(16)));

static int mmc_read(void *ctx, u32 off, u32 n, u8 *dst)
{
    struct mmc_src *s = ctx;
    u32 i = 0, o, p, m;
    while (i < n) {
        o = off + i;
        p = o & ~2047u;
        if (s->have != p + 1) {
            if (fw_mmc_read((s->base + p) >> 9, 2048, s->page))
                return -1;
            s->have = p + 1;
        }
        m = 2048 - (o - p);
        if (m > n - i)
            m = n - i;
        for (u32 j = 0; j < m; j++)
            dst[i + j] = s->page[o - p + j];
        i += m;
    }
    return 0;
}

/* after a write to the high zone (transfer.c): files of the catalogue not on the voice CPU yet are sent now, names
 * follow renames. Returns the files sent. */
u32 ls_refresh(void)
{
    struct st_hzfs fs;
    struct st_sample_entry e;
    u32 i, n, sent = 0;
    int k;
    if (core_hzfs_open(&fs, &core_hzfs_native_io) != ST_HZ_OK)
        return 0;
    n = core_hzfs_count(&fs);
    for (i = 0; i < n; i++) {
        if (core_hzfs_entry(&fs, i, &e) != ST_HZ_OK || e.bytes < 64 || !e.frames)
            continue;
        k = ls_file_index(e.id);
        if (k >= 0) {
            ls_file_rename((u32)k, e.name);
            continue;
        }
        src.base = e.first * ST_HZ_WINDOW;
        src.have = 0;
        if (ls_hot_add(e.id, e.frames, e.name, e.bytes, mmc_read, &src, src.base) < 0)
            break;
        sent++;
    }
    core_hzfs_close(&fs);
    return sent;
}
