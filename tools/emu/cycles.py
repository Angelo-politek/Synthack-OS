"""Stima dei cicli dell'interrupt audio (CPU #1): istruzioni + mancate delle cache + accessi fuori cache.

Le istruzioni contate da isr.py non sono il tempo. Sul dispositivo pesano le mancate delle cache e gli accessi
fuori cache. Modello (MCF54418, core V4e, configurazione dell'OS a 0x40000554):

- cache istruzioni 8 KB e dati 8 KB (datasheet MCF54418), 4 vie, righe da 16 B, LRU;
- CACR = 0xA50CE100: istruzioni in cache ovunque (IDCM = 0); dati fuori cache per default (DDCM = 10,
  inhibited precise); ACR0 = 0x4007E020: dati in cache (copyback) solo in 0x40000000-0x47FFFFFF.
  Le linee di delay e riverbero dell'OS (0x4D570000, 0x4FC00000) sono quindi fuori cache;
- SRAM interna 0x80000000-0x8000FFFF: nessuna mancata, ne' per i dati ne' per le istruzioni (il codice copiato in
  SRAM, come il kernel di LFO3 di Synfact, non passa dalla cache istruzioni: dal 2026-11-05; fino ad allora contava
  come codice in DDR);
- RAM condivisa 0x10000000 e periferiche 0xFC000000: fuori cache, IO cicli per accesso (stima);
- 0x4FE00000-0x4FFFFFFF: impalcatura dell'emulatore (pila, bitmap), non conta.

Base: istruzioni pesate di isr.py (movem = registri, divisioni 20) per CPI. Taratura: l'OS stock a riposo
misura ~89 % del blocco sul dispositivo (docs/audio-path.md), ~148 000 cicli a 250 MHz. Con un solo punto
misurato CPI e MISS non si separano: calibrate(cpi) da' MISS per un CPI scelto. Un secondo punto misurato
(una build con mod, DTIM0) fissa entrambi.

    python tools/emu/cycles.py [--scene rest|typ|max] [mod ...]

Le istruzioni dell'EMAC eseguite in Python (emac.py) non passano dai ganci di memoria: i loro operandi
sono quasi sempre in SRAM (bus delle tracce). Il codice dell'EMAC conta comunque nelle righe istruzioni.
"""

from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import isr  # noqa: E402
from unicorn import UC_HOOK_CODE, UC_HOOK_MEM_READ, UC_HOOK_MEM_WRITE  # noqa: E402

CLOCK = 250_000_000
BLOCK = CLOCK * 32 // 48_000          # cicli in un blocco da 32 campioni: 166 666
STOCK_LOAD = 0.89                     # misurato sul dispositivo, OS stock a riposo
IO = 10                               # cicli per accesso alla RAM condivisa o alle periferiche (stima)
CPIS = (1.0, 1.5)                     # estremi plausibili per il CPI senza mancate
SRAM_LO, SRAM_HI = 0x8000_0000, 0x8001_0000   # SRAM interna: niente mancate, dati o istruzioni


class Cache:
    def __init__(self, size=8 * 1024, ways=4, line=16):
        self.sets, self.ways, self.shift = size // (ways * line), ways, line.bit_length() - 1
        self.tags = [[] for _ in range(self.sets)]
        self.miss = 0

    def touch(self, addr):
        ln = addr >> self.shift
        s = self.tags[ln % self.sets]
        if s and s[-1] == ln:
            return
        if ln in s:
            s.remove(ln)
        else:
            self.miss += 1
            if len(s) >= self.ways:
                del s[0]
        s.append(ln)

    def flush(self):
        self.tags = [[] for _ in range(self.sets)]


def region(a):
    """'c' dati in cache, 'u' DDR fuori cache, 'io' RAM condivisa / periferiche, None SRAM o impalcatura."""
    if 0x4000_0000 <= a < 0x4800_0000:
        return "c"
    if 0x4800_0000 <= a < 0x4FE0_0000:
        return "u"
    if 0x1000_0000 <= a < 0x1100_0000 or a >= 0xFC00_0000:
        return "io"
    return None


class Count:
    def __init__(self, w=0, imiss=0, dmiss=0, ddr=0, io=0):
        self.w, self.imiss, self.dmiss, self.ddr, self.io = w, imiss, dmiss, ddr, io

    def cycles(self, cpi, miss):
        """Cicli stimati. DDR fuori cache: un accesso costa quanto una riga mancata."""
        return cpi * self.w + miss * (self.imiss + self.dmiss + self.ddr) + IO * self.io

    def __repr__(self):
        return (f"weighted {self.w}  I-miss {self.imiss}  D-miss {self.dmiss}  DDR uncached {self.ddr}  "
                f"IO {self.io}")


def calibrate(stock: Count, cpi: float) -> float:
    """MISS (cicli per riga mancata) che porta l'OS stock a STOCK_LOAD del blocco con questo CPI."""
    return (STOCK_LOAD * BLOCK - cpi * stock.w - IO * stock.io) / max(1, stock.imiss + stock.dmiss + stock.ddr)


class Cycles:
    def __init__(self, m: isr.Isr):
        self.m, self.ic, self.dc = m, Cache(), Cache()
        self.ddr = self.io = 0
        self.on = False
        m.uc.hook_add(UC_HOOK_CODE, self._fetch)
        m.uc.hook_add(UC_HOOK_MEM_READ | UC_HOOK_MEM_WRITE, self._data)

    def _fetch(self, uc, pc, size, _):
        if self.on and not SRAM_LO <= pc < SRAM_HI:
            self.ic.touch(pc)
            if (pc + size - 1) >> 4 != pc >> 4:
                self.ic.touch(pc + size - 1)

    def _data(self, uc, access, addr, size, value, _):
        if not self.on:
            return
        r = region(addr)
        if r == "c":
            self.dc.touch(addr)
        elif r == "u":
            self.ddr += 1
        elif r == "io":
            self.io += 1

    def run(self, cold=True) -> Count:
        """Un blocco profilato. cold: cache vuote all'inizio, come dopo l'interfaccia tra due blocchi (con 8 KB
        il percorso dell'interrupt non ci sta comunque: caldo o freddo cambia poco)."""
        if cold:
            self.ic.flush()
            self.dc.flush()
        i0, d0, u0, o0 = self.ic.miss, self.dc.miss, self.ddr, self.io
        self.on = True
        try:
            st = self.m.run()
        finally:
            self.on = False
        self.stats = st
        return Count(st.w, self.ic.miss - i0, self.dc.miss - d0, self.ddr - u0, self.io - o0)


def measure(mods=(), scene="max", cold=True) -> Count:
    m = isr.Isr(list(mods))
    m.scene(scene)
    c = Cycles(m)
    c.run()                               # stato a regime sul percorso dell'interrupt
    return c.run(cold)


def report(counts: dict[str, Count], out=sys.stdout):
    stock = counts.get("stock") or measure((), "rest")
    for cpi in CPIS:
        miss = calibrate(stock, cpi)
        out.write(f"CPI {cpi}: MISS {miss:.0f} cycles per line (stock at rest = {STOCK_LOAD:.0%})\n")
        for name, c in counts.items():
            cy = c.cycles(cpi, miss)
            out.write(f"  {name:14s} {cy:9.0f} cycles  {100 * cy / BLOCK:5.1f} %\n")


def main(argv):
    scene = "max"
    if "--scene" in argv:
        i = argv.index("--scene")
        scene = argv[i + 1]
        argv = argv[:i] + argv[i + 2:]
    counts = {"stock": measure((), "rest"), "+".join(argv) or "stock " + scene: measure(argv, scene)}
    for k, c in counts.items():
        print(f"{k}: {c}")
    report(counts)


if __name__ == "__main__":
    main(sys.argv[1:])
