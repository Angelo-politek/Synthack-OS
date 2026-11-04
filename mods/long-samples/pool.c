/* SPDX-License-Identifier: GPL-2.0-or-later
 * long-samples: Synfact's long samples (HZFS, synfact/) sent to the voice CPU at boot, after the stock samples.
 *
 * The OS sends its sample pool to CPU #2 in 2 KB pages through shared RAM 0x800 (0x40082F90, "PREPARING
 * SAMPLES"): page n of the image at 0x4D84F2C5 (stock total in bytes at 0x4D84F2C1) to CPU #2 0x4004F750 +
 * n * 2048, page index at shared 0x0C, page counter 0x41BBF424. CPU #2 has 64 MB there (0x4004F750..0x4404F750).
 *
 * After the stock pages: one table page, then each HZFS file (stock SAMP header + PCM16BE 48 kHz mono, as on the
 * eMMC), page by page from the eMMC. Table at CPU #2 0x4004F750 + 2048 * ceil(stock bytes / 2048):
 *   +0 'SHLS', +4 count, +8 count x {pointer to the PCM on CPU #2, frames}
 * The SAMPLER machines (mods/sampler/engine) play them as slots 65..128, in catalogue order.
 * Planned right after the OS builds the stock image (0x4008287A: builder 0x40082334), as Synfact does.
 */
#include "synfact/hzfs.h"

typedef unsigned int u32;
typedef unsigned short u16;
typedef unsigned char u8;

#define STOCK_TOTAL ((const volatile u8 *)0x4D84F2C1u)      /* big-endian u32, odd address */
#define IMAGE 0x4D84F2C5u
#define PAGE_NOW (*(volatile u32 *)0x41BBF424u)
#define SHARED_PAGE (*(volatile u16 *)0x1000000Cu)
#define POOL_PAGES (0x4000000u / 2048u)                      /* 64 MB on CPU #2 */
#define CPU2_POOL 0x4004F750u
#define MAX_FILES 64

extern int fw_mmc_read(u32 lba, u32 bytes, void *buf);

struct file { u32 page0, pages, mmc; };
static struct file files[MAX_FILES];
static u32 nfiles, stock_pages, extra_pages;
u32 ls_table[2 + 2 * MAX_FILES];                            /* sent as the first extra page */
char ls_names[MAX_FILES][16];                               /* for the SAMP value text (CPU #1) */
u32 ls_status;                                              /* last plan: files, or < 0 = HZFS error */
static u8 page[2048] __attribute__((aligned(16)));

static u32 stock_bytes(void)
{
    const volatile u8 *p = STOCK_TOTAL;
    return (u32)p[0] << 24 | (u32)p[1] << 16 | (u32)p[2] << 8 | p[3];
}

void ls_plan(void)
{
    struct st_hzfs fs;
    struct st_sample_entry e;
    u32 next, i, k;
    int r;

    nfiles = extra_pages = 0;
    stock_pages = (stock_bytes() + 2047) >> 11;
    ls_table[0] = 0x53484C53;                                /* 'SHLS' */
    ls_table[1] = 0;
    r = core_hzfs_open(&fs, &core_hzfs_native_io);
    ls_status = (u32)r;
    if (r != ST_HZ_OK)
        return;
    next = 1;                                               /* extra page 0 = the table */
    for (i = 0; i < core_hzfs_count(&fs) && nfiles < MAX_FILES; i++) {
        u32 pages;
        if (core_hzfs_entry(&fs, i, &e) != ST_HZ_OK || e.bytes < 64 || !e.frames)
            continue;
        pages = (e.bytes + 2047) >> 11;
        if (stock_pages + next + pages > POOL_PAGES)
            break;                                          /* CPU #2 memory full: the rest stays on the eMMC */
        files[nfiles].page0 = next;
        files[nfiles].pages = pages;
        files[nfiles].mmc = e.first * ST_HZ_WINDOW;
        ls_table[2 + 2 * nfiles] = CPU2_POOL + (stock_pages + next) * 2048 + 64;
        ls_table[3 + 2 * nfiles] = e.frames;
        for (k = 0; k < 15 && e.name[k]; k++)
            ls_names[nfiles][k] = e.name[k];
        ls_names[nfiles][k] = 0;
        next += pages;
        nfiles++;
    }
    core_hzfs_close(&fs);
    ls_table[1] = nfiles;
    if (nfiles)
        extra_pages = next;
    ls_status = nfiles;
}

/* bytes the uploader sends (it rounds up to pages): the stock total, or all pages ours included */
u32 ls_count(void)
{
    return extra_pages ? (stock_pages + extra_pages) * 2048 : stock_bytes();
}

/* page source as an offset from the stock image (the uploader adds 0x4D84F2C5) */
u32 ls_map(void)
{
    u32 n = PAGE_NOW, e, i;

    SHARED_PAGE = (u16)n;
    if (n < stock_pages || !extra_pages)
        return n << 11;
    e = n - stock_pages;
    if (e == 0) {
        u8 *t = (u8 *)ls_table;
        for (i = 0; i < 2048; i++)
            page[i] = i < sizeof(ls_table) ? t[i] : 0;
    } else {
        for (i = 0; i < nfiles; i++)
            if (e >= files[i].page0 && e < files[i].page0 + files[i].pages)
                break;
        if (i == nfiles || fw_mmc_read((files[i].mmc + (e - files[i].page0) * 2048) >> 9, 2048, page))
            for (i = 0; i < 2048; i++)
                page[i] = 0;
    }
    return (u32)page - IMAGE;
}
