import struct
import wave

from wav import write_q31


def test_write_q31_roundtrip(tmp_path):
    samples = [0, 2**30, -(2**30), 2**31 - 1, -(2**31)]
    path = tmp_path / "x.wav"
    peak = write_q31(path, samples)
    with wave.open(str(path)) as w:
        assert (w.getnchannels(), w.getsampwidth(), w.getframerate()) == (1, 4, 48_000)
        data = struct.unpack("<5i", w.readframes(5))
    assert list(data) == samples
    assert abs(peak) < 0.01                                   # picco = fondo scala = 0 dBFS


def test_normalize_to_minus_1_dbfs(tmp_path):
    path = tmp_path / "y.wav"
    peak = write_q31(path, [1000, -500], normalize=True)
    with wave.open(str(path)) as w:
        a, b = struct.unpack("<2i", w.readframes(2))
    assert abs(a / 2**31 - 10 ** (-1 / 20)) < 1e-6
    assert b == -a // 2 or b == -(a // 2)
    assert peak < -120
