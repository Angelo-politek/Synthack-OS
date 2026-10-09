"""Strumento di misura delle parti analogiche: verifica su registrazioni sintetiche."""

import math
import sys
import wave
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools" / "measure"))
import analog  # noqa: E402

RATE = 48000


def write(path, x):
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(RATE)
        w.writeframes((np.clip(x, -1, 1) * 32767).astype("<i2").tobytes())


def test_pitch_and_exponential_fit(tmp_path):
    files = []
    for v in (0, 32, 64, 96, 127):
        f = 20 * math.exp(0.05 * v)
        t = np.arange(RATE) / RATE
        p = tmp_path / f"freq{v:03d}.wav"
        write(p, 0.5 * np.sin(2 * math.pi * f * t) + 0.001 * np.random.default_rng(v).standard_normal(RATE))
        files.append(p)
        x, rate = analog.load(p)
        assert abs(analog.pitch(x, rate) / f - 1) < 0.002
    vals = [analog.value_of(p) for p in files]
    a, b = analog.fit_exp(vals, [analog.pitch(*analog.load(p)) for p in files])
    assert abs(a / 20 - 1) < 0.01 and abs(b / 0.05 - 1) < 0.01


def test_attack_and_decay(tmp_path):
    t = np.arange(3 * RATE) / RATE
    tone = np.sin(2 * math.pi * 440 * t)
    att = np.clip(t / 0.25, 0, 1)                                  # rampa di 250 ms
    dec = np.where(t < 0.25, 1, np.exp(-(t - 0.25) * math.log(1000) / 1.2))   # -60 dB in 1.2 s
    write(tmp_path / "atk1.wav", 0.5 * tone * att)
    write(tmp_path / "dec1.wav", 0.5 * tone * dec + 1e-4 * np.random.default_rng(1).standard_normal(len(t)))
    x, r = analog.load(tmp_path / "atk1.wav")
    assert abs(analog.attack_ms(x, r) - 250) < 10
    x, r = analog.load(tmp_path / "dec1.wav")
    assert abs(analog.t60_ms(x, r) - 1200) < 40


def test_lfo_period(tmp_path):
    t = np.arange(10 * RATE) / RATE
    for per in (0.125, 0.5, 2.0):
        sq = np.where(np.sin(2 * math.pi * t / per) >= 0, 1.0, 0.2)       # LFO quadro su VOL
        write(tmp_path / "lfo.wav", 0.5 * np.sin(2 * math.pi * 330 * t) * sq)
        x, r = analog.load(tmp_path / "lfo.wav")
        assert abs(analog.period_s(x, r) / per - 1) < 0.005, per
