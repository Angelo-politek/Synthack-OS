/* File-owned recorder editor, UI thread only. PCM remains in the existing
 * allocation. A/C move exclusive trim endpoints; B/D zoom their own loupe.
 * Audio-frame clock expires the loupe after 0.8 s even without key activity. */
#define SAM_LOUPE_FRAMES 38400u
static void sam_trim_adjust(u32 field,s32 delta)
{
    u32 side,step,n=sam_frames,point;
    s32 value;
    if(!delta || field>3 || !n || n>SAM_MAX_FRAMES || sam_save_phase)return;
    sam_trim_init();
    if(delta>8)delta=8;
    if(delta< -8)delta=-8;
    side=field>>1;
    if(field&1) {
        value=(s32)sam_zoom[side]+delta;
        if(value<0)value=0;
        if(value>16)value=16;
        sam_zoom[side]=(u32)value;
    } else {
        step=(n>>sam_zoom[side])/126u;if(!step)step=1;
        point=side?sam_trim_end:sam_trim_start;
        value=(s32)point+delta*(s32)step;
        if(!side) {
            if(value<0)value=0;
            if((u32)value>=sam_trim_end)value=(s32)sam_trim_end-1;
        } else {
            if(value<=(s32)sam_trim_start)value=(s32)sam_trim_start+1;
            if(value>(s32)n)value=(s32)n;
        }
        if((u32)value!=point) {
            sam_play_length=0; /* Retire the old audition before publishing edits. */
            __asm__ volatile("" ::: "memory");
            if(side)sam_trim_end=(u32)value;else sam_trim_start=(u32)value;
            sam_saved_id=0;sam_save_message[0]=0;sam_name_wait=0;
        }
    }
    sam_save_message[0]=0;sam_name_wait=0;
    sam_loupe_side=side+1;sam_loupe_at=sam_clock;sam_focus=field;
    sam_report[4]++;sam_redraw();
}
static void sam_frame_text(char *text,u32 n)
{
    char reverse[10];u32 i=0,j;
    do {reverse[i++]='0'+n%10u;n/=10u;}while(n && i<10);
    for(j=0;j<i;j++)text[j]=reverse[i-1-j];
    text[i]=0;
}
/* Exact extrema from complete 256-frame blocks plus PCM at partial edges.
 * At most 510 PCM edge reads per column, plus the disjoint cached blocks.
 * Manually seeded/legacy fixtures retain their coarse-envelope fallback. */
static void sam_trim_range(u32 begin,u32 end,s32 *low,s32 *high)
{
    u32 i,b,e; s32 value;
    *low=0;*high=0;
    if(end>sam_frames)end=sam_frames;
    if(begin>=end)return;
    if(sam_detail_frames==sam_frames) {
        i=begin;
        while(i<end) {
            if(!(i&(SAM_DETAIL_BLOCK-1u)) && end-i>=SAM_DETAIL_BLOCK) {
                b=i/SAM_DETAIL_BLOCK;
                if(sam_detail_low[b]<*low)*low=sam_detail_low[b];
                if(sam_detail_high[b]>*high)*high=sam_detail_high[b];
                i+=SAM_DETAIL_BLOCK;
            } else {
                value=sam_pcm[i++];
                if(value<*low)*low=value;
                if(value>*high)*high=value;
            }
        }
        return;
    }
    if(end-begin<=128u) {
        for(i=begin;i<end;i++){value=sam_pcm[i];if(value<*low)*low=value;if(value>*high)*high=value;}
    } else {
        b=begin*126u/sam_frames;e=(end-1u)*126u/sam_frames;
        if(e>125)e=125;
        for(i=b;i<=e;i++){if(sam_wave_low[i]<*low)*low=sam_wave_low[i];if(sam_wave_high[i]>*high)*high=sam_wave_high[i];}
    }
}
/* Compact owned 3x5 glyphs match four encoder captions on a 128-pixel LCD.
 * No native font object is modified or copied. Row zero is the top row. */
static void sam_small(void *ctx,s32 x,s32 y,const char *text)
{
    static const char alphabet[]="ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789:+()- ";
    static const u8 glyph[][5]={
        {2,5,7,5,5},{6,5,6,5,6},{3,4,4,4,3},{6,5,5,5,6},
        {7,4,6,4,7},{7,4,6,4,4},{3,4,5,5,3},{5,5,7,5,5},
        {7,2,2,2,7},{1,1,1,5,2},{5,5,6,5,5},{4,4,4,4,7},
        {5,7,7,5,5},{5,7,7,7,5},{2,5,5,5,2},{6,5,6,4,4},
        {2,5,5,7,3},{6,5,6,5,5},{3,4,2,1,6},{7,2,2,2,2},
        {5,5,5,5,7},{5,5,5,5,2},{5,5,7,7,5},{5,5,2,5,5},
        {5,5,2,2,2},{7,1,2,4,7},{7,5,5,5,7},{2,6,2,2,7},
        {6,1,2,4,7},{6,1,2,1,6},{5,5,7,1,1},{7,4,6,1,6},
        {3,4,7,5,7},{7,1,2,2,2},{7,5,7,5,7},{7,5,7,1,6},
        {0,2,0,2,0},{0,2,7,2,0},{1,2,2,2,1},{4,2,2,2,4},
        {0,0,7,0,0},{0,0,0,0,0}
    };
    u32 i,row,col;
    for(;*text && x<126;text++,x+=4) {
        for(i=0;alphabet[i] && alphabet[i]!=*text;i++){}
        if(!alphabet[i])continue;
        for(row=0;row<5;row++)for(col=0;col<3;col++)
            if(glyph[i][row]&(4u>>col))WAVE_PIXEL(ctx,x+(s32)col,y+4-(s32)row,1);
    }
}
/* Digitakt 1.54 FUN_400a72d2 scales the 62-column detail by the full-take
 * peak and a ten-pixel half height, matching FUN_400a8c94's overview scale. */
static s32 sam_wave_scale(s32 value)
{
    u32 peak=sam_detail_frames==sam_frames?sam_display_peak:32768u;
    if(!peak)peak=1;
    if(peak>32768u)peak=32768u;
    return value*10/(s32)peak;
}
/* Both the overview and TRIMMED show selected audio inverted. TRIMMED maps
 * its own [start,end) range across the full width, without touching PCM. */
static void sam_draw_selection(void *ctx)
{
    u32 n=sam_frames,begin=sam_trimmed?sam_trim_start:0;
    u32 span=sam_trimmed?sam_trim_end-sam_trim_start:n,i,a,b,selected,start,end;
    s32 lo,hi;
    WAVE_FILL(ctx,0,16,127,40,1);
    start=(sam_trim_start-begin)*126u/span;
    end=(sam_trim_end-begin)*126u/span;
    for(i=0;i<126;i++) {
        a=begin+span*i/126u;b=begin+span*(i+1u)/126u;
        if(b<=a)b=a+1u;
        selected=i>=start && i<end;
        WAVE_FILL(ctx,1+(s32)i,17,1+(s32)i,39,selected);
        if(sam_trimmed)sam_trim_range(a,b,&lo,&hi);
        else {lo=sam_wave_low[i];hi=sam_wave_high[i];}
        WAVE_FILL(ctx,1+(s32)i,28+sam_wave_scale(lo),1+(s32)i,28+sam_wave_scale(hi),selected?0:1);
    }
    if(start>125)start=125;
    if(end>125)end=125;
    WAVE_FILL(ctx,1+(s32)start,17,1+(s32)start,39,0);
    for(i=17;i<=39;i+=2)WAVE_PIXEL(ctx,1+(s32)end,(s32)i,1);
    if(sam_play_length && sam_play_pos>=begin && sam_play_pos<=begin+span) {
        i=(sam_play_pos-begin)*125u/span;
        WAVE_FILL(ctx,1+(s32)i,17,1+(s32)i,39,0);
    }
}
static void sam_draw_loupe(void *ctx,u32 side)
{
    u32 n=sam_frames,span=n>>sam_zoom[side],focus=side?sam_trim_end:sam_trim_start;
    u32 begin,i,a,b,mark; s32 x=side?65:1,lo,hi;
    if(span<62u)span=62u;
    if(span>n)span=n;
    begin=focus>span/2u?focus-span/2u:0;
    if(begin>n-span)begin=n-span;
    WAVE_FILL(ctx,side?65:0,43,side?127:62,63,0);
    for(i=0;i<62;i++) {
        a=begin+span*i/62u;b=begin+span*(i+1u)/62u;
        if(b<=a)b=a+1u;
        sam_trim_range(a,b,&lo,&hi);
        WAVE_FILL(ctx,x+(s32)i,53+sam_wave_scale(lo),x+(s32)i,53+sam_wave_scale(hi),1);
    }
    mark=(focus-begin)*61u/span;if(mark>61)mark=61;
    if(!side)WAVE_FILL(ctx,x+(s32)mark,43,x+(s32)mark,63,1);
    else for(i=43;i<=63;i+=2)WAVE_PIXEL(ctx,x+(s32)mark,(s32)i,1);
}
static void sam_editor_draw(void *ctx)
{
    u32 i;char value[12];
    sam_trim_init();
    WAVE_FILL(ctx,0,0,127,63,0);
    if(!sam_trimmed) {
        /* SyntHack: the four trim controls under encoders A B C D, value over name as on the OS's pages */
        static const char *const names[4]={"START","ZOOM","END","ZOOM"};
        for(i=0;i<4;i++) {
            if(i==0)sam_time_text(value,sam_trim_start);
            else if(i==2)sam_time_text(value,sam_trim_end);
            else {value[0]='X';value[1]=(char)('1'+sam_zoom[i>>1]);value[2]=0;}
            WAVE_TEXT(ctx,(void *)0x443db210u,16+32*(s32)i,57,2,"%s",value);
            WAVE_TEXT(ctx,(void *)0x443db210u,16+32*(s32)i,49,2,"%s",names[i]);
        }
    } else {
        /* The upper overview locates the retained selection in the full take. */
        for(i=0;i<126;i++) {
            WAVE_FILL(ctx,1+(s32)i,55+((s32)sam_wave_low[i]*6>>15),
                      1+(s32)i,55+((s32)sam_wave_high[i]*6>>15),1);
        }
        i=1+sam_trim_start*125u/sam_frames;WAVE_FILL(ctx,(s32)i,48,(s32)i,62,1);
        i=1+sam_trim_end*125u/sam_frames;
        {u32 y;for(y=48;y<=62;y+=2)WAVE_PIXEL(ctx,(s32)i,(s32)y,1);}
    }
    sam_draw_selection(ctx);
    /* SyntHack: the keys, spelled out, one pair a row */
    WAVE_TEXT(ctx,(void *)0x443db210u,1,8,0,"%s",sam_trimmed?"YES: SAVE":"YES: TRIM");
    WAVE_TEXT(ctx,(void *)0x443db210u,66,8,0,"%s","FUNC+YES: PLAY");
    WAVE_TEXT(ctx,(void *)0x443db210u,1,0,0,"%s",sam_trimmed?"NO: UNTRIM":"NO: CLOSE");
    if(!sam_trimmed)WAVE_TEXT(ctx,(void *)0x443db210u,66,0,0,"%s","FUNC+NO: CLEAR");
    if(!sam_trimmed && sam_loupe_side && sam_clock-sam_loupe_at<SAM_LOUPE_FRAMES && !sam_save_phase)
        sam_draw_loupe(ctx,sam_loupe_side-1u);
    if(sam_save_phase || sam_save_message[0]) {   /* SyntHack: SAVED too (the result was never shown here) */
        WAVE_FILL(ctx,5,24,122,42,0);
        WAVE_TEXT(ctx,(void *)0x443db210u,64,33,2,"%s",sam_save_phase?"SAVING":sam_save_message);
        if(sam_save_phase){sam_frame_text(value,sam_save_total?sam_save_pos*100u/sam_save_total:0);WAVE_TEXT(ctx,(void *)0x443db210u,64,25,2,"%s%%",value);}
    }
}
