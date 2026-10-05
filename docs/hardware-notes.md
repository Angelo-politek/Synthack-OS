# Note hardware Syntakt

Tutto ciò che segue viene dalla community di reverse engineering, **non da Elektron**:
sono ipotesi di lavoro da validare (🟡) finché non le verifichiamo noi (✅).

| Componente | Ipotesi | Stato |
|---|---|---|
| CPU | due **NXP ColdFire**: #1 per OS/UI/sequencer **+ mixer/FX/uscita**, #2 come motore delle voci | 🟡 |
| Modello CPU | probabilmente **MCF5441x** (ColdFire V4m, **con EMAC, senza FPU**), per analogia con Digitone mk1/Model:Cycles | 🟡 |
| Caratteristiche MCF5441x (data sheet NXP MCF54418 Rev. 8) | core ColdFire V4 **con EMAC e MMU, nessuna FPU**; fino a **250 MHz**; **64 KB di SRAM interna**; eDMA a **64 canali**; controller DDR2; 2 SSI (interfacce audio seriali). Tutto coerente con il codice visto (DMA ch.47, dati in SRAM a `0x80000000` per 59 440 B < 64 KB). Ancora nessuna prova diretta che il chip sia proprio questo | 🟡 |
| Budget CPU #2 (se 250 MHz) | un blocco = 32 campioni a 48 kHz = 0,667 ms → **~166 000 cicli per blocco** per 8 voci e tutta l'elaborazione | 🟡 |
| Memoria CPU #2 | codice a `0x40000400`; dati copiati all'avvio in SRAM a `0x80000000` (vedi [emulation.md](emulation.md)) | 🟡/✅ |
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
