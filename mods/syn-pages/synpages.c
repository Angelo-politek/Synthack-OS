/* syn-pages on the main CPU (OS 1.42): the SRC view (SourcePageView) asks the registered machine for its pages.
 *
 * Three vtable slots of SourcePageView (0x401CA37C) point here (make_patch.py):
 * - 47, knob -> descriptor (0x40044C54): sp_record; it also gives the view as many pages as the machine has (the
 *   page key already cycles through the view's page list: index +0x90 = (index + 1) % pages);
 * - 19, the page's name (0x40044894, shown on a page key): sp_title, a std::string returned by value;
 * - 4, draw (0x40030B84): sp_draw, the stock page, then the machine's drawing.
 * A machine without an entry gets the stock functions. Page list handling from SY FM4 (Rxuting, MIT).
 */
#include "synpages.h"

typedef uint32_t u32;

#define ORIG_DRAW ((void (*)(void *, void *))0x40030b84)
/* The OS returns pointers in d0; this compiler (m68k-linux ABI) reads a pointer result from a0. */
#define FW_MALLOC ((u32 (*)(u32))0x4010394c)
#define FW_FREE ((void (*)(void *))0x40103958)

#define PAGES_BEGIN 0x7c
#define PAGES_END 0x80
#define PAGES_CAP 0x84
#define PAGE_INDEX 0x90

/* first in the blob: synpages_layout.TABLE */
__attribute__((section(".entries"), used)) sp_machine_t sp_machines[SP_N] = {{0, 0, 0, 0, 0}};

static const sp_machine_t *find(void *view) {
    u32 key = SP_ORIG_RECORD(view, 0);
    for (int i = 0; i < SP_N; i++)
        if (sp_machines[i].key && sp_machines[i].key == key)
            return &sp_machines[i];
    return 0;
}

/* As many pages in the view's page list as the machine has (copies of the first: the page key cycles the index). */
static void fit_pages(void *view, u32 want) {
    u32 *begin = (u32 *)SP_V(view, PAGES_BEGIN);
    u32 n = (SP_V(view, PAGES_END) - (u32)begin) / 4;
    if (begin == 0 || n == 0)
        return;
    want = want < 1 ? 1 : want > SP_PAGES_MAX ? SP_PAGES_MAX : want;
    if (want > n) {
        if (SP_V(view, PAGES_CAP) - (u32)begin < 4 * want) {
            u32 *b = (u32 *)FW_MALLOC(4 * SP_PAGES_MAX);
            if (b == 0)
                return;
            for (u32 i = 0; i < n; i++)
                b[i] = begin[i];
            FW_FREE(begin);
            begin = b;
            SP_V(view, PAGES_BEGIN) = (u32)b;
            SP_V(view, PAGES_CAP) = (u32)(b + SP_PAGES_MAX);
        }
        for (u32 i = n; i < want; i++)
            begin[i] = begin[0];
        SP_V(view, PAGES_END) = (u32)(begin + want);
    } else if (want < n) {
        SP_V(view, PAGES_END) = (u32)(begin + want);
        if (SP_V(view, PAGE_INDEX) >= want)
            SP_V(view, PAGE_INDEX) = 0;
    }
}

u32 sp_record(void *view, u32 knob) {
    const sp_machine_t *m = find(view);
    fit_pages(view, m ? m->pages : 1);
    if (m && m->record)
        return m->record(view, SP_V(view, PAGE_INDEX), knob);
    return SP_ORIG_RECORD(view, knob);
}

const char *sp_title_text(void *view) {
    const sp_machine_t *m = find(view);
    return m && m->title ? m->title(view, SP_V(view, PAGE_INDEX)) : 0;
}

/* std::string by value: the caller passes the string to construct in a0 and gets it back in d0 (0x40044894 builds
 * it with the constructor 0x401bf31e(string, text, allocator)). */
void sp_title(void);
__asm__(
    "    .text\n"
    "    .globl sp_title\n"
    "sp_title:\n"
    "    move.l %a0,-(%sp)\n"           /* string to construct */
    "    move.l 8(%sp),-(%sp)\n"        /* view */
    "    jsr sp_title_text\n"
    "    addq.l #4,%sp\n"
    "    movea.l (%sp)+,%a0\n"
    "    tst.l %d0\n"
    "    bne.s 1f\n"
    "    jmp 0x40044894\n"              /* stock title: a0 and the stack as on entry */
    "1:  move.l %a0,-(%sp)\n"
    "    pea (%sp)\n"                   /* allocator (empty) */
    "    move.l %d0,-(%sp)\n"
    "    move.l %a0,-(%sp)\n"
    "    jsr 0x401bf31e\n"
    "    lea 12(%sp),%sp\n"
    "    move.l (%sp)+,%d0\n"
    "    rts\n");

void sp_draw(void *view, void *bitmap) {
    ORIG_DRAW(view, bitmap);
    const sp_machine_t *m = find(view);
    if (m && m->draw)
        m->draw(view, bitmap, SP_V(view, PAGE_INDEX));
}
