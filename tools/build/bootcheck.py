"""Controllo di avvio: la sezione 3 deve potersi decomprimere "quasi sul posto".

Il bootstrap (sezione 2, funzione 0x80000210) mette l'OS compresso a 0x40200000 e lo decomprime
(aPLib) verso 0x40000400: l'output cresce verso l'alto e insegue l'input. Se lo raggiunge,
sovrascrive byte compressi non ancora letti e l'OS esce corrotto (la Syntakt resta sul logo).
Qui si ripete la decompressione registrando la distanza minima tra il prossimo byte da leggere e
l'ultimo byte scritto. Stock 1.41: +99 938 B; un'immagine a -8 751 B non si avvia (provato).

    python tools/build/bootcheck.py out/synthack.syx
"""

from __future__ import annotations

import struct
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "tools" / "unpack"))
import eft  # noqa: E402

SRC, DST = 0x4020_0000, 0x4000_0400     # dove il bootstrap mette l'OS compresso / decompresso
MIN_MARGIN = 4096                       # soglia di sicurezza (letture anticipate, arrotondamenti)
ELE3_COUNT_OFF, ELE3_TABLE_OFF, ELE3_ENTRY_SZ = 0x1C, 0x20, 16
HDR, BIAS, REUSE, FAR = 8, 767, 2, 3328  # costanti di aplib.c (elektron-firmware-tool)


def section_stream(syx: Path, sid: int = 3) -> bytes:
    with tempfile.TemporaryDirectory(prefix="bootcheck-") as t:
        c = Path(t) / "container.bin"
        eft._run("-i", Path(syx), "--emit-container", c)
        data = c.read_bytes()
    for k in range(struct.unpack_from(">I", data, ELE3_COUNT_OFF)[0]):
        s, off, clen, _ = struct.unpack_from(">4I", data, ELE3_TABLE_OFF + ELE3_ENTRY_SZ * k)
        if s == sid:
            return data[off:off + clen]
    raise ValueError(f"sezione {sid} assente")


def depack_margin(stream: bytes) -> tuple[int, int]:
    """Decomprime come aplib.c; ritorna (byte prodotti, margine minimo in byte)."""
    ip, op, tag, last_off = HDR, 0, 0, 1
    n = len(stream)
    worst = 1 << 40
    base = SRC - DST

    def bit() -> int:
        nonlocal tag, ip
        tag = (tag << 1) & 0xFFFF
        if not tag & 0xFF:
            by = stream[ip]
            ip += 1
            tag = (by << 1) | 1
            return by >> 7
        return (tag >> 8) & 1

    def gamma() -> int:
        v = 1
        while True:
            v = (v << 1) + bit()
            if bit():
                return v

    try:
        while ip < n:
            if bit():
                ip += 1
                op += 1
            else:
                g = gamma()
                if g == REUSE:
                    off = last_off
                else:
                    off = (g << 8) + stream[ip]
                    ip += 1
                    if off == BIAS:
                        break
                    off -= BIAS
                    last_off = off
                sl = 2 * bit()
                sl += bit()
                length = sl if sl else gamma() + 2
                if off > FAR:
                    length += 1
                op += length + 1
            m = base + ip - op
            if m < worst:
                worst = m
    except IndexError:          # fine dello stream senza marcatore (come allow_trunc)
        pass
    return op, worst


def check(syx: Path) -> tuple[int, int]:
    """(byte decompressi della sezione 3, margine minimo)."""
    return depack_margin(section_stream(syx))


if __name__ == "__main__":
    for f in sys.argv[1:]:
        size, m = check(Path(f))
        print(f"{f}: sezione 3 {size} B, margine di decompressione {m} B"
              + ("" if m >= MIN_MARGIN else "  <-- NON SI AVVIA"))
