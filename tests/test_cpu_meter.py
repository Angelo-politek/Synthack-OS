"""cpu-meter: interrupt audio con i ganci d'ingresso e d'uscita, misura con DTCN0 simulato, testo sulla pagina."""

import struct
import sys
from pathlib import Path

import pytest

pytest.importorskip("unicorn")

ROOT = Path(__file__).resolve().parent
SY = ROOT.parent / "firmware" / "Syntakt_OS1.42.syx"
pytestmark = pytest.mark.skipif(not SY.exists(), reason="OS stock assente")
sys.path[:0] = [str(ROOT.parent / "tools" / "emu")]

DTCN0 = 0xFC07_000C


def timer(m, step):
    """DTCN0 che avanza di `step` a ogni lettura di cpu-meter (ingresso, poi uscita: durata = step). Le letture
    dell'OS (0x400822B4) vedono lo stesso valore senza farlo avanzare."""
    from unicorn import UC_HOOK_MEM_READ
    from unicorn.m68k_const import UC_M68K_REG_PC
    t = [1000]
    lo, hi = m.sym["cm_entry"], m.sym["cm_exit"] + 0x10

    def rd(uc, acc, addr, size, value, _):
        if lo <= uc.reg_read(UC_M68K_REG_PC) < hi:
            t[0] += step
        uc.mem_write(DTCN0, struct.pack(">I", t[0] & 0xFFFF_FFFF))
    m.uc.hook_add(UC_HOOK_MEM_READ, rd, begin=DTCN0, end=DTCN0 + 3)


def test_interrupt_runs_and_measures():
    import isr
    stock, m = isr.Isr([]), isr.Isr(["cpu-meter"])
    timer(m, 50)                                                # prima della scena: tutti i blocchi misurati
    for x in (stock, m):
        x.scene("max")
    a, b = stock.run(), m.run()
    assert b.n - a.n <= 40, (a.n, b.n)                           # costo per blocco
    # stessa uscita dell'interrupt: bus d'uscita e copia dei parametri
    for addr, n in ((0x8000_DAD0, 0x100), (0x8000_21B0, 0x300)):
        assert stock.uc.mem_read(addr, n) == m.uc.mem_read(addr, n)
    sym = m.sym
    m.fast(1100)                                               # seconda finestra: la prima parte da t0 = 0
    pub = struct.unpack(">3I", m.uc.mem_read(sym["cm_pub"], 12))
    # ogni lettura avanza di 50: ingresso -> uscita 50, ingresso -> ingresso 100 (due letture per blocco)
    assert pub == (512 * 50, 512 * 100, 50), pub


def test_text_on_the_parameter_page(tmp_path):
    import screens
    ui = screens.UI(["cpu-meter"])
    ui.put(ui.sym["cm_pub"], ">3I", 512 * 934, 512 * 1000, 971)   # 93.4 % di media, 97.1 % di picco
    frame = ui.draw(ui.view)
    screens.png(frame, tmp_path / "meter.png")
    rows = screens.pixels(frame)
    lit = [(x, y) for y in range(8) for x in range(80, 128) if rows[y][x]]
    assert lit, "nessun testo in alto a destra"
    ui.put(ui.sym["cm_pub"], ">3I", 0, 0, 0)                      # niente misure: pagina stock
    stock = screens.UI([])
    assert ui.draw(ui.view) == stock.draw(stock.view)
