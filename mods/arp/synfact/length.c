/* SPDX-License-Identifier: GPL-2.0-or-later
 * Authored arithmetic, checked against the original gate producer and label
 * table. No extracted duration/string table or executable bytes are shipped.
 */
#include "length.h"
arp_u32 arp_note_gate(unsigned int n)
{
    unsigned int j;
    if(n>=128)return 0;
    /* The native producer adds one entry to the displayed setting. */
    j=n+1;
    if(j<=62)return 84375u*(j+2);
    if(j<=78)return 337500u*(j-46);
    if(j<=94)return 675000u*(j-62);
    if(j<=110)return 1350000u*(j-78);
    if(j<=123)return 10800000u*(j-106);
    if(j<=127)return 43200000u*(j-119);
    /* OS 1.44 reads past its regular duration table at the maximum setting.
     * The following positive word reaches the native signed gate countdown
     * unchanged. Preserve this observed edge, not a guessed infinite gate. */
    return 2136268810u;
}
static char *whole(char *s,unsigned int n)
{
    if(n>=100)*s++='0'+n/100;
    if(n>=10)*s++='0'+n/10%10;
    *s++='0'+n%10;return s;
}
char *arp_format_note_length(char *out,unsigned int n)
{
    unsigned int units,v,f;char *s=out;
    if(n>=128){out[0]='?';out[1]=0;return out;}
    if(n==6 || n==14 || n==30 || n==62 || n==78 || n==94){
        *s++='1';*s++='/';s=whole(s,n==6?64:n==14?32:n==30?16:n==62?8:n==78?4:2);*s=0;return out;
    }
    if(n<=62)units=n+2;
    else if(n<=78)units=4*(n-46);
    else if(n<=94)units=8*(n-62);
    else if(n<=110)units=16*(n-78);
    else if(n<=123)units=128*(n-106);
    else units=512*(n-119);
    if(units<32){
        v=(units*1000+16)/32;*s++='.';*s++='0'+v/100;
        *s++='0'+v/10%10;*s++='0'+v%10;
    }else if(units<320){
        v=(units*100+16)/32;s=whole(s,v/100);f=v%100;
        *s++='.';*s++='0'+f/10;
        if(n!=46)*s++='0'+f%10; /* Original spells this one value "1.5". */
    }else if(units<3200){
        v=(units*10+16)/32;s=whole(s,v/10);*s++='.';*s++='0'+v%10;
    }else s=whole(s,units/32);
    *s=0;return out;
}
