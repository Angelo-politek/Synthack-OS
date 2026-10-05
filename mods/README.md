# mods/

Una cartella per mod (`mods/<nome>/`), ognuna indipendente e attivabile. Ancora vuota:
nessuna mod si scrive finché la Fase 0 (round-trip, emulazione, recovery) non è completa.

Struttura prevista per ogni mod (da definire con la prima, `dual-mono`):

```
mods/<nome>/
  README.md        cosa fa, rischi, costo stimato CPU/RAM, sezioni toccate
  patch.json       tabella di patch (offset, hash atteso della regione, byte nuovi nostri)
  src/             eventuale codice C/asm nostro
  tests/           test in emulazione
```
