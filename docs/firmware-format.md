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

## Sezioni di Syntakt OS 1.41 (etichette di elektron-firmware-tool)

Ordine fisico nel container: 5, 2, 1, 3, 4, 6, 7, 8. Dimensioni = byte decompressi.

| id | etichetta | dimensione | compressa | contenuto ipotizzato | noi |
|---|---|---:|---|---|---|
| 1 | FPGA | 149 516 | sì | bitstream FPGA (formato non Xilinx standard 🟡) | non toccare |
| 2 | bootstrap | 30 782 | sì | menu di avvio / OS upgrade (ColdFire) ✅ | **MAI toccare** |
| 3 | MAIN OS | 3 438 480 | sì | OS principale + mixer/FX (🟡), ColdFire #1, a `0x40000400` ✅ | patch UI/sequencer/master |
| 4 | updater | 32 776 | no | ? | non toccare |
| 5 | meta | 15 | no | timestamp di build (ASCII) ✅ | non toccare |
| 6 | boot | 1 744 | no | stub ColdFire | **MAI toccare** |
| 7 | blob | 383 760 | **no** | codice ColdFire senza stringhe → motore audio (🟡), a `0x40000400` ✅ | patch DSP (voci/machine) |
| 8 | (nessuna) | 159 948 | sì | inizia con `FF…`: seconda FPGA? 🟡 | non toccare |

Il wrapper salva la sezione 8 come `section_8_unknown.bin`.

## Round-trip

- **Byte-esatto** (`-r`): le sezioni vengono copiate così come sono, senza ricompressione.
  L'output deve essere identico all'input: dimostra che la catena di lettura/scrittura del
  container non perde nulla.
- **Semantico** (`-c`): una sezione viene decompressa e ricompressa. I byte compressi
  possono cambiare (la stessa sezione si può comprimere in più modi validi), ma una volta
  decompressa deve tornare identica. Questa è la situazione reale delle nostre patch.
