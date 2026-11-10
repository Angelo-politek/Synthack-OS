/* SPDX-License-Identifier: GPL-2.0-or-later
 * about: a SYNTHACK row at the end of the settings menu. YES opens a list: the version, the mods in this build
 * with their status, the repository, the credits. UP/DOWN or an encoder scroll, NO closes.
 *
 * The row is added as Synfact adds its own (mods/core/settings.s and mods/system-info-st, GSM1980 and
 * contributors, on elekloader by irpina, GPL-2.0-or-later): a hook after the last row of the menu's item builder
 * and a MenuItem built from four std::function objects. Addresses are OS 1.42.
 *
 * The list is drawn over the frame while it is open (sfcore's draw event) and takes every key but transport.
 * Rows come from about_data.h, written by make_patch.py: text, and for a mod the address of its first bytes in
 * the mod area. The loader zeroes the area beyond the code of the build, so a mod that is not in the build
 * reads zero there and its row is skipped. Nothing in the audio interrupt, nothing saved.
 */
#include "synthack.h"

#define FILL       ((void (*)(void *, s32, s32, s32, s32, u32))0x400F7FB6u)     /* (bitmap, x0, y0, x1, y1, ink) */
#define INVALIDATE ((void (*)(void *))0x400FFE22u)
#define LINES 9
#define KEY_NO 13
#define KEY_UP 14
#define KEY_DOWN 15

struct row { const char *text; u32 probe; };            /* probe: 0 = always shown */
#include "about_data.h"                                 /* static const struct row rows[]; ROWS */

struct capture { void *data; u32 unused, manager, invoke; };
struct sub { u32 event; void (*callback)(void); };
struct module { const char *name; int (*init)(const void *); const struct sub *subs; u32 count; };

u32 about_open DATA = 0, about_top DATA = 0;
static u32 dirty DATA = 0, swallow DATA = 0;
#define open about_open
#define top about_top
static u8 shown[ROWS] DATA = {0};
static u32 count DATA = 0;

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
    u32 last = count > LINES ? count - LINES : 0;
    if (d < 0 && top)
        top--;
    if (d > 0 && top < last)
        top++;
    dirty = 1;
}

/* the list, on a 128 x 64 bitmap (y = 0 is the bottom line) */
void about_paint(void *bmp)
{
    u32 k;
    if (!count)
        collect();
    FILL(bmp, 0, 0, 127, 63, 0);
    for (k = 0; k < LINES && top + k < count; k++)
        DRAW_TEXT(bmp, FONT_4X6, 2, 57 - 7 * (s32)k, 0, 0, "XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX", "%s",
                  rows[shown[top + k]].text);
    if (count > LINES) {                                /* scroll bar on the right edge */
        s32 h = 64 * LINES / (s32)count, y = 63 - (s32)(64 * top / count);
        FILL(bmp, 126, y - h + 1 < 0 ? 0 : y - h + 1, 127, y, 1);
    }
}

static void about_draw(void *bmp, void *ctrl)
{
    (void)ctrl;
    if (open)
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

/* while the list is open every key is its own, transport (9, 10, 11) excepted; NO's release too after closing */
int about_key(void *brain, void *ev)
{
    u32 key = be((const u8 *)ev + 12), flags = be((const u8 *)ev + 16);
    (void)brain;
    if (!(flags & 1)) {
        if (swallow && key == swallow) {
            swallow = 0;
            return 1;
        }
        return open && !(key >= 9 && key <= 11);
    }
    if (!open || (key >= 9 && key <= 11))
        return 0;
    if (key == KEY_NO) {
        open = 0;
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
    if (!open)
        return 0;
    if (delta)
        move(delta > 0 ? 1 : -1);
    return 1;
}

/* ---- the settings row */
const char *about_label_text(void) { return "SYNTHACK"; }

static void about_select(const struct capture *fn)
{
    collect();
    open = 1;
    top = 0;
    dirty = 1;
    if (fn->data)
        INVALIDATE((u8 *)fn->data + 0x38);
}
static void about_icon(const struct capture *fn, void *item, void *bmp, int x, int y)
{
    (void)fn; (void)item; (void)bmp; (void)x; (void)y;
}
static void about_change(const struct capture *fn, int amount) { (void)fn; (void)amount; }

extern void about_label(void);
extern void about_additem(void *menu, const void *row);
void about_rows(void *menu)
{
    static const void *const row[] = {about_label, about_select, about_icon, about_change};
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
