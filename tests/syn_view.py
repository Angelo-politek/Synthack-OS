"""Vista SRC (pagina SYN) di una traccia con una machine scelta, nell'emulatore dell'interfaccia (OS 1.42).

    v = SynView(["sy-fm4"], machine=4)      # UI con le mod; il suono mostrato ha la machine 4 (SY FM4)
    v.record(k), v.page(1), v.title(), v.frame()

La machine del suono la decide 0x400249CE(suono): qui risponde sempre `machine` (4 = SY TONE/SY FM4, 44 = SP
TWINSHOT/SAMPLER). Gli slot della vtable di SourcePageView: 47 manopola -> descrittore, 19 titolo, 4 disegno.
"""

from __future__ import annotations

import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools" / "emu"))
import screens  # noqa: E402

SOUND_MACHINE = 0x4002_49CE
TITLE_OUT = 0x4FE0_3000
SEQ_VALUES = 0x8000_21B0                 # valori per traccia: 0x47 parole da +0xE


class SynView:
    def __init__(self, mods: list[str], machine: int):
        from unicorn import UC_HOOK_CODE
        from unicorn.m68k_const import UC_M68K_REG_A7, UC_M68K_REG_D0, UC_M68K_REG_PC
        self.ui = ui = screens.UI(mods)
        self.machine = machine

        def answer(uc, _a, _s, _d):
            sp = uc.reg_read(UC_M68K_REG_A7)
            uc.reg_write(UC_M68K_REG_D0, self.machine)
            uc.reg_write(UC_M68K_REG_A7, sp + 4)
            uc.reg_write(UC_M68K_REG_PC, struct.unpack(">I", uc.mem_read(sp, 4))[0])
        ui.uc.hook_add(UC_HOOK_CODE, answer, begin=SOUND_MACHINE, end=SOUND_MACHINE)
        self.view = ui.tab("SRC")

    def slot(self, n: int) -> int:
        return self.ui.long(self.ui.long(self.view) + 4 * n)

    def record(self, knob: int) -> int:
        return self.ui.call(self.slot(47), [self.view, knob])

    def knobs(self) -> list[int]:
        return [self.record(k) for k in range(9)]

    def pages(self) -> int:
        return (self.ui.long(self.view + 0x80) - self.ui.long(self.view + 0x7C)) // 4

    def page(self, n: int) -> None:
        self.ui.put(self.view + 0x90, ">I", n)

    def highlight(self, knob: int | None) -> None:
        """Valore in evidenza (come dopo un giro di manopola) per knob 0..7, None per nessuna."""
        for k in range(8):
            self.ui.put(self.view + 180 + 20 * k, ">i", 40 if k == knob else 0)

    def set_value(self, track: int, lix: int, value: int) -> None:
        self.ui.put(SEQ_VALUES + 2 * (0xE + track * 0x47 + lix), ">H", value)

    def title(self, fn: int | None = None) -> bytes:
        """Slot 19: std::string per valore, costruita all'indirizzo in a0 e restituita in d0; la stringa (GCC) e'
        un puntatore ai caratteri."""
        from unicorn.m68k_const import UC_M68K_REG_A0
        ui = self.ui
        ui.put(TITLE_OUT, ">I", 0)
        ui.uc.reg_write(UC_M68K_REG_A0, TITLE_OUT)
        assert ui.call(fn or self.slot(19), [self.view]) == TITLE_OUT
        return bytes(ui.uc.mem_read(ui.long(TITLE_OUT), 32)).split(b"\0")[0]

    def frame(self) -> bytes:
        self.record(0)                       # come l'OS prima di disegnare: pagine della machine
        return self.ui.draw(self.view)

    def png(self, path: Path) -> None:
        screens.png(self.frame(), path)
