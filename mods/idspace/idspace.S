| idspace: parameter ids above 504 for the mods (OS 1.42). See README.md and tools/build/idspace_layout.py.
|
| Constants from make_patch.py (--defsym): TABLE, EXT, OBJDEF, OBJ, BUILT, PAGEDEF, FIRST, N, PAGE_FIRST, PAGE_N.
        .equ    STOCK_DESC,     0x4022D83C      | descriptors of the OS, 505 x 52 B
        .equ    STOCK_OBJ,      0x41BA0A24      | parameter objects of the OS, 505 x 84 B
        .equ    PAGES,          0x41BA03C8      | page elements of the OS, 37 x 44 B
        .equ    FN_COPY,        0x40188482      | std::function copy-construct (dst, src): clone through the manager
        .equ    FN_INVOKE,      0x4018837A      | std::function call (fn, a, b)
        .equ    RESULT52,       0x41B9FBCC      | where the OS's +52 lookup leaves its result

        .text
| ---- fixed entry at CODE + 0 (idspace_layout.OBJ_ENTRY): the mods call the object lookup through it, so the
| addresses inside idspace can move without rebuilding them
        .globl  ids_entry, ids_page_hook
ids_entry:
        jmp     ids_obj32
        .word   0
ids_page_hook:                                  | CODE + 8: u32 (*)(u32 index), 0 = none (sfcore: POLY's page 3)
        .long   0
| ---- boot list (before the static constructors): the OS's 505 descriptors, then the mods' (empty: as id 0)
        .globl  ids_boot
ids_boot:
        lea     STOCK_DESC,%a0
        lea     TABLE,%a1
        move.l  #505*13,%d0
1:      move.l  (%a0)+,(%a1)+
        subq.l  #1,%d0
        bne.s   1b
        lea     EXT,%a0
        moveq   #N-FIRST,%d1
2:      tst.l   40(%a0)                         | long name: an entry the mod wrote
        bne.s   3f
        lea     STOCK_DESC,%a0                  | empty: a copy of id 0, as the OS treats unknown ids
3:      moveq   #13,%d0
4:      move.l  (%a0)+,(%a1)+
        subq.l  #1,%d0
        bne.s   4b
        move.l  %a1,%d0                         | next source: EXT + 52 * k
        sub.l   #TABLE+52*505,%d0
        add.l   #EXT,%d0
        movea.l %d0,%a0
        subq.l  #1,%d1
        bne.s   2b
        bra.w   ids_dest_boot                   | then the DEST lists (rts there)

| ---- object of id d1 -> a0 (UI only). OS ids and unknown ids as the OS does (unknown: object 0); mods' ids
| from OBJDEF, built at the first lookup. Saves everything but a0.
ids_obj:
        cmpi.l  #FIRST,%d1
        bcs.s   1f
        cmpi.l  #N,%d1
        bcc.s   2f
        lea     -16(%sp),%sp
        movem.l %d0-%d2/%a1,(%sp)
        tst.l   BUILT
        bne.s   3f
        bsr.w   ids_build
3:      move.l  %d1,%d2
        subi.l  #FIRST,%d2
        movea.l %d2,%a0
        lsl.l   #4,%d2
        lea     OBJDEF,%a1
        tst.l   (%a1,%d2.l)                     | no definition: object 0
        movem.l (%sp),%d0-%d2/%a1
        lea     16(%sp),%sp
        beq.s   2f
        move.l  %a0,%d1                         | k
        mulu.w  #84,%d1
        lea     OBJ,%a0
        adda.l  %d1,%a0
        rts
2:      moveq   #0,%d1
1:      move.l  %d1,-(%sp)
        mulu.w  #84,%d1
        lea     STOCK_OBJ,%a0
        adda.l  %d1,%a0
        move.l  (%sp)+,%d1
        rts

| build every defined object: +0..+19 from the template, each std::function from the prototype the mod gives
| (+20, +36, +68) or from the template
ids_build:
        lea     -36(%sp),%sp
        movem.l %d0-%d4/%a0-%a3,(%sp)
        moveq   #1,%d0
        move.l  %d0,BUILT
        lea     OBJDEF,%a2
        lea     OBJ,%a3
        moveq   #N-FIRST,%d4
1:      move.l  (%a2),%d1                       | template id
        beq.s   8f
        mulu.w  #84,%d1
        lea     STOCK_OBJ,%a1
        adda.l  %d1,%a1                         | template object
        move.l  (%a1),(%a3)                     | +0 type, +4..+19 value prototype: plain data
        move.l  4(%a1),4(%a3)
        move.l  8(%a1),8(%a3)
        move.l  12(%a1),12(%a3)
        move.l  16(%a1),16(%a3)
        lea     fields,%a0
2:      mvs.w   (%a0)+,%d2                      | field offset
        bmi.s   8f
        mvs.w   (%a0)+,%d3                      | prototype index in OBJDEF (0 = none)
        move.l  %a1,%d0
        add.l   %d2,%d0                         | template field
        tst.w   %d3
        beq.s   3f
        ext.l   %d3
        move.l  (%a2,%d3.l),%d1
        beq.s   3f
        move.l  %d1,%d0                         | the mod's prototype
3:      move.l  %a3,%d1
        add.l   %d2,%d1
        lea     -24(%sp),%sp
        movem.l %d2-%d4/%a0-%a2,(%sp)
        move.l  %d0,-(%sp)
        move.l  %d1,-(%sp)
        jsr     FN_COPY
        addq.l  #8,%sp
        movem.l (%sp),%d2-%d4/%a0-%a2
        lea     24(%sp),%sp
        bra.s   2b
8:      lea     16(%a2),%a2
        lea     84(%a3),%a3
        subq.l  #1,%d4
        bne.s   1b
        movem.l (%sp),%d0-%d4/%a0-%a3
        lea     36(%sp),%sp
        rts
fields: .word   20,4, 36,8, 52,0, 68,12, -1    | std::function fields, prototype index in OBJDEF

| ---- 0x4007BA2A: object of id 4(sp)
        .globl  ids_obj32
ids_obj32:
        move.l  4(%sp),%d1
        move.l  %a0,-(%sp)
        bsr.w   ids_obj
        move.l  %a0,%d0
        movea.l (%sp)+,%a0
        rts

| ---- 0x4007BBE2: calls the +20 std::function (text) of id 4(sp) with 8(sp), result in RESULT52
        .globl  ids_obj52
ids_obj52:
        move.l  4(%sp),%d1
        move.l  %a0,-(%sp)
        bsr.w   ids_obj
        move.l  %a0,%d0
        movea.l (%sp)+,%a0
        addi.l  #20,%d0
        pea     RESULT52
        move.l  12(%sp),-(%sp)
        move.l  %d0,-(%sp)
        jsr     FN_INVOKE
        lea     12(%sp),%sp
        move.l  #RESULT52,%d0
        rts

| ---- 0x4007BA48: page element of index 4(sp); PAGE_FIRST.. are the mods' (PAGEDEF)
        .globl  ids_page
ids_page:
        move.l  ids_page_hook,%d0               | first the hook: an element, or 0
        beq.s   3f
        move.l  4(%sp),-(%sp)
        movea.l %d0,%a0
        jsr     (%a0)
        addq.l  #4,%sp
        tst.l   %d0
        beq.s   3f
        rts
3:      move.l  4(%sp),%d0
        moveq   #PAGE_FIRST,%d1
        cmp.l   %d1,%d0
        bcs.s   1f
        moveq   #PAGE_FIRST+PAGE_N,%d1
        cmp.l   %d1,%d0
        bcc.s   2f
        subi.l  #PAGE_FIRST,%d0
        mulu.w  #44,%d0
        addi.l  #PAGEDEF,%d0
        rts
2:      moveq   #-1,%d0                         | as the OS: beyond the array
1:      moveq   #44,%d1
        muls.l  %d1,%d0
        addi.l  #PAGES,%d0
        rts

| ==== menu DEST degli LFO: 66 voci invece di 33 (due id da 16 bit per parola della lista dell'OS) ============
        .equ    DEST_STOCK,     0x4022B390      | righe stock: 46 x 33 id (45 machine, poi la FX track)
        .equ    TYPE_OF,        0x400A5CE4      | gruppo (tipo) di un id: il ciclo del menu e le etichette
        .equ    MENU_EXIT,      0x4004E672      | fine del ciclo che crea le voci del menu

| ---- avvio (da ids_boot): righe impacchettate = voci stock, ognuna seguita dalle voci DESTX registrate dopo di lei
        .globl  ids_dest_boot
ids_dest_boot:
        lea     -24(%sp),%sp
        movem.l %d2-%d5/%a2-%a3,(%sp)
        lea     DEST_STOCK,%a0
        lea     ROWS,%a1
        moveq   #0,%d2                          | riga (machine)
1:      movea.l %a1,%a3                         | inizio della riga
        moveq   #0,%d3                          | voce stock
2:      move.l  (%a0)+,%d0
        move.w  %d0,(%a1)+
        lea     DESTX,%a2                       | voci registrate dopo questa
        moveq   #DESTX_N,%d4
3:      mvz.w   2(%a2),%d0                      | id (0 = vuota)
        beq.s   4f
        mvz.b   (%a2),%d1
        cmp.l   %d2,%d1
        bne.s   4f
        mvz.b   1(%a2),%d1
        cmp.l   %d3,%d1
        bne.s   4f
        move.l  %a1,%d5                         | posto nella riga (al massimo DEST_N - 1 voci)
        sub.l   %a3,%d5
        cmpi.l  #2*(DEST_N-1),%d5
        bcc.s   4f
        move.w  %d0,(%a1)+
4:      addq.l  #4,%a2
        subq.l  #1,%d4
        bne.s   3b
        addq.l  #1,%d3
        moveq   #33,%d0
        cmp.l   %d3,%d0
        bne.s   2b
        lea     2*DEST_N(%a3),%a2               | resto della riga: fine
5:      cmpa.l  %a2,%a1
        bcc.s   6f
        move.w  #-1,(%a1)+
        bra.s   5b
6:      addq.l  #1,%d2
        moveq   #DEST_ROWS,%d0
        cmp.l   %d2,%d0
        bne.s   1b
        movem.l (%sp),%d2-%d5/%a2-%a3
        lea     24(%sp),%sp
        rts

| ---- 0x400A6598: riga della machine 4(sp) nella lista a0 (0x84 B, ora 66 id da 16 bit); d0 = a0
        .globl  ids_destcopy
ids_destcopy:
        move.l  4(%sp),%d1
        moveq   #0x2C,%d0
        cmp.l   %d1,%d0
        bcc.s   1f
        moveq   #0x22,%d1                       | come l'OS: machine sconosciuta -> riga vuota
1:      mulu.w  #2*DEST_N,%d1
        lea     ROWS,%a1
        adda.l  %d1,%a1
        move.l  %a0,%d0
        moveq   #DEST_N/2,%d1
2:      move.l  (%a1)+,(%a0)+
        subq.l  #1,%d1
        bne.s   2b
        rts

| ---- 0x400A65D2: (voce 4(sp), machine 8(sp), tipo 12(sp)) -> id interno della voce, -1 se non c'e'
        .globl  ids_destiid
ids_destiid:
        move.l  12(%sp),%d0
        moveq   #12,%d1
        cmp.l   %d0,%d1
        bcs.s   9f
        beq.s   1f
        move.l  8(%sp),%d1
        moveq   #0x2C,%d0
        cmp.l   %d1,%d0
        bcs.s   9f
        bra.s   2f
1:      moveq   #0x2D,%d1                       | FX track
2:      move.l  4(%sp),%d0
        cmpi.l  #DEST_N-1,%d0
        bhi.s   9f
        mulu.w  #2*DEST_N,%d1
        lea     ROWS,%a0
        adda.l  %d1,%a0
        mvz.w   (%a0,%d0.l*2),%d1
        cmpi.l  #0xFFFF,%d1
        beq.s   9f
        cmpi.l  #N,%d1
        bcs.s   3f
        moveq   #0,%d1
3:      mulu.w  #52,%d1
        lea     TABLE,%a0
        move.l  4(%a0,%d1.l),%d0
        rts
9:      moveq   #-1,%d0
        rts

| ---- 0x4004E55E, ciclo delle voci del menu (al posto di lea TYPE_OF,a3 ; move.l (a0)+,-$310(a6)): la voce dalla
| lista impacchettata; alla fine della riga esce dal ciclo
        .globl  ids_destnext
ids_destnext:
        lea     ids_dest_type,%a3
        mvz.w   (%a0)+,%d0
        cmpi.l  #0xFFFF,%d0
        beq.s   1f
        move.l  %d0,-0x310(%a6)
        rts
1:      addq.l  #4,%sp
        jmp     MENU_EXIT

| ---- 0x4004E8A8 (al posto di move.l 4(a2,d0.l*4),-(sp) ; jsr TYPE_OF): la voce d0 della closure a2
        .globl  ids_dest_e8a8
ids_dest_e8a8:
        movea.l (%sp)+,%a1
        mvz.w   4(%a2,%d0.l*2),%d0
        move.l  %d0,-(%sp)
        move.l  %a1,-(%sp)
        bra.w   ids_dest_type

| ---- 0x4004EC0A (al posto di lea (a6,d0.l*4),a0 ; move.l -$84(a0),-(sp) ; jsr TYPE_OF): la voce d0 della lista
        .globl  ids_dest_ec0a
ids_dest_ec0a:
        movea.l (%sp)+,%a1
        lea     0(%a6,%d0.l*2),%a0
        mvz.w   -0x84(%a0),%d0
        move.l  %d0,-(%sp)
        move.l  %a1,-(%sp)
        bra.w   ids_dest_type

| ---- istruzione per 0x4004E090 (closure del testo della voce): mvz.w 4(a3,d0.l*2),d4 al posto di move.l
        .globl  ids_op_e090
ids_op_e090:
        mvz.w   4(%a3,%d0.l*2),%d4

| ---- 0x4004E542 (al posto di jsr TYPE_OF): gruppo iniziale del ciclo dalla prima voce da 16 bit (l'OS passa la
| prima parola lunga, che ora contiene due id: senza questo il menu si apriva con un gruppo ERR)
        .globl  ids_dest_first
ids_dest_first:
        move.l  4(%sp),%d0
        swap    %d0
        ext.l   %d0                             | 0xFFFF (riga vuota) -> -1, come l'OS
        move.l  %d0,4(%sp)
        bra.w   ids_dest_type

| ---- 0x400A5CE4 (jmp, tutto l'OS): gruppo di un id. Come l'OS (id oltre la tabella: quello dell'id 0); un id delle
| mod senza gruppo (descrittore +0 = -1, es. SY FM4 521..528, fuori dalle tabelle per machine dell'OS) prende la
| machine della sua voce DESTX: nel menu DEST e nella lista della manopola DEST (ordinata per gruppo, 0x4001427C)
| sta con la sua machine invece che sotto ERR
        .globl  ids_dest_type
ids_dest_type:
        move.l  4(%sp),%d1
        cmpi.l  #N,%d1
        bcs.s   1f
        moveq   #0,%d1
1:      move.l  %d1,%d0
        mulu.w  #52,%d0
        lea     TABLE,%a0
        move.l  (%a0,%d0.l),%d0
        cmpi.l  #FIRST,%d1
        bcs.s   9f
        cmpi.l  #-1,%d0
        bne.s   9f
        bsr.s   ids_destx_find
        beq.s   8f
        mvz.b   (%a0),%d0                       | la machine della voce
        rts
8:      moveq   #-1,%d0
9:      rts

| id d1 tra le voci DESTX? Z = 0 e a0 = la voce se c'e'; usa d0/a0
ids_destx_find:
        lea     DESTX,%a0
        moveq   #DESTX_N,%d0
1:      cmp.w   2(%a0),%d1
        beq.s   2f
        addq.l  #4,%a0
        subq.l  #1,%d0
        bne.s   1b
        rts                                     | Z = 1: non c'e'
2:      moveq   #1,%d0                          | Z = 0
        rts

| ---- 0x4001476E (lea dell'OS 0x400A66E2 nella lista della manopola DEST, 0x4001471C, filtro coi flag del
| descrittore +24): come l'OS per i suoi id. Un id delle mod passa (come un parametro di machine, 0xE00) solo se
| e' una voce DESTX della machine della traccia: a5 = il modello della traccia (SoundParameterSet, come in
| 0x40011F6C: Sound = vt[0x28] dell'oggetto a +16, machine = Sound +0xA2), o della FX track (machine 45). Gli
| altri no: LFO3 530..537 (flag di LFO1: sotto LFO2 in testa, sotto ERR) e SY FM4 sulle tracce di altre machine.
        .equ    DESC_FLAGS,     0x400A66E2
        .globl  ids_dest_flags
ids_dest_flags:
        move.l  4(%sp),%d1
        cmpi.l  #FIRST,%d1
        bcs.s   9f
        cmpi.l  #N,%d1
        bcc.s   9f
        moveq   #-1,%d0                         | machine della traccia: -1 = da leggere
        move.l  %d0,-(%sp)
        lea     DESTX,%a0
1:      cmp.w   2(%a0),%d1
        bne.s   4f
        mvz.b   (%a0),%d0
        cmpi.l  #45,%d0                         | FX track: i suoi id ci sono solo li'
        beq.s   6f
        tst.l   (%sp)
        bpl.s   3f
        lea     -8(%sp),%sp                     | legge la machine una volta
        movem.l %d1/%a0,(%sp)
        bsr.s   track_machine
        move.l  %d0,8(%sp)
        movem.l (%sp),%d1/%a0
        lea     8(%sp),%sp
3:      mvz.b   (%a0),%d0
        cmp.l   (%sp),%d0
        beq.s   6f
4:      addq.l  #4,%a0
        cmpa.l  #DESTX+4*DESTX_N,%a0
        bcs.s   1b
        addq.l  #4,%sp
        moveq   #0,%d0
        rts
6:      addq.l  #4,%sp
        move.l  #0xE00,%d0
        rts
9:      jmp     DESC_FLAGS

| machine della traccia del modello in a5 (Sound +0xA2, 0..255), 256 se non si legge
track_machine:
        move.l  #256,%d0
        move.l  %a5,%d1
        beq.s   9f
        movea.l 16(%a5),%a0
        move.l  %a0,%d1
        beq.s   9f
        movea.l (%a0),%a1
        move.l  %a0,-(%sp)
        movea.l 40(%a1),%a1
        jsr     (%a1)
        addq.l  #4,%sp
        tst.l   %d0
        beq.s   8f
        movea.l %d0,%a0
        mvz.b   162(%a0),%d0
        rts
8:      move.l  #256,%d0
9:      rts
