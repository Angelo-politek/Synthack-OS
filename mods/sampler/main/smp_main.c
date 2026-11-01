/* SAMPLER on the Syntakt's main CPU (OS 1.42): SP TWINSHOT's page shown as the Digitakt's.
 *
 * SP TWINSHOT's eight descriptors (497..504) are rewritten by make_patch.py: names, ranges and
 * defaults of the Digitakt's ONESHOT page, knob H the machine type; logical indices 0x12..0x19 (0x1A, the
 * overdrive every machine has, has no knob here). The values travel to the voice
 * engine like any machine's (engine/syn.c); nothing here is saved.
 *
 * Here:
 * - sm_invoke: the text of each value (the OS calls it through the std::function copied from
 *   sm_proto, see readable-values), and the names and ranges of knobs E, F, G for the track's type;
 * - sm_block: once per audio block, the tempo to shared RAM for REPITCH and WERP.
 */
#include <stdint.h>

typedef uint32_t u32;
typedef int32_t s32;

#define OBJS 0x41BA0A24u                    /* per-parameter objects, 84 B, index = id */
#define OBJ_SIZE 84u
#define DESC 0x4022D83Cu                    /* descriptors, 52 B per id */
#define TRACKS ((const volatile short *)0x800021B0u)    /* per-track values: 0x47 words from +0xE */
#define TRACK_WORDS 0x47
#define LIX_MODE 0x19
#define PROJECT (*(void *const volatile *)0x444E23F4u)
#define GET_TRACK ((s32 (*)(void *))0x4001FF74u)
#define TEMPO (*(const volatile u32 *)0x402D7360u)      /* BPM x 120 */
#define SHARED_TEMPO (*(volatile u32 *)(0x10000000u + 0x7F0u))
#define ORIG_BLOCK ((void (*)(u32))0x40095608u)

typedef struct {
    u32 owner, lix, min, max, def, r5, midi, cc, id, flags;
    const char *longname, *group, *shortname;
} desc_t;

#define ROW(id) ((volatile desc_t *)(DESC + 52u * (id)))

/* knobs E, F, G per machine type: name, short name, range, default */
typedef struct {
    const char *name, *shortname;
    u32 min, max, def;
} knob_t;

static const char group[] = "SMPL";

static const knob_t knobs[4][3] = {
    {{"Start", "STRT", 0, 0x7800, 0}, {"Length", "LEN", 0, 0x7800, 0x7800}, {"Loop Pos", "LOOP", 0, 0x7802, 0}},
    {{"Segment Size", "SEG", 0, 0x200, 0x100}, {"Segment Mode", "SMOD", 0, 0x300, 0x300},
     {"Bars", "BARS", 0, 0x300, 0x200}},
    {{"Start", "STRT", 0, 0x7800, 0}, {"Length", "LEN", 0, 0x7800, 0x7800}, {"Bars", "BARS", 0, 0x300, 0x200}},
    {{"Slice Select", "SLIC", 0, 0x4000, 0}, {"Slice Length", "LEN", 0, 0x3F00, 0},
     {"Slice Grid", "GRID", 0, 0x400, 0}},
};

/* make_patch.py copies these into descriptors 497..504 (52 B each, as the OS's), with SP TWINSHOT's MIDI
 * fields and parameter numbers. SP TWINSHOT's page puts them on knobs A B C G E F H D: logical indices
 * follow the knobs, 0x12 (A) to 0x19 (H), the Digitakt's order (engine/sampler.h). */
#define ID_PLAY 498
#define ID_P7 500
#define ID_P5 501
#define ID_P6 502
#define ID_TYPE 503
#define ID_SAMP 504
__attribute__((used)) const desc_t sm_rows[8] = {
    {44, 0x12, 0x0400, 0x5800, 0x4000, 1, 0, 0, 0, 0xE00, "Tune", group, "TUNE"},           /* 497, A */
    {44, 0x13, 0, 0x300, 0x300, 1, 0, 0, 0, 0xE00, "Play Mode", group, "PLAY"},             /* 498, B */
    {44, 0x14, 0, 0x7F00, 0, 0, 0, 0, 0, 0xE00, "Bit Reduction", group, "BR"},              /* 499, C */
    {44, 0x18, 0, 0x7802, 0, 1, 0, 0, 0, 0xE00, "Loop Pos", group, "LOOP"},                 /* 500, G */
    {44, 0x16, 0, 0x7800, 0, 1, 0, 0, 0, 0xE00, "Start", group, "STRT"},                    /* 501, E */
    {44, 0x17, 0, 0x7800, 0x7800, 1, 0, 0, 0, 0xE00, "Length", group, "LEN"},               /* 502, F */
    {44, 0x19, 0, 0x300, 0, 1, 0, 0, 0, 0xE00, "Machine Type", group, "TYPE"},              /* 503, H */
    {44, 0x15, 0, 0x3F00, 0, 1, 0, 0, 0, 0xE00, "Sample Slot", group, "SAMP"},              /* 504, D */
};

/* knobs E, F, G: descriptors */
static const u32 knob_ids[3] = {ID_P5, ID_P6, ID_P7};

static s32 active_track(void) {
    void *p = PROJECT;
    return p ? GET_TRACK((char *)p + 48) : -1;
}

static int track_type(void) {
    s32 t = active_track();
    if (t < 0 || t >= 8)
        return 0;
    int v = TRACKS[0xE + TRACK_WORDS * t + LIX_MODE] >> 8;
    return v < 0 ? 0 : v > 3 ? 3 : v;
}

/* names and ranges of knobs E, F, G for the track's machine type */
static void fit_knobs(int type) {
    for (int k = 0; k < 3; k++) {
        const knob_t *n = &knobs[type][k];
        volatile desc_t *r = ROW(knob_ids[k]);
        if (r->longname != n->name) {
            r->longname = n->name;
            r->shortname = n->shortname;
            r->min = n->min;
            r->max = n->max;
            r->def = n->def;
        }
    }
}

static char *put_s(char *b, const char *s) {
    while (*s)
        *b++ = *s++;
    return b;
}

static char *put_u(char *b, u32 n) {
    char t[10];
    int k = 0;
    do {
        t[k++] = (char)('0' + n % 10);
        n /= 10;
    } while (n);
    while (k)
        *b++ = t[--k];
    return b;
}

static const char *const play_names[4] = {"REV", "REV.L", "FWD.L", "FWD"};
static const char *const type_names[4] = {"ONE", "WERP", "PTCH", "SLIC"};
static const char *const seg_names[3] = {"1/32", "1/16", "1/8"};

static u32 clampi(s32 v, s32 hi) {
    return v < 0 ? 0 : v > hi ? (u32)hi : (u32)v;
}

void sm_invoke(const void *fn, s32 value, char *buf) {
    u32 off = (u32)fn - (OBJS + 20), id = off / OBJ_SIZE;
    u32 v = clampi(value, 0x7F00), i = v >> 8;
    char *b = buf;
    int type = track_type();
    fit_knobs(type);
    if (off % OBJ_SIZE)
        id = 0;
    switch (id) {
    case ID_PLAY:
        b = put_s(b, play_names[clampi((s32)i, 3)]);
        break;
    case ID_SAMP:                               /* slot 1..64 */
        b = put_u(b, i + 1);
        break;
    case ID_P5:                                 /* STRT | SEG | STRT | SLICE */
        if (type == 1)
            b = put_s(b, seg_names[clampi((s32)i, 2)]);
        else if (type == 3 && i == 0)
            b = put_s(b, "KEY");
        else
            b = put_u(b, i);
        break;
    case ID_P6:                                 /* LEN | segment MODE | LEN | slice LEN */
        if (type == 1)
            b = put_s(b, play_names[clampi((s32)i, 3)]);
        else
            b = put_u(b, type == 3 ? i + 1 : i);
        break;
    case ID_P7:                                 /* LOOP | BARS | BARS | GRID */
        if (type == 0)
            b = v ? put_u(b, (v - 1) >> 8) : put_s(b, "STRT");
        else if (type == 3)
            b = put_u(b, 4u << clampi((s32)i, 4));
        else
            b = put_u(b, 1u << clampi((s32)i, 3));
        break;
    case ID_TYPE:
        b = put_s(b, type_names[clampi((s32)i, 3)]);
        break;
    default:                                    /* BR, and anything else: 0..127 */
        b = put_u(b, i);
        break;
    }
    *b = 0;
}

/* std::function manager: nothing to copy or free */
int sm_mgr(void *dst, const void *src, int op) {
    (void)dst;
    (void)src;
    (void)op;
    return 0;
}

/* copied by the OS into each object's +20 (make_patch.py points the constructors here) */
const void *const sm_proto[4] __attribute__((aligned(4))) = {0, 0, (const void *)sm_mgr, (const void *)sm_invoke};

/* once per audio block, in place of the call to 0x40095608 */
void sm_block(u32 arg) {
    SHARED_TEMPO = TEMPO;
    ORIG_BLOCK(arg);
}

__attribute__((section(".entries"), used)) const void *const sm_entries[3] = {
    (const void *)sm_proto, (const void *)sm_block, (const void *)sm_rows};
