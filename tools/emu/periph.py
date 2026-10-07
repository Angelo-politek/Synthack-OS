"""Modelli comportamentali delle periferiche del MCF5441x usate dal motore audio.

Come in una simulazione con modelli comportamentali al posto dei chip veri: ogni
lettura/scrittura nelle zone periferiche (0xEC.., 0xFC..) passa da qui.
Registri e significati: reference manual NXP MCF54418RM (vedi docs/re-journal.md).
Tutto cio' che non e' modellato si comporta come una semplice memoria.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from unicorn import Uc

PIT1_PCSR = 0xFC08_4000        # PIT 1: control/status, bit 2 = PIF (conteggio finito)
PIT_PIF = 0x0004

EDMA_SSRT = 0xFC04_401E        # eDMA "set START bit": scrivere n avvia il canale n
EDMA_TCD0 = 0xFC04_5000        # descrittore (TCD) del canale n = EDMA_TCD0 + 0x20*n
TCD_SADDR, TCD_NBYTES, TCD_DADDR, TCD_CITER, TCD_CSR = 0x00, 0x08, 0x10, 0x14, 0x1E
TCD_CSR_DONE = 0x0080


@dataclass
class Peripherals:
    regs: dict[int, int] = field(default_factory=dict)
    trace: list[tuple[str, int, int, int | None]] | None = None   # (R/W, addr, size, valore)
    dma_transfers: list[tuple[int, int, int, int]] = field(default_factory=list)

    # -- callback MMIO (firma richiesta da Unicorn: uc, offset, size, [value], user_data=base)

    def read(self, uc: Uc, offset: int, size: int, base: int) -> int:
        addr = base + offset
        value = self.regs.get(addr, 0)
        if addr == PIT1_PCSR:
            value |= PIT_PIF                      # i ritardi finiscono subito
        elif addr >= EDMA_TCD0 and (addr - EDMA_TCD0) % 0x20 == TCD_CSR:
            value |= TCD_CSR_DONE                 # il DMA risulta sempre concluso
        if self.trace is not None:
            self.trace.append(("R", addr, size, None))
        return value

    def write(self, uc: Uc, offset: int, size: int, value: int, base: int) -> None:
        addr = base + offset
        self.regs[addr] = value
        if self.trace is not None:
            self.trace.append(("W", addr, size, value))
        if addr == EDMA_SSRT:
            self._run_dma(uc, value & 0x3F)

    # -- eDMA: esegue subito tutto il trasferimento descritto dal TCD

    def _reg(self, addr: int, size: int) -> int:
        """Ricompone un registro da scritture di dimensione diversa (es. 2+2 byte)."""
        if addr in self.regs:
            return self.regs[addr]
        if size == 4:
            return (self.regs.get(addr, 0) << 16) | self.regs.get(addr + 2, 0)
        return 0

    def _run_dma(self, uc: Uc, ch: int) -> None:
        tcd = EDMA_TCD0 + 0x20 * ch
        src = self._reg(tcd + TCD_SADDR, 4)
        dst = self._reg(tcd + TCD_DADDR, 4)
        nbytes = self._reg(tcd + TCD_NBYTES, 4)
        citer = self.regs.get(tcd + TCD_CITER, 0)
        # Con ELINK (bit 15) il campo CITER e' di 9 bit; senza, di 15 (ref. manual cap. 19)
        loops = citer & (0x1FF if citer & 0x8000 else 0x7FFF)
        total = nbytes * loops
        uc.mem_write(dst, bytes(uc.mem_read(src, total)))
        self.dma_transfers.append((ch, src, dst, total))
