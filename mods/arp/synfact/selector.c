/* SPDX-License-Identifier: GPL-2.0-or-later
 * Source implementation of Digitone 1.44 MAIN 40097e46..40098130's selection
 * semantics. Differential oracle: the untouched routine from the user's OS.
 * No donor instruction bytes are distributed. See README.md for scope.
 */
#include "arp.h"
void arp_reset(struct arp_selector *s,arp_u32 generation)
{
    unsigned int i;
    for(i=0;i<4;i++)s->mask[i]=0;
    s->count=0;s->generation=generation;
    s->step=-1;s->word=0;s->ascending=0;s->last=-1;s->cursor=-1;
    s->octave=0;s->remaining=~0u;
}
int arp_hold(struct arp_selector *s,unsigned int note)
{
    arp_u32 bit;
    if(note>127)return 0;
    bit=1u<<(note&31);
    if(s->mask[note>>5]&bit)return 0;
    if(s->count>=128)return 0;
    s->mask[note>>5]|=bit;s->order[s->count++]=(unsigned char)note;
    return 1;
}
int arp_release(struct arp_selector *s,unsigned int note)
{
    unsigned int i;
    arp_u32 bit;
    if(note>127)return 0;
    bit=1u<<(note&31);
    if(!(s->mask[note>>5]&bit))return 0;
    s->mask[note>>5]&=~bit;
    for(i=0;i<s->count && s->order[i]!=note;i++);
    if(s->cursor>=(int)i)s->cursor--;
    for(;i+1<s->count;i++)s->order[i]=s->order[i+1];
    s->count--;return 1;
}
static void next_octave(struct arp_selector *s,const struct arp_settings *p)
{if(++s->octave>p->range)s->octave=0;}
/* Match ColdFire's zero result for a logical shift by 32, without undefined C. */
static arp_u32 left(arp_u32 n,unsigned int k){return k>=32?0:n<<k;}
static arp_u32 right(arp_u32 n,unsigned int k){return k>=32?0:n>>k;}
static int low_bit(arp_u32 n){return 31-__builtin_clz(n&-n);}
static int high_bit(arp_u32 n){return 31-__builtin_clz(n);}
int arp_next(struct arp_selector *s,const struct arp_settings *p,arp_u32 generation)
{
    arp_u32 m;int note=-1,word,tries,again=1;
    if(generation!=s->generation || !s->count || p->length>=16)return -2;
    if(++s->step>p->length)s->step=0;
    if(!(p->enabled&(1u<<s->step)))return -1;
    if(!p->mode)return -1;
    if(p->mode==1){
        if(s->cursor>=0 && (unsigned int)(s->cursor+1)>=s->count)next_octave(s,p);
        s->cursor++;
        if((unsigned int)s->cursor>=s->count)s->cursor=0;
        note=s->order[s->cursor];
    }else if(p->mode==2 || p->mode==3){
        word=p->mode==2?s->word:3-s->word;
        m=s->mask[word]&s->remaining;
        if(!m)s->remaining=~0u;
        for(tries=4;!m && tries;tries--){
            s->word=(s->word+1)&3;
            if(!s->word)next_octave(s,p);
            word=p->mode==2?s->word:3-s->word;
            m=s->mask[word]&s->remaining;
        }
        if(!m)return -1;
        if(p->mode==2){note=low_bit(m);s->remaining=left(~0u,note+1);}
        else {note=high_bit(m);s->remaining=right(~0u,32-note);}
        note+=32*word;
    }else {
        do {
            word=s->ascending?s->word:3-s->word;
            m=s->mask[word]&s->remaining;
            if(!m)s->remaining=~0u;
            for(tries=8;!m && tries;tries--){
                s->word=(s->word+1)&3;
                if(!s->word){
                    if(s->ascending)s->ascending=0;
                    else {next_octave(s,p);s->ascending=1;}
                }
                word=s->ascending?s->word:3-s->word;
                m=s->mask[word]&s->remaining;
            }
            if(!m){note=-1;break;}
            if(s->ascending){note=low_bit(m);s->remaining=left(~0u,note+1);}
            else {note=high_bit(m);s->remaining=right(~0u,32-note);}
            note+=32*word;
            if(note!=s->last || !again)break;
            again=0;
        }while(1);
    }
    s->last=note;
    return note+12*s->octave+p->offset[s->step];
}
