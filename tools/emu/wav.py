"""Scrittura di campioni Q31 (int32 con segno, 1.0 = 2^31) in file WAV."""

from __future__ import annotations

import struct
import wave
from pathlib import Path

SAMPLE_RATE = 48_000


def write_q31(path: Path, samples: list[int], normalize: bool = False, rate: int = SAMPLE_RATE) -> float:
    """Scrive un WAV mono a 32 bit. Con normalize=True porta il picco a -1 dBFS.

    Ritorna il picco originale in dBFS (utile per capire il livello reale del motore).
    """
    import math
    peak = max((abs(s) for s in samples), default=0)
    peak_db = 20 * math.log10(peak / 2**31) if peak else float("-inf")
    if normalize and peak:
        gain = (2**31 - 1) * 10 ** (-1 / 20) / peak
        samples = [int(s * gain) for s in samples]
    clipped = [max(-(2**31), min(2**31 - 1, s)) for s in samples]
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(4)
        w.setframerate(rate)
        w.writeframes(struct.pack(f"<{len(clipped)}i", *clipped))
    return peak_db
