"""Chiamate dal C delle mod alle funzioni dell'OS: risultato in d0.

L'OS restituisce anche i puntatori in d0; il nostro compilatore (m68k-linux-gnu, ABI SVR4) legge un risultato di
tipo puntatore da a0. Una funzione dell'OS dichiarata con un tipo di ritorno puntatore restituisce quindi un valore
a caso (SY FM4, test3 sulla macchina: elenco delle pagine scritto dove puntava a0). Le funzioni dell'OS vanno
dichiarate con un ritorno intero, poi convertito.
"""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
# cast di un indirizzo a puntatore a funzione con ritorno puntatore: ((T *(*)(...))0x...)
PTR_RET = re.compile(r"\(\s*[A-Za-z_][\w\s]*\*+\s*\(\s*\*\s*\)\s*\([^)]*\)\s*\)\s*\(?\s*0x[0-9A-Fa-f]+")


def test_no_os_function_returns_a_pointer():
    found = []
    for f in sorted([*(ROOT / "mods").rglob("*.[ch]"), *(ROOT / "sdk").glob("*.h")]):
        for n, line in enumerate(f.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
            if PTR_RET.search(line):
                found.append(f"{f.relative_to(ROOT)}:{n}: {line.strip()}")
    assert found == []


def test_pattern_catches_the_fm4_bug():
    assert PTR_RET.search("#define FW_MALLOC      ((u32 *(*)(u32))0x4010394c)")
    assert not PTR_RET.search("#define FW_MALLOC      ((u32 (*)(u32))0x4010394c)")
