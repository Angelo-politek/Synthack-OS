/* SPDX-License-Identifier: GPL-2.0-or-later
 * long-samples: the OS's transfer window for the high-zone uploads (Synfact's HZFS windows /samples/(8185 + k)).
 *
 * The stock route /samples/N (0x400B9DFE) copies into FileInfo.write_started a std::function of the samples service
 * (0x400B9C58, built at 0x400078B6): a plain function, 0x40007712. The raw writer (0x400B60B6) calls it when the
 * write opens; it posts 0x4000796E to the UI task, which shows SampleTransferMessage ("SAMPLES ARE BEING
 * TRANSFERRED." / "PLEASE REBOOT WHEN DONE.", 0x4016DD90) unless one is already up. The window has no progress.
 * Synfact's route (high-storage.c) leaves write_started empty: no window. Here the high windows get the same
 * std::function, and their written capture closes the window once a catalogue window (0x600, 0x601: the last write
 * of a put, rm or slot-map change) is written: the UI task sends the window the key that closes it (NO).
 */
typedef unsigned int u32;

struct fn { u32 data, reserved, manager, invoke; };

#define WRITE_STARTED 0x40007712u                 /* stock: post the window to the UI task */
#define FN_MANAGER 0x4016DA7Eu                    /* std::function of a plain function: manager, invoke */
#define FN_INVOKE 0x4016DA76u
#define APP ((u32 (*)(void))0x4016E044u)          /* the application (singleton) */
#define POST ((void (*)(u32, const struct fn *))0x40009DD8u)   /* run a std::function<void()> in the UI task */
#define LOCK ((void (*)(u32))0x40001980u)
#define UNLOCK ((void (*)(u32))0x40001AA2u)
#define DYNCAST ((u32 (*)(u32, u32, u32, u32))0x401BA614u)
#define VIEW_TYPE 0x40241EBCu                     /* the views of the application's list */
#define MESSAGE_TYPE 0x401C197Cu                  /* SampleTransferMessage */
#define KEY_NO 13u                                /* 0x400F62AC: YES (12) and NO (13) close the message */
#define KEY_RELEASED 0x10u

#define CATALOGUE_END 0x602u                      /* ST_HZ_DATA: windows 0x600, 0x601 hold the catalogues */

extern void core_fn_manager(void);
u32 ls_transfer_closes;                           /* windows closed (tests) */

static void close_window(void)
{
    u32 list = APP() + 64, node, view, msg = 0;   /* 0x40008392: the views shown, a list at +20, mutex at +4 */
    volatile u32 ev[8];                           /* KeyEvent: +12 key, +16 flags (no memset from the compiler) */
    u32 i;

    LOCK(list + 4);
    for (node = *(u32 *)(list + 20); node != list + 20; node = *(u32 *)node) {
        view = *(u32 *)(node + 8);
        if (view && (msg = DYNCAST(view, VIEW_TYPE, MESSAGE_TYPE, 0)) && !*(volatile unsigned char *)(msg + 48))
            break;                                /* +48: closing (0x400FFEC6), removed by the UI loop */
        msg = 0;
    }
    UNLOCK(list + 4);
    if (!msg)
        return;                                   /* closed by hand already */
    for (i = 0; i < 8; i++)
        ev[i] = 0;
    ev[3] = KEY_NO;
    ev[4] = KEY_RELEASED;
    ((void (*)(u32, volatile u32 *))(*(u32 **)msg)[2])(msg, ev);
    ls_transfer_closes++;
}

/* written capture of a high window (DataWriteClose, after the last byte): data = the window */
void ls_written(const struct fn *f, const void *header)
{
    volatile struct fn post;
    (void)header;
    if (f->data >= CATALOGUE_END)
        return;
    post.data = (u32)close_window;
    post.reserved = 0;
    post.manager = FN_MANAGER;
    post.invoke = FN_INVOKE;
    POST(APP(), (const struct fn *)&post);
}

/* after core_high_route built a high window's FileInfo in out (Result: +0 valid, +8 FileInfo) */
void ls_route_done(unsigned char *out)
{
    struct fn *ws = (struct fn *)(out + 8 + 60), *wr = (struct fn *)(out + 8 + 76);
    u32 k = ((struct fn *)(out + 8 + 108))->data;    /* validate capture: the window */
    if (out[0] != 1)
        return;
    ws->data = WRITE_STARTED;
    ws->reserved = 0;
    ws->manager = FN_MANAGER;
    ws->invoke = FN_INVOKE;
    wr->data = k;
    wr->reserved = 0;
    wr->manager = (u32)core_fn_manager;
    wr->invoke = (u32)ls_written;
}
