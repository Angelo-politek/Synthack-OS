/* SPDX-License-Identifier: GPL-2.0-or-later */
#ifndef SYNFACT_ST_ARP_UI_H
#define SYNFACT_ST_ARP_UI_H
#include "arp.h"
enum {ARP_FILL,ARP_RECT,ARP_VLINE,ARP_HLINE,ARP_PIXEL};
struct arp_canvas {
    void *context;
    void (*text)(void *,unsigned int font,int x,int y,unsigned int align,const char *);
    void (*shape)(void *,unsigned int kind,int x,int y,int x2,int y2,unsigned int color);
    void (*bitmap)(void *,unsigned int resource,int x,int y,unsigned int mode);
};
struct arp_screen {
    const struct arp_settings *settings;
    unsigned int track,selected,show_length;
    unsigned int locked; /* MODE, SPEED, RANGE, LEN: bits 0..3, drawn inverted */
    const char *speed_text,*length_text;
    unsigned int length_bitmap;
};
/* Coordinates, primitive order and labels from DN 1.44 40051390..40051928.
 * Bitmap/font resources are supplied by the adapter; no firmware bytes here. */
void arp_draw(const struct arp_screen *,const struct arp_canvas *);
#endif
