# Roadmap e lista delle mod

Fonte delle feature: il brief ([CLAUDE.md §8–12](../CLAUDE.md)). Questo file aggiunge lo **stato** e
quello che abbiamo scoperto lavorando. Va aggiornato a ogni passo concluso.

**Stato:** ✅ fatto · 🔄 in corso · ⏸️ in pausa · ⬜ da fare
**Sezione:** dove vive la modifica nel firmware (3 = OS/UI/sequencer/mixer su CPU #1, 7 = motore
delle voci su CPU #2). 🟡 = ipotesi da verificare.
**Emulabile:** se possiamo provarla nell'emulatore prima di flashare (oggi copriamo solo la sezione 7).

## Fase 0 — Fondamenta

| Voce | Stato | Note |
|---|---|---|
| Scaffold repo, docs sicurezza/legali | ✅ | [recovery.md](recovery.md), [legal.md](legal.md) |
| Wrapper unpack/repack + round-trip su OS 1.41 | ✅ | `tools/unpack/eft.py`, byte-esatto e semantico |
| Procedura di recupero verificata sul manuale | ✅ | manuale OS 1.30 §15.4 |
| Aggiornamento della Syntakt a 1.41 (USB) | ✅ | 2026-10-08 |
| **Prova di recupero via MIDI DIN** | ✅ | 2026-10-08, UMC404HD + Transfer: riuscita (lenta) → i flash di mod sono sbloccati |
| Harness di emulazione sezione 7 | ✅ | [emulation.md](emulation.md): avvio, blocchi audio, EMAC, WAV |
| Survey dei 12 engine (ID machine ↔ nome) | ✅ | 12 engine identificati (BD MODERN … CP VINTAGE, SY TOY, SY BITS, SY SWARM, SP TWINSHOT); SY CHORD confermato all'ascolto |
| Mappa sezione 7 in Ghidra | 🔄 | main, interrupt, tabelle engine, contratto CPU #1 ↔ CPU #2 |
| Mappa sezione 3 in Ghidra | 🔄 | appena iniziata: prelievo blocchi audio vicino a `0x400A4798`, stringhe di routing |

## Infrastruttura comune alle mod

| Voce | Stato | Serve per |
|---|---|---|
| Formato patch `mods/<nome>/patch.json` (indirizzo, hash atteso, dati nuovi) | ✅ | tutte le mod |
| `tools/build/build.py`: OS stock + mod → `.syx` verificato (mai sezioni 2/6) | ✅ | tutte le mod |
| Cross-compiler ColdFire (WSL) + linker script | ⬜ | mod con codice nuovo |
| Spazio libero in memoria per il nostro codice (sez. 3 e 7) | ⬜ | mod con codice nuovo |
| Test A/B in emulazione (stock vs modificato) | ⬜ | mod nella sezione 7 |

## Mod di collaudo e identità

| Mod | Stato | Sezione | Emulabile | Note |
|---|---|---|---|---|
| **Mod zero**: cambio di un testo nel menu (stessa lunghezza) | ✅ 2026-10-08 | 3 | non serve | collauda la catena build → `.syx` → flash: sezione 3 ricompressa + MAC ricalcolato accettati dalla macchina |
| **Splash "SyntHack 0.1"** dopo l'intro ufficiale, logo in ASCII art (figlet *smslant*) | ✅ 2026-10-08 (v2) | 3 | ✅ `splash_draw` eseguita in Unicorn, framebuffer = design | 5 elenchi di animazione nuovi {originale accorciata di 57 fotogrammi, splash ×57, fine}: durata dell'avvio invariata (la v0.1, più lunga di ~4 s, bloccava su "PREPARING SAMPLES"); logo con righe invertite nel riempimento libero `0x40338740`; reindirizzate le 5 `pea` del task dell'intro. Diventa la firma di versione delle build |

## Fase 1 — Primo mod reale

| Mod | Stato | Sezione | Emulabile | Note / prerequisiti |
|---|---|---|---|---|
| **Input dual mono v1**: in modalità EXT IN "mono", **IN L e IN R** affiancati sulla pagina EXTERNAL MIXER | 🔄 analisi | 3 | solo le funzioni modificate, isolate | Oggi la pagina ha in riga 1 `IN LR` + 3 posti vuoti, in riga 2 `DEL REV PAN FX`. In mono: riga 1 `IN L | IN R`, riga 2 `DEL REV — FX` (mandate comuni). IN L = valore di IN LR, **IN R = valore di PAN/BAL** (in mono il bilanciamento non serve) → nessun dato nuovo da salvare; effetto collaterale: tornando in stereo il PAN riparte dal valore di IN R. Hardware: 2 VCA `extin_left` (CV 4) / `extin_right` (CV 9). Pan per ingresso non possibile (2 VCA) |
| Input dual mono **v2** (ideale): **due pagine** IN L e IN R, ciascuna con le sue mandate; la seconda compare solo in modalità mono | ⬜ | 3 🟡 | solo funzioni isolate | richiede: mandate FX dell'ingresso calcolate in software (da verificare), una pagina nuova nel sistema dei menu, salvataggio dei nuovi parametri nei dati del pattern/kit |

## Fase 2 — Loudness e basi

| Mod | Stato | Sezione | Emulabile | Note / prerequisiti |
|---|---|---|---|---|
| Master compressor/limiter (Q31) | ⬜ | 3 | solo l'algoritmo, da solo | la sez. 7 non mixa: mixer/FX/uscita sono sulla CPU #1. Indizi di ADC che ridigitalizzano (ritorni pre/post FX) → verificare cosa copre il "master" (brief §9) |
| Wavetable custom in SY CHORD | ⏸️ | 7 | sì | in pausa per scelta. Engine 5 legge una wavetable 512×int32 a `0x4001A300`; coordinarsi con syntakt-firmware-workbench |
| Nuove forme di LFO | ⬜ | 3 🟡 | no | il workbench patcha l'LFO nella sezione 3 |

## Fase 3 — FX e performance

| Mod | Stato | Sezione | Emulabile | Note |
|---|---|---|---|---|
| Suite Master FX | ⬜ | 3 🟡 | solo l'algoritmo | come il compressor |
| Beat-repeat / performance FX | ⬜ | 3 🟡 | no | legato a sequencer e buffer audio |
| Arpeggiatore | ⬜ | 3 | no | sequencer |
| Resampling verso Twinshot | ⬜ | 3 🟡 + 7 | parziale | SP TWINSHOT = engine 11 (ID 44) della sez. 7; i campioni arrivano probabilmente col comando 2 (blocchi da 2 KB) |
| UI euclidea a cerchi | ⬜ | 3 | no | display e interfaccia |
| SY SWARM+ | ⬜ | 7 | sì | SY SWARM = engine 10 (ID 38) della sezione 7 ✅ |

## Fase 4 — Avanzate e sperimentali

| Mod | Stato | Sezione | Emulabile | Note |
|---|---|---|---|---|
| Sampler avanzato (slice, loop, sample lunghi, granulare) | ⬜ | 3 + 7 🟡 | parziale | riferimento: Model-TG |
| Machine RISER / DOWNFILTER | ⬜ | 7 + 3 | il motore sì | nuovo engine (come SD VINTAGE in Modded-Cycles) + sincronia col sequencer (brief §10) |
| Terzo LFO / mod matrix | ⬜ | 3 | no | |
| Polifonia a prestito tra tracce digitali | ⬜ | 3 + 7 | parziale | le 8 voci digitali sono della CPU #2 |

## Trasversali

| Voce | Stato | Note |
|---|---|---|
| Web builder (brief §11) | ⬜ | parte quando esistono formato patch e `build.py`; valutare il core Syntakt per elekloader (GPL) |
| AI machine creator (brief §12) | ⬜ | parte dopo almeno un engine custom funzionante nell'emulatore |
