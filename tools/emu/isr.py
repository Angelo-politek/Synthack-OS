"""Interrupt audio della CPU #1 (OS 1.42) intero nell'emulatore, con profilo per routine.

Avvio come screens.UI (copia in SRAM, costruttori, sequencer, progetto nuovo), poi l'interrupt audio da
0x400A38CE al suo rte (0x400A5520) un blocco alla volta. Periferiche: trasferimento DSPI finito, CPU #2
presente, DMA gia' conclusi (le attese dell'interrupt non girano a vuoto). EMAC eseguita in Python
(tools/emu/emac.py): sui blocchi profilati da un gancio su ogni istruzione, nei blocchi veloci con ILLEGAL
sui siti gia' visti.

    m = Isr(["fx3", "fastmix"])     # OS stock + mod (con le dipendenze)
    m.scene("max")                  # livelli e mandate, smussamento a regime, 20 blocchi
    st = m.run()                    # un blocco profilato: st.n istruzioni, st.w pesate (movem = registri)
    tree(st, sys.stdout)            # chi chiama chi, istruzioni incluse e proprie

    python tools/emu/isr.py [--scene rest|typ|max] [mod ...]
"""

from __future__ import annotations

import collections
import random
import struct
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), str(HERE.parents[1] / "tools" / "unpack")]
import screens  # noqa: E402
import unicorn.m68k_const as K  # noqa: E402
from emac import ILLEGAL, UnicornEmac  # noqa: E402
from unicorn import UC_HOOK_CODE, UC_HOOK_MEM_READ, UcError  # noqa: E402

ISR, RTE = 0x400A_38CE, 0x400A_5520
STACK = 0x4FF0_0000 - 256
DMA_ACTIVE = [0xFC04_53DE]             # stato di un canale eDMA letto in attesa (delay): sempre finito
ENG = 0x8000_21B0                      # copia dei parametri del motore: 142 B per traccia
VEL = 0x8000_4670                      # velocity dell'ultima nota per traccia
SMOOTH_S, SMOOTH_OUT, SMOOTH_N = 0x8000_E9B0, 0x8000_6348, 938
SET = 0x4000_DA32                      # scrittura di un parametro di kit (vparams per gli id virtuali)
FX3 = {"TYPE": 505, "SPD": 506, "DEP": 507, "TIME": 509, "FDBK": 510, "WID": 511, "DSND": 508, "RSND": 512}   # idspace
COMP_RAT = 518                                  # idspace
NAMES = {
    0x4008F242: "mix (master/FX)", 0x40096EB4: "reverb", 0x40096908: "delay", 0x400979CA: "parameter smoothing",
    0x4008EF8C: "sum 10 ch", 0x4008F024: "sum 9 ch", 0x4008F0B6: "sum 8 ch", 0x40097B74: "modulation",
    0x4011942A: "LFOs", 0x4008EC34: "ADC deinterleave", 0x40090442: "CV/gains", 0x4008FF34: "track out (x12)",
    0x400A20AE: "CPU #2 wait", 0x4008EF42: "x10/x8 integer scale",
}


class Stats:
    def __init__(self):
        self.n = 0                                   # istruzioni
        self.w = 0                                   # pesate: movem = numero di registri, divisioni 20
        self.pc = collections.Counter()
        self.calls = collections.Counter()
        self.site = collections.Counter()            # (chiamante, routine) -> istruzioni incluse
        self.wsite = collections.Counter()


class Isr:
    def __init__(self, mods=(), setup=None, uses=(), extra=None):
        self.ui = screens.UI(list(mods), setup=setup, uses=uses, extra=extra)
        self.uc = self.ui.uc
        self.sym = self.ui.sym
        self.mods = set(self.ui.mods)
        self.emac = UnicornEmac(self.uc, [])
        self.code: dict[int, tuple | None] = {}
        self.st = None
        self.h = self.uc.hook_add(UC_HOOK_CODE, self._hook)
        for a in DMA_ACTIVE:
            self.uc.hook_add(UC_HOOK_MEM_READ, lambda u, acc, addr, size, v, d: u.mem_write(addr & ~1, bytes(2)),
                             begin=a, end=a + 1)

    def periph(self):
        uc = self.uc
        uc.mem_write(0xFC03_C02C, struct.pack(">I", 0x1000_0000))   # DSPI: EOQF, trasferimento finito
        uc.mem_write(0x43BD_D824, struct.pack(">I", 1))             # CPU #2 presente: DMA delle voci
        uc.mem_write(0xFC04_55FE, struct.pack(">H", 0x80))          # eDMA ch 47 DONE

    def put16(self, a, *v):
        self.uc.mem_write(a, struct.pack(f">{len(v)}h", *v))

    def put32(self, a, *v):
        self.uc.mem_write(a, struct.pack(f">{len(v)}I", *[x & 0xFFFF_FFFF for x in v]))

    def words(self, a, n):
        return list(struct.unpack(f">{n}h", self.uc.mem_read(a, 2 * n)))

    # ------------------------------------------------------------------ gancio
    def _info(self, pc):
        op = int.from_bytes(self.uc.mem_read(pc, 2), "big")
        if op >> 12 == 0xA:
            return ("emac", self.emac._compile(pc, op), op)
        if 0x4E80 <= op <= 0x4EBF or op >> 8 == 0x61:
            return ("call", None, op)
        if op & 0xFB80 == 0x4880 and op & 0x38 in (0x10, 0x28):     # movem.l (An) / (d16,An)
            mask = int.from_bytes(self.uc.mem_read(pc + 2, 2), "big")
            return ("movem", bin(mask).count("1"), op)
        if op & 0xF1C0 == 0x81C0 or op & 0xFFC0 == 0x4C40:           # divs.w, divs/divu.l, rem
            return ("div", 20, op)
        return None

    def _hook(self, uc, pc, size, _):
        st = self.st
        if st is None:
            return
        info = self.code.get(pc, 0)
        if info == 0:
            info = self.code[pc] = self._info(pc)
        st.n += 1
        stack = self.stack
        if stack:
            sp = uc.reg_read(K.UC_M68K_REG_A7)
            while stack and sp > stack[-1][1]:
                entry, sp0, n0, w0, caller = stack.pop()
                st.site[(caller, entry)] += st.n - 1 - n0
                st.wsite[(caller, entry)] += st.w - w0
        if self.pending is not None:
            stack.append((pc, uc.reg_read(K.UC_M68K_REG_A7), st.n - 1, st.w, self.pending))
            self.pending = None
            st.calls[pc] += 1
        st.pc[pc] += 1
        w = 1
        if info is not None:
            kind, x, _op = info
            if kind == "emac":
                n = x()
                st.w += 1
                uc.reg_write(K.UC_M68K_REG_PC, pc + n)
                if self.emac.error:
                    raise self.emac.error
                return
            if kind == "call":
                self.pending = stack[-1][0] if stack else ISR
            else:
                w = x
        st.w += w

    # ------------------------------------------------------------------ blocchi
    def _start(self, count):
        uc = self.uc
        self.periph()
        uc.mem_write(STACK, struct.pack(">HHI", 0x4000 | (64 << 2), 0x2000, 0x4000_0400))
        uc.reg_write(K.UC_M68K_REG_SR, 0x2700)
        uc.reg_write(K.UC_M68K_REG_A7, STACK)
        try:
            uc.emu_start(ISR, RTE, count=count)
        except UcError as e:
            raise RuntimeError(f"{e} at {uc.reg_read(K.UC_M68K_REG_PC):#x}: "
                               + " ".join(hex(a) for a in self.ui.ring)) from None
        if self.emac.error:
            raise self.emac.error
        if uc.reg_read(K.UC_M68K_REG_PC) != RTE:
            raise RuntimeError(f"interrupt non finito a {uc.reg_read(K.UC_M68K_REG_PC):#x}")

    def run(self, count=5_000_000) -> Stats:
        """Un blocco profilato."""
        st = self.st = Stats()
        self.stack, self.pending = [], None
        self.uc.ctl_flush_tb()
        try:
            self._start(count)
        finally:
            self.st = None
        while self.stack:
            entry, sp0, n0, w0, caller = self.stack.pop()
            st.site[(caller, entry)] += st.n - n0
            st.wsite[(caller, entry)] += st.w - w0
        return st

    def fast(self, n):
        """n blocchi senza profilo (EMAC sui siti visti dai blocchi profilati: prima serve un run())."""
        uc, sites = self.uc, {pc: info[2] for pc, info in self.code.items() if info and info[0] == "emac"}
        uc.hook_del(self.h)
        for pc, op in sites.items():
            self.emac.ops[pc] = op
            uc.mem_write(pc, ILLEGAL)
        uc.ctl_flush_tb()
        try:
            for _ in range(n):
                self._start(10_000_000)
        finally:
            for pc, op in sites.items():
                uc.mem_write(pc, op.to_bytes(2, "big"))
            uc.ctl_flush_tb()
            self.h = uc.hook_add(UC_HOOK_CODE, self._hook)

    # ------------------------------------------------------------------ scene
    def settle(self):
        """Smussamento dei parametri a regime (stato = valore << 16, uscita = valore), come dopo ~400 blocchi."""
        self.put32(SMOOTH_S, *[(v & 0xFFFF) << 16 for v in self.words(ENG, SMOOTH_N)])
        self.uc.mem_write(SMOOTH_OUT, bytes(self.uc.mem_read(ENG, 2 * SMOOTH_N)))

    def tracks(self, vol=0x6400, vel=0x6400, pan=0x4000, dsend=0, rsend=0, snd3=0, n=12):
        """Livelli come dopo una nota su ogni traccia: VOL, PAN, velocity, mandate DEL/REV/SND3."""
        for t in range(n):
            b = ENG + 142 * t
            self.put16(b + 106, snd3)
            self.put16(b + 118, dsend)
            self.put16(b + 120, rsend)
            self.put16(b + 122, pan)
            self.put16(b + 124, vol)
            self.put16(VEL + 2 * t, vel)

    def noise(self, seed=1):
        """Segnale nelle tracce digitali e nell'anello dell'ADC: gli effetti non vanno a riposo."""
        rnd = random.Random(seed)
        self.put32(0x8000_3D50, *[rnd.randrange(-2 ** 28, 2 ** 28) for _ in range(8 * 32)])
        self.put32(0x8000_1800, *[rnd.randrange(-2 ** 28, 2 ** 28) for _ in range(8 * 64)])

    def vset(self, pid, v):
        self.ui.call(SET, [0x4FE0_3000, pid, v << 8, 1])

    def scene(self, name, blocks=20):
        """rest: livelli, nessuna mandata. typ: 3 tracce al delay, 4 al riverbero, 2 in FX3 (chorus).
        max: tutte le mandate al massimo, FX3 phaser con retroazione e mandate DEL/REV, compressore acceso,
        ingresso mono. Poi smussamento a regime e qualche blocco (rampe dei guadagni finite)."""
        if not self.code:
            self.run()
        self.noise()
        if name == "rest":
            self.tracks()
        elif name == "typ":
            self.tracks()
            for t in (0, 2, 5):
                self.put16(ENG + 142 * t + 118, 0x4000)
            for t in (1, 2, 6, 9):
                self.put16(ENG + 142 * t + 120, 0x3000)
            if "fx3" in self.mods:
                for t in (3, 4):
                    self.put16(ENG + 142 * t + 106, 0x5000)
                self.vset(FX3["TYPE"], 1)
        elif name == "max":
            self.tracks(dsend=0x7F00, rsend=0x7F00, snd3=0x7F00 if "fx3" in self.mods else 0)
            if "fx3" in self.mods:
                self.vset(FX3["TYPE"], 0)
                for k in ("SPD", "DEP", "TIME", "FDBK", "WID", "DSND", "RSND"):
                    self.vset(FX3[k], 127)
            if "master-comp" in self.mods:
                self.vset(COMP_RAT, 4 * 0xFE0 >> 8)
            self.uc.mem_write(0x8000_3146, b"\x00")                  # ingresso in mono (dual mono)
        else:
            raise ValueError(name)
        self.settle()
        self.run()                                                   # siti EMAC del nuovo percorso
        self.fast(blocks)


def tree(st, out, root=ISR, depth=0, maxdepth=3, minn=150):
    """Albero delle chiamate: istruzioni incluse, proprie (senza le chiamate), chiamate per blocco."""
    kids = collections.Counter()
    for (c, e), n in st.site.items():
        if c == root:
            kids[e] += n
    if root == ISR:
        out.write(f"ISR {st.n} instructions ({st.w} weighted)\n")
    for e, n in kids.most_common():
        if n < minn:
            continue
        sub = sum(v for (c, x), v in st.site.items() if c == e)
        out.write(f"{'  ' * (depth + 1)}{e:#010x} {n:6d}  self {n - sub:6d}  x{st.calls[e]}  {NAMES.get(e, '')}\n")
        if depth + 1 < maxdepth:
            tree(st, out, e, depth + 1, maxdepth, minn)
    if root == ISR:
        out.write(f"  (ISR body) {st.n - sum(kids.values())}\n")


def main(argv):
    scene = "rest"
    if "--scene" in argv:
        i = argv.index("--scene")
        scene = argv[i + 1]
        argv = argv[:i] + argv[i + 2:]
    m = Isr(argv)
    m.scene(scene)
    tree(m.run(), sys.stdout)


if __name__ == "__main__":
    main(sys.argv[1:])
