"""Carico di ogni mod per l'indicatore del web builder: CPU audio, area mod, kit, progetto, sezione 7.

    python tools/build/budget.py        # rigenera web-builder/src/budget.json

- cpu: cicli in piu' per blocco audio nel caso peggiore, stimati nell'emulatore con le cache (tools/emu/cycles.py,
  tests/test_cycles.py); AUDIO_CPU tiene le istruzioni (tests/test_cpu_budget.py e i test delle mod);
- modarea, kit, project: spazio prenotato nel registro (registry.py);
- sec7: byte accodati alla sezione 7 (CPU #2), dai patch.json.

Il margine di decompressione all'avvio non e' qui: misurato mod per mod con build vere (2026-11-01) non e'
additivo (valori anche negativi, somma lontana dal totale), quindi lo da' solo la build.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import build  # noqa: E402
import kitstore_layout  # noqa: E402
import modarea_layout  # noqa: E402
import projstore_layout  # noqa: E402
import registry  # noqa: E402

REPO = HERE.parents[1]
OUT = REPO / "web-builder" / "src" / "budget.json"

# istruzioni per blocco, caso peggiore (2026-10-30, OS 1.42; fx3 2026-11-03): fx3 PHSR con 12 tracce e ingresso in mandata,
# master-comp con compressione piena, dual-mono = mandate di IN R (v2) + VCA degli ingressi (v1).
# perf-fx gira nell'interrupt del sequencer, readable-values nell'interfaccia: 0 qui.
# xparams: copia degli indici 0x36..0x3d verso la CPU #2 a ogni blocco (xp_dma_wait, tests/test_xparams.py): 131, srotolata
# (era ~410, in sy-fm4); piu' le parole della machine non smussate (0x11..0x1a, 8 tracce): 335 in tutto.
# sampler: il tempo nella RAM condivisa (sm_block, tests/test_sampler.py); il motore gira sulla CPU #2.
# fastmix (2026-11-03): credito, routine dell'OS piu' veloci. Misurato sull'interrupt intero (tools/emu/isr.py,
# scena "max": tutte le mandate, guadagni fermi): -11 000 con o senza le altre mod. Qui -10 000. Nei blocchi in
# cui i guadagni sono in rampa o i parametri si muovono (dopo un cambio di kit) il credito sparisce (+~400).
# xparams (2026-11-04): copia in un ciclo per traccia (362, piu' istruzioni, meno codice: vedi AUDIO_CYCLES).
# 2026-11-05: fx3 in assembly (2 664), xparams una copia a blocco invece di due (~240), fastmix con meno codice e
# qualche istruzione in piu' (credito -5 000).
AUDIO_CPU = {"fx3": 2670, "master-comp": 578, "dual-mono": 324 + 133, "xparams": 240, "sampler": 8, "fastmix": -5000}

# cicli in piu' per blocco (2026-11-04 sera: fastmix senza smussamento, xparams a parole lunghe, fx3 con i valori
# derivati precalcolati; tools/emu/cycles.py, scena "max", taratura prudente CPI 1.0: una riga
# mancata ~54 cicli). L'interrupt non sta nella cache istruzioni da 8 KB: ogni 16 byte di codice eseguito e ogni
# riga di dati in DDR costano una lettura dalla DDR a ogni blocco. fx3, master-comp, dual-mono contati sopra
# fastmix; sampler e sy-fm4 sopra xparams; fastmix sopra lo stock. Il sito somma questi valori.
# 2026-11-05 (fx3 in assembly con lo stato in un blocco, fastmix compatto, xparams una copia, master-comp con codice e
# dati di ogni blocco contigui): misurati fx3 10 730, master-comp 3 353, dual-mono 2 386, xparams 1 589, sampler 303,
# fastmix -4 588; tutte le mod dell'audio 162 200 cicli = 97,3 % del blocco (prima 101,2 %).
AUDIO_CYCLES = {"fx3": 10900, "master-comp": 3500, "dual-mono": 2400, "xparams": 1700, "sampler": 400, "sy-fm4": 0,
                "fastmix": -4300}
# cpu-meter (2026-11-05): lettura del timer all'ingresso e all'uscita dell'interrupt, 10 righe di codice: 735 cicli.
# Senza, il profilo "every mod" sul sito restava sotto il misurato (20 500 contro 21 131).
AUDIO_CYCLES["cpu-meter"] = 800
# modulation-skip (2026-11-05): blocco saltato -6 178 cicli (-6 447 istruzioni pesate); ogni mod insieme 21 131 ->
# 14 956. Qui un credito prudente: nei blocchi con ingressi cambiati (nota con altra velocity, LFO/parametri mossi,
# 1 su 64 di controllo) gira lo stock piu' la registrazione (tests/test_modulation_skip.py).
# sfcore: solo interfaccia (0); gli adattatori audio e nativi si contano nella mod che li usa ("uses").
AUDIO_CYCLES["modulation-skip"] = -5000
AUDIO_CPU["modulation-skip"] = -5500

SEC7_ROOM = 127_695

# blocco audio e carico dello stock (tools/emu/cycles.py): il sito mostra la CPU anche in % del blocco
BLOCK = 166_666
STOCK_LOAD = 0.89

# profili: combinazioni misurate intere nell'emulatore (tools/emu/cycles.py, scena "max", CPI 1.0), cicli in piu'
# per blocco rispetto allo stock. Il sito somma AUDIO_CYCLES delle mod scelte (dipendenze comprese): per ogni
# profilo la somma non deve stare sotto il misurato (tests/test_cycles.py), cosi' qualunque combinazione oltre il
# limite si vede in rosso. Le combinazioni pesanti si possono costruire: il sito avverte, non blocca.
PROFILES = {
    # 2026-11-06 (fx3 in assembly unito): +14 564 cicli, 97,7 % del blocco (stock a riposo 89 %); prima 101,7 %
    "every mod but modulation-skip": {"mods": [
        "cpu-meter", "dual-mono", "fastmix", "fx3", "kitstore", "long-samples", "master-comp", "modarea", "modarea7",
        "perf-fx", "projstore", "readable-values", "sampler", "splash", "sy-fm4", "syn-pages", "vparams", "xparams"],
        "cycles": 14564},
    # 2026-11-06: +8 390 cicli, 94,0 % (blocco saltato da modulation-skip); prima 98,0 %
    "every mod": {"mods": [
        "cpu-meter", "dual-mono", "fastmix", "fx3", "kitstore", "long-samples", "master-comp", "modarea", "modarea7",
        "modulation-skip", "perf-fx", "projstore", "readable-values", "sampler", "sfcore", "splash", "sy-fm4",
        "syn-pages", "vparams", "xparams"], "cycles": 8390},
}

LIMITS = {
    # stock a riposo ~89 % del blocco (166 666 cicli): 10 000 cicli in piu' = interrupt al ~95 %. Provvisorio, da
    # tarare con una misura DTIM0 sul dispositivo (docs/audio-path.md); fx3 laggava gia' sulla macchina
    "cpu": 10000,
    "modarea": modarea_layout.SIZE,
    "kit": kitstore_layout.WORDS_PER_BLOCK * kitstore_layout.N_BLOCKS,
    "project": 256,
    # staging della sezione 7 (0x60000 - 5) meno lo stub di modarea7 e la sezione stock compressa (SHLZ):
    # il codice dei motori si conta non compresso, quindi per eccesso (tests/test_modarea7.py controlla il valore)
    "sec7": SEC7_ROOM,
}


def mods() -> list[str]:
    return sorted(p.parent.name for p in (REPO / "mods").glob("*/mod.json"))


def static(name: str) -> dict:
    spec = build.read_spec(REPO / "mods" / name)
    return {
        "cpu": AUDIO_CYCLES.get(name, 0),
        "modarea": sum(b - a for a, b, who, _ in registry.MODAREA if who == name),
        "kit": len(kitstore_layout.PARTS.get(name, [])),
        "project": projstore_layout.PARTS.get(name, (0, 0))[1],
        "sec7": sum(p["len"] for p in spec["patches"] if p["section"] == 7 and p.get("append")),
    }


def data() -> dict:
    return {"limits": LIMITS, "audio": {"block": BLOCK, "stock": STOCK_LOAD}, "mods": {n: static(n) for n in mods()}}


def shown(names: list[str]) -> int:
    """Cicli che il sito mostra per queste mod (dipendenze comprese), come web-builder/src/load.ts."""
    order, _ = build.resolve([REPO / "mods" / n for n in names])
    return sum(AUDIO_CYCLES.get(build.read_spec(d)["name"], 0) for d in order)


def main() -> int:
    OUT.write_text(json.dumps(data(), indent=2) + "\n", encoding="utf-8")
    print(f"scritto {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
