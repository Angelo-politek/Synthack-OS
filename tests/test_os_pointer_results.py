"""Chiamate a funzioni dell'OS con risultato puntatore, in tutte le mod in C.

L'OS (gcc m68k-elf) restituisce i puntatori in d0; il nostro m68k-linux-gnu-gcc li legge da a0. Una chiamata
dichiarata con risultato puntatore legge quindi un registro a caso: va dichiarata con risultato intero e
convertita (docs/modding-guide.md). Sulla macchina: il doppio TRIG non apriva l'arpeggiatore (proxy del parametro
letto da a0) e il registratore non trovava il Sound della traccia a cui assegnare la ripresa.
"""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CAST = re.compile(r"[(,]\s*(?:const\s+)?[A-Za-z_0-9]+\s*\*+\s*\(\*\)\s*\(")


def test_no_os_call_declared_with_a_pointer_result():
    found = []
    for f in sorted((ROOT / "mods").rglob("*.[ch]")):
        for n, line in enumerate(f.read_text(encoding="utf-8", errors="ignore").splitlines(), 1):
            if CAST.search(line):
                found.append(f"{f.relative_to(ROOT)}:{n}: {line.strip()}")
    assert not found, "\n".join(found)
