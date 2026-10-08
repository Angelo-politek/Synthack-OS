# splash — "SyntHack v0.1" dopo l'animazione d'avvio

Dopo l'animazione ufficiale (qualunque delle 5, scelta a caso dall'OS) mostra per ~2 s il logo
**SyntHack** in ASCII art (figlet *smslant*) con la versione **v0.1**.

**Come funziona** (analisi in `docs/re-journal.md`, 2026-10-08):
- il task dell'intro esegue elenchi di segmenti `{funzione, n. fotogrammi}` e a ogni fotogramma
  chiama `funzione(fotogramma, totale, Bitmap*)`;
- `splash.S` definisce `splash_draw`, che copia il logo (1024 B, formato a colonne) nel framebuffer;
- `make_patch.py` mette codice, logo e 5 elenchi nuovi `{originale, splash_draw ×120, fine}` nel
  riempimento libero `0x40338740–0x40338BD8` e reindirizza le 5 istruzioni `pea` che scelgono l'elenco.

**Verifiche:** `tests/test_splash_mod.py` esegue `splash_draw` in Unicorn e confronta il
framebuffer con il design; il build controlla le impronte dei byte originali.

- Sezione: 3 · Rischio: basso (solo avvio; recupero via MIDI DIN provato)
- Rigenerare la patch: `python mods/splash/make_patch.py` (servono i binutils m68k in WSL)
- Build: `python tools/build/build.py --stock firmware/Syntakt_OS1.41.syx mods/splash -o out/build/synthack_0.1.syx`
- Durata: `SPLASH_FRAMES` in `make_patch.py` (120 fotogrammi, ~2 s se l'intro va a ~60 fps: da verificare)
