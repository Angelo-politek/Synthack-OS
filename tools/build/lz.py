"""SHLZ: compressione LZ77 minimale per l'area mod (decompressa all'avvio da mods/modarea/modarea.S).

Formato: "SHLZ", lunghezza decompressa (u32 BE), lunghezza del flusso (u32 BE), poi gettoni:
    0xxxxxxx                  -> seguono x+1 byte letterali (1..128)
    1lllllll hi lo            -> copia l+3 byte (3..130) da distanza (hi<<8|lo) (1..65535) all'indietro
La decompressione si ferma quando ha prodotto la lunghezza dichiarata.

SHLW = SHLZ "sbiancato" (whiten): stessa intestazione con la sigla "SHLW", flusso allungato con zeri a un multiplo
di 4 e messo in XOR, una parola alla volta, con un xorshift32. Serve all'area mod: la sezione 3 viene poi compressa
con aPLib, e un flusso SHLZ e' ancora comprimibile; l'uscita della decompressione d'avvio corre allora piu' dell'
ingresso e il margine (bootcheck.py) cala con ogni byte di codice delle mod (misurato 2026-11-09: 6 375 B con SHLZ,
17 680 B con una coda incomprimibile, qualunque sia la sua lunghezza).
"""

from __future__ import annotations

import struct

MAGIC = b"SHLZ"
HDR = 12
MIN, MAX_LEN, MAX_LIT, WINDOW = 3, 130, 128, 0xFFFF


def compress(data: bytes) -> bytes:
    n = len(data)
    out = bytearray()
    lits = bytearray()
    heads: dict[bytes, list[int]] = {}

    def flush() -> None:
        for k in range(0, len(lits), MAX_LIT):
            chunk = lits[k:k + MAX_LIT]
            out.append(len(chunk) - 1)
            out.extend(chunk)
        lits.clear()

    i = 0
    while i < n:
        best_len, best_off = 0, 0
        if i + MIN <= n:
            key = bytes(data[i:i + MIN])
            for j in reversed(heads.get(key, [])[-64:]):     # i candidati piu' vicini
                if i - j > WINDOW:
                    break
                L = MIN
                while L < MAX_LEN and i + L < n and data[j + L] == data[i + L]:
                    L += 1
                if L > best_len:
                    best_len, best_off = L, i - j
                    if L == MAX_LEN:
                        break
        step = best_len if best_len >= MIN else 1
        for k in range(i, min(i + step, n - MIN + 1)):
            heads.setdefault(bytes(data[k:k + MIN]), []).append(k)
        if best_len >= MIN:
            flush()
            out.append(0x80 | (best_len - MIN))
            out.extend(struct.pack(">H", best_off))
        else:
            lits.append(data[i])
        i += step
    flush()
    return MAGIC + struct.pack(">II", n, len(out)) + bytes(out)


def decompress(blob: bytes) -> bytes:
    if blob[:4] != MAGIC:
        raise ValueError("non e' un flusso SHLZ")
    n, clen = struct.unpack_from(">II", blob, 4)
    src = blob[HDR:HDR + clen]
    out = bytearray()
    i = 0
    while len(out) < n:
        c = src[i]
        i += 1
        if c & 0x80:
            L = (c & 0x7F) + MIN
            off = (src[i] << 8) | src[i + 1]
            i += 2
            if not 0 < off <= len(out):
                raise ValueError("distanza non valida")
            for _ in range(L):
                out.append(out[-off])
        else:
            out += src[i:i + c + 1]
            i += c + 1
    if len(out) != n or i != clen:
        raise ValueError("lunghezze incoerenti")
    return bytes(out)


MAGIC_W = b"SHLW"
SEED = 0x53484C57


def _keystream(words: int):
    x = SEED
    for _ in range(words):
        x ^= (x << 13) & 0xFFFFFFFF
        x ^= x >> 17
        x ^= (x << 5) & 0xFFFFFFFF
        yield x


def whiten(blob: bytes) -> bytes:
    """Flusso SHLZ -> SHLW (vedi sopra)."""
    if blob[:4] != MAGIC:
        raise ValueError("non e' un flusso SHLZ")
    body = blob[HDR:] + bytes(-(len(blob) - HDR) % 4)
    words = struct.unpack(f">{len(body) // 4}I", body)
    return MAGIC_W + blob[4:HDR] + struct.pack(f">{len(words)}I", *(w ^ k for w, k in zip(words, _keystream(len(words)))))


def unwhiten(blob: bytes) -> bytes:
    """Flusso SHLW -> SHLZ, senza gli zeri aggiunti."""
    if blob[:4] != MAGIC_W:
        raise ValueError("non e' un flusso SHLW")
    clen = struct.unpack_from(">I", blob, 8)[0]
    n = (clen + 3) // 4
    if len(blob) < HDR + 4 * n:
        raise ValueError("flusso SHLW troncato")
    words = struct.unpack_from(f">{n}I", blob, HDR)
    body = struct.pack(f">{n}I", *(w ^ k for w, k in zip(words, _keystream(n))))
    return MAGIC + blob[4:HDR] + body[:clen]
