"""Test del nucleo EMAC contro la semantica del reference manual (cap. 5).

Notazione Q31: 0x4000_0000 = +0.5, 0x2000_0000 = +0.25, 0x8000_0000 = -1.0.
"""

from emac import FI, OMC, RT, SU, V, Z, EmacState

FRAC = FI | OMC          # 0xA0: modalita' usata dal motore audio della Syntakt


def frac_state(macsr=FRAC):
    e = EmacState()
    e.load_macsr(macsr)
    return e


def test_half_times_half_is_quarter():
    e = frac_state()
    e.load_acc(0, 0)
    e.mac(0, 0x4000_0000, 0x4000_0000, sub=False, long=True)
    assert e.store_acc(0) == 0x2000_0000


def test_msac_subtracts():
    e = frac_state()
    e.load_acc(1, 0x4000_0000)                       # 0.5
    e.mac(1, 0x4000_0000, 0x4000_0000, sub=True, long=True)
    assert e.store_acc(1) == 0x2000_0000             # 0.5 - 0.25


def test_linear_interpolation_like_the_oscillator():
    # acc = y0 + f*y1 - f*y0, con y0 = 0.25, y1 = 0.75, f = 0.5 -> 0.5
    e = frac_state()
    y0, y1, f = 0x2000_0000, 0x6000_0000, 0x4000_0000
    e.load_acc(0, y0)
    e.mac(0, f, y1, sub=False, long=True)
    e.mac(0, f, y0, sub=True, long=True)
    assert e.store_acc(0) == 0x4000_0000


def test_minus_one_squared_saturates_on_store():
    # -1 * -1 = +1.0, non rappresentabile in Q31: con OMC lo store satura a 0x7FFFFFFF
    e = frac_state()
    e.load_acc(0, 0)
    e.mac(0, 0x8000_0000, 0x8000_0000, sub=False, long=True)
    assert e.acc[0] > 0
    assert e.store_acc(0) == 0x7FFF_FFFF


def test_store_without_omc_wraps():
    e = frac_state(FI)
    e.load_acc(0, 0)
    e.mac(0, 0x8000_0000, 0x8000_0000, sub=False, long=True)
    assert e.store_acc(0) == 0x8000_0000


def test_accumulator_keeps_8_bits_below_q31():
    # In frazionario l'accumulatore e' Q39: 2^-31 * 0.5 = 2^-32 e' rappresentabile (= 2^7)
    e = frac_state()
    e.load_acc(0, 0)
    e.mac(0, 0x0000_0001, 0x4000_0000, sub=False, long=True)
    assert e.acc[0] == 0x80


def test_truncate_vs_convergent_rounding_on_mac():
    # prodotto grezzo = 1 * 0x00C00000 * 2 = 0x1800000: sotto i 40 bit avanza esattamente
    # meta' LSB (0x800000) e la parte alta e' dispari (1)
    e = frac_state()                                  # R/T = 0: tronca
    e.load_acc(0, 0)
    e.mac(0, 0x0000_0001, 0x00C0_0000, sub=False, long=True)
    assert e.acc[0] == 1
    e = frac_state(FRAC | RT)                         # R/T = 1: meta' esatta -> al pari (2)
    e.load_acc(0, 0)
    e.mac(0, 0x0000_0001, 0x00C0_0000, sub=False, long=True)
    assert e.acc[0] == 2
    e = frac_state(FRAC | RT)                         # parte alta pari (0): resta 0
    e.load_acc(0, 0)
    e.mac(0, 0x0000_0001, 0x0040_0000, sub=False, long=True)
    assert e.acc[0] == 0


def test_word_operands_use_upper_or_lower_half():
    e = frac_state()
    e.load_acc(0, 0)
    # Ry = {0x4000, 0x2000}: upper = 0.5, lower = 0.25 ; Rx lower = 0.5
    e.mac(0, 0x4000_2000, 0x0000_4000, sub=False, long=False, uly=True, ulx=False)
    assert e.store_acc(0) == 0x2000_0000
    e.load_acc(0, 0)
    e.mac(0, 0x4000_2000, 0x0000_4000, sub=False, long=False, uly=False, ulx=False)
    assert e.store_acc(0) == 0x1000_0000


def test_flags_zero_and_overflow_sticky():
    e = frac_state()
    e.load_acc(0, 0)
    assert e.macsr & Z
    e.load_acc(2, 0x7FFF_FFFF)
    for _ in range(300):                              # spinge oltre i 48 bit -> PAV2 e V
        e.mac(2, 0x7FFF_FFFF, 0x7FFF_FFFF, sub=False, long=True)
    assert e.macsr & V
    assert e.macsr & (1 << (8 + 2))


def test_signed_integer_mode():
    e = EmacState()                                   # MACSR = 0: intero con segno
    e.load_acc(0, 10)
    e.mac(0, -3 & 0xFFFF_FFFF, 7, sub=False, long=True)
    assert e.store_acc(0) == (10 - 21) & 0xFFFF_FFFF


def test_accext_roundtrip_fractional():
    e = frac_state()
    e.acc[0] = -0x1234_5678_9A                         # valore a 48 bit qualsiasi
    e.acc[1] = 0x12_3456_7890
    ext = e.accext(0)
    lo0, lo1 = e.acc[0] & 0xFF, e.acc[1] & 0xFF
    e.acc[0] &= ~0xFF
    e.acc[1] &= ~0xFF
    e.load_accext(0, ext)
    assert (e.acc[0] & 0xFF, e.acc[1] & 0xFF) == (lo0, lo1)


def test_su_store_rounds_to_16_bits():
    e = frac_state(FI | SU)
    e.load_acc(0, 0x1234_8000)                        # parte bassa = 0x8000 esatto, lsb alto pari
    assert e.store_acc(0) == 0x1234
    e.load_acc(0, 0x1235_8000)                        # lsb alto dispari -> arrotonda su
    assert e.store_acc(0) == 0x1236
