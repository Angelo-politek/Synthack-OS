"""Harness del motore audio della Syntakt (sezione 7, OS 1.41) su Unicorn.

Fa girare il codice ORIGINALE della CPU audio: avvio completo dall'entry, poi un
interrupt per ogni blocco audio. Le parti che dipendono da hardware assente sono
sostituite da modelli (periph.py) o da scorciatoie documentate qui sotto.

    eng = Engine()            # carica la sezione 7
    eng.boot()                # avvio "fedele", con handshake simulato della CPU #1
    out = eng.render_block(params)   # 0x1B0 B di parametri -> 8 voci x 32 campioni Q31
"""

from __future__ import annotations

import struct
from dataclasses import dataclass, field
from pathlib import Path

from unicorn import UC_ARCH_M68K, UC_HOOK_CODE, UC_HOOK_MEM_WRITE, UC_MODE_BIG_ENDIAN, Uc, UcError
from unicorn.m68k_const import UC_CPU_M68K_CFV4E, UC_M68K_REG_A7, UC_M68K_REG_D0, UC_M68K_REG_PC, UC_M68K_REG_SR

import memmap
from periph import Peripherals

# --- indirizzi del codice (sezione 7, OS 1.41) — vedi docs/re-journal.md
AUDIO_ISR = 0x4000_0934          # gestore dell'interrupt DTIM0 (vettore 96)
IDLE_LOOP = 0x4000_106E          # "bra.s *" finale di audio_main: avvio concluso
MEMCLR = 0x4000_9F08             # memclr(ptr, len), byte per byte
EXT_CHIP_INIT = 0x4000_0706      # invio dati via GPIO a un chip esterno (FPGA?)
WAIT_TICK_POLL = 0x4000_0B34     # ciclo che aspetta che l'interrupt azzeri TICK_FLAG
TICK_FLAG = 0x4404_F750
VBR = 0x4000_0000
VECTOR_DTIM0 = 96

# --- RAM condivisa con la CPU #1 (lato CPU #2 parte da 0)
MBOX_HANDSHAKE = 0x0             # "HO"/"HA"/"NO" scritti dal motore, "B0" atteso
MBOX_COMMAND = 0x2               # comando dalla CPU #1: 2 = carica blocco, 3 = avvio
MBOX_STATUS = 0x8                # codice di avanzamento 1..12
PARAMS_SIZE = 0x1B0              # blocco parametri scritto dalla CPU #1 a ogni interrupt
AUDIO_OUT = 0x1B0                # dove il DMA deposita l'audio (8 voci x 32 x 4 B)
AUDIO_SIZE = 0x400
VOICES, BLOCK = 8, 32

BOOT_STEPS = list(range(3, 13))  # 1, poi 3..12 se l'handshake va a buon fine


class EngineError(RuntimeError):
    pass


@dataclass
class Engine:
    section7_path: Path | None = None
    trace_periph: bool = False
    uc: Uc = field(init=False)
    periph: Peripherals = field(init=False)
    status: list[int] = field(default_factory=list, init=False)
    ticks: int = field(default=0, init=False)

    def __post_init__(self) -> None:
        sec = memmap.load_section7(self.section7_path or memmap.default_section7())
        self.periph = Peripherals(trace=[] if self.trace_periph else None)
        uc = self.uc = Uc(UC_ARCH_M68K, UC_MODE_BIG_ENDIAN, cpu=UC_CPU_M68K_CFV4E)
        for r in memmap.REGIONS:
            if r.name.startswith("periph"):
                uc.mmio_map(r.base, r.size, self.periph.read, r.base, self.periph.write, r.base)
            else:
                uc.mem_map(r.base, r.size)
        uc.mem_write(memmap.LOAD_ADDR, sec)

        uc.hook_add(UC_HOOK_MEM_WRITE, self._cpu1_mailbox, begin=MBOX_STATUS, end=MBOX_STATUS + 1)
        uc.hook_add(UC_HOOK_CODE, self._fast_memclr, begin=MEMCLR, end=MEMCLR)
        uc.hook_add(UC_HOOK_CODE, self._ext_chip_ok, begin=EXT_CHIP_INIT, end=EXT_CHIP_INIT)
        uc.hook_add(UC_HOOK_CODE, self._tick, begin=WAIT_TICK_POLL, end=WAIT_TICK_POLL)

    # ------------------------------------------------------------------ utilità

    def rd32(self, addr: int) -> int:
        return int.from_bytes(self.uc.mem_read(addr, 4), "big")

    def _return_from_call(self, d0: int | None = None) -> None:
        """Simula un 'rts': torna al chiamante (l'indirizzo di ritorno e' in cima allo stack)."""
        sp = self.uc.reg_read(UC_M68K_REG_A7)
        if d0 is not None:
            self.uc.reg_write(UC_M68K_REG_D0, d0)
        self.uc.reg_write(UC_M68K_REG_PC, self.rd32(sp))
        self.uc.reg_write(UC_M68K_REG_A7, sp + 4)

    def _run(self, start: int, until: int, budget: int = 200_000_000) -> None:
        pc, step = start, 5_000_000
        for _ in range(budget // step):
            try:
                self.uc.emu_start(pc, until, count=step)
            except UcError as e:
                raise EngineError(f"{e} a PC={self.uc.reg_read(UC_M68K_REG_PC):08X}") from e
            pc = self.uc.reg_read(UC_M68K_REG_PC)
            if pc == until:
                return
        raise EngineError(f"budget di istruzioni esaurito, PC={pc:08X}")

    # ------------------------------------------------------------ "CPU #1" e scorciatoie

    def _cpu1_mailbox(self, uc, access, addr, size, value, _ud) -> None:
        """Facciamo la parte della CPU #1 nell'handshake (protocollo come Digitone mk1)."""
        if addr != MBOX_STATUS or size != 2:
            return
        self.status.append(value)
        if value == 5:
            uc.mem_write(MBOX_HANDSHAKE, b"B0")
        elif value == 10:
            uc.mem_write(MBOX_COMMAND, struct.pack(">H", 3))

    def _fast_memclr(self, uc, addr, size, _ud) -> None:
        """memclr grandi (64 MB all'avvio) in Python invece che byte per byte: stesso risultato."""
        sp = uc.reg_read(UC_M68K_REG_A7)
        dst, n = self.rd32(sp + 4), self.rd32(sp + 8)
        if n < 0x10000:
            return
        for off in range(0, n, 1 << 20):
            uc.mem_write(dst + off, bytes(min(1 << 20, n - off)))
        self._return_from_call()

    def _ext_chip_ok(self, uc, addr, size, _ud) -> None:
        """Il chip esterno configurato via GPIO non esiste qui: rispondiamo 'tutto ok' (0)."""
        self._return_from_call(d0=0)

    def _tick(self, uc, addr, size, _ud) -> None:
        """Il codice aspetta un fronte del clock esterno: lo facciamo arrivare subito."""
        self.ticks += 1
        uc.mem_write(TICK_FLAG, bytes(4))

    # ---------------------------------------------------------------- API

    def boot(self) -> None:
        self.uc.reg_write(UC_M68K_REG_SR, 0x2700)       # supervisore, come dopo un reset
        self.uc.reg_write(UC_M68K_REG_A7, 0x47F0_0000)
        self._run(memmap.ENTRY, IDLE_LOOP)
        if self.status[-len(BOOT_STEPS):] != BOOT_STEPS:
            raise EngineError(f"handshake inatteso: {self.status}")
        if self.rd32(VBR + 4 * VECTOR_DTIM0) != AUDIO_ISR:
            raise EngineError("il gestore dell'interrupt audio non e' stato installato")

    def render_block(self, params: bytes) -> list[list[int]]:
        """Un interrupt = un blocco: ritorna 8 liste di 32 campioni Q31 (int32 con segno)."""
        if len(params) != PARAMS_SIZE:
            raise ValueError(f"servono {PARAMS_SIZE} byte di parametri, non {len(params)}")
        uc = self.uc
        uc.mem_write(0, params)
        # Simuliamo l'ingresso nell'interrupt: frame d'eccezione ColdFire da 2 long
        # [formato 4 | vettore | SR] + [PC di ritorno]. L'RTE finale ci riporta a IDLE_LOOP.
        sp = 0x47F0_0000 - 8
        frame = (0x4 << 28) | (VECTOR_DTIM0 << 18) | 0x2000
        uc.mem_write(sp, struct.pack(">II", frame, IDLE_LOOP))
        uc.reg_write(UC_M68K_REG_A7, sp)
        uc.reg_write(UC_M68K_REG_SR, 0x2700)
        self._run(AUDIO_ISR, IDLE_LOOP, budget=50_000_000)
        raw = bytes(uc.mem_read(AUDIO_OUT, AUDIO_SIZE))
        samples = struct.unpack(">256i", raw)
        return [list(samples[v * BLOCK:(v + 1) * BLOCK]) for v in range(VOICES)]
