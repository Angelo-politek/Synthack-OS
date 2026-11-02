/* syn-pages: SYN pages of their own for a machine (OS 1.42), shared by the machines that use them.
 *
 * A machine registers once, from the mod area's boot list (sp_register): the descriptor of knob A on its stock
 * page as the key, how many pages it has, and up to three callbacks the SRC view calls through syn-pages:
 * - record(view, page, knob): the descriptor id under the knob (0..8, 8 = LEV) on that page;
 * - title(view, page): the page's name, 0 for the stock one;
 * - draw(view, bitmap, page): drawn after the stock page.
 * Drawing helpers for the screen bitmap follow (each machine has its own copy).
 */
#ifndef SYNPAGES_H
#define SYNPAGES_H

#include <stdint.h>

typedef struct {
    uint32_t key, pages;
    uint32_t (*record)(void *view, uint32_t page, uint32_t knob);
    const char *(*title)(void *view, uint32_t page);
    void (*draw)(void *view, void *bitmap, uint32_t page);
} sp_machine_t;

#define SP_N 4
#define SP_PAGES_MAX 4
#ifdef SP_TABLE
static inline void sp_register(const sp_machine_t *m) {
    volatile sp_machine_t *t = (volatile sp_machine_t *)SP_TABLE;
    for (int i = 0; i < SP_N; i++)
        if (t[i].key == 0 || t[i].key == m->key) {
            t[i].pages = m->pages;
            t[i].record = m->record;
            t[i].title = m->title;
            t[i].draw = m->draw;
            t[i].key = m->key;
            return;
        }
}
#endif

/* The SRC view (ParameterPagesView): page list and page index, and per knob (0..7) how long its value stays
 * highlighted after a turn (+0 of a 20-byte slot at +180; 0 = not highlighted). */
#define SP_V(view, off) (*(volatile uint32_t *)((uint8_t *)(view) + (off)))
#define SP_PAGE(view) SP_V(view, 0x90)
#define SP_HIGHLIGHT(view, knob) SP_V(view, 180 + 20 * (knob))

#define SP_ORIG_RECORD ((uint32_t (*)(void *, uint32_t))0x40044c54)
#define SP_DRAW_TEXT ((void (*)(void *, const void *, int32_t, int32_t, int32_t, int32_t, const char *, const char *, \
                                ...))0x400F8DDCu)  /* (bitmap, font, x, y, centred, 0, width template, fmt, ...) */
#define SP_FONT ((const void *)0x402A9510u)        /* 4x6 */

/* Screen bitmap (0x400F72BE): +4 width, +8 height, +12 words per column, +16 pixels. Columns from the left; in a
 * column, y 0 is the bottom of the screen (the panel is mounted upside down) and bit 31 of a word is its first
 * row. Here y counts from the top, as the text calls do. */
__attribute__((unused, noinline)) static void sp_px(void *bm, int x, int y, int on) {
    int32_t w = *(int32_t *)((uint8_t *)bm + 4), h = *(int32_t *)((uint8_t *)bm + 8);
    if (x < 0 || y < 0 || x >= w || y >= h)
        return;
    uint32_t wpc = *(uint32_t *)((uint8_t *)bm + 12);
    volatile uint32_t *col = *(uint32_t **)((uint8_t *)bm + 16) + (uint32_t)x * wpc;
    uint32_t m = (uint32_t)(h - 1 - y), bit = 0x80000000u >> (m & 31);
    if (on)
        col[m >> 5] |= bit;
    else
        col[m >> 5] &= ~bit;
}

__attribute__((unused, noinline)) static void sp_clear(void *bm, int x0, int y0, int x1, int y1) {
    for (int x = x0; x < x1; x++)
        for (int y = y0; y < y1; y++)
            sp_px(bm, x, y, 0);
}

__attribute__((unused, noinline)) static void sp_hline(void *bm, int x0, int x1, int y, int step) {
    if (x0 > x1) {
        int t = x0;
        x0 = x1;
        x1 = t;
    }
    for (int x = x0; x <= x1; x += step)
        sp_px(bm, x, y, 1);
}

__attribute__((unused, noinline)) static void sp_vline(void *bm, int x, int y0, int y1, int step) {
    if (y0 > y1) {
        int t = y0;
        y0 = y1;
        y1 = t;
    }
    for (int y = y0; y <= y1; y += step)
        sp_px(bm, x, y, 1);
}

#endif
