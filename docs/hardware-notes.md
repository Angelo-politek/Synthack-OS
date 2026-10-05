# Note hardware Syntakt

Tutto ciò che segue viene dalla community di reverse engineering, **non da Elektron**:
sono ipotesi di lavoro da validare (🟡) finché non le verifichiamo noi (✅).

| Componente | Ipotesi | Stato |
|---|---|---|
| CPU | due **NXP ColdFire**: #1 per OS/UI/sequencer, #2 come motore audio | 🟡 |
| DSP | **nessuno SHARC** (a differenza di Digitakt II / Digitone II) → codice DT2/DN2 non portabile | 🟡 |
| Parentela | famiglia "ColdFire" come Digitakt/Digitone mk1 e Model:Cycles/Samples → codice di quelle macchine in principio studiabile | 🟡 |
| FPGA | due Xilinx Spartan | 🟡 |
| RAM | ~256 MB DDR2 | 🟡 |
| Storage | "+Drive" per progetti/suoni/sample | 🟡 |
| Codec audio | probabilmente Cirrus Logic | 🟡 |

## Cos'è un ColdFire (contesto)

ColdFire è una famiglia di microcontrollori Motorola/Freescale/NXP che deriva dal 68000
(m68k): stesso stile di istruzioni, ma un sottoinsieme semplificato. Per questo il
cross-compiler si chiama `m68k-…-gcc` e si sceglie il modello esatto con `-mcpu=…`.
Ghidra lo supporta come processore "68000 / ColdFire".

## Da scoprire (in ordine di utilità)

1. Modello esatto del ColdFire #2 (decide il flag `-mcpu`, la presenza della MAC/EMAC — un'unità
   di moltiplica-accumula utile per il DSP — e la FPU).
2. Come l'OS (ColdFire #1) passa parametri e audio al motore (ColdFire #2): memoria condivisa? FPGA?
3. Dove avviene la somma del mix: nel motore digitale o dopo, in analogico (decisivo per il master compressor).
