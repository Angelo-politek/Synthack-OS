"""Master compressor math: tables, constants and a bit-exact Python model of comp.S.

Everything is generated from formulas (no Elektron data):
- attack:  tau = 0.1 + 99.9 * (i/127)^2   ms   (i = 0..127)
- release: tau = 10 + 1990 * (i/127)^2.5  ms
- one-pole coefficient c = round(2^31 * exp(-1000 / (tau * 48000)))
- ratio slope = 1/R for R = 1.5, 2, 3, 4, 6, 8, 16, 20
Log domain: 2^23 units per dB (C_OCT units per octave).
"""

from __future__ import annotations

import math

FS = 48_000
M32 = 0xFFFF_FFFF
THR_K = 503_316_480      # threshold: thr = THR_K * (THR<<16) - THR_K   (0 -> -60 dB, 0x7F00 -> 0 dB)
MUP_K = 202_017_810      # makeup:    mk  = MUP_K * (MUP<<16) - MUP_K   (0 -> -24 dB, then x16)
EXP_K = -356_689_313     # log units -> octaves
C_OCT = 0x6054_5A93 >> 5  # log units per octave
LOG_T = [round(C_OCT * math.log2(1 + i / 16)) for i in range(17)]
EXP_T = [round(65536 * 2 ** (-i / 16)) for i in range(17)]
RATIOS = [1.5, 2, 3, 4, 6, 8, 16, 20]


def coef(tau_ms: float) -> int:
    return round(2**31 * math.exp(-1000 / (tau_ms * FS)))


ATTACK = [coef(0.1 + 99.9 * (i / 127) ** 2) for i in range(128)]
RELEASE = [coef(10 + 1990 * (i / 127) ** 2.5) for i in range(128)]
RATIO = [round(2**31 / r) for r in RATIOS]


def s32(v: int) -> int:
    v &= M32
    return v - (1 << 32) if v & 0x8000_0000 else v


def frac(a: int, b: int) -> int:
    """EMAC fractional product (Q31 x Q31 -> Q31, truncated)."""
    return (a * b * 2) >> 32


def frac2(a: int, b: int, c: int, d: int) -> int:
    """a*b + c*d accumulated and truncated once."""
    return ((a * b + c * d) * 2) >> 32


def ff1(x: int) -> int:
    return 32 - (x & M32).bit_length()


class Preset:
    """Compressor constants from UI values THR ATK REL MUP (0..0x7F00) and ratio index 0..7."""

    def __init__(self, thr: int, atk: int, rel: int, mup: int, ratio_index: int):
        self.thr = frac(THR_K, s32(thr << 16)) - THR_K
        self.slope = RATIO[ratio_index]
        self.rel = RELEASE[rel >> 8]
        self.att = ATTACK[atk >> 8]
        self.mk = frac(MUP_K, s32(mup << 16)) - MUP_K
        # rilevatore per blocco (v0.8.1): i due filtri per campione risolti su 32 campioni
        self.a32 = self.att
        self.r32 = self.rel
        for _ in range(5):
            self.a32 = frac(self.a32, self.a32)
            self.r32 = frac(self.r32, self.r32)
        k, rn = 0, self.rel                      # K = (1-a) * sum r^n a^(32-n), n = 1..32
        for _ in range(32):
            k = frac2(self.att, k, (1 << 31) - 1 - self.att, rn)
            rn = frac(rn, self.rel)
        self.k = k


class Compact:
    """Same steps and truncations as comp.S: 32 ADC samples in, VCA gain G (Q12, 65536 = x16) out.

    Detector per block (v0.8.1): the block peak (as the Digitakt, |x| = x ^ (x >> 31), floor 256) drives
    the per-sample hold/release and attack filters solved over 32 samples with a constant input:
    st = gr + r^32 * min(st - gr, 0), at = gr + a^32 * (at - gr) + K * min(st - gr, 0).
    The gain was already applied once per block (VCA control voltages)."""

    def __init__(self, pr: Preset):
        self.pr = pr
        self.rel_state = 0
        self.att_state = 0

    @staticmethod
    def log(x: int) -> int:
        lz = ff1(x)
        m = (x << (lz - 1)) & M32                # [2^30, 2^31)
        i = (m >> 26) & 15
        f = (m & 0x03FF_FFFF) << 5
        return LOG_T[i] + frac(LOG_T[i + 1] - LOG_T[i], f) - lz * C_OCT

    def block(self, left: list[int], right: list[int]) -> int:
        pr = self.pr
        st, at = self.rel_state, self.att_state
        hi, lo = max(left + right), min(left + right)
        x = max(s32(hi ^ (hi >> 31)), s32(lo ^ (lo >> 31)), 256)
        lg = self.log(x)
        y = lg if pr.thr > lg else frac(pr.slope, lg - pr.thr) + pr.thr
        gr = y - lg
        d = min(st - gr, 0)
        at = gr + frac2(pr.a32, at - gr, pr.k, d)
        st = gr + frac(pr.r32, d)
        self.rel_state, self.att_state = st, at
        v = frac(EXP_K, pr.mk + at)
        sh, i, f = v >> 23, (v >> 19) & 15, (v & 0x7_FFFF) << 12
        g = EXP_T[i] + frac(EXP_T[i + 1] - EXP_T[i], f)
        return g >> sh
