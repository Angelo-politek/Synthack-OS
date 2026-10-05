# Formato del firmware `.syx` (Syntakt)

Pagina di sintesi. Le scoperte, con data e fonte, vanno in [re-journal.md](re-journal.md);
qui teniamo solo lo stato attuale.

Legenda: ✅ verificato da noi · 🟡 fonte esterna / ipotesi

## Strati

Un `.syx` è una "matrioska" di tre strati:

1. **Trasporto SysEx** — il file è una sequenza di messaggi MIDI SysEx (`F0 … F7`). Il
   MIDI trasporta solo byte a 7 bit, quindi i dati a 8 bit sono "impacchettati" e ogni
   pacchetto ha il suo checksum. 🟡
2. **Container ELE3** — dentro i SysEx c'è un container con un header (modello, versione),
   una tabella delle sezioni e, in coda, un **digest HMAC-SHA256** su tutto. 🟡
   La chiave HMAC si ricava dall'immagine stessa: non c'è una firma asimmetrica, quindi
   chiunque abbia l'immagine può ricalcolare il MAC. `elektron-firmware-tool` lo fa per noi.
3. **Sezioni** — blocchi compressi con un algoritmo LZ77 in stile **aPLib**. aPLib è un
   compressore molto semplice, pensato per decomprimere velocemente su CPU piccole. 🟡

## Sezioni (etichette di elektron-firmware-tool)

| id | etichetta | contenuto ipotizzato | noi |
|---|---|---|---|
| 1 | FPGA | bitstream delle FPGA Spartan | non toccare |
| 2 | bootstrap | menu di avvio / OS upgrade (ColdFire) | **MAI toccare** |
| 3 | MAIN OS | OS principale, ColdFire #1, caricato a `0x40000000` 🟡 | patch UI/sequencer |
| 4 | updater | ? | non toccare |
| 5 | meta | ? | non toccare |
| 6 | boot | stub ColdFire ~1.5 kB | **MAI toccare** |
| 7 | blob | motore audio, ColdFire #2, caricato a `0x40000400` 🟡 | patch DSP |

Da verificare sul nostro 1.41: numero effettivo di sezioni (il brief dice 8), id, dimensioni.

## Round-trip

- **Byte-esatto** (`-r`): le sezioni vengono copiate così come sono, senza ricompressione.
  L'output deve essere identico all'input: dimostra che la catena di lettura/scrittura del
  container non perde nulla.
- **Semantico** (`-c`): una sezione viene decompressa e ricompressa. I byte compressi
  possono cambiare (la stessa sezione si può comprimere in più modi validi), ma una volta
  decompressa deve tornare identica. Questa è la situazione reale delle nostre patch.
