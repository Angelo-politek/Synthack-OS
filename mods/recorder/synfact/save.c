/* UI-task HZFS writer. Data and index are verified before pool publication.
 * Both valid index copies reserve their extents. No low-zone IO or formatting.
 * Scratch allocations are owned and freed on every exit; RAM take is retained. */
#define SAM_IO 4096u
static u8 *sam_save_index DATA=0,*sam_save_io DATA=0,*sam_save_check DATA=0;
static u32 sam_save_phase DATA=0,sam_save_pos DATA=0,sam_save_total DATA=0;
static u32 sam_save_first DATA=0,sam_save_id DATA=0,sam_saved_id DATA=0;
static u32 sam_save_start DATA=0,sam_save_frames DATA=0;
static u32 sam_save_index_len DATA=0,sam_save_target DATA=0,sam_save_crc DATA=0;
static char sam_save_name[17] DATA={0},sam_save_message[25] DATA={0};
static u8 *sam_name_view DATA=0;
static void sam_redraw(void);
/* CHORUS_INTEGRATED: between naming and saving, the native TrackSelect popup (SoundMenuView's
 * "SELECT TRACK" view, ctor 4006e1c6) asks for a track. It draws the popup,
 * lights the trig LEDs of the allowed tracks white (palette 20 current, 21 rest)
 * and calls back on key release with the track, or -1 for NO. */
#define BRAIN REC_BRAIN
/* SyntHack: the SAMPLER (mods/sampler, SP TWINSHOT's machine slot) and its SAMP (id 504, storage id from the
 * descriptor); raw = position in the sample list << 8 (glue.c, rec_publish) */
#define ASSIGN_TYPE 44u
/* SyntHack: the machine menu's value for the SAMPLER's ONESHOT (mods/sampler: 45..48 = the four types). Set this
 * way the track gets machine 44 with the type and the type's start values, as when it is picked in the menu;
 * machine 44 set raw kept the old machine's word as the type. */
#define ASSIGN_MENU 45u
extern u32 rec_samp_engine(void);
extern int rec_publish(u32 id);
#define ASSIGN_SAMP rec_samp_engine()
enum { SAM_ASSIGN_IDLE, SAM_ASSIGN_OPEN, SAM_ASSIGN_SHOWN, SAM_ASSIGN_DONE };
static u32 sam_assign_phase DATA=0,sam_assign_mask DATA=0,sam_yes_down DATA=0,sam_assign_at DATA=0;
static s32 sam_assign_answer DATA=-1,sam_assign_track DATA=-1;
static char sam_assign_text[25] DATA={0};
/* UI task, after the pool add. Machine menu path 4000f7be (defaults, notifications,
 * POLY slave guard), then SAMP through the native Sound setter 40013304. */
static const char *sam_assign_apply(u32 slot)
{
    s32 track=sam_assign_track;u8 *kit,*model,*sound;u32 proxy[5];
    sam_assign_track=-1;
    if(track<0 || track>7)return "SAVED + IN POOL";
    kit=BRAIN()+0x130;
    REC_SET_MACHINE(kit,(u32)track,ASSIGN_MENU,1,1);
    model=REC_TRACK_MODEL(kit,(u32)track);
    sound=(u8 *)((u32 (*)(void *))(*(u32 **)model)[0x28/4])(model);   /* SyntHack: the pointer comes back in d0 */
    if(!sound || sound[0xa2]!=ASSIGN_TYPE) {
        /* SyntHack: say what the track has instead (99: no Sound), for bug reports */
        u32 m=sound?sound[0xa2]:99u;
        text_set(sam_assign_text,"SAVED / TRACK HAS M00",24);
        sam_assign_text[19]=(char)('0'+m/10u%10u);sam_assign_text[20]=(char)('0'+m%10u);
        return sam_assign_text;
    }
    /* SoundParameterSet (vtable 401c3aac) borrowing the track model at +10. */
    proxy[0]=0x401c3d4cu;proxy[1]=0;proxy[2]=0;proxy[3]=0;proxy[4]=(u32)model;
    REC_SET_PARAM(proxy,ASSIGN_SAMP,slot<<8,(u32)track,0,1);
    text_set(sam_assign_text,"SAVED > TRACK 1",16);sam_assign_text[14]=(char)('1'+track);
    return sam_assign_text;
}

static s32 sam_write(u32 lba,u32 bytes,const void *src)
{
    u32 sectors=bytes>>9,card=CARD_SECTORS;
    if(card>0x800000u)card=0x800000u;
    if(!bytes || (bytes&511u) || bytes>SAM_IO || lba<HZ_INDEX_A ||
        lba>=card || sectors>card-lba)return -1;
    return MMC_WRITE(lba,bytes,src);
}
static void sam_save_cleanup(const char *message)
{
    sam_save_phase=0;sam_assign_track=-1; /* a failed save never assigns */
    if(sam_save_index)FREE(sam_save_index);
    if(sam_save_io)FREE(sam_save_io);
    if(sam_save_check)FREE(sam_save_check);
    sam_save_index=0;sam_save_io=0;sam_save_check=0;
    /* A verified saved slice returns to the intact take and its selection.
     * Failed writes remain in TRIMMED so naming/save can be retried. */
    if(message[0]=='S' && message[1]=='A' && message[2]=='V' && message[3]=='E' && message[4]=='D') {
        sam_trimmed=0;sam_loupe_side=0;sam_play_length=0;
    }
    recorder_save_release();text_set(sam_save_message,message,24);sam_redraw();
}
/* A read error is not an absent index. Never write if either copy could not
 * be read. Malformed CRC-valid entries also stop allocation, rather than
 * interpreting their extents as free. */

static u32 sam_name_equal(const u8 *a,const char *b)
{
    u32 i;for(i=0;i<32;i++){if(a[i]!=(u8)b[i])return 0;if(!a[i])return 1;}
    return 1;
}
/* Add only after commit verification. SyntHack: long-samples' list and the voice CPU at once (hot upload) instead
 * of Synfact's project pool. A full voice CPU never undoes the eMMC save: the file loads at the next boot. */
static void sam_save_add(void)
{
    s32 samp;
    if(!recorder_save_acquire()){sam_save_cleanup("TRANSFER BUSY");return;}
    samp=rec_publish(sam_saved_id);
    sam_save_cleanup(samp>=0?sam_assign_apply((u32)samp):"SAVED / AFTER REBOOT");
}
static void sam_save_init(void)
{
    u8 *copies[2]={0,0},*best,*e,*f;u32 lens[2]={0,0},k,i,j,len,n,id,blocks,at,end;
    u32 best_k,windows,next,seq,again; s32 status;const char *error="INDEX ERROR";
    if(!recorder_save_acquire()){error="TRANSFER BUSY";goto fail;}
    if(CARD_SECTORS/HZ_BLOCK_SECTORS<=HZ_DATA_FIRST)goto fail;
    {
        struct st_hzfs fs;
        status=host->hz_open(&fs,host->storage);
        if(status!=ST_HZ_OK){error=status==ST_HZ_MEMORY?"NO MEMORY":"INDEX READ ERROR";goto fail;}
        for(k=0;k<2;k++){copies[k]=fs.copy[k];lens[k]=fs.length[k];fs.copy[k]=0;}
        host->hz_close(&fs);
    }
    if(!copies[0] && !copies[1]){error="HZFS NOT FOUND";goto fail;}
    best_k=!copies[0] || (copies[1] && be32(copies[1]+8)>be32(copies[0]+8));
    best=copies[best_k];len=lens[best_k];n=be32(best+12);seq=be32(best+8);
    id=be32(best+28);windows=be32(best+24);
    if(seq==0xffffffffu || !id || id>=HZ_FLAG || len>HZ_MAX_LEN-(be32(best+4)==2?68u:64u)){error="INDEX FULL";goto fail;}
    /* Index names are UTF-8; the native selector is restricted here to its
     * ASCII repertoire (16 chars), matching SAMP's 16-byte name field. */
    for(i=0;i<n;i++)if(!st_hz_member(best,i) && sam_name_equal(best+HZ_ENTRIES+i*HZ_ENTRY+32,sam_save_name)){
        error="NAME EXISTS";goto fail;
    }
    blocks=(64+2*sam_save_frames+HZ_MAX_LEN-1)/HZ_MAX_LEN;at=HZ_DATA_FIRST;
    do {
        again=0;
        for(k=0;k<2;k++)if(copies[k])for(j=0;j<be32(copies[k]+12);j++) {
            f=copies[k]+HZ_ENTRIES+j*HZ_ENTRY;end=be32(f+4)+be32(f+8);
            if(at<end && be32(f+4)<at+blocks){at=end;again=1;}
        }
    }while(again && at<=windows && blocks<=windows-at);
    if(at>=windows || blocks>windows-at){error="eMMC FULL";goto fail;}
    next=len+(be32(best+4)==2?68u:64u);
    sam_save_index=MALLOC((next+511)&~511u);
    if(!heap_ok(sam_save_index)){sam_save_index=0;error="NO MEMORY";goto fail;}
    for(i=0;i<((next+511)&~511u);i++)sam_save_index[i]=i<HZ_ENTRIES+64*n?best[i]:0;
    if(be32(best+4)==2){
        for(i=0;i<4*n;i++)sam_save_index[HZ_ENTRIES+64*(n+1)+i]=best[HZ_ENTRIES+64*n+i];
        for(i=0;i<ST_HZ_FOLDER_BYTES*st_hz_folder_count(best);i++)
            sam_save_index[HZ_ENTRIES+68*(n+1)+i]=best[HZ_ENTRIES+68*n+i];
    }
    sam_save_io=MALLOC(SAM_IO);if(!heap_ok(sam_save_io)){sam_save_io=0;error="NO MEMORY";goto fail;}
    sam_save_check=MALLOC(SAM_IO);if(!heap_ok(sam_save_check)){sam_save_check=0;error="NO MEMORY";goto fail;}
    put32(sam_save_index+8,seq+1);put32(sam_save_index+12,n+1);
    put32(sam_save_index+28,id+1);put32(sam_save_index+36,next);
    e=sam_save_index+HZ_ENTRIES+64*n;put32(e,id);put32(e+4,at);put32(e+8,blocks);
    put32(e+12,64+2*sam_save_frames);put32(e+16,sam_save_frames);
    for(i=0;i<16 && sam_save_name[i];i++)e[32+i]=(u8)sam_save_name[i];
    sam_save_index_len=next;sam_save_first=at*HZ_BLOCK_SECTORS;sam_save_id=id;
    /* Always replace the older/invalid copy. On equal sequences choose B;
     * A remains the valid newest copy throughout the transaction. */
    sam_save_target=best_k?HZ_INDEX_A:HZ_INDEX_B;
    sam_save_total=64+2*sam_save_frames;sam_save_pos=0;sam_save_crc=0;
    sam_save_phase=2;
    for(k=0;k<2;k++)if(copies[k])FREE(copies[k]);
    return;
fail:
    for(k=0;k<2;k++)if(copies[k])FREE(copies[k]);
    sam_save_cleanup(error);
}
static void sam_save_step(void)
{
    u32 bytes,logical,i,lba;u8 *e;
    if(sam_save_phase==1){sam_save_init();return;}
    if(sam_save_phase==4){sam_save_add();return;}
    logical=sam_save_total-sam_save_pos;if(logical>SAM_IO)logical=SAM_IO;
    bytes=(logical+511u)&~511u;
    if(sam_save_phase==2) {
        for(i=0;i<bytes;i++) {
            u32 p=sam_save_pos+i;
            sam_save_io[i]=0;
            if(i<logical && p>=64){
                u32 q=p-64;u16 value=(u16)sam_pcm[sam_save_start+(q>>1)];
                sam_save_io[i]=(u8)(q&1?value:value>>8);
            }
        }
        if(!sam_save_pos) {
            put32(sam_save_io,0x53414d50u);put32(sam_save_io+8,sam_save_frames);
            for(i=0;i<16 && sam_save_name[i];i++)sam_save_io[12+i]=(u8)sam_save_name[i];
        }
        lba=sam_save_first+(sam_save_pos>>9);
    }else {
        for(i=0;i<bytes;i++)sam_save_io[i]=i<logical?sam_save_index[sam_save_pos+i]:0;
        lba=sam_save_target+(sam_save_pos>>9);
    }
    if(sam_write(lba,bytes,sam_save_io)){sam_save_cleanup("WRITE ERROR");return;}
    if(MMC_READ(lba,bytes,sam_save_check)){sam_save_cleanup("VERIFY READ ERROR");return;}
    for(i=0;i<bytes;i++)if(sam_save_check[i]!=sam_save_io[i]){sam_save_cleanup("VERIFY ERROR");return;}
    sam_save_crc=crc_update(sam_save_crc,sam_save_check,logical);sam_save_pos+=logical;
    if(sam_save_pos!=sam_save_total)return;
    if(sam_save_phase==2) {
        e=sam_save_index+HZ_ENTRIES+64*(be32(sam_save_index+12)-1);put32(e+20,~sam_save_crc);
        put32(sam_save_index+32,0);put32(sam_save_index+32,crc32(sam_save_index,sam_save_index_len));
        sam_save_pos=0;sam_save_total=sam_save_index_len;sam_save_crc=0;sam_save_phase=3;
    }else {sam_saved_id=sam_save_id;sam_save_phase=4;}
}
static u32 sam_name_manager(struct fn_capture *dst,const struct fn_capture *src,u32 op)
{
    (void)src;if(op<3){dst->data=0;dst->reserved=0;}return 0;
}
static void sam_name_done(const struct fn_capture *fn,u8 **q,u32 number)
{
    const u8 *name=*q;u32 n=0,i; (void)fn;(void)number;
    if(!sam_pcm || !sam_frames || sam_frames>SAM_MAX_FRAMES || sam_state!=SAM_READY) {
        text_set(sam_save_message,"INVALID TAKE",24);return;
    }
    while(n<16 && name[n])n++;
    while(n && name[n-1]==' ')n--;
    sam_keys_down=0;
    if(!n){text_set(sam_save_message,"EMPTY NAME",24);return;}
    for(i=0;i<n;i++)if(name[i]<32 || name[i]>126){text_set(sam_save_message,"USE ASCII NAME",24);return;}
    for(i=0;i<n;i++)sam_save_name[i]=(char)name[i];
    sam_save_name[n]=0;
    sam_trim_init();sam_save_start=sam_trim_start;sam_save_frames=sam_trim_end-sam_trim_start;
    sam_save_pos=0;sam_save_total=64+2*sam_save_frames;sam_save_message[0]=0;
    /* Save starts after the track popup (sam_assign_step), not here. */
    sam_assign_track=-1;sam_assign_answer=-1;sam_assign_phase=SAM_ASSIGN_OPEN;
}
static void sam_assign_done(const struct fn_capture *fn,s32 track)
{
    (void)fn;
    sam_assign_answer=track>=0 && track<8 && ((sam_assign_mask>>track)&1u)?track:-1;
    sam_assign_phase=SAM_ASSIGN_DONE;
}
/* Pushes are applied on a later manager pass, so the recorder may still be on
 * top while the popup lives. Its end is the destruction of TrackSelect's copy
 * (dtor 4006e082 -> op 3). Closed without an answer (a trig outside the mask):
 * ask again. */
static u32 sam_assign_manager(struct fn_capture *dst,const struct fn_capture *src,u32 op)
{
    (void)src;
    if(op<3){dst->data=0;dst->reserved=0;}
    else if(sam_assign_phase==SAM_ASSIGN_SHOWN)sam_assign_phase=SAM_ASSIGN_OPEN;
    return 0;
}
/* Same layout as native make_shared<TrackSelect> (40186e02): inplace control
 * block, vtable 401d26c8, object at +16 (0x9c B). Mask = tracks 1..8 where
 * SP ONE SHOT is available (native 4000f72a, hooked availability). */
static void sam_assign_open(void)
{
    u8 *block,alloc=0;u32 text=0;void *pair[2];
    struct fn_capture callback={0,0,sam_assign_manager,sam_assign_done};
    sam_assign_mask=REC_AVAILABILITY(0,ASSIGN_TYPE)&0xFFu;
    block=sam_assign_mask?MALLOC(0xac):0;
    if(!heap_ok(block)){sam_assign_answer=-1;sam_assign_phase=SAM_ASSIGN_DONE;return;}
    put32(block,0x401d2968u);put32(block+4,1);put32(block+8,1);*(u8 **)(block+12)=block+16;
    QSTR_INIT(&text,"ASSIGN SAMPLE TO TRACK?\nPRESS TRIG KEY TO ASSIGN.\nPRESS NO TO SKIP.",&alloc);
    REC_TRACK_CTOR(block+16,&callback,sam_assign_mask,&text);
    REC_QSTR_DTOR(&text);
    pair[0]=block+16;pair[1]=block;sam_assign_phase=SAM_ASSIGN_SHOWN;sam_assign_at=sam_clock;
    UI_PUSH(sam_manager,pair,0);UI_DROP(pair+1);
}
/* The popup is not opaque: manager+0x1c (sam_foreground) keeps RECORDER while
 * the popup is the stack tail (+0x18), which receives the keys. */
static u32 sam_tail_is_recorder(void)
{
    u8 *node=sam_manager?*(u8 **)(sam_manager+0x18):0;
    return node && node!=sam_manager+0x14 && *(u8 **)(node+8)==sam_view;
}
/* Recorder idle, foreground only. TrackSelect acts on key release, so it opens
 * once the naming YES is up. If RECORDER is the tail for 1 s while the popup
 * should be shown, it was lost: ask again rather than lock the keys. */
static void sam_assign_step(void)
{
    if(sam_assign_phase==SAM_ASSIGN_OPEN){if(!sam_yes_down)sam_assign_open();return;}
    if(sam_assign_phase==SAM_ASSIGN_SHOWN) {
        if(!sam_tail_is_recorder())sam_assign_at=sam_clock;
        else if(sam_clock-sam_assign_at>48000u)sam_assign_phase=SAM_ASSIGN_OPEN;
        return;
    }
    sam_assign_track=sam_assign_answer;sam_assign_phase=SAM_ASSIGN_IDLE;sam_save_phase=1;
}
static void sam_name_open(void)
{
    u8 *view,*control,alloc=0;u32 title=0,name=0;void *pair[2];
    struct fn_capture callback={0,0,sam_name_manager,sam_name_done};
    sampler_suspend();sam_keys_down=0;
    if(sam_saved_id){sam_save_add();return;}
    view=MALLOC(0xa0);if(!heap_ok(view)){text_set(sam_save_message,"NO MEMORY",24);return;}
    control=MALLOC(16);if(!heap_ok(control)){FREE(view);text_set(sam_save_message,"NO MEMORY",24);return;}
    QSTR_INIT(&title,"ENTER SAMPLE NAME",&alloc);QSTR_INIT(&name,sam_save_name[0]?sam_save_name:"RECORDING",&alloc);
    REC_NAME_CTOR(view,&title,&name,0,16,0,&callback);
    REC_QSTR_DTOR(&name);REC_QSTR_DTOR(&title);
    put32(control,0x401c98d8u);put32(control+4,1);put32(control+8,1);*(u8 **)(control+12)=view;
    pair[0]=view;pair[1]=control;sam_name_view=view;
    UI_PUSH(sam_manager,pair,0);UI_DROP(pair+1);
}
