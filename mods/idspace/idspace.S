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
        rts

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
        move.l  4(%sp),%d0
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
