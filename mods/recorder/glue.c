/* SPDX-License-Identifier: GPL-2.0-or-later
 * recorder: SyntHack glue around Synfact's recorder-st (synfact/). The take is saved by Synfact's HZFS writer
 * (long-samples' storage through sfcore's host API); then, instead of Synfact's project pool (slots 65..128) and
 * SP ONE, it goes to long-samples' list and to the voice CPU at once (ls_refresh: hot upload), and the chosen track
 * gets the SAMPLER with SAMP on it.
 */
typedef unsigned int u32;
typedef unsigned char u8;

void *memcpy(void *d, const void *s, u32 n)
{
    u8 *a = d;
    const u8 *b = s;
    while (n--)
        *a++ = *b++;
    return d;
}

/* long-samples and sampler (make_patch.py: --defsym from their patch.json) */
extern u32 ls_refresh(void);
extern int ls_file_index(u32 id);
extern u8 ls_pos[64];
extern u32 ls_table[];
extern u32 sm_long_samp(u32 position);

/* SAMP's storage id (descriptor +32 of id 504, the copy the OS reads: mods/idspace) */
u32 rec_samp_engine(void)
{
    return *(const volatile u32 *)(IDS_TABLE + 52u * 504u + 32u);
}

/* After the HZFS commit of file `id`: new files to the voice CPU (the take among them), then the take's SAMP value
 * for the SAMPLER (its position in the sample list), or -1 if it could not be sent (voice CPU memory full). */
int rec_publish(u32 id)
{
    int k;
    u32 i, n;
    ls_refresh();
    k = ls_file_index(id);
    if (k < 0)
        return -1;
    n = ls_table[1];
    for (i = 0; i < n && i < 64; i++)
        if (ls_pos[i] == (u8)k)
            return (int)sm_long_samp(i);
    return -1;
}
