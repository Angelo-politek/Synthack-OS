# Note legali e regole di pubblicazione

> **Non è consulenza legale.** Sono le regole che il progetto si dà per restare dalla parte
> giusta. In caso di dubbi concreti, chiedi a un professionista.

## Non affiliazione

Syntakt+ è un progetto indipendente, **non affiliato, approvato o supportato da Elektron
Music Machines**. "Elektron", "Syntakt", "Digitakt", "Digitone" e gli altri nomi sono
marchi dei rispettivi titolari e qui servono solo a indicare con quale prodotto il progetto
è compatibile.

## Cosa NON pubblichiamo mai

- **Nessun byte del firmware Elektron**: niente `.syx` né sezioni estratte, decompresse
  o disassemblate, nemmeno "solo un pezzetto".
- **Nessun output di decompilatore copiato** dal firmware dentro il nostro codice.
- **Nessuna chiave**: il MAC dell'immagine viene ricalcolato a runtime dal tool, a partire
  dall'immagine fornita dall'utente.

Come lo garantiamo:

1. `.gitignore` esclude `*.syx`, `*.bin`, `firmware/`, gli output di unpack e i progetti Ghidra.
2. L'hook `tools/hooks/pre-commit` rifiuta i file che contengono firme da firmware
   Elektron e i blob binari grandi. Va attivato una volta per clone:
   `git config core.hooksPath tools/hooks`.

## Cosa pubblichiamo

- Codice scritto da noi (Python, C, web), sotto licenza **MIT**.
- **Tabelle di patch** che descrivono *dove* applicare una modifica (offset, valore atteso
  prima, valore nuovo). I byte "nuovi" devono essere nostri, cioè codice nostro compilato o
  costanti nostre. Il "valore atteso prima" deve essere il più corto possibile e serve solo a
  verificare che la patch vada sulla versione giusta: dove si può, al suo posto
  usiamo un **hash**.
- Documentazione e note di reverse engineering espresse con parole nostre (fatti di
  compatibilità: offset, formati, convenzioni di chiamata).

## Base giuridica: interoperabilità

Le analisi servono a ottenere le informazioni necessarie per far funzionare **programmi
creati in modo indipendente** (le nostre mod) insieme al firmware della macchina che
l'utente possiede legittimamente.

- Direttiva 2009/24/CE, artt. 5 e 6 (analisi del funzionamento e decompilazione per
  interoperabilità).
- L. 633/1941, artt. 64-ter e 64-quater.

Regole pratiche che ne derivano:

- Analizziamo **solo** ciò che serve per l'interoperabilità delle mod.
- Le informazioni ottenute non le usiamo per creare un prodotto concorrente né
  le diffondiamo oltre quanto serve all'interoperabilità.
- Teniamo un **registro delle analisi** in [re-journal.md](re-journal.md): cosa, quando,
  perché.

## Licenze di terze parti

| Progetto | Licenza | Come lo usiamo | Conseguenza |
|---|---|---|---|
| `mischa85/elektron-firmware-tool` | MIT | clonato e compilato in locale (`third_party/`), invocato come programma esterno | compatibile con MIT |
| `irpina/elekloader` | **GPL-2.0-or-later** | per ora solo studio | se copiamo codice o contribuiamo un "core Syntakt" a monte, **quel** codice è GPL. Va deciso consapevolmente, caso per caso |
| `irpina/digiemu`, `m-dwyer/digikit` | **GPL-2.0-or-later** | studio; eventuale Unicorn patchato installato a parte dall'utente | mai copiati nel repo; solo come processo/pacchetto esterno |
| `18nelli18/Modded-Cycles` | **nessuna licenza** (= tutti i diritti riservati) | studio; output usato come riferimento di confronto nei test | riusiamo solo **fatti** (indirizzi, layout), mai codice. Chiedere una licenza via issue |
| `Bezronczek/syntakt-firmware-workbench` | MIT | costanti (offset, hash) | riusabili citando la fonte |
| `DigiAlchemydsp/Tone-FX` | da verificare | studio | — |
| Unicorn engine | GPL-2.0 | dipendenza installata via pip, non inclusa | il nostro sorgente MIT che la importa resta pubblicabile; un eventuale binario unico distribuito ricadrebbe sotto GPL |
| `TinyGregAudio/Model-TG` | MIT | studio/riferimento | compatibile |

Chiamare un programma GPL come processo separato (riga di comando) non rende GPL il nostro
codice. Copiare o linkare il suo codice sì.

## Dove pubblichiamo

- **GitHub**: repo principale.
- Eventualmente **Elektronmods**.
- **Non** su Elektronauts: il forum vieta mod, tool e istruzioni di questo tipo
  (regola segnalata dall'utente, in vigore dal 16/09/2026).
- **Nessuna vendita**, né delle mod né di `.syx` già pronti. Ogni utente costruisce il
  proprio `.syx` partendo dal proprio OS stock.
