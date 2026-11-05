/* SPDX-License-Identifier: GPL-2.0-or-later
 * Syntakt SMZ4 machine ABI 0x454c0001. Target: 32-bit big-endian ColdFire.
 * File-only machine definitions; not subscriptions to the resident hook bus.
 */
#ifndef ELEKLOADER_ST_MACHINE_API_H
#define ELEKLOADER_ST_MACHINE_API_H
typedef unsigned int st_u32;
struct st_pool_sample {st_u32 frames;const short *pcm;};
/* Generic core-owned project pool on AUDIO, independent of a machine bank.
 * Null before installation. Zero frames denotes an empty/unavailable slot.
 * PCM remains borrowed; a machine must check its latched entry on each update
 * and stop if the entry is retired or replaced. No eMMC IO in machine callbacks.
 */
static __inline__ const struct st_pool_sample *st_machine_sample(st_u32 slot)
{
    const volatile st_u32 *api=(const volatile st_u32 *)0x40040f50u;
    if(api[0]!=0x454c5001u || slot>=128)return (const struct st_pool_sample *)0;
    return ((const struct st_pool_sample *(*)(st_u32))api[1])(slot);
}
#define ST_MACHINE_CONTROL_CAPACITY 32u
#define ST_MACHINE_SYN_PAGES 4u
#define ST_MACHINE_STORED_CONTROLS 28u
/* AUDIO-only service. Returns 24 extended Q8/raw words for this track,
 * parameter indices 8..31; null before a bank is installed, for a bad track,
 * and (core 0.12.4) until MAIN's values were received for the machine type
 * now on that voice. On null keep your own defaults/last values: never treat
 * an unreceived row as zeros. The native first eight words retain the normal
 * AUDIO update ABI. */
static __inline__ const unsigned short *st_machine_extended(const void *params)
{
    const volatile st_u32 *api=(const volatile st_u32 *)0x40040f40u;
    if(api[0]!=0x454c0001u)return (const unsigned short *)0;
    return ((const unsigned short *(*)(const void *))api[1])(params);
}
struct core_machine_param {const char *label,*name;st_u32 min,max,initial,alias;} __attribute__((aligned(4)));
struct core_machine_def {
    st_u32 type,params;const char *name,*short_name,*group;
    const struct core_machine_param *parameter;
    int (*on_load)(const struct core_machine_def *);
    st_u32 borrow,category,rank;
} __attribute__((aligned(4)));
/* Optional SMZ machine-ui-v1 directory. All callbacks belong to the retained
 * machine image. Rendering/idle run in the UI task; no IO or waits in draw. */
struct st_machine_wave {st_u32 code,frames,ready;short lo[96],hi[96];};
struct st_machine_cursor {st_u32 pointer,frames,position,active;};
/* Compound value codec for native page transactions only; ordinary Sound
 * values and parameter locks remain separate scalar controls. */
struct st_machine_action_codec {
    st_u32 id;
    void (*range)(st_u32 *);
    st_u32 (*get)(void *proxy);
    st_u32 (*set)(void *proxy,st_u32 raw,st_u32 track,st_u32 flag7,st_u32 flag6);
};
static __inline__ void st_machine_cursor_publish(st_u32 track,st_u32 pointer,st_u32 frames,st_u32 position,st_u32 active)
{
    const volatile st_u32 *api=(const volatile st_u32 *)0x42100770u;
    if(api[0]==0x454c4301u)
        ((void (*)(st_u32,st_u32,st_u32,st_u32,st_u32))api[1])(track,pointer,frames,position,active);
}
struct st_machine_ui_api {
    st_u32 version;
    const struct st_machine_wave *(*wave)(st_u32 slot);
    void (*wave_idle)(st_u32 slot,st_u32 budget);
    int (*sample_name)(st_u32 slot,char *out);
    const struct st_machine_cursor *(*cursor)(st_u32 track,st_u32 slot);
    /* Appended in API version 2. Read only when version >= 2. The format
     * callback can keep a control label fixed while naming its popup value. */
    st_u32 format_context;
    /* Version 3: explicit parameter edits still use native Sound/lock routing.
     * These calls are synchronous, UI-task only, and do not bypass native undo. */
    void (*edit)(void *view,st_u32 id,int delta,st_u32 knob);
    void (*clear)(void *view,st_u32 id,st_u32 whole_page,st_u32 knob);
    /* Retired in API 4: always declines registration. Kept at its ABI offset
     * so older input modules fail initialization cleanly. Subscribe to the
     * existing KEY/ENC events with ST_EV_VIEW instead. */
    int (*bind_input)(st_u32 type,int (*encoder)(void *,void *,st_u32),void (*key)(void *,void *));
    int (*bind_codec)(const struct st_machine_action_codec *);
    /* API 5: borrowed generic core services for file-owned UI modules.
     * API 6: host API 2; DRAW context follows each complete native view.
     * API 7: guarded ENC context follows the actual virtual resolver, including
     * SourcePageView. Selector/native edit guards run before any subscriber. */
    const struct st_machine_host_api *host;
};
#define ST_UI_FORMAT_POPUP 0u
#define ST_UI_FORMAT_CONTROL 1u
struct st_machine_dial {void *model;st_u32 id,raw,a,b;void *ctx;int x,y;};
struct st_machine_ui {
    st_u32 type,pages;
    const st_u32 *layout; /* pages * 8 parameter indices, ffffffff = empty */
    void (*draw)(const struct st_machine_ui_api *,const struct core_machine_def *,void *view,void *ctx,st_u32 page);
    int (*idle)(const struct st_machine_ui_api *,const struct core_machine_def *,void *view,st_u32 page);
    int (*dial)(const struct st_machine_ui_api *,const struct core_machine_def *,st_u32 index,const struct st_machine_dial *);
    const char *(*format)(const struct st_machine_ui_api *,const struct core_machine_def *,st_u32 index,st_u32 raw);
    st_u32 (*policy)(st_u32 index); /* native encoder-policy alias, ffffffff = default */
} __attribute__((aligned(4)));
#define ST_MACHINE_NO_CALLBACK ((void *)0xffffffffu)
/* on_load: zero = success; nonzero rejects the whole bank. Only initialize
 * private machine memory; do not subscribe hooks or change firmware objects.
 * Use ST_MACHINE_NO_INIT when no MAIN initializer is needed. */
#define ST_MACHINE_NO_INIT ((int (*)(const struct core_machine_def *))0xffffffffu)
#define ST_MACHINE_PARAM(short_name,long_name,minimum,maximum,initial) \
    {short_name,long_name,minimum,maximum,initial,0x13}
#endif
