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
| Formato patch `mods/<nome>/patch.json` (indirizzo, hash atteso, dati nuovi) | ⬜ | tutte le mod |
| `tools/build/build.py`: OS stock + mod → `.syx` verificato (mai sezioni 2/6) | ⬜ | tutte le mod |
| Cross-compiler ColdFire (WSL) + linker script | ⬜ | mod con codice nuovo |
| Spazio libero in memoria per il nostro codice (sez. 3 e 7) | ⬜ | mod con codice nuovo |
| Test A/B in emulazione (stock vs modificato) | ⬜ | mod nella sezione 7 |

## Mod di collaudo e identità

| Mod | Stato | Sezione | Emulabile | Note |
|---|---|---|---|---|
| **Mod zero**: cambio di un testo nel menu (stessa lunghezza) | ⬜ | 3 | non serve | collauda la catena build → `.syx` → flash: sezione 3 ricompressa + MAC ricalcolato accettati dalla macchina |
| **Splash "SyntHack 0.1"** dopo l'intro ufficiale, logo in ASCII art | ⬜ | 3 | il disegno sì (funzioni isolate → PNG del framebuffer) | trampolino alla fine dell'intro (`intro/intro_dither.cpp`); usare le funzioni grafiche dell'OS; display 🟡 128×64 mono (~21×8 caratteri) → ASCII art compatta o "disegnata" come bitmap. Diventa la firma di versione delle build |

## Fase 1 — Primo mod reale

| Mod | Stato | Sezione | Emulabile | Note / prerequisiti |
|---|---|---|---|---|
| **Input dual mono v1**: L e R come due ingressi separati, con **volume indipendente** (+ pan se possibile) | 🔄 analisi | 3 | solo le funzioni modificate, isolate | ✅ volume L/R fattibile: l'hardware ha 2 VCA distinti (`extin_left` = CV 4, `extin_right` = CV 9) scritti dal software e inviati via SPI (DSPI1). ⚠️ pan per ingresso: probabilmente no nel percorso analogico (2 VCA in tutto, ne servirebbero 4). Prossimo: funzione che calcola i due guadagni da IN LR + BAL |
| Input dual mono **v2**: mandate separate L/R a delay e riverbero | ⬜ | 3 🟡 | solo funzioni isolate | fattibile solo se le mandate dell'ingresso sono calcolate in software (non FPGA/analogico); con v1 restano 1 manopola libera per DEL R/REV R → spostare PRE/POST nelle impostazioni o seconda pagina; salvataggio dei nuovi parametri nei dati del pattern/kit |

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
