typedef unsigned int u32;
typedef unsigned char u8;
typedef signed int s32;
extern const volatile u8 poly_owner_map[12];

/* Called twice per track on every published block (1500/s). : plain
 * signed byte (any MCF54415 form is allowed since 2026-10-19). */
u32 poly_effective_type(const volatile u8 *cursor)
{
    u32 track=(u32)cursor-0x80002f50u,owner;
    if(track<8) {
        owner=poly_owner_map[track];
        if(owner<=track)cursor=(const volatile u8 *)(0x80002f50u+owner);
    }
    return (u32)(s32)(signed char)*cursor;
}
