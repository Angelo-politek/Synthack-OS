"""Misure sulle registrazioni della Syntakt per le parti analogiche (legge non ricavabile dal codice).

    python tools/measure/analog.py freq rec/freq*.wav     # auto-oscillazione del filtro: Hz per valore
    python tools/measure/analog.py env  rec/atk*.wav      # attacco: dall'inizio al picco
    python tools/measure/analog.py env  rec/dec*.wav      # decadimento: tempo a -60 dB
    python tools/measure/analog.py period rec/lfo*.wav    # periodo di una modulazione d'ampiezza (LFO)

Il valore del parametro (0..127) e' il numero nel nome del file: freq064.wav -> 64.
"""

from __future__ import annotations

import math
import re
import sys
import wave
from pathlib import Path

import numpy as np


def load(path: Path) -> tuple[np.ndarray, int]:
    with wave.open(str(path), "rb") as w:
        n, ch, width, rate = w.getnframes(), w.getnchannels(), w.getsampwidth(), w.getframerate()
        raw = w.readframes(n)
    if width == 3:                                  # 24 bit: estende a 32
        b = np.frombuffer(raw, dtype=np.uint8).reshape(-1, 3)
        x = (b[:, 0].astype(np.int32) << 8 | b[:, 1].astype(np.int32) << 16 | b[:, 2].astype(np.int32) << 24) >> 8
        x = x.astype(np.float64) / 2**23
    else:
        dt = {1: np.uint8, 2: np.int16, 4: np.int32}[width]
        x = np.frombuffer(raw, dtype=dt).astype(np.float64)
        x = (x - 128) / 128 if width == 1 else x / float(2 ** (8 * width - 1))
    x = x.reshape(-1, ch).mean(axis=1)
    return x, rate


def value_of(path: Path) -> int:
    m = re.findall(r"\d+", path.stem)
    if not m:
        raise SystemExit(f"{path.name}: manca il valore del parametro nel nome")
    return int(m[-1])


def pitch(x: np.ndarray, rate: int) -> float:
    """Frequenza fondamentale della parte centrale (FFT con finestra di Hann, interpolazione parabolica)."""
    seg = x[len(x) // 10: 9 * len(x) // 10]        # senza attacco e coda
    seg = seg * np.hanning(len(seg))
    n = 1 << (int(math.log2(len(seg))) + 4)         # zero-padding x16
    spec = np.abs(np.fft.rfft(seg, n))
    spec[:max(1, int(2 * n / rate))] = 0           # sotto i 2 Hz: componente continua
    k = int(np.argmax(spec))
    a, b, c = spec[k - 1], spec[k], spec[k + 1]
    p = 0.5 * (a - c) / (a - 2 * b + c) if a - 2 * b + c else 0.0
    return (k + p) * rate / n


def envelope(x: np.ndarray, rate: int, win_ms: float = 1.0) -> np.ndarray:
    w = max(1, int(rate * win_ms / 1000))
    e = np.sqrt(np.convolve(x * x, np.ones(w) / w, mode="same"))
    return e


def attack_ms(x: np.ndarray, rate: int) -> float:
    e = envelope(x, rate)
    peak = e.max()
    start = int(np.argmax(e > 0.01 * peak))
    top = int(np.argmax(e > 0.98 * peak))
    return (top - start) * 1000 / rate


def t60_ms(x: np.ndarray, rate: int) -> float:
    """Decadimento esponenziale: 60 dB diviso la pendenza (regressione tra -6 e -40 dB dal picco)."""
    e = envelope(x, rate, 5.0)
    i0 = int(np.argmax(e))
    db = 20 * np.log10(np.maximum(e[i0:], 1e-12) / e[i0])
    k6, k40 = int(np.argmax(db < -6)), int(np.argmax(db < -40))
    if not 0 < k6 < k40 - 10:
        return float("nan")
    sel = np.arange(k6, k40)                        # fino al primo -40 dB: niente rumore di fondo
    slope = np.polyfit(sel / rate, db[sel], 1)[0]   # dB al secondo
    return -60 / slope * 1000


def period_s(x: np.ndarray, rate: int) -> float:
    """Periodo della modulazione d'ampiezza: primo massimo dell'autocorrelazione dell'inviluppo."""
    step = max(1, rate // 1000)                     # inviluppo a 1 kHz
    e = envelope(x, rate, 5.0)[::step]
    e = e - e.mean()
    n = len(e)
    f = np.fft.rfft(e, 2 * n)
    ac = np.fft.irfft(f * np.conj(f))[:n]
    ac /= ac[0]
    ac = np.convolve(ac, np.ones(9) / 9, mode="same")   # niente massimi spuri dall'ondulazione del tono
    neg = int(np.argmax(ac < 0))                    # dopo il primo passaggio sotto zero
    if neg == 0:
        return float("nan")
    seg = ac[neg:n // 2]
    top = seg.max()
    peaks = [i for i in range(1, len(seg) - 1) if seg[i - 1] < seg[i] >= seg[i + 1] and seg[i] >= 0.8 * top]
    k = neg + (peaks[0] if peaks else int(np.argmax(seg)))   # il primo picco alto: non un multiplo
    a, b, c = ac[k - 1], ac[k], ac[k + 1]
    p = 0.5 * (a - c) / (a - 2 * b + c) if a - 2 * b + c else 0.0
    return (k + p) * step / rate


def fit_exp(vals: list[int], hz: list[float]) -> tuple[float, float]:
    b, a = np.polyfit(vals, np.log(hz), 1)
    return math.exp(a), b


def main(argv: list[str]) -> int:
    if len(argv) < 2 or argv[0] not in ("freq", "env", "period"):
        print(__doc__)
        return 1
    files = sorted((Path(f) for f in argv[1:]), key=value_of)
    if argv[0] == "freq":
        vals, hz = [], []
        for f in files:
            x, rate = load(f)
            vals.append(value_of(f))
            hz.append(pitch(x, rate))
            print(f"{f.name:20s} valore {vals[-1]:3d}  {hz[-1]:9.2f} Hz")
        if len(vals) >= 3:
            a, b = fit_exp(vals, hz)
            print(f"\nf = {a:.4f} Hz * e^({b:.6f} * valore)   ({math.log(2) / b:.2f} valori per ottava)")
            for v, f in zip(vals, hz):
                print(f"  {v:3d}: misura {f:9.2f}  modello {a * math.exp(b * v):9.2f}  scarto {100 * (f / (a * math.exp(b * v)) - 1):+.2f}%")
    elif argv[0] == "period":
        for f in files:
            x, rate = load(f)
            print(f"{f.name:24s} periodo {period_s(x, rate) * 1000:9.1f} ms")
    else:
        for f in files:
            x, rate = load(f)
            print(f"{f.name:20s} valore {value_of(f):3d}  attacco {attack_ms(x, rate):9.1f} ms  "
                  f"decadimento a -60 dB {t60_ms(x, rate):9.1f} ms")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
