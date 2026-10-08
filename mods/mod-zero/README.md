# mod-zero — collaudo della catena build → flash

Cambia l'etichetta di menu **EXTERNAL IN** (SETTINGS → AUDIO ROUTING) in **SYNTHACK IN**.
Nessun effetto sul suono o sul comportamento.

**Scopo:** dimostrare che la Syntakt accetta un OS ricostruito da noi (sezione 3 ricompressa,
checksum e MAC ricalcolati, dimensione diversa dall'originale). Se dopo il flash vedi
"SYNTHACK IN" nel menu, l'intera catena funziona.

- Sezione toccata: 3 (11 byte di testo, 8 diversi)
- Rischio: minimo; recupero via MIDI DIN provato il 2026-10-08
- Build: `python tools/build/build.py --stock firmware/Syntakt_OS1.41.syx mods/mod-zero -o out/build/synthack_mod-zero.syx`
