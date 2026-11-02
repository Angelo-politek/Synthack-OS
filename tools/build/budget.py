"""Carico di ogni mod per l'indicatore del web builder: CPU audio, area mod, kit, progetto, sezione 7.

    python tools/build/budget.py        # rigenera web-builder/src/budget.json

- cpu: istruzioni in piu' per blocco audio nel caso peggiore, misurate nell'emulatore
  (tests/test_cpu_budget.py controlla che le misure non superino questi valori);
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
# sy-fm4: copia della pagina 2/2 verso la CPU #2 a ogni blocco (fm4m_dma_wait, tests/test_sy_fm4.py).
# sampler: il tempo nella RAM condivisa (sm_block, tests/test_sampler.py); il motore gira sulla CPU #2.
AUDIO_CPU = {"fx3": 2743, "master-comp": 578, "dual-mono": 324 + 133, "sy-fm4": 410, "sampler": 8}

SEC7_ROOM = 127_695

LIMITS = {
    "cpu": 3000,                   # ~3 000 istruzioni in piu' per blocco fanno gia' laggare l'interfaccia (prova sulla macchina)
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
        "cpu": AUDIO_CPU.get(name, 0),
        "modarea": sum(b - a for a, b, who, _ in registry.MODAREA if who == name),
        "kit": len(kitstore_layout.PARTS.get(name, [])),
        "project": projstore_layout.PARTS.get(name, (0, 0))[1],
        "sec7": sum(p["len"] for p in spec["patches"] if p["section"] == 7 and p.get("append")),
    }


def data() -> dict:
    return {"limits": LIMITS, "mods": {n: static(n) for n in mods()}}


def main() -> int:
    OUT.write_text(json.dumps(data(), indent=2) + "\n", encoding="utf-8")
    print(f"scritto {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
