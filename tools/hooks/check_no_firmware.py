"""Controlla i file in staging e blocca il commit se sembrano firmware Elektron.

E' la seconda linea di difesa dopo .gitignore: copre il caso di un ``git add -f``
o di una sezione estratta rinominata con un'estensione innocua.
"""

from __future__ import annotations

import subprocess
import sys

# SysEx (F0) + manufacturer ID Elektron (00 20 3C): l'inizio di ogni .syx Elektron.
ELEKTRON_SYSEX = b"\xf0\x00\x20\x3c"
CONTAINER_MAGICS = (b"ELE3", b"ELE2", b"ELEK")
FORBIDDEN_EXT = (".syx", ".bin", ".raw", ".elf", ".img")
MAX_BINARY_BYTES = 256 * 1024


def is_binary(data: bytes) -> bool:
    return b"\x00" in data[:8192]


def check_blob(path: str, data: bytes) -> str | None:
    """Ritorna il motivo del rifiuto, o None se il file va bene."""
    if path.lower().endswith(FORBIDDEN_EXT):
        return "estensione da firmware/binario"
    if ELEKTRON_SYSEX in data:
        return "contiene un header SysEx Elektron (F0 00 20 3C)"
    if is_binary(data):
        if any(m in data for m in CONTAINER_MAGICS):
            return "file binario con magic di container Elektron"
        if len(data) > MAX_BINARY_BYTES:
            return f"file binario di {len(data)} B (> {MAX_BINARY_BYTES} B)"
    return None


def staged_files() -> list[str]:
    out = subprocess.run(
        ["git", "diff", "--cached", "--name-only", "--diff-filter=ACMR", "-z"],
        capture_output=True, check=True,
    ).stdout
    return [p.decode("utf-8") for p in out.split(b"\0") if p]


def main() -> int:
    problems = []
    for path in staged_files():
        data = subprocess.run(["git", "show", f":{path}"], capture_output=True, check=True).stdout
        if reason := check_blob(path, data):
            problems.append((path, reason))
    if not problems:
        return 0
    print("pre-commit: commit bloccato, possibile firmware Elektron nello staging:", file=sys.stderr)
    for path, reason in problems:
        print(f"  {path}: {reason}", file=sys.stderr)
    print("Rimuovilo con: git rm --cached <file>   (vedi LEGAL.md)", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
