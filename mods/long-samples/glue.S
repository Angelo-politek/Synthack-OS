| SPDX-License-Identifier: GPL-2.0-or-later
| long-samples: OS 1.42 glue for Synfact's long-sample storage (synfact/, see synfact/ORIGIN).
| From Synfact mods/core-st (GSM1980 and contributors, on elekloader by irpina): fw.s (services, here with
| their 1.42 addresses, tools/build/osmap.py + code checked), settings.s (core_fn_manager), files.s (route and
| write veneers, here with one fixed subscriber each), high-storage.s (core_high_validate). Ours: the boot hook
| target and the 1.42 return addresses.

        .macro FW name,value
        .globl \name
        .set \name,\value
        .endm
        FW fw_mmc_read,0x4010f612
        FW fw_mmc_write,0x4010f7f8
        FW fw_mmc_ready,0x444ba6fc
        FW fw_mmc_sectors,0x444ba720
        FW fw_empty_string,0x444e24b8
        FW fw_info_copy,0x4019c4de
        FW fw_string_ctor,0x401bf31e
        FW fw_string_assign,0x401be0ce
        FW fw_free,0x401038d6
        .set FS_ROUTE_RET,0x400b8108
        .set FS_WRITE_RET,0x400b620c
        .set BOOT_NEXT,0x400bd74e           | the call the boot hook (0x4008271e) displaces

        .text
| at the start of the blob (mod area + 0xFFF0, registry): read by the SAMPLER's main CPU side for names and lengths
        .globl ls_header
ls_header:
        .long 0x4C534844                    | 'LSHD'
        .long ls_table                      | 'SHLS', count, {pointer on CPU #2, frames} x 64
        .long ls_names                      | 64 x 16 chars

| malloc of the OS (0x401036d0) returns the pointer in d0; m68k-linux-gnu-gcc reads it from a0 (Synfact builds with
| m68k-elf, which reads d0): docs/modding-guide.md, OS functions returning a pointer
        .globl fw_malloc
fw_malloc:
        move.l 4(%sp),-(%sp)
        jsr 0x401036d0
        addq.l #4,%sp
        movea.l %d0,%a0
        rts

| std::function manager for the captures in a FileInfo: clone copies the functor words, destroy clears
        .globl core_fn_manager
core_fn_manager:
        move.l 4(%sp),%a0
        move.l 12(%sp),%d0
        beq.s 1f
        cmpi.l #3,%d0
        beq.s 3f
        move.l 8(%sp),%a1
        cmpi.l #1,%d0
        beq.s 2f
        move.l (%a1),(%a0)
        bra.s 3f
1:      clr.l (%a0)
        bra.s 3f
2:      move.l %a1,(%a0)
3:      moveq #0,%d0
        rts

| Native std::function BoolResult invoke(fn*, header*), hidden A0 result.
        .globl core_high_validate
core_high_validate:
        move.l %a2,-(%sp)
        movea.l %a0,%a2
        move.l 12(%sp),-(%sp)
        move.l 12(%sp),-(%sp)
        move.l %a2,-(%sp)
        jsr core_high_check_header
        lea 12(%sp),%sp
        move.l %a2,%d0
        movea.l (%sp)+,%a2
        rts

| ev_fs_route: int f(router, const std::string *path, Result<FileInfo> *out); 0x400b8100 jumps here
        .globl core_fs_route
core_fs_route:
        lea -16(%sp),%sp
        movem.l %a2-%a5,(%sp)
        movea.l %a0,%a2
        movea.l 20(%sp),%a3
        movea.l 24(%sp),%a4
        move.l %a2,-(%sp)
        move.l %a4,-(%sp)
        move.l %a3,-(%sp)
        jsr core_high_route
        lea 12(%sp),%sp
        tst.l %d0
        beq.s 3f
        move.l %a2,-(%sp)                   | ours (transfer.c): the OS's transfer window for the write
        jsr ls_route_done
        addq.l #4,%sp
        move.l %a2,%d0
        movem.l (%sp),%a2-%a5
        lea 16(%sp),%sp
        rts
3:      movea.l %a2,%a0
        movem.l (%sp),%a2-%a5
        lea 16(%sp),%sp
        link %a6,#-40
        movem.l %d2-%d3/%a2-%a5,(%sp)
        jmp FS_ROUTE_RET

| ev_fs_write: int f(router, FileInfo *info, Result<Writer> *out); 0x400b6204 jumps here
        .globl core_fs_write
core_fs_write:
        lea -16(%sp),%sp
        movem.l %a2-%a5,(%sp)
        movea.l %a0,%a2
        movea.l 20(%sp),%a3
        movea.l 24(%sp),%a4
        move.l %a2,-(%sp)
        move.l %a4,-(%sp)
        move.l %a3,-(%sp)
        jsr core_sample_write_guard
        lea 12(%sp),%sp
        tst.l %d0
        beq.s 3f
        move.l %a2,%d0
        movem.l (%sp),%a2-%a5
        lea 16(%sp),%sp
        rts
3:      movea.l %a2,%a0
        movem.l (%sp),%a2-%a5
        lea 16(%sp),%sp
        link %a6,#-76
        movem.l %d2-%d5/%a2-%a4,(%sp)
        jmp FS_WRITE_RET

| application startup, before project and sample loading (0x4008271e: jsr 0x400bd74e)
        .globl ls_boot
ls_boot:
        jsr core_hzfs_startup
        jmp BOOT_NEXT

| stock image built (0x4008287a: bsr 0x40082334 ; jsr 0x40082e9c), then our plan, as Synfact's core_pool_blob
        .globl ls_blob
ls_blob:
        jsr 0x40082334
        jsr ls_plan
        jmp 0x40082e9c

| sample upload to CPU #2 (0x40082f90): page count and page source
        .globl ls_count_hook, ls_map_hook
ls_count_hook:                              | at 0x40082fb6, in place of move.l 0x4d84f2c1,%d2
        lea -16(%sp),%sp
        movem.l %d0-%d1/%a0-%a1,(%sp)
        jsr ls_count
        move.l %d0,%d2
        movem.l (%sp),%d0-%d1/%a0-%a1
        lea 16(%sp),%sp
        rts
ls_map_hook:                                | at 0x40082fce, in place of move.l 0x41bbf424,%d0 ; move.w %d0,0x1000000c ; lsl.l %d1,%d0
        lea -12(%sp),%sp
        movem.l %d1/%a0-%a1,(%sp)
        jsr ls_map
        movem.l (%sp),%d1/%a0-%a1
        lea 12(%sp),%sp
        rts
