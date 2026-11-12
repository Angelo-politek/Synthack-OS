/* SPDX-License-Identifier: GPL-2.0-or-later
 * sample-manager: a SAMPLES row in the settings menu (added by mods/about, which owns the menu's hook). YES opens
 * the project's list of long samples (mods/long-samples): position, name, tag, length.
 *
 *   UP / DOWN, any encoder   move
 *   YES                      the active track (1-8) gets the SAMPLER with this sample
 *   FUNC + YES               play the first seconds of the sample / stop
 *   RIGHT                    the sample's tag: none, KICK, SNARE, HAT, PERC, BASS, LEAD, PAD, FX, VOX, LOOP
 *   LEFT                     show: all, or one tag
 *   FUNC + RIGHT             rename (the OS's name editor)
 *   FUNC + UP / DOWN         move the sample up or down in the list
 *   FUNC + NO, twice         delete the sample from the Syntakt
 *   NO                       close
 *
 * The list is drawn over the frame while it is open and takes every key but transport (sfcore's events), as
 * mods/about's. Storage, the list and its order are long-samples' (pool.c: ls_id_at, ls_swap, ls_forget,
 * ls_mmc_at; Synfact's HZFS, plus core_hzfs_update for names and tags). A tag is the low byte of the catalogue
 * entry's flags word, which nothing else reads: the site and Synfact's tool keep it. The track gets the SAMPLER as
 * from the recorder. The preview reads the start of the file from the eMMC into the heap (UI task) and the audio
 * interrupt only mixes it into the preview bus, as the recorder's audition (sfcore's main-mix event).
 */
#include "synthack.h"

#define FILL       ((void (*)(void *, s32, s32, s32, s32, u32))0x400F7FB6u)
#define INVALIDATE ((void (*)(void *))0x400FFE22u)
#define BRAIN()    ((u8 *)((u32 (*)(void))0x4016E9C8u)())
#define ACTIVE_TRACK ((u32 (*)(u32))0x4001FF74u)
#define SET_MACHINE ((u32 (*)(void *, u32, u32, u32, u32))0x4000F7BEu)
#define TRACK_MODEL(k, t) ((u8 *)((u32 (*)(void *, u32))0x4000F04Cu)((k), (t)))
#define SET_PARAM  ((void (*)(void *, u32, u32, u32, u32, u32))0x40013304u)
#define MMC_READ   ((int (*)(u32, u32, void *))0x4010F612u)             /* (lba, bytes, buffer) -> 0 = ok */
#define QSTR_INIT  ((u32 (*)(void *, const char *, void *))0x401BF31Eu)
#define QSTR_DTOR  ((void (*)(void *))0x401BD86Eu)
#define NAME_CTOR  ((void (*)(void *, void *, void *, u32, u32, u32, void *))0x400FCA64u)
#define UI_PUSH    ((u32 (*)(void *, void *, u32))0x40100D86u)
#define UI_DROP    ((void (*)(void *))0x4016DFACu)
#define PREVIEW_BUS ((volatile s32 *)0x8000DFD0u)                      /* reaches MAIN without the analog FX block */
#define SAMPLER_MACHINE 44u
#define SAMPLER_MENU 45u                                /* ONESHOT in the machine menu (mods/sampler) */

/* long-samples, sampler, idspace: addresses from make_patch.py */
#define TABLE      ((volatile const u32 *)LS_TABLE)     /* 'SHLS', count, {pointer, frames} in list order */
#define NAMES      ((volatile const char (*)[16])LS_NAMES)
#define ID_AT      ((u32 (*)(u32))LS_ID_AT)
#define MMC_AT     ((u32 (*)(u32))LS_MMC_AT)
#define SWAP       ((int (*)(u32))LS_SWAP)
#define FORGET     ((void (*)(u32))LS_FORGET)
#define FILE_INDEX ((int (*)(u32))LS_FILE_INDEX)
#define FILE_RENAME ((void (*)(u32, const char *))LS_FILE_RENAME)
#define REMOVE     ((int (*)(const void *, u32))HZFS_REMOVE)
#define UPDATE     ((int (*)(const void *, u32, const char *, u32, u32))HZFS_UPDATE)
#define HZ_OPEN    ((int (*)(void *, const void *))HZFS_OPEN)
#define HZ_CLOSE   ((void (*)(void *))HZFS_CLOSE)
#define HZ_COUNT   ((u32 (*)(const void *))HZFS_COUNT)
#define HZ_ENTRY   ((int (*)(const void *, u32, void *))HZFS_ENTRY)
#define LONG_SAMP  ((u32 (*)(u32))SM_LONG_SAMP)
#define SAMP_ID    (*(volatile const u32 *)(IDS_TABLE + 52u * 504u + 32u))

#define ROWS 6
#define MAX 64
#define NTAGS 11
#define PREVIEW_FRAMES 144000u                          /* 3 s */
enum { KEY_YES = 12, KEY_NO, KEY_UP, KEY_DOWN, KEY_LEFT, KEY_RIGHT };

struct capture { void *data; u32 unused; void *manager, *invoke; };
struct sub { u32 event; void (*callback)(void); };
struct module { const char *name; int (*init)(const void *); const struct sub *subs; u32 count; };
struct hz_entry { u32 id, first, blocks, bytes, frames, crc, created, flags; char name[33]; };

static const char *const tag_names[NTAGS] = {"", "KICK", "SNARE", "HAT", "PERC", "BASS", "LEAD", "PAD", "FX", "VOX",
                                             "LOOP"};

u32 smgr_open DATA = 0, smgr_cursor DATA = 0;           /* cursor: index among the shown rows */
u32 smgr_filter DATA = 0, smgr_naming DATA = 0;
u8 smgr_tags[MAX] DATA = {0};                           /* by list position */
char smgr_note[32] DATA = {0};
static u8 shown[MAX] DATA = {0};                        /* shown row -> list position */
static u32 nshown DATA = 0, top DATA = 0, dirty DATA = 0, swallow DATA = 0, confirm DATA = 0xFFFFFFFFu;
static u32 note_ticks DATA = 0, tag_dirty DATA = 0xFFFFFFFFu, rename_id DATA = 0;
static void *app DATA = 0;
/* preview: the audio interrupt reads these, the UI task owns the buffer */
static s16 *volatile pcm DATA = 0;
static volatile u32 play_len DATA = 0, play_pos DATA = 0;

static u32 count(void) { return TABLE[0] == 0x53484C53u ? (TABLE[1] > MAX ? MAX : TABLE[1]) : 0; }

static void note(const char *s)
{
    u32 i;
    for (i = 0; i < 31 && s[i]; i++)
        smgr_note[i] = s[i];
    smgr_note[i] = 0;
    note_ticks = 90;                                    /* ~3 s of UI ticks */
    dirty = 1;
}

/* the rows shown: every position, or those with the filter's tag */
static void rebuild(void)
{
    u32 n = count(), i;
    nshown = 0;
    for (i = 0; i < n; i++)
        if (!smgr_filter || smgr_tags[i] == smgr_filter)
            shown[nshown++] = (u8)i;
    if (smgr_cursor >= nshown)
        smgr_cursor = nshown ? nshown - 1 : 0;
    if (smgr_cursor < top)
        top = smgr_cursor;
    if (smgr_cursor >= top + ROWS)
        top = smgr_cursor - ROWS + 1;
    dirty = 1;
}

/* tags from the catalogue (the low byte of each entry's flags), by list position */
void smgr_load_tags(void)
{
    u32 fs[8], n, i, p, total = count();
    struct hz_entry e;
    for (p = 0; p < MAX; p++)
        smgr_tags[p] = 0;
    if (HZ_OPEN(fs, (const void *)HZFS_IO) != 1)
        return;
    n = HZ_COUNT(fs);
    for (i = 0; i < n; i++) {
        if (HZ_ENTRY(fs, i, &e) != 1)
            continue;
        for (p = 0; p < total; p++)
            if (ID_AT(p) == e.id)
                smgr_tags[p] = (u8)((e.flags & 0xFFu) < NTAGS ? e.flags & 0xFFu : 0);
    }
    HZ_CLOSE(fs);
}

/* a tag changed with RIGHT is written when the cursor leaves the row or the list closes: one write, not ten */
static void flush_tag(void)
{
    u32 pos = tag_dirty, id;
    tag_dirty = 0xFFFFFFFFu;
    if (pos >= MAX || !(id = ID_AT(pos)))
        return;
    if (UPDATE((const void *)HZFS_IO, id, 0, 1, smgr_tags[pos]) != 1)
        note("TAG NOT SAVED");
}

static void preview_stop(void)
{
    s16 *p = pcm;
    play_len = 0;                                       /* the interrupt stops at its next block */
    __asm__ volatile("" ::: "memory");
    pcm = 0;
    if (p)
        FW_FREE(p);
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
static char *put_s(char *b, const char *s)
{
    while (*s)
        *b++ = *s++;
    return b;
}

static void row_text(u32 row, char *out)
{
    char *b = out;
    u32 pos = shown[row], frames = TABLE[3 + 2 * pos], k, tenths, c;
    *b++ = row == smgr_cursor ? '>' : ' ';
    b = put_u(b, pos + 1, 2);
    *b++ = ' ';
    if (!frames)
        b = put_s(b, "- EMPTY -");
    else {
        for (k = 0; k < 15 && (c = (u32)(unsigned char)NAMES[pos][k]) != 0; k++)
            *b++ = (char)(c >= 'a' && c <= 'z' ? c - 32 : c);
        *b++ = ' ';
        tenths = (frames + 2400) / 4800;
        b = put_u(b, tenths / 10, 1);
        *b++ = '.';
        *b++ = (char)('0' + tenths % 10);
        *b++ = 'S';
        if (smgr_tags[pos]) {
            *b++ = ' ';
            b = put_s(b, tag_names[smgr_tags[pos]]);
        }
    }
    *b = 0;
}

/* the list, on a 128 x 64 bitmap (y = 0 is the bottom line) */
void smgr_paint(void *bmp)
{
    char line[48], *b;
    u32 k;
    FILL(bmp, 0, 0, 127, 63, 0);
    b = put_s(line, "SAMPLES ");
    b = put_u(b, nshown, 1);
    b = put_s(b, " / ");
    b = put_u(b, count(), 1);
    b = put_s(b, "  ");
    b = put_s(b, smgr_filter ? tag_names[smgr_filter] : "ALL");
    *b = 0;
    DRAW_TEXT(bmp, FONT_4X6, 2, 57, 0, 0, "XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX", "%s", line);
    FILL(bmp, 0, 54, 127, 54, 1);
    if (!nshown)
        DRAW_TEXT(bmp, FONT_4X6, 2, 40, 0, 0, "XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX", "%s",
                  count() ? "NO SAMPLE WITH THIS TAG" : "NO LONG SAMPLES");
    for (k = 0; k < ROWS && top + k < nshown; k++) {
        row_text(top + k, line);
        DRAW_TEXT(bmp, FONT_4X6, 2, 46 - 7 * (s32)k, 0, 0, "XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX", "%s", line);
    }
    FILL(bmp, 0, 8, 127, 8, 1);
    DRAW_TEXT(bmp, FONT_4X6, 2, 1, 0, 0, "XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX", "%s",
              smgr_note[0] ? smgr_note : play_len ? "PLAYING  FUNC+YES: STOP" : "YES:ASSIGN  FUNC+YES:PLAY");
}

static void smgr_draw(void *bmp, void *ctrl)
{
    (void)ctrl;
    if (smgr_open && !smgr_naming)                      /* the name editor draws itself */
        smgr_paint(bmp);
}

static void smgr_tick(void *ctrl)
{
    if (note_ticks && !--note_ticks) {
        smgr_note[0] = 0;
        confirm = 0xFFFFFFFFu;
        dirty = 1;
    }
    if (pcm && !play_len) {                             /* the preview ran out */
        preview_stop();
        dirty = 1;
    }
    if (dirty) {
        dirty = 0;
        ((u8 *)ctrl)[0x20] = 1;
    }
}

/* audio interrupt, every block (sfcore's main-mix event): 32 frames of the preview, inverted Q31 as the bus */
void smgr_mix(void)
{
    u32 n = play_len, p = play_pos, i, b;
    const s16 *d = pcm;
    if (!n || !d)
        return;
    for (i = 0; i < 32 && p < n; i++, p++) {
        s32 x = (s32)d[p] * 2048;
        x += x >> 2;
        for (b = 0; b < 2; b++) {
            s32 y = PREVIEW_BUS[2 * i + b];
            u32 a = (u32)y, r = a - (u32)x;
            if (((a ^ (u32)x) & (a ^ r)) & 0x80000000u)
                r = y < 0 ? 0x80000000u : 0x7FFFFFFFu;
            PREVIEW_BUS[2 * i + b] = (s32)r;
        }
    }
    play_pos = p;
    if (p >= n)
        play_len = 0;
}

static void preview(u32 pos)
{
    u32 frames = TABLE[3 + 2 * pos], mmc = MMC_AT(pos), bytes, off;
    s16 *buf;
    if (pcm) {                                          /* FUNC+YES while it plays: stop; after its end: again */
        u32 playing = play_len;
        preview_stop();
        dirty = 1;
        if (playing)
            return;
    }
    if (!frames || !mmc) {
        note("EMPTY POSITION");
        return;
    }
    if (frames > PREVIEW_FRAMES)
        frames = PREVIEW_FRAMES;
    bytes = (64 + 2 * frames + 2047) & ~2047u;          /* whole 2 KB reads, the SAMP header first */
    buf = (s16 *)FW_MALLOC(bytes);
    if ((u32)buf < 0x40000000u) {
        note("NO MEMORY");
        return;
    }
    for (off = 0; off < bytes; off += 2048)
        if (MMC_READ((mmc + off) >> 9, 2048, (u8 *)buf + off)) {
            FW_FREE(buf);
            note("READ ERROR");
            return;
        }
    play_len = 0;
    play_pos = 32;                                      /* 64 bytes of header = 32 words */
    pcm = buf;
    __asm__ volatile("" ::: "memory");
    play_len = 32 + frames;
    dirty = 1;
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
    preview_stop();
    if (REMOVE((const void *)HZFS_IO, id) != 1) {
        note("DELETE FAILED");
        return;
    }
    FORGET(id);
    smgr_tags[pos] = 0;
    rebuild();
    note("DELETED");
}

/* ---- rename: the OS's name editor, pushed on the view stack as the recorder does. Its callback gets the text. */
void smgr_rename_to(u32 id, const char *text)
{
    char name[17];
    u32 n = 0, i;
    int r, k;
    while (n < 16 && text[n])
        n++;
    while (n && text[n - 1] == ' ')
        n--;
    for (i = 0; i < n; i++) {
        if ((u8)text[i] < 32 || (u8)text[i] > 126) {
            note("USE ASCII NAME");
            return;
        }
        name[i] = text[i];
    }
    name[n] = 0;
    if (!n) {
        note("EMPTY NAME");
        return;
    }
    r = UPDATE((const void *)HZFS_IO, id, name, 0, 0);
    if (r != 1) {
        note(r == -7 ? "NAME EXISTS" : "RENAME FAILED");
        return;
    }
    k = FILE_INDEX(id);
    if (k >= 0)
        FILE_RENAME((u32)k, name);
    note("RENAMED");
}
static u32 name_manager(struct capture *dst, const struct capture *src, u32 op)
{
    (void)src;
    if (op < 3) {
        dst->data = 0;
        dst->unused = 0;
    } else {                                            /* the editor's copy is destroyed: it has closed */
        smgr_naming = 0;
        dirty = 1;
    }
    return 0;
}
static void name_done(const struct capture *fn, u8 **text, u32 number)
{
    (void)fn; (void)number;
    if (rename_id && text && *text)
        smgr_rename_to(rename_id, (const char *)*text);
    rename_id = 0;
}
static void rename_open(u32 pos)
{
    u8 *view, *control, alloc = 0;
    u32 title = 0, name = 0, id = ID_AT(pos), k;
    char old[17];
    void *pair[2];
    struct capture callback;
    if (!id || !app) {
        note("EMPTY POSITION");
        return;
    }
    callback.data = 0;
    callback.unused = 0;
    callback.manager = (void *)name_manager;
    callback.invoke = (void *)name_done;
    preview_stop();
    for (k = 0; k < 16 && NAMES[pos][k]; k++)
        old[k] = NAMES[pos][k];
    old[k] = 0;
    view = (u8 *)FW_MALLOC(0xA0);
    control = (u8 *)FW_MALLOC(16);
    if ((u32)view < 0x40000000u || (u32)control < 0x40000000u) {
        note("NO MEMORY");
        return;
    }
    QSTR_INIT(&title, "RENAME SAMPLE", &alloc);
    QSTR_INIT(&name, old, &alloc);
    NAME_CTOR(view, &title, &name, 0, 16, 0, &callback);
    QSTR_DTOR(&name);
    QSTR_DTOR(&title);
    *(u32 *)control = 0x401C98D8u;                      /* the shared-pointer control block the OS uses for it */
    *(u32 *)(control + 4) = 1;
    *(u32 *)(control + 8) = 1;
    *(u8 **)(control + 12) = view;
    pair[0] = view;
    pair[1] = control;
    rename_id = id;
    smgr_naming = 1;
    UI_PUSH((u8 *)app + 0x40, pair, 0);
    UI_DROP(pair + 1);
}

static u32 be(const u8 *p) { return (u32)p[0] << 24 | (u32)p[1] << 16 | (u32)p[2] << 8 | p[3]; }

static void leave_row(void)
{
    if (tag_dirty != 0xFFFFFFFFu)
        flush_tag();
}

int smgr_key(void *brain, void *ev)
{
    u32 key = be((const u8 *)ev + 12), flags = be((const u8 *)ev + 16), func = flags & 2, pos;
    app = brain;
    if (smgr_naming)                                    /* the name editor has the keys */
        return 0;
    if (!(flags & 1)) {
        if (swallow && key == swallow) {
            swallow = 0;
            return 1;
        }
        return smgr_open && !(key >= 9 && key <= 11);
    }
    if (!smgr_open || (key >= 9 && key <= 11))
        return 0;
    if ((flags & 8) && key != KEY_UP && key != KEY_DOWN)    /* key repeat: only for moving */
        return 1;
    pos = nshown ? shown[smgr_cursor] : MAX;
    if (key == KEY_NO && func) {
        if (pos < MAX)
            smgr_delete(pos);
    } else if (key == KEY_NO) {
        leave_row();
        preview_stop();
        smgr_open = 0;
        swallow = KEY_NO;
        smgr_note[0] = 0;
        note_ticks = 0;
        confirm = 0xFFFFFFFFu;
        dirty = 1;
    } else if (key == KEY_YES && pos < MAX) {
        if (func)
            preview(pos);
        else
            smgr_assign(pos);
    } else if (key == KEY_RIGHT && pos < MAX) {
        if (func)
            rename_open(pos);
        else if (ID_AT(pos)) {
            smgr_tags[pos] = (u8)((smgr_tags[pos] + 1) % NTAGS);
            tag_dirty = pos;
            dirty = 1;                                  /* the row stays while it is the cursor's, filter or not */
        }
    } else if (key == KEY_LEFT) {
        leave_row();
        smgr_filter = (smgr_filter + 1) % NTAGS;
        smgr_cursor = top = 0;
        rebuild();
    } else if (key == KEY_UP && smgr_cursor) {
        leave_row();
        if (func && (smgr_filter || !SWAP(pos - 1)))
            return 1;
        if (func) {
            u8 t = smgr_tags[pos];
            smgr_tags[pos] = smgr_tags[pos - 1];
            smgr_tags[pos - 1] = t;
        }
        smgr_cursor--;
        rebuild();
    } else if (key == KEY_DOWN && smgr_cursor + 1 < nshown) {
        leave_row();
        if (func && (smgr_filter || !SWAP(pos)))
            return 1;
        if (func) {
            u8 t = smgr_tags[pos];
            smgr_tags[pos] = smgr_tags[pos + 1];
            smgr_tags[pos + 1] = t;
        }
        smgr_cursor++;
        rebuild();
    }
    return 1;
}

static int smgr_enc(void *brain, void *ev)
{
    int delta = (int)be((const u8 *)ev + 16);
    (void)brain;
    if (!smgr_open || smgr_naming)
        return 0;
    if ((delta < 0 && smgr_cursor) || (delta > 0 && smgr_cursor + 1 < nshown)) {
        leave_row();
        smgr_cursor += delta < 0 ? -1 : 1;
        rebuild();
    }
    return 1;
}

/* ---- the settings row, added by mods/about (it reads smgr_row) */
const char *smgr_label_text(void) { return "SAMPLES"; }

void smgr_show(void)
{
    smgr_open = 1;
    smgr_naming = 0;
    confirm = 0xFFFFFFFFu;
    tag_dirty = 0xFFFFFFFFu;
    smgr_note[0] = 0;
    smgr_load_tags();
    rebuild();
}
static void smgr_select(const struct capture *fn)
{
    smgr_show();
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
    {1, (void (*)(void))smgr_draw}, {0, (void (*)(void))smgr_tick},
    {10, (void (*)(void))smgr_mix}};                    /* ST_EV_MAIN_MIX */
const struct module smgr_module = {"SAMPLE MANAGER", smgr_init, subs, 5};

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
