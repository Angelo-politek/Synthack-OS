/* SPDX-License-Identifier: GPL-2.0-or-later */
#ifndef CORE_ST_STORAGE_H
#define CORE_ST_STORAGE_H
typedef unsigned char core_u8;
typedef unsigned int core_u32;
#define CORE_MODS_BASE 0x02400000u
#define CORE_MODS_MAX  0x01000000u
/* One transport metadata sector AFTER the full 16 MiB payload capacity.
 * The file itself is opaque: no SMZ4 header/layout is defined here. */
#define CORE_MODS_META (CORE_MODS_BASE+CORE_MODS_MAX)
#define CORE_MODS_LBA (CORE_MODS_META>>9)
struct core_mods_io {
    int (*read)(core_u32,core_u32,void *);
    int (*write)(core_u32,core_u32,const void *);
    core_u32 (*sectors)(void);
};
struct core_mods_store {core_u32 pending,bytes,commit_ok;};
int core_mods_path(const char *);
int core_mods_span(core_u32,core_u32);
/* 1: committed file, 0: absent/invalid record, -1: IO/card unavailable. */
int core_mods_stat_io(const struct core_mods_io *,core_u32 *);
/* Reject an invalid size/card BEFORE any IO. Invalidate metadata before body IO. */
int core_mods_begin_io(struct core_mods_store *,const struct core_mods_io *,core_u32);
/* Native DataWriteClose must already have validated header/footer and closed
 * its bounded safe writer. Commit only the matching original header size. */
int core_mods_commit_io(struct core_mods_store *,const struct core_mods_io *,core_u32);
#endif
