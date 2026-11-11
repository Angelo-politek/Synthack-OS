/* SPDX-License-Identifier: GPL-2.0-or-later
 * long-samples: Synfact's long samples (HZFS, synfact/) sent to the voice CPU at boot, after the stock samples, and
 * the project's list of them (its own SAMP order, saved with the project, as Synfact's project pool).
 *
 * The OS sends its sample pool to CPU #2 in 2 KB pages through shared RAM 0x800 (0x40082F90, "PREPARING
 * SAMPLES"): page n of the image at 0x4D84F2C5 (stock total in bytes at 0x4D84F2C1) to CPU #2 0x4004F750 +
 * n * 2048, page index at shared 0x0C, page counter 0x41BBF424. CPU #2 has 64 MB there (0x4004F750..0x4404F750).
 *
 * After the stock pages: one table page, then each HZFS file (stock SAMP header + PCM16BE 48 kHz mono, as on the
 * eMMC), page by page from the eMMC. Table at CPU #2 0x4004F750 + 2048 * ceil(stock bytes / 2048):
 *   +0 'SHLS', +4 count, +8 count x {pointer to the PCM on CPU #2, frames}       (the loaded files, in load order)
 * Load order: the catalogue's slot map (web builder's Samples page), else the catalogue order; the first 64 that
 * fit. Planned right after the OS builds the stock image (0x4008287A: builder 0x40082334), as Synfact does.
 *
 * The project's list (SAMP 65.. after the stock samples): positions -> loaded files, saved with the project in
 * projstore (PS_POOL: 'LP', count, HZFS ids; Synfact keeps HZFS ids per position the same way, in its POOL record).
 * A project without a list gets the load order (as before), kept in RAM and saved with the project: from then on its
 * SAMP values point at the same files whatever the catalogue does. Files the list does not name come after its
 * positions; a position whose file is gone stays, empty. The voice CPU reads the positions from shared RAM
 * (LS_MAP, mods/sampler/engine/syn.c); the main CPU from ls_table / ls_names in list order (LSHD header).
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

/* shared RAM (registry): the project's positions for the voice CPU */
#define LS_MAP_MAGIC (*(volatile u32 *)0x10000780u)
#define LS_MAP_COUNT (*(volatile u32 *)0x10000784u)
#define LS_MAP ((volatile u8 *)0x10000788u)
#define MAP_MAGIC 0x4C534D31u                               /* 'LSM1' */
#define HOLE 0xFFu

/* projstore (tools/build/projstore_layout.py): 'L' 'P', count, 0, then count big-endian u16 HZFS ids */
#define REC ((volatile u8 *)PS_POOL)

extern int fw_mmc_read(u32 lba, u32 bytes, void *buf);

struct file { u32 id, ptr, frames, page0, pages, mmc; };
static struct file files[MAX_FILES];
u32 ls_loaded;                                              /* files on CPU #2 (boot plan, then added ones) */
static u32 stock_pages, extra_pages, used_pages;      /* used: pages after the stock ones, table first */
u32 ls_cpu2[2 + 2 * MAX_FILES];                             /* CPU #2's table, sent as the first extra page */
u32 ls_table[2 + 2 * MAX_FILES];                            /* the project's list: 'SHLS', count, {pointer, frames} */
char ls_names[MAX_FILES][16];                               /* and its names, for the SAMP value text (CPU #1) */
static char loaded_names[MAX_FILES][16];
u8 ls_pos[MAX_FILES];                                       /* list position -> loaded file, HOLE = none */
u32 ls_status;                                              /* last plan: files, or < 0 = HZFS error */
u32 ls_applied;                                             /* times the list was rebuilt (tests) */
static u8 page[2048] __attribute__((aligned(16)));

static u32 stock_bytes(void)
{
    const volatile u8 *p = STOCK_TOTAL;
    return (u32)p[0] << 24 | (u32)p[1] << 16 | (u32)p[2] << 8 | p[3];
}

static u32 rec_id(u32 i) { return (u32)REC[4 + 2 * i] << 8 | REC[5 + 2 * i]; }

/* The project's list from its saved ids and the loaded files; saved back (materialized) when it names any file. */
void ls_apply(void)
{
    u32 n = 0, i, j, id, valid = REC[0] == 'L' && REC[1] == 'P' && REC[2] <= MAX_FILES;
    u16 ids[MAX_FILES];

    if (valid)
        for (; n < REC[2]; n++) {
            id = rec_id(n);
            ids[n] = (u16)id;
            for (j = 0; id && j < ls_loaded && files[j].id != id; j++)
                ;
            ls_pos[n] = id && j < ls_loaded ? (u8)j : HOLE;
        }
    for (j = 0; j < ls_loaded && n < MAX_FILES; j++) {      /* the files it does not name, in load order */
        for (i = 0; i < n && ls_pos[i] != j; i++)
            ;
        if (i == n && files[j].id != 0xFFFFFFFFu) {         /* not a deleted one (ls_forget) */
            ls_pos[n] = (u8)j;
            ids[n++] = (u16)files[j].id;
        }
    }
    if (n) {
        REC[0] = 'L';
        REC[1] = 'P';
        REC[2] = (u8)n;
        REC[3] = 0;
        for (i = 0; i < n; i++) {
            REC[4 + 2 * i] = (u8)(ids[i] >> 8);
            REC[5 + 2 * i] = (u8)ids[i];
        }
    }
    ls_table[0] = 0x53484C53;                               /* 'SHLS' */
    for (i = 0; i < n; i++) {
        j = ls_pos[i];
        ls_table[2 + 2 * i] = j == HOLE ? 0 : files[j].ptr;
        ls_table[3 + 2 * i] = j == HOLE ? 0 : files[j].frames;
        for (u32 k = 0; k < 16; k++)
            ls_names[i][k] = j == HOLE ? 0 : loaded_names[j][k];
    }
    ls_table[1] = n;
    LS_MAP_MAGIC = 0;
    LS_MAP_COUNT = n;
    for (i = 0; i < MAX_FILES; i++)
        LS_MAP[i] = i < n ? ls_pos[i] : HOLE;
    LS_MAP_MAGIC = MAP_MAGIC;
    ls_applied++;
}

/* a project was loaded (0x4001D6FE): its list */
void ls_project_loaded(u32 ok)
{
    if (ok & 0xFF)
        ls_apply();
}

/* NEW PROJECT (0x4001D16A): no list saved yet, the load order */
void ls_project_new(void)
{
    for (u32 i = 0; i < 4 + 2 * MAX_FILES; i++)
        REC[i] = 0;
    ls_apply();
}

void ls_plan(void)
{
    struct st_hzfs fs;
    struct st_sample_entry e;
    u32 next, i, k;
    int r;

    ls_loaded = extra_pages = 0;
    used_pages = 1;
    stock_pages = (stock_bytes() + 2047) >> 11;
    ls_cpu2[0] = 0x53484C53;                                /* 'SHLS' */
    ls_cpu2[1] = 0;
    r = core_hzfs_open(&fs, &core_hzfs_native_io);
    ls_status = (u32)r;
    if (r != ST_HZ_OK) {
        ls_apply();
        return;
    }
    next = 1;                                               /* extra page 0 = the table */
    /* order: the catalogue's 64 associations (+0x40, Synfact's slot map, set by the web builder's Samples page),
     * else the catalogue order */
    const u8 *map = fs.copy[fs.best] + 0x40;
    u32 mapped = 0, n = core_hzfs_count(&fs);
    for (k = 0; k < 64; k++)
        mapped |= (u32)map[4 * k] << 24 | (u32)map[4 * k + 1] << 16 | (u32)map[4 * k + 2] << 8 | map[4 * k + 3];
    for (u32 pos = 0; pos < (mapped ? 64u : n) && ls_loaded < MAX_FILES; pos++) {
        u32 pages;
        if (mapped) {
            u32 id = (u32)map[4 * pos] << 24 | (u32)map[4 * pos + 1] << 16 | (u32)map[4 * pos + 2] << 8 | map[4 * pos + 3];
            for (i = 0; id && i < n; i++)
                if (core_hzfs_entry(&fs, i, &e) == ST_HZ_OK && e.id == id)
                    break;
            if (!id || i == n)
                continue;
        } else {
            i = pos;
            if (core_hzfs_entry(&fs, i, &e) != ST_HZ_OK)
                continue;
        }
        if (e.bytes < 64 || !e.frames)
            continue;
        pages = (e.bytes + 2047) >> 11;
        if (stock_pages + next + pages > POOL_PAGES)
            break;                                          /* CPU #2 memory full: the rest stays on the eMMC */
        struct file *f = &files[ls_loaded];
        f->id = e.id;
        f->page0 = next;
        f->pages = pages;
        f->mmc = e.first * ST_HZ_WINDOW;
        f->ptr = CPU2_POOL + (stock_pages + next) * 2048 + 64;
        f->frames = e.frames;
        ls_cpu2[2 + 2 * ls_loaded] = f->ptr;
        ls_cpu2[3 + 2 * ls_loaded] = e.frames;
        for (k = 0; k < 15 && e.name[k]; k++)
            loaded_names[ls_loaded][k] = e.name[k];
        for (; k < 16; k++)
            loaded_names[ls_loaded][k] = 0;
        next += pages;
        ls_loaded++;
    }
    core_hzfs_close(&fs);
    ls_cpu2[1] = ls_loaded;
    if (ls_loaded)
        extra_pages = next;
    used_pages = next;
    ls_status = ls_loaded;
    ls_apply();
}

/* ---- files added while the Syntakt runs (upload.c) */

/* first free page on CPU #2 for pages more (absolute page index from the pool's start), 0 if they don't fit */
u32 ls_free_page(u32 pages)
{
    if (!stock_pages || stock_pages + used_pages + pages > POOL_PAGES)
        return 0;
    return stock_pages + used_pages;
}

int ls_file_index(u32 id)
{
    for (u32 j = 0; j < ls_loaded; j++)
        if (files[j].id == id)
            return (int)j;
    return -1;
}

void ls_file_rename(u32 j, const char *name)
{
    u32 k, changed = 0;
    for (k = 0; k < 15 && name[k]; k++) {
        changed |= loaded_names[j][k] != name[k];
        loaded_names[j][k] = name[k];
    }
    for (; k < 16; k++)
        loaded_names[j][k] = 0;
    if (changed)
        ls_apply();
}

/* a file now on CPU #2 at ptr (its PCM): loaded index, at the end of the project's list */
int ls_file_add(u32 id, u32 ptr, u32 frames, u32 pages, u32 mmc, const char *name)
{
    if (ls_loaded >= MAX_FILES)
        return -1;
    struct file *f = &files[ls_loaded];
    f->id = id;
    f->ptr = ptr;
    f->frames = frames;
    f->page0 = used_pages;
    f->pages = pages;
    f->mmc = mmc;
    ls_cpu2[2 + 2 * ls_loaded] = ptr;
    ls_cpu2[3 + 2 * ls_loaded] = frames;
    ls_cpu2[1] = ++ls_loaded;
    used_pages += pages;
    for (u32 k = 0; k < 16; k++)
        loaded_names[ls_loaded - 1][k] = 0;
    ls_file_rename(ls_loaded - 1, name);
    ls_apply();
    return (int)ls_loaded - 1;
}

/* ---- the project's list, for mods/sample-manager (UI task only) */

/* HZFS id of the file at position pos of the list, 0 if the position is empty or beyond the list */
u32 ls_id_at(u32 pos)
{
    if (!(REC[0] == 'L' && REC[1] == 'P') || pos >= REC[2] || ls_pos[pos] == HOLE)
        return 0;
    return rec_id(pos);
}

/* Positions pos and pos + 1 change places. SAMP values that pointed at one now point at the other. */
int ls_swap(u32 pos)
{
    u8 a, b;
    if (!(REC[0] == 'L' && REC[1] == 'P') || pos + 1 >= REC[2])
        return 0;
    a = REC[4 + 2 * pos];
    b = REC[5 + 2 * pos];
    REC[4 + 2 * pos] = REC[6 + 2 * pos];
    REC[5 + 2 * pos] = REC[7 + 2 * pos];
    REC[6 + 2 * pos] = a;
    REC[7 + 2 * pos] = b;
    ls_apply();
    return 1;
}

/* File id is gone from the storage (core_hzfs_remove): its position stays in the list, empty, so the SAMP values of
 * the others keep pointing at the same samples. Its memory on the voice CPU is free again at the next boot. */
void ls_forget(u32 id)
{
    for (u32 j = 0; j < ls_loaded; j++)
        if (files[j].id == id) {
            files[j].id = 0xFFFFFFFFu;
            loaded_names[j][0] = 0;
        }
    ls_apply();
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
        u8 *t = (u8 *)ls_cpu2;
        for (i = 0; i < 2048; i++)
            page[i] = i < sizeof(ls_cpu2) ? t[i] : 0;
    } else {
        for (i = 0; i < ls_loaded; i++)
            if (e >= files[i].page0 && e < files[i].page0 + files[i].pages)
                break;
        if (i == ls_loaded || fw_mmc_read((files[i].mmc + (e - files[i].page0) * 2048) >> 9, 2048, page))
            for (i = 0; i < 2048; i++)
                page[i] = 0;
    }
    return (u32)page - IMAGE;
}
