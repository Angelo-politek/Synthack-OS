/* SPDX-License-Identifier: GPL-2.0-or-later
 * about: a SYNTHACK row at the end of the settings menu, with its icon. YES opens a cover with the boot screen's
 * logo (mods/splash: version and the builder's name), then, DOWN or an encoder, a list: the mods in this build with
 * their status, the repository, the credits. UP / DOWN or an encoder scroll, NO closes.
 *
 * The row is added as Synfact adds its own (mods/core/settings.s and mods/system-info-st, GSM1980 and
 * contributors, on elekloader by irpina, GPL-2.0-or-later): a hook after the last row of the menu's item builder
 * and a MenuItem built from four std::function objects. It also adds mods/sample-manager's SAMPLES row (SMGR_ROW).
 *
 * Drawn over the frame while open (sfcore's draw event); takes every key but transport. Rows come from
 * about_data.h, written by make_patch.py; a mod's row has the address of its first bytes in the mod area, zero
 * when the mod is not in the build, and is then skipped. Nothing in the audio interrupt, nothing saved.
 */
#include "synthack.h"

#define INVALIDATE ((void (*)(void *))0x400FFE22u)
#define LINES 6                                         /* list rows under the header */
#define KEY_NO 13
#define KEY_UP 14
#define KEY_DOWN 15
/* mods/splash's animation entry (make_patch.py): +8 the function (frame, frames, bitmap), +12 its frames */
#define SPLASH_FN     (*(void (*const *)(u32, u32, void *))(SPLASH_ENTRY + 8))
#define SPLASH_FRAMES (*(const u32 *)(SPLASH_ENTRY + 12))

enum { TEXT, HEAD, MOD };
struct row { u8 kind, status; const char *text; u32 probe; };   /* status: 0 stable, 1 beta, 2 experimental */
#include "about_data.h"                                 /* static const struct row rows[ROWS]; VERSION */

struct capture { void *data; u32 unused, manager, invoke; };
struct sub { u32 event; void (*callback)(void); };
struct module { const char *name; int (*init)(const void *); const struct sub *subs; u32 count; };

u32 about_open DATA = 0, about_top DATA = 0;            /* top 0 = the cover; 1.. = the list from row top - 1 */
static u32 dirty DATA = 0, swallow DATA = 0;
static u8 shown[ROWS] DATA = {0};
static u32 count DATA = 0;
static const u32 mark[9] = {0x80000000u, 0x40000000u, 0x30000000u, 0x8C000000u, 0x43000000u, 0x30800000u,
                            0x0C000000u, 0x03000000u, 0x00800000u};   /* the "//" of the brand */

static void collect(void)
{
    u32 i;
    count = 0;
    for (i = 0; i < ROWS; i++)
        if (!rows[i].probe || *(volatile const u32 *)rows[i].probe)
            shown[count++] = (u8)i;
}

static void move(int d)
{
    u32 last = count > LINES ? count - LINES + 1 : 1;
    if (d < 0 && about_top)
        about_top--;
    if (d > 0 && about_top < last)
        about_top++;
    dirty = 1;
}

static void text(void *bmp, s32 x, s32 y, const char *s)
{
    DRAW_TEXT(bmp, FONT_4X6, x, y, 0, 0, "XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX", "%s", s);
}
static u32 len(const char *s) { u32 n = 0; while (s[n]) n++; return n; }

static void cover(void *bmp)
{
    u32 n = SPLASH_FRAMES;
    if (n && n < 1000)
        SPLASH_FN(n - 1, n, bmp);                       /* the boot screen's last frame: logo, version, name */
    FILL_RECT(bmp, 118, 0, 127, 6, 0);                  /* a down arrow: there is more */
    FILL_RECT(bmp, 120, 4, 126, 4, 1);
    FILL_RECT(bmp, 121, 3, 125, 3, 1);
    FILL_RECT(bmp, 122, 2, 124, 2, 1);
    FILL_RECT(bmp, 123, 1, 123, 1, 1);
}

/* the cover or the list, on a 128 x 64 bitmap (y = 0 is the bottom line) */
void about_paint(void *bmp)
{
    static const char *const badge[3] = {"", "BETA", "EXP"};
    u32 k, first;
    if (!count)
        collect();
    FILL_RECT(bmp, 0, 0, 127, 63, 0);
    if (!about_top) {
        cover(bmp);
        return;
    }
    sh_icon9(bmp, mark, 2, 55);                         /* header: the brand mark and the version, inverted */
    text(bmp, 14, 57, "SYNTHACK OS " VERSION);
    text(bmp, 106, 57, "1.42");
    sh_invert(bmp, 0, 55, 127, 63);
    first = about_top - 1;
    for (k = 0; k < LINES && first + k < count; k++) {
        const struct row *r = &rows[shown[first + k]];
        s32 y = 45 - 8 * (s32)k;
        if (r->kind == HEAD) {                          /* section: a bar with the title on it */
            text(bmp, 4, y, r->text);
            sh_invert(bmp, 0, y - 1, 123, y + 6);
        } else {
            text(bmp, r->kind == MOD ? 6 : 2, y, r->text);
            if (r->kind == MOD && r->status) {          /* status badge, right-aligned, inverted */
                s32 w = 5 * (s32)len(badge[r->status]) + 2;   /* the 4x6 font advances 5 pixels */
                text(bmp, 122 - w + 2, y, badge[r->status]);
                sh_invert(bmp, 122 - w, y - 1, 121, y + 6);
            }
        }
    }
    if (count > LINES) {                                /* scroll bar on the right edge */
        s32 h = 53 * LINES / (s32)count, y = 53 - (s32)(53 * first / count);
        FILL_RECT(bmp, 126, 0, 126, 53, 1);
        FILL_RECT(bmp, 125, y - h + 1 < 0 ? 0 : y - h + 1, 127, y, 1);
    }
}

static void about_draw(void *bmp, void *ctrl)
{
    (void)ctrl;
    if (about_open)
        about_paint(bmp);
}

static void about_tick(void *ctrl)
{
    if (dirty) {
        dirty = 0;
        ((u8 *)ctrl)[0x20] = 1;
    }
}

static u32 be(const u8 *p) { return (u32)p[0] << 24 | (u32)p[1] << 16 | (u32)p[2] << 8 | p[3]; }

/* while open every key is its own, transport (9, 10, 11) excepted; NO's release too after closing */
int about_key(void *brain, void *ev)
{
    u32 key = be((const u8 *)ev + 12), flags = be((const u8 *)ev + 16);
    (void)brain;
    if (!(flags & 1)) {
        if (swallow && key == swallow) {
            swallow = 0;
            return 1;
        }
        return about_open && !(key >= 9 && key <= 11);
    }
    if (!about_open || (key >= 9 && key <= 11))
        return 0;
    if (key == KEY_NO) {
        about_open = 0;
        swallow = KEY_NO;
        dirty = 1;
    } else if (key == KEY_UP)
        move(-1);
    else if (key == KEY_DOWN)
        move(1);
    return 1;
}

static int about_enc(void *brain, void *ev)
{
    int delta = (int)be((const u8 *)ev + 16);
    (void)brain;
    if (!about_open)
        return 0;
    if (delta)
        move(delta > 0 ? 1 : -1);
    return 1;
}

/* ---- the settings rows */
const char *about_label_text(void) { return "SYNTHACK"; }

static void about_select(const struct capture *fn)
{
    collect();
    about_open = 1;
    about_top = 0;
    dirty = 1;
    if (fn->data)
        INVALIDATE((u8 *)fn->data + 0x38);
}
void about_icon(const struct capture *fn, void *item, void *bmp, int x, int y)
{
    (void)fn; (void)item;
    sh_icon9(bmp, mark, x, y);
}
static void about_change(const struct capture *fn, int amount) { (void)fn; (void)amount; }

extern void about_label(void);
extern void about_additem(void *menu, const void *row);
void about_rows(void *menu)
{
    static const void *const row[] = {about_label, about_select, about_icon, about_change};
#if SMGR_ROW
    /* mods/sample-manager's row (its four callbacks at SMGR_ROW, zeros when that mod is not in the build): this
     * mod owns the menu's hook, so it adds the row for it, before its own */
    if (*(volatile const u32 *)SMGR_ROW)
        about_additem(menu, (const void *)SMGR_ROW);
#endif
    about_additem(menu, row);
}

static int about_init(const void *api) { (void)api; return 0; }
static const struct sub subs[] = {
    {2, (void (*)(void))about_key},                     /* ST_EV_KEY */
    {3, (void (*)(void))about_enc},                     /* ST_EV_ENC */
    {1, (void (*)(void))about_draw},                    /* ST_EV_DRAW */
    {0, (void (*)(void))about_tick}};                   /* ST_EV_TICK */
const struct module about_module = {"ABOUT", about_init, subs, 4};

__asm__(
    "        .text\n"
    /* 0x4005F176 in the settings menu's item builder (movea.l (a2),a0 ; pea 2.w), after the last row; a2 = menu */
    "        .globl  about_settings\n"
    "about_settings:\n"
    "        move.l  %a2,-(%sp)\n"
    "        jsr     about_rows\n"
    "        addq.l  #4,%sp\n"
    "        movea.l (%a2),%a0\n"                       /* the instructions this replaced */
    "        pea     2.w\n"
    "        jmp     0x4005F17C\n"
    /* std::string by value: the caller passes the string to build in a0 and takes it back in d0 */
    "        .globl  about_label\n"
    "about_label:\n"
    "        link    %a6,#-4\n"
    "        move.l  %d2,-(%sp)\n"
    "        move.l  %a0,%d2\n"
    "        jsr     about_label_text\n"
    "        pea     -1(%a6)\n"
    "        move.l  %d0,-(%sp)\n"
    "        move.l  %d2,-(%sp)\n"
    "        jsr     0x401BF31E\n"                      /* std::string(const char *, allocator) */
    "        lea     12(%sp),%sp\n"
    "        move.l  %d2,%d0\n"
    "        move.l  -8(%a6),%d2\n"
    "        unlk    %a6\n"
    "        rts\n"
    /* manager of a std::function that holds one borrowed pointer: (dst, src, op) */
    "about_fn_manager:\n"
    "        move.l  4(%sp),%a0\n"
    "        move.l  12(%sp),%d0\n"
    "        beq.s   1f\n"
    "        cmpi.l  #3,%d0\n"
    "        beq.s   3f\n"
    "        move.l  8(%sp),%a1\n"
    "        cmpi.l  #1,%d0\n"
    "        beq.s   2f\n"
    "        move.l  (%a1),(%a0)\n"
    "        bra.s   3f\n"
    "1:      clr.l   (%a0)\n"
    "        bra.s   3f\n"
    "2:      move.l  %a1,(%a0)\n"
    "3:      moveq   #0,%d0\n"
    "        rts\n"
    /* about_additem(menu, row): a 0x54-byte MenuItem from four callbacks: label, select, draw, change */
    "        .globl  about_additem\n"
    "about_additem:\n"
    "        link    %a6,#-64\n"
    "        lea     -12(%sp),%sp\n"
    "        movem.l %d2/%a2-%a3,(%sp)\n"
    "        movea.l 8(%a6),%a2\n"
    "        movea.l 12(%a6),%a3\n"
    "        lea     -64(%a6),%a0\n"                    /* label: no payload */
    "        clr.l   (%a0)\n"
    "        clr.l   4(%a0)\n"
    "        move.l  #about_fn_manager,%d0\n"
    "        move.l  %d0,8(%a0)\n"
    "        move.l  (%a3),%d0\n"
    "        move.l  %d0,12(%a0)\n"
    "        lea     -48(%a6),%a0\n"                    /* select: payload = the menu */
    "        move.l  %a2,(%a0)\n"
    "        clr.l   4(%a0)\n"
    "        move.l  #about_fn_manager,%d0\n"
    "        move.l  %d0,8(%a0)\n"
    "        move.l  4(%a3),%d0\n"
    "        move.l  %d0,12(%a0)\n"
    "        lea     -32(%a6),%a0\n"                    /* draw: no payload */
    "        clr.l   (%a0)\n"
    "        clr.l   4(%a0)\n"
    "        move.l  #about_fn_manager,%d0\n"
    "        move.l  %d0,8(%a0)\n"
    "        move.l  8(%a3),%d0\n"
    "        move.l  %d0,12(%a0)\n"
    "        lea     -16(%a6),%a0\n"                    /* change: payload = the menu */
    "        move.l  %a2,(%a0)\n"
    "        clr.l   4(%a0)\n"
    "        move.l  #about_fn_manager,%d0\n"
    "        move.l  %d0,8(%a0)\n"
    "        move.l  12(%a3),%d0\n"
    "        move.l  %d0,12(%a0)\n"
    "        pea     0x54.w\n"
    "        jsr     0x4010394C\n"                      /* operator new */
    "        addq.l  #4,%sp\n"
    "        move.l  %d0,%d2\n"
    "        pea     8.w\n"
    "        pea     -1.w\n"
    "        pea     -16(%a6)\n"
    "        pea     -32(%a6)\n"
    "        pea     -48(%a6)\n"
    "        pea     -64(%a6)\n"
    "        move.l  %d2,-(%sp)\n"
    "        jsr     0x400FA84C\n"                      /* MenuItem(this, label, select, draw, change, id, step) */
    "        lea     28(%sp),%sp\n"
    "        move.l  %d2,-(%sp)\n"
    "        move.l  %a2,-(%sp)\n"
    "        jsr     0x400FA082\n"                      /* Menu::addItem(menu, item) */
    "        addq.l  #8,%sp\n"
    "        movem.l -76(%a6),%d2/%a2-%a3\n"
    "        unlk    %a6\n"
    "        rts\n");
