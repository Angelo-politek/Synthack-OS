/* SPDX-License-Identifier: GPL-2.0-or-later
 * arp: SyntHack glue around Synfact's arp-st (synfact/).
 *
 * Settings: 24 bytes per audio track saved with the project (mods/projstore, PS_ARP from make_patch.py), each byte
 * XORed with the default so that a project without them (zeros) loads the defaults.
 *
 * Locks: MODE, SPEED, RANGE and LEN of a trig are one native pattern lock on logical index 0x46, the Sound's spare
 * index (mods/xparams saves it as lane 0x60). A lock value must stay below 0x8000 (the OS reads it signed: negative
 * is "no lock"), so the four fields, each with "not locked", are packed in mixed radix 6 x 19 x 5 x 57 = 32 490:
 * LEN takes 56 values (len_table), here and on the ARP page alike.
 */
#include "synfact/arp.h"
#include "synfact/persist.h"
typedef unsigned int u32;
typedef unsigned short u16;
typedef unsigned char u8;

#define LOCK_LIX 0x46u
#define LOCK_LANES_MAX 79u                       /* Synfact's shared maximum (the file holds 80 lane rows) */
#define LOCK_GET ((int (*)(void *,u32,u32,u32))0x4001722Au)
#define LOCK_SET ((u32 (*)(void *,u32,u32,u32,int))0x40017602u)
#define LOCK_DEL ((u32 (*)(void *,u32,u32,u32))0x4001741Eu)
#define MATRIX_TRACK 0x2447u                     /* per track: u16 value[64][72], then u8 used[71] at +0x2400 */

volatile arp_u32 arp_blocks;

void *memcpy(void *d, const void *s, u32 n)
{
    u8 *a = d;
    const u8 *b = s;
    while (n--)
        *a++ = *b++;
    return d;
}

void *memset(void *d, int c, u32 n)
{
    u8 *a = d;
    while (n--)
        *a++ = (u8)c;
    return d;
}

/* ---- note LEN: 56 values of the native length (0..127) */
static const u8 len_table[56] = {
    0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23, 24, 25, 26, 27, 28, 29, 30,
    32, 34, 36, 38, 40, 42, 44, 46, 48, 50, 52, 54, 56, 58, 60, 62,
    66, 70, 74, 78,
    86, 94, 102, 110, 127};

static unsigned int len_index(unsigned int n)
{
    unsigned int i = 0;
    while (i + 1 < sizeof len_table && len_table[i + 1] <= n)
        i++;
    return i;
}

unsigned int arp_len_step(unsigned int n, int delta)
{
    int i = (int)len_index(n);
    if (delta < 0 && len_table[i] < n)          /* off the table (below n): the first step down lands on it */
        delta++;
    i += delta;
    if (i < 0)
        i = 0;
    if (i >= (int)sizeof len_table)
        i = sizeof len_table - 1;
    return len_table[i];
}

/* ---- settings saved with the project */
static const u8 defaults[24] = {0, 9, 1, 30, 15, 0, 0xff, 0xff};

static u8 *track_bytes(u32 track)
{
    return (u8 *)(PS_ARP + 24u * track);
}

static int valid(const struct arp_settings *p)
{
    unsigned int i;
    if (p->mode > 4 || p->speed >= 18 || p->range > 3 || p->note_length >= 128 || p->length >= 16)
        return 0;
    for (i = 0; i < 16; i++)
        if (p->offset[i] < -24 || p->offset[i] > 24)
            return 0;
    return 1;
}

static void unpack(struct arp_settings *p, const u8 *s)
{
    unsigned int i;
    u8 b[24];
    for (i = 0; i < 24; i++)
        b[i] = s[i] ^ defaults[i];
    p->mode = b[0];
    p->speed = b[1];
    p->range = b[2];
    p->note_length = b[3];
    p->length = b[4];
    ((volatile u8 *)p)[5] = 0;
    p->enabled = (u16)(b[6] << 8 | b[7]);
    for (i = 0; i < 16; i++)
        p->offset[i] = (signed char)b[8 + i];
}

void arp_track_read(arp_u32 track, struct arp_settings *p)
{
    if (track < ARP_TRACKS) {
        unpack(p, track_bytes(track));
        if (valid(p))
            return;
    }
    unpack(p, (const u8 *)"\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0");
}

/* 1 if the track's saved bytes changed since the last call (6 long compares: NOTE_ACCEPT runs it on every note) */
int arp_track_changed(arp_u32 track)
{
    static u32 seen[ARP_TRACKS][6];
    const volatile u32 *w = (const volatile u32 *)track_bytes(track);
    u32 *c, k, changed = 0;
    if (track >= ARP_TRACKS)
        return 0;
    c = seen[track];
    for (k = 0; k < 6; k++)
        if (c[k] != w[k]) {
            c[k] = w[k];
            changed = 1;
        }
    return (int)changed;
}

int arp_track_store(arp_u32 track, const struct arp_settings *p)
{
    unsigned int i;
    u8 b[24], *d;
    if (track >= ARP_TRACKS || !valid(p))
        return 0;
    b[0] = p->mode;
    b[1] = p->speed;
    b[2] = p->range;
    b[3] = p->note_length;
    b[4] = p->length;
    b[5] = 0;
    b[6] = (u8)(p->enabled >> 8);
    b[7] = (u8)p->enabled;
    for (i = 0; i < 16; i++)
        b[8 + i] = (u8)p->offset[i];
    d = track_bytes(track);
    for (i = 0; i < 24; i++)
        d[i] = b[i] ^ defaults[i];
    return 1;
}

/* ---- packed locks. f[k] = 0: field k not locked, else its value + 1 (LEN: its len_table index + 1). */
static const u8 radix[4] = {6, 19, 5, 57};

static u32 pack(const u8 *f)
{
    return ((f[0] * 19u + f[1]) * 5u + f[2]) * 57u + f[3];
}

static void unpack_lock(u32 v, u8 *f)
{
    int k;
    for (k = 3; k >= 0; k--) {
        f[k] = (u8)(v % radix[k]);
        v /= radix[k];
    }
}

static int field_value(const u8 *f, u32 k)
{
    if (!f[k])
        return -1;
    return k == 3 ? len_table[f[k] - 1] : f[k] - 1;
}

/* The lock object of a queued event (event +0x44): count at +8, then from +20 pairs of 8 bytes {u16 logical index,
 * u16 value, ...}, as the native apply (0x4009792C) reads them. Bits 0..3: MODE, SPEED, RANGE, LEN locked. */
arp_u32 synfact_extra_locks(arp_u32 track, arp_u32 lock, unsigned short *out)
{
    const u8 *o = (const u8 *)lock;
    u32 n, i, mask = 0, k;
    u8 f[4];
    if (track >= ARP_TRACKS || !out || lock < 0x40000000u || lock >= 0x48000000u || (lock & 1))
        return 0;
    n = *(const volatile u32 *)(o + 8);
    if (n > 71)
        return 0;
    for (i = 0; i < n; i++) {
        const volatile u16 *pair = (const volatile u16 *)(o + 20 + 8 * i);
        if (pair[0] != LOCK_LIX)
            continue;
        if (pair[1] >= 0x8000u)
            return 0;
        unpack_lock(pair[1], f);
        for (k = 0; k < 4; k++)
            if (f[k] && f[k] < radix[k]) {
                out[k] = (unsigned short)field_value(f, k);
                mask |= 1u << k;
            }
        return mask;
    }
    return 0;
}

static u32 matrix_of(void *model)
{
    u32 *vt;
    if (!model || !(vt = *(u32 **)model))
        return 0;
    return ((u32 (*)(void *))vt[10])(model);
}

static u32 native_lanes(u32 matrix)
{
    u32 t, i, n = 0;
    for (t = 0; t < 13; t++) {
        const volatile u8 *used = (const volatile u8 *)(matrix + t * MATRIX_TRACK + 0x2400u);
        for (i = 0; i < 71; i++)
            n += used[i] != 0;
    }
    return n;
}

int arp_lock_get(void *model, arp_u32 track, arp_u32 step, arp_u32 field)
{
    int raw;
    u8 f[4];
    if (!model || track >= ARP_TRACKS || step >= 64 || field >= 4)
        return -1;
    raw = LOCK_GET(model, track, step, LOCK_LIX);
    if (raw < 0)
        return -1;
    unpack_lock((u32)raw, f);
    return field_value(f, field);
}

arp_u32 arp_lock_set(void *model, arp_u32 track, arp_u32 step, arp_u32 field, int value)
{
    int raw;
    u32 matrix;
    u8 f[4] = {0, 0, 0, 0};
    if (!model || track >= ARP_TRACKS || step >= 64 || field >= 4 || !(matrix = matrix_of(model)))
        return 0;
    raw = LOCK_GET(model, track, step, LOCK_LIX);
    if (raw >= 0)
        unpack_lock((u32)raw, f);
    if (value < 0)
        f[field] = 0;
    else if (field == 3)
        f[3] = (u8)(len_index((unsigned int)value) + 1);
    else if (value < radix[field] - 1)
        f[field] = (u8)(value + 1);
    else
        return 0;
    if (!f[0] && !f[1] && !f[2] && !f[3])
        return raw >= 0 ? (u8)LOCK_DEL(model, track, step, LOCK_LIX) : 0;
    /* a new lane (the first ARP lock of this track in the pattern) only while the file has room */
    if (!*(const volatile u8 *)(matrix + track * MATRIX_TRACK + 0x2400u + LOCK_LIX) &&
        native_lanes(matrix) >= LOCK_LANES_MAX)
        return 0;
    return (u8)LOCK_SET(model, track, step, LOCK_LIX, (int)pack(f));
}
