/* SPDX-License-Identifier: GPL-2.0-or-later */
#include "ui.h"
static char *decimal(char *s,int n)
{
    char *p=s;
    if(n<0){*p++='-';n=-n;}
    if(n>=100)*p++='0'+n/100;
    if(n>=10)*p++='0'+n/10%10;
    *p++='0'+n%10;*p=0;return s;
}
static int absolute(int n){return n<0?-n:n;}
void arp_draw(const struct arp_screen *v,const struct arp_canvas *c)
{
    const struct arp_settings *p=v->settings;
    static const char *modes[]={"OFF","TRUE","UP","DOWN","CYCL"};
    char value[24],title[32];unsigned int i,j;int scale=1,height[16],pad,selected,x,off,extent;
    const char *suffix=" ARPEGGIATOR";
#define TEXT(f,x,y,a,s) c->text(c->context,f,x,y,a,s)
#define SHAPE(k,x,y,x2,y2,col) c->shape(c->context,k,x,y,x2,y2,col)
    title[0]='T';decimal(title+1,(int)v->track+1);
    for(j=0;title[j];j++);
    for(i=0;suffix[i];i++)title[j++]=suffix[i];
    title[j]=0;
    TEXT(0,64,59,2,title); /* 64 - native font height (5 pixels) */
    TEXT(0,16,48,2,modes[p->mode<=4?p->mode:0]);TEXT(0,16,37,2,"MODE");
    TEXT(0,48,48,2,v->speed_text);TEXT(0,48,37,2,"SPEED");
    TEXT(0,80,48,2,decimal(value,p->range+1));TEXT(0,80,37,2,"RANGE");
    /* Mode 3: centred (as always) and negative while LEN is p-locked. */
    c->bitmap(c->context,v->length_bitmap,112,48,(v->locked&8u)?3u:1u);
    SHAPE(ARP_FILL,106,37,118,42,0);
    TEXT(0,112,37,2,v->show_length?v->length_text:"LEN");
    /* A p-locked value is inverted, as the native pages show it: the fill
     * XORs with a negative colour (400f7df2). */
    /* LEN (bit 3) is the length marker, inverted by the bitmap call above. */
    for(i=0;i<3;i++)if(v->locked&(1u<<i))SHAPE(ARP_FILL,16+32*(int)i-14,47,16+32*(int)i+13,54,0xffffffffu);
    c->bitmap(c->context,0xffffffffu,1,7,0); /* native ARP rail artwork */
    title[0]='A';title[1]='R';title[2]='P';title[3]=' ';title[4]='T';decimal(title+5,(int)v->track+1);
    TEXT(1,14,2,1,title);
    SHAPE(ARP_VLINE,29,1,29,32,1);
    SHAPE(ARP_VLINE,33+4*(p->length+1),7,33+4*(p->length+1),31,1);
    for(i=0;i<16;i++)if(p->enabled&(1u<<i)){
        extent=(absolute(p->offset[i])+10)/11;
        if(extent>scale)scale=extent;
    }
    for(i=0;i<16;i++)height[i]=p->offset[i]/scale+19;
    for(i=0;i<16;i++){
        selected=i==v->selected;pad=1+selected;x=34+4*i;off=p->offset[i];
        if(i<=p->length){
            if(p->enabled&(1u<<i)){
                if(absolute(height[i]-19)<=11)
                    SHAPE(off%12?ARP_RECT:ARP_FILL,x-pad,height[i]-pad,x+pad,height[i]+pad,1);
            }else SHAPE(ARP_HLINE,x-1,19,x+1,19,1);
        }
        if(i<=p->length)SHAPE(i%4?ARP_RECT:ARP_FILL,x-1,3-selected,x+1,1-selected,1);
        else SHAPE(ARP_PIXEL,x,2-selected,x,2-selected,1);
    }
    TEXT(1,114,9,1,"OFS (E)");TEXT(1,114,2,1,decimal(value,p->offset[v->selected&15]));
    TEXT(1,114,26,1,"LEN (F)");TEXT(1,114,19,1,decimal(value,p->length+1));
    SHAPE(ARP_VLINE,100,0,100,31,1);SHAPE(ARP_HLINE,100,15,127,15,0);
    SHAPE(ARP_RECT,0,0,127,32,1);
#undef TEXT
#undef SHAPE
}
