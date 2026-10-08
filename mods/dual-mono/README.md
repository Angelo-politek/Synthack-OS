# dual-mono — INPUT L e INPUT R come due ingressi separati

Quando **SETTINGS → AUDIO ROUTING → EXTERNAL IN** è in modalità mono:
- **volume indipendente**: IN L regola solo INPUT L, IN R solo INPUT R (ciascuno con la legge
  di bilanciamento al centro, quindi stesso volume di oggi in stereo con BAL al centro);
- pagina **EXTERNAL MIXER**: riga 1 `IN L | IN R`, riga 2 `DEL | REV | — | FX` (mandate comuni).
In modalità stereo tutto resta **identico all'originale** (verificato bit per bit in emulazione).

**Come funziona** (analisi in `docs/re-journal.md`, 2026-10-08):
- trampolino al posto del blocco `0x40090872–0x400908F8` della funzione dei guadagni del mixer
  analogico: `jsr dm_hook ; bra.w 0x400908FC`;
- `dm_hook` (`dualmono.S`, a `0x40338BE0`) legge il flag globale EXTERNAL IN (`0x80003146`):
  stereo → trascrizione fedele del blocco; mono → due calcoli indipendenti (IN LR per L, BAL per R);
- interfaccia: riscrive la definizione della pagina MIX3 in RAM (`0x41B9F7F0`, solo se la
  riconosce) e i nomi brevi dei parametri 68/69/70 (`IN L`, `IN R`); in stereo li ripristina.

**Verifiche** (`tests/test_dual_mono.py`): stereo identico all'originale in 5 modalità EMAC e
centinaia di combinazioni; mono = originale con bilanciamento al centro per ciascun canale;
interfaccia commutata e ripristinata; nessuna modifica se la pagina non è quella attesa.

- Sezione: 3 · Spazio: `0x40338BE0–0x40338D42` (riempimento libero, dopo lo splash)
- Rigenerare: `python mods/dual-mono/make_patch.py` (binutils m68k in WSL)
- 🟡 Da verificare sulla macchina: come viene **visualizzato** il valore di IN R (BAL è bipolare:
  potrebbe apparire −64…+63 invece di 0…127)
