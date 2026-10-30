"""Porta i sorgenti di una mod (o dei test) da un OS all'altro: traduce ogni indirizzo dell'OS scritto
esplicitamente (0x4008_FB04, 0x41B9F7E8, ...) con la mappa di osmap.py.

Si lavora sui sorgenti, non sui byte assemblati: nel codice macchina due istruzioni consecutive possono
sembrare un indirizzo, nel testo no. Dopo il port si rigenera patch.json con make_patch.py, che ricontrolla
i byte originali sull'OS nuovo, e si rilanciano i test (che eseguono il codice originale dell'OS).

    python tools/build/port_source.py 1.42 mods/la-mia-mod tests/test_la_mia_mod.py --dry-run
    python tools/build/port_source.py 1.42 mods/la-mia-mod tests/test_la_mia_mod.py

Indirizzi in zone di codice cambiate fra le due versioni: elencati e lasciati com'erano, da sistemare a mano.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import osmap  # noqa: E402

TOKEN = re.compile(r"\b0[xX]([0-9A-Fa-f][0-9A-Fa-f_]*)(?=[uUlL]*\b)")     # anche 0x41B9FA24u
SUFFIXES = {".py", ".c", ".h", ".S", ".s", ".ts", ".md"}


def fmt(old: str, new: int) -> str:
    """Stesso stile dell'originale: maiuscole/minuscole e '_' fra le due meta'."""
    digits = old.replace("_", "")
    h = f"{new:08x}"
    if digits.upper() == digits and any(c.isalpha() for c in digits + h):
        h = h.upper()
    if "_" in old:
        h = h[:4] + "_" + h[4:]
    return h


def port_text(text: str, os: str) -> tuple[str, list[tuple[int, str, str]], list[tuple[int, str]]]:
    changes, unmapped = [], []

    def sub(m: re.Match) -> str:
        raw = m.group(1)
        digits = raw.replace("_", "")
        if len(digits) != 8:
            return m.group(0)
        v = int(digits, 16)
        if not osmap.is_os_address(v):
            return m.group(0)
        line = text.count("\n", 0, m.start()) + 1
        try:
            n = osmap.addr(v, os)
        except osmap.Unmapped:
            unmapped.append((line, m.group(0)))
            return m.group(0)
        if n == v:
            return m.group(0)
        new = m.group(0)[:2] + fmt(raw, n)
        changes.append((line, m.group(0), new))
        return new

    return TOKEN.sub(sub, text), changes, unmapped


HEXSTR = re.compile(r"""(["'])([0-9a-fA-F]{8,})\1""")


def opcode_with_abs(op: int) -> bool:
    """Istruzione con operando assoluto lungo o immediato (sorgente: modo 7 reg 1/4, campo 0x39/0x3C;
    move con destinazione assoluta: campo 0x0F nei bit 6-11): seguono i 32 bit dell'operando."""
    if (op & 0x3F) in (0x39, 0x3C) and op >> 12 in (0x0, 0x2, 0x3, 0x4, 0xB, 0xC, 0xD, 0x8, 0x9):
        return True
    return op >> 12 in (0x2, 0x3) and (op >> 6) & 0x3F == 0x0F


def port_hex_strings(text: str, os: str) -> tuple[str, list[tuple[int, str, str]]]:
    """Byte scritti come stringa esadecimale ("4eb940096890": i byte originali attesi, o istruzioni nostre):
    traduce le parole a 32 bit, a passo di 2 byte, che sono indirizzi dell'OS. Un falso positivo qui non passa
    inosservato: i byte attesi non corrisponderebbero all'OS e make_patch.py si fermerebbe."""
    changes = []

    def sub(m: re.Match) -> str:
        s = m.group(2)
        if len(s) % 2:
            return m.group(0)
        b = bytearray.fromhex(s)
        k = 0
        while k + 4 <= len(b):
            w = int.from_bytes(b[k:k + 4], "big")
            if opcode_with_abs(w >> 16) and k + 6 <= len(b):
                k += 2                                  # l'indirizzo e' la parola dopo l'opcode
                continue
            if osmap.is_os_address(w):
                try:
                    n = osmap.addr(w, os)
                except osmap.Unmapped:
                    n = w
                if n != w:
                    b[k:k + 4] = n.to_bytes(4, "big")
                    k += 4
                    continue
            k += 2
        new = b.hex().upper() if s.upper() == s and not s.isdigit() else b.hex()
        if new == s:
            return m.group(0)
        changes.append((text.count("\n", 0, m.start()) + 1, s, new))
        return m.group(1) + new + m.group(1)

    return HEXSTR.sub(sub, text), changes


def files(paths: list[Path]) -> list[Path]:
    out = []
    for p in paths:
        if p.is_dir():
            out += sorted(f for f in p.rglob("*") if f.suffix in SUFFIXES and "__pycache__" not in f.parts)
        else:
            out.append(p)
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("os", choices=sorted(osmap.FIXED))
    ap.add_argument("paths", type=Path, nargs="+")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--hex-strings", action="store_true",
                    help="anche le parole-indirizzo dentro le stringhe esadecimali dei .py (byte attesi)")
    a = ap.parse_args(argv)
    total = bad = 0
    for f in files(a.paths):
        text = f.read_text(encoding="utf-8")
        new, changes, unmapped = port_text(text, a.os)
        if a.hex_strings and f.suffix == ".py":
            new, more = port_hex_strings(new, a.os)
            changes += more
        total += len(changes)
        bad += len(unmapped)
        for line, old, nw in changes if a.dry_run else []:
            print(f"{f}:{line}: {old} -> {nw}")
        for line, old in unmapped:
            print(f"{f}:{line}: {old} NON MAPPATO (codice cambiato): da sistemare a mano")
        if changes and not a.dry_run:
            f.write_text(new, encoding="utf-8", newline="")
    print(f"{total} indirizzi tradotti, {bad} non mappati")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
