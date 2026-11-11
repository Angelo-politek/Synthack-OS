/* SPDX-License-Identifier: GPL-2.0-or-later
 * sample-manager: a SAMPLES row in the settings menu (added by mods/about, which owns the menu's hook). YES opens
 * the project's list of long samples (mods/long-samples): position, name, length.
 *
 *   UP / DOWN, any encoder   move
 *   YES                      the active track (1-8) gets the SAMPLER with this sample
 *   FUNC + UP / DOWN         move the sample up or down in the list
 *   FUNC + NO, twice         delete the sample from the Syntakt
 *   NO                       close
 *
 * The list is drawn over the frame while it is open and takes every key but transport (sfcore's events), as
 * mods/about's. Storage, the list and its order are long-samples' (pool.c: ls_id_at, ls_swap, ls_forget;
 * Synfact's core_hzfs_remove). The track gets the SAMPLER as from the recorder (the machine menu's value, then
 * SAMP through the Sound's setter). UI task only; nothing in the audio interrupt.
 */
#include "synthack.h"

#define FILL       ((void (*)(void *, s32, s32, s32, s32, u32))0x400F7FB6u)
#define INVALIDATE ((void (*)(void *))0x400FFE22u)
#define BRAIN()    ((u8 *)((u32 (*)(void))0x4016E9C8u)())
#define ACTIVE_TRACK ((u32 (*)(u32))0x4001FF74u)
#define SET_MACHINE ((u32 (*)(void *, u32, u32, u32, u32))0x4000F7BEu)
#define TRACK_MODEL(k, t) ((u8 *)((u32 (*)(void *, u32))0x4000F04Cu)((k), (t)))
#define SET_PARAM  ((void (*)(void *, u32, u32, u32, u32, u32))0x40013304u)
#define SAMPLER_MACHINE 44u
#define SAMPLER_MENU 45u                                /* ONESHOT in the machine menu (mods/sampler) */

/* long-samples, sampler, idspace: addresses from make_patch.py */
#define TABLE      ((volatile const u32 *)LS_TABLE)     /* 'SHLS', count, {pointer, frames} in list order */
#define NAMES      ((volatile const char (*)[16])LS_NAMES)
#define ID_AT      ((u32 (*)(u32))LS_ID_AT)
#define SWAP       ((int (*)(u32))LS_SWAP)
#define FORGET     ((void (*)(u32))LS_FORGET)
#define REMOVE     ((int (*)(const void *, u32))HZFS_REMOVE)
#define LONG_SAMP  ((u32 (*)(u32))SM_LONG_SAMP)
#define SAMP_ID    (*(volatile const u32 *)(IDS_TABLE + 52u * 504u + 32u))

#define ROWS 6
enum { KEY_YES = 12, KEY_NO, KEY_UP, KEY_DOWN };

struct capture { void *data; u32 unused, manager, invoke; };
struct sub { u32 event; void (*callback)(void); };
struct module { const char *name; int (*init)(const void *); const struct sub *subs; u32 count; };

u32 smgr_open DATA = 0, smgr_cursor DATA = 0;
static u32 top DATA = 0, dirty DATA = 0, swallow DATA = 0, confirm DATA = 0xFFFFFFFFu, note_ticks DATA = 0;
char smgr_note[32] DATA = {0};

static u32 count(void) { return TABLE[0] == 0x53484C53u ? (TABLE[1] > 64 ? 64 : TABLE[1]) : 0; }

static void note(const char *s)
{
    u32 i;
    for (i = 0; i < 31 && s[i]; i++)
        smgr_note[i] = s[i];
    smgr_note[i] = 0;
    note_ticks = 90;                                    /* ~3 s of UI ticks */
    dirty = 1;
}

static void clamp(void)
{
    u32 n = count();
    if (smgr_cursor >= n)
        smgr_cursor = n ? n - 1 : 0;
    if (smgr_cursor < top)
        top = smgr_cursor;
    if (smgr_cursor >= top + ROWS)
        top = smgr_cursor - ROWS + 1;
    dirty = 1;
}

static char *put_u(char *b, u32 v, u32 digits)
{
    u32 d, div = 1;
    for (d = 1; d < digits || v / div >= 10; d++)
        div *= 10;
    for (; div; div /= 10)
        *b++ = (char)('0' + v / div % 10);
    return b;
}

static void row_text(u32 pos, char *out)
{
    char *b = out;
    u32 frames = TABLE[3 + 2 * pos], k, tenths, c;
    *b++ = pos == smgr_cursor ? '>' : ' ';
    b = put_u(b, pos + 1, 2);
    *b++ = ' ';
    if (!frames) {
        for (k = 0; "- EMPTY -"[k]; k++)
            *b++ = "- EMPTY -"[k];
    } else {
        for (k = 0; k < 15 && (c = (u32)(unsigned char)NAMES[pos][k]) != 0; k++)
            *b++ = (char)(c >= 'a' && c <= 'z' ? c - 32 : c);
        *b++ = ' ';
        *b++ = ' ';
        tenths = (frames + 2400) / 4800;
        b = put_u(b, tenths / 10, 1);
        *b++ = '.';
        *b++ = (char)('0' + tenths % 10);
        *b++ = 'S';
    }
    *b = 0;
}

/* the list, on a 128 x 64 bitmap (y = 0 is the bottom line) */
void smgr_paint(void *bmp)
{
    char line[40], *b;
    u32 n = count(), k;
    FILL(bmp, 0, 0, 127, 63, 0);
    b = line;
    for (k = 0; "SAMPLES  "[k]; k++)
        *b++ = "SAMPLES  "[k];
    b = put_u(b, n, 1);
    *b++ = ' ';
    *b++ = '/';
    *b++ = ' ';
    b = put_u(b, 64, 1);
    *b = 0;
    DRAW_TEXT(bmp, FONT_4X6, 2, 57, 0, 0, "XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX", "%s", line);
    FILL(bmp, 0, 54, 127, 54, 1);
    if (!n)
        DRAW_TEXT(bmp, FONT_4X6, 2, 40, 0, 0, "XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX", "%s", "NO LONG SAMPLES");
    for (k = 0; k < ROWS && top + k < n; k++) {
        row_text(top + k, line);
        DRAW_TEXT(bmp, FONT_4X6, 2, 46 - 7 * (s32)k, 0, 0, "XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX", "%s", line);
    }
    FILL(bmp, 0, 8, 127, 8, 1);
    DRAW_TEXT(bmp, FONT_4X6, 2, 1, 0, 0, "XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX", "%s",
              smgr_note[0] ? smgr_note : "YES:ASSIGN  FUNC+NO:DELETE");
}

static void smgr_draw(void *bmp, void *ctrl)
{
    (void)ctrl;
    if (smgr_open)
        smgr_paint(bmp);
}

static void smgr_tick(void *ctrl)
{
    if (note_ticks && !--note_ticks) {
        smgr_note[0] = 0;
        confirm = 0xFFFFFFFFu;
        dirty = 1;
    }
    if (dirty) {
        dirty = 0;
        ((u8 *)ctrl)[0x20] = 1;
    }
}

/* the active track gets the SAMPLER (kept as it is if it has it already) with the sample at pos */
void smgr_assign(u32 pos)
{
    u8 *brain = BRAIN(), *kit = brain + 0x130, *model, *sound;
    u32 track = ACTIVE_TRACK((u32)brain + 0x30), proxy[5];
    if (track >= 8) {
        note("DIGITAL TRACKS 1-8 ONLY");
        return;
    }
    if (!TABLE[3 + 2 * pos]) {
        note("EMPTY POSITION");
        return;
    }
    model = TRACK_MODEL(kit, track);
    sound = (u8 *)((u32 (*)(void *))(*(u32 **)model)[0x28 / 4])(model);
    if (!sound || sound[0xA2] != SAMPLER_MACHINE) {
        SET_MACHINE(kit, track, SAMPLER_MENU, 1, 1);
        model = TRACK_MODEL(kit, track);
        sound = (u8 *)((u32 (*)(void *))(*(u32 **)model)[0x28 / 4])(model);
    }
    if (!sound || sound[0xA2] != SAMPLER_MACHINE) {
        note("TRACK REFUSED THE SAMPLER");
        return;
    }
    proxy[0] = 0x401C3D4Cu;                             /* SoundParameterSet borrowing the track model */
    proxy[1] = proxy[2] = proxy[3] = 0;
    proxy[4] = (u32)model;
    SET_PARAM(proxy, SAMP_ID, LONG_SAMP(pos) << 8, track, 0, 1);
    note("SAMPLE > TRACK 1");
    smgr_note[15] = (char)('1' + track);
}

static void smgr_delete(u32 pos)
{
    u32 id = ID_AT(pos);
    if (!id) {
        note("EMPTY POSITION");
        return;
    }
    if (confirm != pos) {
        confirm = pos;
        note("FUNC+NO AGAIN: DELETE FOR GOOD");
        return;
    }
    confirm = 0xFFFFFFFFu;
    if (REMOVE((const void *)HZFS_IO, id) != 1) {
        note("DELETE FAILED");
        return;
    }
    FORGET(id);
    note("DELETED");
}

static u32 be(const u8 *p) { return (u32)p[0] << 24 | (u32)p[1] << 16 | (u32)p[2] << 8 | p[3]; }

int smgr_key(void *brain, void *ev)
{
    u32 key = be((const u8 *)ev + 12), flags = be((const u8 *)ev + 16), func = flags & 2, n = count();
    (void)brain;
    if (!(flags & 1)) {
        if (swallow && key == swallow) {
            swallow = 0;
            return 1;
        }
        return smgr_open && !(key >= 9 && key <= 11);
    }
    if (!smgr_open || (key >= 9 && key <= 11))
        return 0;
    if (flags & 8)                                      /* key repeat: only for moving */
        func = key == KEY_UP || key == KEY_DOWN ? func : 4;
    if (func == 4)
        return 1;
    if (key == KEY_NO && func)
        smgr_delete(smgr_cursor);
    else if (key == KEY_NO) {
        smgr_open = 0;
        swallow = KEY_NO;
        smgr_note[0] = 0;
        note_ticks = 0;
        confirm = 0xFFFFFFFFu;
        dirty = 1;
    } else if (key == KEY_YES && n)
        smgr_assign(smgr_cursor);
    else if (key == KEY_UP && smgr_cursor) {
        if (func && !SWAP(smgr_cursor - 1))
            return 1;
        smgr_cursor--;
        clamp();
    } else if (key == KEY_DOWN && smgr_cursor + 1 < n) {
        if (func && !SWAP(smgr_cursor))
            return 1;
        smgr_cursor++;
        clamp();
    }
    return 1;
}

static int smgr_enc(void *brain, void *ev)
{
    int delta = (int)be((const u8 *)ev + 16);
    u32 n = count();
    (void)brain;
    if (!smgr_open)
        return 0;
    if (delta < 0 && smgr_cursor)
        smgr_cursor--;
    if (delta > 0 && smgr_cursor + 1 < n)
        smgr_cursor++;
    clamp();
    return 1;
}

/* ---- the settings row, added by mods/about (it reads smgr_row) */
const char *smgr_label_text(void) { return "SAMPLES"; }

static void smgr_select(const struct capture *fn)
{
    smgr_open = 1;
    confirm = 0xFFFFFFFFu;
    smgr_note[0] = 0;
    clamp();
    if (fn->data)
        INVALIDATE((u8 *)fn->data + 0x38);
}
static void smgr_icon(const struct capture *fn, void *item, void *bmp, int x, int y)
{
    (void)fn; (void)item; (void)bmp; (void)x; (void)y;
}
static void smgr_change(const struct capture *fn, int amount) { (void)fn; (void)amount; }
extern void smgr_label(void);
const void *smgr_row[4] DATA = {smgr_label, smgr_select, smgr_icon, smgr_change};

static int smgr_init(const void *api) { (void)api; return 0; }
static const struct sub subs[] = {
    {2, (void (*)(void))smgr_key}, {3, (void (*)(void))smgr_enc},
    {1, (void (*)(void))smgr_draw}, {0, (void (*)(void))smgr_tick}};
const struct module smgr_module = {"SAMPLE MANAGER", smgr_init, subs, 4};

__asm__(
    "        .text\n"
    /* std::string by value: the caller passes the string to build in a0 and takes it back in d0 */
    "        .globl  smgr_label\n"
    "smgr_label:\n"
    "        link    %a6,#-4\n"
    "        move.l  %d2,-(%sp)\n"
    "        move.l  %a0,%d2\n"
    "        jsr     smgr_label_text\n"
    "        pea     -1(%a6)\n"
    "        move.l  %d0,-(%sp)\n"
    "        move.l  %d2,-(%sp)\n"
    "        jsr     0x401BF31E\n"
    "        lea     12(%sp),%sp\n"
    "        move.l  %d2,%d0\n"
    "        move.l  -8(%a6),%d2\n"
    "        unlk    %a6\n"
    "        rts\n");
