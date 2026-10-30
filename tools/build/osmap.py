"""Dove sta, in un'altra versione dell'OS, lo stesso codice o la stessa variabile della 1.41.

Le mod sono scritte con gli indirizzi della 1.41 (l'OS su cui sono state studiate). Per un'altra versione:
- codice e dati in sola lettura (sezione 3): zone a spostamento costante, trovate allineando le due immagini
  stock su sequenze di 16 byte uniche in entrambe (le zone cambiate restano fuori e sono rifiutate);
- variabili (BSS 0x40339000..0x45565490, heap compreso): uno spostamento unico, misurato sugli operandi delle
  istruzioni corrispondenti; SRAM (0x80000000..) e periferiche: invariate (verificato allo stesso modo);
- riempimento libero in fondo all'immagine (splash, dual-mono, caricatore dell'area mod) e area mod accodata:
  dichiarati qui sotto, controllati dai test.

La tabella generata sta in osmap-<versione>.json (solo zone e spostamenti, nessun byte dell'OS):

    python tools/build/osmap.py 1.42          # rigenera dalla 1.41 e dalla 1.42 stock (in firmware/)
"""

from __future__ import annotations

import bisect
import json
import sys
from functools import lru_cache
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
LOAD = 0x4000_0400
REF = "1.41"
STOCK_SHA256 = {
    "1.41": "8e2488f462c4a5656396a895f113bcd415e9900fa8709340dccf45d4cb9ed19e",
    "1.42": "ded3c59fdb909eb9e2c3307b30a486452c8fa6947b12c14e0ce35a187b7f37c1",
}
BSS_141 = (0x4033_9000, 0x4556_5490)
FREE_141 = (0x4033_8740, 0x4033_9000)          # riempimento a zero prima del BSS
IMG_141 = 0x4034_8000                          # area mod accodata alla sezione 3
# per versione: spostamento del BSS (e del riempimento libero che lo precede) e dell'area mod accodata
FIXED = {"1.42": {"bss": 0x1000, "free": 0x1000, "img": 0x1000}}
K = 16                                         # lunghezza delle sequenze di allineamento


class Unmapped(KeyError):
    pass


def table_file(os: str) -> Path:
    return HERE / f"osmap-{os}.json"


@lru_cache(maxsize=None)
def table(os: str) -> tuple[list[int], list[tuple[int, int, int]]]:
    runs = [tuple(int(v, 16) for v in r) for r in json.loads(table_file(os).read_text(encoding="utf-8"))["runs"]]
    return [r[0] for r in runs], runs


def addr(a: int, os: str) -> int:
    """Indirizzo 1.41 -> stesso codice o variabile in `os`. Unmapped se cade in una zona cambiata."""
    if os == REF:
        return a
    f = FIXED[os]
    if BSS_141[0] <= a < BSS_141[1]:
        return a + f["bss"]
    if FREE_141[0] <= a < FREE_141[1]:
        return a + f["free"]
    if IMG_141 <= a < IMG_141 + 0x1_0000:
        return a + f["img"]
    if not LOAD <= a < FREE_141[0]:
        return a                                # SRAM, periferiche, RAM fuori dal BSS: invariate
    los, runs = table(os)
    i = bisect.bisect_right(los, a) - 1
    if i >= 0 and a < runs[i][1]:
        return a + runs[i][2]
    raise Unmapped(f"{a:#010x}: code changed between 1.41 and {os}")


def is_os_address(w: int) -> bool:
    return LOAD <= w < BSS_141[1] or IMG_141 <= w < IMG_141 + 0x1_0000


def generate(os: str) -> list[tuple[int, int, int]]:
    """Zone [inizio, fine) a spostamento costante, dagli allineamenti delle due sezioni 3 stock."""
    import numpy as np
    sys.path.insert(0, str(REPO / "tools" / "unpack"))
    import eft
    secs = []
    for v in (REF, os):
        f = REPO / "firmware" / f"Syntakt_OS{v}.syx"
        secs.append(np.frombuffer(eft.unpack(f, REPO / "unpacked" / f.stem, ids=[3])[3].read_bytes(), np.uint8))
    x, y = secs

    def unique(a):
        idx = np.arange(0, (len(a) - K) // 2 * 2, 2)
        h = np.zeros(len(idx), np.uint64)
        for k in range(K):
            h = h * np.uint64(1099511628211) + a[idx + k].astype(np.uint64)
        _, inv, cnt = np.unique(h, return_inverse=True, return_counts=True)
        keep = cnt[inv] == 1
        return dict(zip(h[keep].tolist(), idx[keep].tolist()))

    ux, uy = unique(x), unique(y)
    pairs = sorted((ux[h], uy[h]) for h in ux.keys() & uy.keys())
    runs: list[list[int]] = []
    for p, q in pairs:
        d = q - p
        if runs and runs[-1][2] == d and p - runs[-1][1] <= 64:
            runs[-1][1] = p + K
        else:
            runs.append([p, p + K, d])
    # zone di almeno 32 byte; due zone consecutive con lo stesso spostamento si uniscono (fra le due nessuna
    # sequenza unica dice altro: tratti ripetitivi, o istruzioni che chiamano codice spostato)
    out: list[list[int]] = []
    for a, b, d in runs:
        if b - a < 32 or LOAD + b > FREE_141[0]:
            continue
        if out and out[-1][2] == d:
            out[-1][1] = LOAD + b
        else:
            out.append([LOAD + a, LOAD + b, d])
    return [tuple(r) for r in out]


if __name__ == "__main__":
    os_ = sys.argv[1] if len(sys.argv) > 1 else "1.42"
    runs = generate(os_)
    rows = ",\n".join(f'    ["{a:#010x}", "{b:#010x}", "{d:#x}"]' for a, b, d in runs)
    table_file(os_).write_text(
        "{\n"
        f'  "from": "{REF}", "to": "{os_}", "how": "python tools/build/osmap.py {os_}",\n'
        f'  "stock_sha256": {json.dumps({REF: STOCK_SHA256[REF], os_: STOCK_SHA256[os_]})},\n'
        '  "code": "[1.41 start, 1.41 end, delta]",\n'
        f'  "runs": [\n{rows}\n  ]\n}}\n', encoding="utf-8")
    covered = sum(b - a for a, b, _ in runs)
    print(f"{len(runs)} zone, {covered} B su {FREE_141[0] - LOAD} di codice e dati mappati -> {table_file(os_).name}")
