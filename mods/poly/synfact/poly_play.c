/* Pattern-owned LFO behavior: shared M.LFO or independent POLY. */
extern const volatile u8 poly_owner_map[12];
static u8 poly_modes[8] DATA={0},poly_next_modes[8] DATA={0};
u8 poly_lfo_map[12] DATA={0,1,2,3,4,5,6,7,8,9,10,11};
static u8 poly_post_map[12] DATA={0,1,2,3,4,5,6,7,8,9,10,11};
static u32 poly_shared_mask DATA=0;
/* Packed first/end (exclusive), computed only when the topology changes. */
static u32 poly_publish_span DATA=0x0108;
extern void poly_fast_publish(u8 *,const volatile u8 *);
extern void poly_fast_publish_span(u8 *,const volatile u8 *,u32);
extern void poly_fast_publish_one(u8 *,const volatile u8 *,u32);
typedef void (*poly_publish_t)(u8 *,const volatile u8 *,u32);
static poly_publish_t poly_publish_entry DATA=poly_fast_publish_span;
extern void poly_mod_shared(void);
extern void poly_mod_all(void);

static void poly_play_maps(const volatile u8 *owners)
{
    u32 t,o,independent,first=12,end=12;
    poly_shared_mask=0;
    for(t=0;t<12;t++) {
        o=owners[t];independent=t<8 && o<t && poly_modes[o]==1;
        poly_lfo_map[t]=(u8)(independent?t:o);
        poly_post_map[t]=(u8)(independent?t:o);
        if(!independent && o<t){
            poly_shared_mask|=1u<<t;
            if(first==12)first=t;end=t+1;
        }
    }
    poly_publish_span=(first<<8)|end;
    poly_publish_entry=end==first+1?poly_fast_publish_one:poly_fast_publish_span;
}
