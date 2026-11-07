/* SPDX-License-Identifier: GPL-2.0-or-later
 * SyntHack glue for the POLY port: gcc copies local array initializers with memcpy, and there is no libc here.
 */
typedef unsigned int u32;
void *memcpy(void *d, const void *s, u32 n)
{
    unsigned char *a = d;
    const unsigned char *b = s;
    while (n--)
        *a++ = *b++;
    return d;
}
