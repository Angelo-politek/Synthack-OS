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
| Aggiornamento della Syntakt a 1.41 (USB) | ⬜ | hardware, utente |
| **Prova di recupero via MIDI DIN** | ⬜ | **prerequisito di qualunque flash modificato** |
| Harness di emulazione sezione 7 | ✅ | [emulation.md](emulation.md): avvio, blocchi audio, EMAC, WAV |
| Survey dei 12 engine (ID machine ↔ nome) | 🔄 | `cli.py survey`, da ascoltare |
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

## Fase 1 — Primo mod reale

| Mod | Stato | Sezione | Emulabile | Note / prerequisiti |
|---|---|---|---|---|
| **Input dual mono** (routing "external in" + UI) | ⬜ | 3 🟡 | no | analisi del routing dell'ingresso esterno in sezione 3 (indizi: stringhe `EXT_IN_L/R`, ritorni ADC); test su hardware con recupero già provato |

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
| Resampling verso Twinshot | ⬜ | 3 🟡 + 7 🟡 | parziale | SP TWINSHOT è tra le machine; da capire dove vivono i sample |
| UI euclidea a cerchi | ⬜ | 3 | no | display e interfaccia |
| SY SWARM+ | ⬜ | 7 🟡 | sì | se SY SWARM è uno dei 12 engine della sez. 7 (da confermare col survey) |

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
