"""Wrapper Python su elektron-firmware-tool.

Il lavoro vero (SysEx, container ELE3, aPLib, checksum, MAC) lo fa il tool C di
mischa85; qui aggiungiamo solo:

- un'interfaccia Python riusabile (dal build delle mod, dai test, dal web builder);
- il ponte Windows -> WSL (il tool e' compilato per Linux);
- le nostre regole di sicurezza: mai sostituire le sezioni protette (bootstrap, boot);
- il comando ``roundtrip``, che dimostra che la pipeline non altera il firmware.

Uso:
    python tools/unpack/eft.py info      firmware/Syntakt_OS1.41.syx
    python tools/unpack/eft.py unpack    firmware/Syntakt_OS1.41.syx [-o unpacked/1.41]
    python tools/unpack/eft.py repack    firmware/Syntakt_OS1.41.syx -o out.syx [--replace N FILE]
    python tools/unpack/eft.py roundtrip firmware/Syntakt_OS1.41.syx
"""

from __future__ import annotations

import argparse
import hashlib
import os
import re
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
DEFAULT_BIN = REPO / "third_party" / "elektron-firmware-tool" / "elektron-firmware-tool"

# Sezioni che il nostro tooling non deve MAI riscrivere: sono quelle che
# permettono il recovery (vedi docs/recovery.md).
PROTECTED_SECTIONS = frozenset({2, 6})

# Sezioni ricompresse nel round-trip semantico: quelle che un giorno patcheremo.
PATCHABLE_SECTIONS = (3, 7)


class EftError(RuntimeError):
    pass


# --------------------------------------------------------------------------- #
# Invocazione del tool
# --------------------------------------------------------------------------- #

def to_wsl_path(p: Path | str) -> str:
    """C:\\Users\\x\\f.syx -> /mnt/c/Users/x/f.syx (montaggio di default di WSL)."""
    p = Path(p).resolve()
    drive = p.drive
    if len(drive) != 2 or drive[1] != ":":
        raise EftError(f"percorso non convertibile per WSL: {p}")
    return f"/mnt/{drive[0].lower()}{p.as_posix()[2:]}"


def _find_bin() -> Path:
    b = Path(os.environ.get("EFT_BIN", DEFAULT_BIN))
    if not b.exists():
        raise EftError(
            f"elektron-firmware-tool non trovato in {b}\n"
            "  -> esegui in WSL: bash tools/unpack/setup_eft.sh  (oppure imposta EFT_BIN)"
        )
    return b


def _run(*args: str | Path) -> str:
    """Esegue il tool e ritorna stdout. Gli argomenti Path vengono convertiti per WSL."""
    b = _find_bin()
    via_wsl = os.name == "nt" and b.suffix.lower() != ".exe"
    if via_wsl:
        cmd = ["wsl.exe", "-e", to_wsl_path(b)]
        cmd += [to_wsl_path(a) if isinstance(a, Path) else a for a in args]
    else:
        cmd = [str(b), *map(str, args)]
    proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if proc.returncode != 0:
        raise EftError(
            f"elektron-firmware-tool ha fallito (exit {proc.returncode}):\n"
            f"  {' '.join(map(str, cmd))}\n{proc.stderr.strip() or proc.stdout.strip()}"
        )
    return proc.stdout


# --------------------------------------------------------------------------- #
# info
# --------------------------------------------------------------------------- #

@dataclass
class Section:
    id: int
    name: str
    size: int          # byte decompressi (o byte grezzi se raw)
    raw: bool          # True se la sezione non e' compressa


@dataclass
class Info:
    device: str = ""
    version: str = ""
    container: str = ""
    sections: list[Section] = field(default_factory=list)
    checksums_ok: bool = False
    text: str = ""

    def section(self, sid: int) -> Section | None:
        return next((s for s in self.sections if s.id == sid), None)


_RE_FIELD = re.compile(r"^(device|version|container|checksums)\s*:\s*(.*)$")
_RE_SECTION = re.compile(r"^\s+id\s+(\d+)\s+(.*?)\s+(\d+) B( \(raw\))?\s*$")


def parse_info(text: str) -> Info:
    """Interpreta il riepilogo di ``elektron-firmware-tool -i``."""
    info = Info(text=text)
    for line in text.splitlines():
        if m := _RE_SECTION.match(line):
            info.sections.append(Section(int(m[1]), m[2], int(m[3]), bool(m[4])))
        elif m := _RE_FIELD.match(line):
            key, val = m[1], m[2].strip()
            if key == "checksums":
                info.checksums_ok = val == "ok"
            else:
                setattr(info, key, val)
    return info


def info(syx: Path) -> Info:
    return parse_info(_run("-i", Path(syx)))


# --------------------------------------------------------------------------- #
# unpack / repack
# --------------------------------------------------------------------------- #

def unpack(syx: Path, outdir: Path, ids: list[int] | None = None) -> dict[int, Path]:
    """Decomprime le sezioni (tutte se ``ids`` e' None). Ritorna {id: file}."""
    outdir = Path(outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    args: list[str | Path] = ["-i", Path(syx)]
    for sid in ids or []:
        args += ["-d", str(sid)]
    _run(*args, "-o", outdir)

    wanted = ids if ids is not None else [s.id for s in info(syx).sections]
    found: dict[int, Path] = {}
    for sid in wanted:
        # Il nome dopo l'id e' solo un'etichetta del tool: cerchiamo per prefisso.
        matches = sorted(outdir.glob(f"section_{sid}_*"))
        if len(matches) != 1:
            raise EftError(f"attesi 1 file per la sezione {sid} in {outdir}, trovati {len(matches)}")
        found[sid] = _safe_name(matches[0])
    return found


def safe_section_name(name: str) -> str:
    """section_8_?.bin -> section_8_unknown.bin

    Il tool usa "?" per le sezioni senza etichetta; su NTFS via WSL diventa un
    carattere Unicode privato (U+F03F) scomodo da usare su Windows.
    """
    stem, dot, ext = name.rpartition(".")
    head, _, label = stem.partition("_")[2].partition("_")
    if re.fullmatch(r"[A-Za-z0-9_-]+", label):
        return name
    return f"section_{head}_unknown{dot}{ext}"


def _safe_name(p: Path) -> Path:
    new = p.with_name(safe_section_name(p.name))
    if new != p:
        os.replace(p, new)
    return new


def repack(syx: Path, out: Path, replace: dict[int, Path] | None = None, level: int = 3) -> None:
    """Ricostruisce il .syx.

    Senza ``replace``: modalita' -r, sezioni copiate cosi' come sono (output identico).
    Con ``replace``: le sezioni indicate vengono ricompresse da file grezzi; checksum e
    MAC vengono ricalcolati dal tool.
    """
    if not replace:
        _run("-i", Path(syx), "-r", "-o", Path(out))
        return
    forbidden = PROTECTED_SECTIONS & replace.keys()
    if forbidden:
        raise EftError(f"rifiutato: le sezioni {sorted(forbidden)} sono protette (recovery)")
    args: list[str | Path] = ["-i", Path(syx), "-l", str(level)]
    for sid, f in sorted(replace.items()):
        args += ["-c", str(sid), Path(f)]
    _run(*args, "-o", Path(out))


# --------------------------------------------------------------------------- #
# round-trip
# --------------------------------------------------------------------------- #

def sha256(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def roundtrip(syx: Path, workdir: Path, level: int = 3, log=print) -> bool:
    """Due verifiche:

    1. byte-esatta: repack -r -> SHA-256 identico all'originale;
    2. semantica: le sezioni patchabili vengono decompresse e ricompresse, poi si
       controlla che, decomprimendo di nuovo, TUTTE le sezioni siano identiche.
    """
    syx, workdir = Path(syx), Path(workdir)
    ok = True

    orig = info(syx)
    log(f"device {orig.device} | version {orig.version} | container {orig.container}")
    for s in orig.sections:
        tag = " PROTETTA" if s.id in PROTECTED_SECTIONS else ""
        log(f"  sezione {s.id:<2} {s.name:<10} {s.size:>10} B{' (raw)' if s.raw else ''}{tag}")
    if not orig.checksums_ok:
        log("FAIL  checksum dell'originale non validi: file corrotto o non supportato")
        return False

    # 1. byte-esatto
    exact = workdir / "repack_exact.syx"
    repack(syx, exact)
    h_in, h_out = sha256(syx), sha256(exact)
    same = h_in == h_out
    ok &= same
    log(f"{'OK  ' if same else 'FAIL'}  byte-esatto (-r): {h_in[:16]}... {'==' if same else '!='} {h_out[:16]}...")

    # 2. semantico
    a = unpack(syx, workdir / "orig")
    # Le sezioni raw restano raw anche se sostituite: il test copre entrambi i percorsi
    # (ricompressione aPLib per quelle compresse, copia per quelle raw).
    targets = {sid: a[sid] for sid in PATCHABLE_SECTIONS if orig.section(sid) is not None}
    if not targets:
        log("FAIL  nessuna sezione patchabile trovata (attese id 3 e/o 7)")
        return False

    rebuilt = workdir / "repack_replaced.syx"
    repack(syx, rebuilt, replace=targets, level=level)
    if not info(rebuilt).checksums_ok:
        log("FAIL  il .syx ricostruito non passa i checksum")
        return False
    kinds = ", ".join(f"{sid} {'raw' if orig.section(sid).raw else 'ricompressa'}" for sid in sorted(targets))
    log(f"OK    sostituzione sezioni [{kinds}] (livello {level}): checksum validi")

    b = unpack(rebuilt, workdir / "rebuilt")
    for sid in sorted(a):
        same = sid in b and sha256(a[sid]) == sha256(b[sid])
        ok &= same
        log(f"{'OK  ' if same else 'FAIL'}  sezione {sid}: contenuto decompresso {'identico' if same else 'DIVERSO'}")

    log("ROUND-TRIP OK" if ok else "ROUND-TRIP FALLITO")
    return ok


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #

def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="eft.py", description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("info", help="riepilogo e verifica checksum")
    p.add_argument("syx", type=Path)
    p.add_argument("-v", "--verbose", action="store_true", help="report completo di tutti gli strati")

    p = sub.add_parser("unpack", help="decomprime le sezioni")
    p.add_argument("syx", type=Path)
    p.add_argument("-o", "--out", type=Path, help="default: unpacked/<nome file>/")
    p.add_argument("-d", "--section", type=int, action="append", help="solo questa sezione (ripetibile)")

    p = sub.add_parser("repack", help="ricostruisce il .syx (identico, o sostituendo sezioni)")
    p.add_argument("syx", type=Path)
    p.add_argument("-o", "--out", type=Path, required=True)
    p.add_argument("--replace", nargs=2, action="append", metavar=("N", "FILE"), default=[])
    p.add_argument("-l", "--level", type=int, default=3, choices=range(4))

    p = sub.add_parser("roundtrip", help="verifica che unpack->repack non alteri nulla")
    p.add_argument("syx", type=Path)
    p.add_argument("-l", "--level", type=int, default=3, choices=range(4))
    p.add_argument("--keep", type=Path, help="conserva i file intermedi in questa cartella")

    args = ap.parse_args(argv)
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):  # console Windows (cp1252) -> UTF-8
            stream.reconfigure(encoding="utf-8", errors="replace")
    if not args.syx.is_file():
        print(f"errore: file non trovato: {args.syx}  (vedi firmware/README.md)", file=sys.stderr)
        return 2
    try:
        if args.cmd == "info":
            if args.verbose:
                print(_run("-i", args.syx, "-v"), end="")
                return 0
            i = info(args.syx)
            print(i.text, end="")
            return 0 if i.checksums_ok else 1
        if args.cmd == "unpack":
            out = args.out or REPO / "unpacked" / args.syx.stem
            for sid, f in unpack(args.syx, out, args.section).items():
                print(f"sezione {sid}: {f}")
            return 0
        if args.cmd == "repack":
            repack(args.syx, args.out, {int(n): Path(f) for n, f in args.replace}, args.level)
            print(f"scritto {args.out}")
            return 0
        if args.cmd == "roundtrip":
            if args.keep:
                args.keep.mkdir(parents=True, exist_ok=True)
                return 0 if roundtrip(args.syx, args.keep, args.level) else 1
            with tempfile.TemporaryDirectory(prefix="syntakt-rt-") as tmp:
                return 0 if roundtrip(args.syx, Path(tmp), args.level) else 1
    except EftError as e:
        print(f"errore: {e}", file=sys.stderr)
        return 2
    return 2


if __name__ == "__main__":
    sys.exit(main())
