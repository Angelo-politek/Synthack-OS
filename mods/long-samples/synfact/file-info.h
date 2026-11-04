/* SPDX-License-Identifier: GPL-2.0-or-later */
#ifndef CORE_ST_FILE_INFO_H
#define CORE_ST_FILE_INFO_H
#include "storage.h"
typedef core_u32 u32;typedef core_u8 u8;
struct fn {u32 data,reserved;void *manager,*invoke;};
struct info {
    u32 type,kind;unsigned short permissions,pad;
    u32 address,bytes,id,tag;
    struct fn prepare,read_started,write_started,written,other,validate;
};
typedef char info_size_must_be_124[sizeof(struct info)==0x7c?1:-1];
#endif
