/* Destructive voice setup. Base Sounds are installed only on group entry,
 * voice growth and task-side edits. The render loop never copies them.
 * Native event copies already share the master's reference-counted lock
 * object, so p-locks are applied by the native per-track event path. */
static volatile u32 poly_copy_pending DATA=0;

static void poly_copy_mark(u32 owner)
{
    u32 t;
    for(t=owner+1;t<8;t++)if(poly_owner_map[t]==owner)poly_copy_pending|=1u<<t;
}

static void poly_copy_record(volatile u8 *d,const volatile u8 *s)
{
    u32 i;
    for(i=0;i<0x123u;i++)d[i]=s[i];
}

static void poly_copy_group(u32 track,u32 owner)
{
    u32 kit=*(volatile u32 *)0x43bd843cu;
    if(!kit || track>=8 || owner>=track)return;
    poly_copy_record((volatile u8 *)(kit+0x2au+track*0x123u),
                     (const volatile u8 *)(kit+0x2au+owner*0x123u));
    /* Publish from the master: optional LFO3 knows that Sound's own record.
     * This path runs at the existing IRQ-masked configuration boundary. */
    native_publish_sound((const volatile u8 *)(kit+0x2au+owner*0x123u),track);
    poly_copy_pending|=1u<<track;
}

/* UI task after a completed native setter. Copy through native memcpy so
 * LFO3's existing Sound-copy service includes its shadow record. The active
 * KIT is the same native source used by 400a3548 for notes. No heap work in
 * an IRQ, no polling/comparing 291-byte records on every render block. */
static void poly_copy_ui(void)
{
    u32 pending=poly_copy_pending,kit=*(volatile u32 *)0x800030b8u,t,o;
    u32 sequence_kit=*(volatile u32 *)0x43bd843cu;
    u32 command[6]={0x504f4c59u,0x434f5059u,0,0,0,0};
    if(!pending || !kit)return;
    /* The native private-command boundary exchanges the mask under IRQ
     * exclusion; a newly queued voice cannot be lost between load/clear. */
    native_immediate(command);pending=command[5];
    for(t=1;t<8;t++) {
        o=poly_owner_map[t];
        if(o>=t || !(pending&(1u<<t)))continue;
        POLY_CALL(0x4011613cu,void *(*)(void *,const void *,u32))
            ((void *)(kit+0x2au+t*0x123u),(const void *)(kit+0x2au+o*0x123u),0x123u);
        if(sequence_kit && sequence_kit!=kit)
            POLY_CALL(0x4011613cu,void *(*)(void *,const void *,u32))
                ((void *)(sequence_kit+0x2au+t*0x123u),(const void *)(kit+0x2au+o*0x123u),0x123u);
        native_publish_sound((const volatile u8 *)(kit+0x2au+t*0x123u),t);
    }
}
