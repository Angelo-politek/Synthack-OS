/* SPDX-License-Identifier: GPL-2.0-or-later
 * long-samples on the voice CPU: long samples sent while the Syntakt runs (a recording, an upload), no reboot.
 * After Synfact's runtime receiver (mods/core-st/audio-pool.c, GSM1980 and contributors, on elekloader by irpina):
 * the same window (shared RAM 0x800, free after the boot upload), sequence, checksum and acknowledgement, called at
 * the end of every audio interrupt (0x40000B04, Synfact's site). Ours: two commands on the table the SAMPLER reads.
 *
 *   +0 'LSRX'  +4 seq << 16 | cmd  +8 dst  +12 len  +16 sum (magic + word 1 + dst + len + data words)
 *   +24 ack: seq << 16 | 1 (done) or 2 (refused)   +32 data, up to 992 bytes
 *   cmd 2 DATA: len bytes (multiple of 4) to dst, inside the long-sample memory (after the table's page)
 *   cmd 3 ENTRY: entry dst (< 64) of the table = {pointer +32, frames len}; count at least dst + 1
 * A request is copied once: the same sequence again gets the same answer.
 */
typedef unsigned int u32;

#define WIN ((volatile u32 *)0x800u)
#define MAGIC 0x4C535258u                           /* 'LSRX' */
#define SAMPLES ((volatile const u32 *)0x4404f754u)  /* stock table: 64 x {length, pointer} */
#define POOL 0x4004f750u
#define POOL_END (POOL + 0x4000000u)
#define LONG_MAGIC 0x53484c53u                       /* 'SHLS' */
#define DATA_MAX 992u

static u32 last, answer;
u32 ls_rx_count;                                     /* requests done (tests) */

static u32 table(void)
{
    u32 bytes = 4 * 64, s;
    for (s = 0; s < 64; s++)
        bytes += 2 * SAMPLES[2 * s];
    return POOL + ((bytes + 2047) & ~2047u);
}

void ls_rx(void)
{
    u32 seq, cmd, dst, len, sum, i, n, t, lo;
    volatile u32 *tab;

    if (WIN[0] != MAGIC)
        return;
    seq = WIN[1] >> 16;
    cmd = WIN[1] & 0xffffu;
    if (!seq)
        return;
    if (seq == last) {
        WIN[6] = seq << 16 | answer;
        return;
    }
    dst = WIN[2];
    len = WIN[3];
    n = cmd == 2 ? len : cmd == 3 ? 4 : 0;
    if (n > DATA_MAX)
        n = 0;
    sum = MAGIC + WIN[1] + dst + len;
    for (i = 0; i < n / 4; i++)
        sum += WIN[8 + i];
    if (sum != WIN[4])
        return;                                      /* not all written yet: no answer */
    t = table();
    lo = t + 2048;
    answer = 2;
    if (cmd == 2 && lo < POOL_END) {
        if (len && len <= DATA_MAX && !(len & 3) && !(dst & 3) && dst >= lo && dst < POOL_END && len <= POOL_END - dst) {
            for (i = 0; i < len / 4; i++)
                ((volatile u32 *)dst)[i] = WIN[8 + i];
            answer = 1;
        }
    } else if (cmd == 3 && lo < POOL_END) {
        u32 p = WIN[8];
        if (dst < 64 && (!len || (p >= lo && p < POOL_END && len <= (POOL_END - p) / 2))) {
            tab = (volatile u32 *)t;
            if (tab[0] != LONG_MAGIC) {
                tab[1] = 0;
                tab[0] = LONG_MAGIC;
            }
            tab[3 + 2 * dst] = 0;                    /* the engine never sees a half entry */
            tab[2 + 2 * dst] = len ? p : 0;
            tab[3 + 2 * dst] = len;
            if (tab[1] <= dst)
                tab[1] = dst + 1;
            answer = 1;
        }
    }
    last = seq;
    ls_rx_count++;
    WIN[6] = seq << 16 | answer;
}
