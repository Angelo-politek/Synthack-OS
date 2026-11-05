/* SPDX-License-Identifier: GPL-2.0-or-later */
#ifndef ELEKLOADER_ST_MODULES_H
#define ELEKLOADER_ST_MODULES_H
#include "machines.h"
enum st_smz_event { ST_EV_TICK,ST_EV_DRAW,ST_EV_KEY,ST_EV_ENC,ST_EV_SETTINGS,
    ST_EV_RENDER_IN,ST_EV_RENDER_OUT,ST_EV_FS_ROUTE,ST_EV_FS_WRITE,
    ST_EV_FS_WRITTEN,ST_EV_MAIN_MIX,ST_EV_NATIVE,ST_EV_COUNT };
/* Core 0.10 / module service API 2: opt into the native receiving-view phase
 * of the SAME event collection. Ordinary subscriptions retain their ABI and
 * run once at the global site. No second input registry is involved.
 * DRAW: void f(view, bitmap, 0), after that view, below later native overlays.
 * KEY: void f(view, event, 0), after that view's native key processing.
 * ENC: int f(view, normalized_event, parameter), before the native edit;
 * nonzero consumes it. Only DRAW/KEY/ENC accept this flag. */
#define ST_EV_VIEW 0x100u
/* API 3: pre-native, consuming KEY context in the same KEY collection.
 * Callback int f(view, native_event, 1). Existing post-native KEY stays void. */
#define ST_EV_PRE 0x200u
#define ST_EV_INDEX(event) ((event)&0xffu)
struct st_smz_api {st_u32 version;const struct st_machine_ui_api *ui;};
struct st_smz_subscription {st_u32 event;void (*callback)(void);} __attribute__((aligned(4)));
struct st_smz_module {
    const char *name;
    int (*init)(const struct st_smz_api *); /* zero success; private state only */
    const struct st_smz_subscription *subscriptions;
    st_u32 count;
} __attribute__((aligned(4)));
/* Event signatures match the resident elekloader hook bus. KEY/ENC and FS
 * routing return nonzero to consume. IRQ events must not allocate, wait or IO.
 * Subscriptions are appended to the existing event lists once at boot. */
#endif
