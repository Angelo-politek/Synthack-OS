# Emulazione del motore audio (sezione 7) — proposta

Stato: **proposta**, nessun codice ancora. Basata su una ricerca dell'ottobre 2026 sui progetti
della community (solo lettura; dettagli e date in [re-journal.md](re-journal.md)).

## Perché ci serve

L'emulatore è il nostro banco prova, come una simulazione SPICE prima di montare la scheda:
eseguiamo il codice della CPU #2 sul PC, gli diamo note e parametri, registriamo l'audio in un
`.wav`, e confrontiamo originale e versione modificata, senza mai rischiare la macchina.

## Cosa esiste già

| Progetto | Licenza | Cosa fa | Uso per noi |
|---|---|---|---|
| `18nelli18/Modded-Cycles` | **nessuna** (tutti i diritti riservati) | fa girare la **sezione 7 della Syntakt** in Unicorn, chiamando direttamente la funzione di rendering delle voci; produce WAV | **solo i fatti** (indirizzi, layout), non il codice |
| `irpina/digiemu` | GPL-2.0-or-later | emulatore completo Digitone mk1, incluso il secondo ColdFire; Unicorn patchato (EMAC) | dipendenza esterna installata a parte; documentazione |
| `m-dwyer/digikit` | GPL-2.0-or-later | solo CPU principale di DT2/DN2, niente audio | poco utile |
| `Bezronczek/syntakt-firmware-workbench` | MIT | patch alle wavetable della sezione 7; nessun emulatore | costanti riusabili citando la fonte |

Alternative generiche scartate: **QEMU** (nessun modello di ColdFire MCF5441x, il `cfv4e` ha
difetti) e **Musashi** (non supporta ColdFire). **Unicorn** (motore di emulazione CPU basato su
QEMU, usabile da Python) è l'unica strada pratica, **a patto di correggere l'EMAC**.

### Il problema EMAC

L'**EMAC** è l'unità multiply-accumulate del ColdFire, l'equivalente di un piccolo DSP dentro la
CPU, ed è ciò che il motore audio usa per i filtri e gli oscillatori. Unicorn "di serie" la
emula male in modalità frazionaria con segno: secondo digiemu, l'audio risulta muto. Due
soluzioni note: le patch di digiemu a Unicorn (GPL, da installare a parte) oppure intercettare
le istruzioni MAC e rieseguirle in Python (la soluzione di Modded-Cycles).

## Fatti tecnici raccolti (🟡 = da fonti esterne, ✅ = verificato da noi)

- ✅ Sezione 7 di OS 1.41: 383 760 B, SHA-256 `daf6451c…ec783bc2`, uguale a quella del workbench.
- ✅ Caricamento a `0x40000400`, entry `0x40001070` (nostro test statistico + Modded-Cycles).
- ✅ Fine della sezione = `0x4005DF10`, che coincide con la fine dell'area copiata in SRAM da Modded-Cycles.
- 🟡 All'avvio i dati in `0x4004F6E0..0x40057670` vanno copiati in SRAM a `0x80000000`, e
  `0x40057670..0x4005DF10` a `0x80008000`.
- 🟡 Funzione di rendering: `0x40004324(out, params, trig_mask, release_mask)`, con `MACSR = 0xA0`;
  8 voci, ciascuna produce blocchi mono di 32 campioni int32 in **Q31** (formato a virgola
  fissa: un intero a 32 bit che rappresenta un numero tra -1 e +1) a 48 kHz.
- 🟡 Inizializzazione voci: `0x40002544` (prep), `0x40003EE0` (reset).
- 🟡 La sezione 7 **non fa il mix**: per analogia con il Digitone mk1, mixer, effetti e uscita
  sono sulla CPU #1 (sezione 3). → **Il master compressor (§9 del brief) andrà agganciato nella
  sezione 3, non nella 7.**

## Proposta

Scriviamo un **harness minimo nostro** (`tools/emu/`, MIT), in Python su Unicorn installato da
pip, che **reimplementa i fatti** documentati sopra senza copiare codice altrui.

1. **Conferma in Ghidra** degli indirizzi chiave (`0x40001070`, `0x40004324`, tabelle a
   `0x400148F0/0x40014920/0x40014950`). Prima di scrivere codice.
2. **`tools/emu/st_engine.py`:**
   - mappa di memoria, copia dei dati in SRAM e inizializzazione delle voci;
   - una funzione `render_block()` che esegue la funzione di rendering e scrive WAV;
   - EMAC: intercettore nostro, scritto dal manuale NXP del ColdFire.
3. **Test "golden".** Una machine con i parametri di default e la nota 60: il nostro output deve
   coincidere bit per bit con quello di Modded-Cycles, lanciato come processo separato e usato
   solo come riferimento di confronto ("oracolo").

## Limiti da tenere presenti

- È un harness **a livello di funzione**: niente interrupt, handshake tra CPU o timing reale.
  Unicorn non conta i cicli: come stima del costo possiamo contare le istruzioni eseguite.
- Le voci analogiche della Syntakt non sono emulabili.
- Il layout dei parametri (142 B per traccia) è decodificato solo in parte.

## Contributi a monte da proporre

- Issue su Modded-Cycles per chiedere una licenza esplicita (il README dice che il progetto si
  basa su lavoro "all MIT licensed", ma il repo non ha un file LICENSE).
- Core Syntakt per elekloader (GPL), quando avremo la prima mod.
