| Splash SyntHack — segmento di animazione d'avvio (ColdFire, sezione 3, OS 1.41)
|
| Il task dell'intro della Syntakt chiama, per ogni fotogramma, ogni segmento come:
|     funzione(fotogramma, totale_fotogrammi, Bitmap *bm)
| dove bm->data (offset +16) e' il framebuffer 128x64 a 1 bit (1024 B, per colonne).
| Questo segmento copia ogni volta il nostro logo (gia' nel formato giusto) nel framebuffer.
|
| Usa solo i registri "scratch" della convenzione di chiamata (d0, a0, a1): nessun salvataggio.

        .text
        .globl  splash_draw
splash_draw:
        move.l  12(%sp),%a0             | a0 = Bitmap *bm (terzo argomento)
        move.l  16(%a0),%a1             | a1 = bm->data, il framebuffer di questo fotogramma
        lea     logo(%pc),%a0           | a0 = il nostro logo (subito dopo il codice)
        moveq   #63,%d0                 | 64 giri x 16 byte = 1024 byte
1:      move.l  (%a0)+,(%a1)+
        move.l  (%a0)+,(%a1)+
        move.l  (%a0)+,(%a1)+
        move.l  (%a0)+,(%a1)+
        subq.l  #1,%d0
        bpl.s   1b
        rts

        .balign 4
logo:
        .incbin "logo.bin"              | generato da make_patch.py (tools/splash/render.py)
