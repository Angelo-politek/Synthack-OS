"""EMAC (Enhanced Multiply-ACcumulate) del ColdFire, emulata in Python.

Perche': Unicorn/QEMU emula male l'EMAC (modalita' frazionaria con segno, forma
"MAC con load"); il motore audio della Syntakt la usa per oscillatori e filtri.

Fonti:
- semantica: reference manual NXP MCF54418RM, cap. 5 (pseudo-codice di MAC/MSAC,
  rounding, saturazione, layout dell'accumulatore a 48 bit);
- codifiche: specifica SLEIGH di Ghidra (68000.sinc) e QEMU (target/m68k);
- un dettaglio su cui le due fonti divergono (bit dell'accumulatore nella forma
  "MAC con load") e' stato risolto analizzando il flusso dei dati nel codice:
  vedi docs/re-journal.md.

Rappresentazione: ogni accumulatore e' un intero Python con segno su 48 bit.
"""

from __future__ import annotations

from dataclasses import dataclass, field

# --- campi di MACSR
PAV_SHIFT = 8
OMC, SU, FI, RT = 0x80, 0x40, 0x20, 0x10
N, Z, V, EV = 0x8, 0x4, 0x2, 0x1

M48 = (1 << 48) - 1


def s32(v: int) -> int:
    v &= 0xFFFF_FFFF
    return v - (1 << 32) if v & 0x8000_0000 else v


def s48(v: int) -> int:
    v &= M48
    return v - (1 << 48) if v & (1 << 47) else v


def u32(v: int) -> int:
    return v & 0xFFFF_FFFF


@dataclass
class EmacState:
    acc: list[int] = field(default_factory=lambda: [0, 0, 0, 0])   # 48 bit con segno
    macsr: int = 0
    mask: int = 0xFFFF_FFFF

    # ------------------------------------------------------------ helper modalita'

    @property
    def mode(self) -> int:
        """MACSR[S/U,F/I]: 0 = intero con segno, 1/3 = frazionario, 2 = intero senza segno."""
        return (self.macsr >> 5) & 3

    def _set_flags(self, n: int) -> None:
        a = self.acc[n]
        pav = (self.macsr >> (PAV_SHIFT + n)) & 1
        f = (V if pav else 0) | (N if a < 0 else 0) | (Z if a == 0 else 0)
        if self.mode in (1, 3):
            ev = not (-(1 << 39) <= a < (1 << 39))          # ACC[47:39] non tutti uguali
        elif self.mode == 0:
            ev = not (-(1 << 31) <= a < (1 << 31))
        else:
            ev = (a & M48) >> 32 != 0
        f |= EV if ev else 0
        self.macsr = (self.macsr & ~0xF) | f

    def _set_pav(self, n: int, on: bool) -> None:
        bit = 1 << (PAV_SHIFT + n)
        self.macsr = (self.macsr | bit) if on else (self.macsr & ~bit)

    def _pav(self, n: int) -> bool:
        return bool(self.macsr & (1 << (PAV_SHIFT + n)))

    # ------------------------------------------------------------ MAC / MSAC

    def mac(self, n: int, ry: int, rx: int, *, sub: bool, long: bool,
            uly: bool = False, ulx: bool = False, sf: int = 0) -> None:
        """MAC (sub=False) o MSAC (sub=True) su ACCn. ry/rx = contenuto dei registri (32 bit)."""
        omc = bool(self.macsr & OMC)
        if omc and self._pav(n):
            self._set_flags(n)          # accumulatore saturato: resta fermo finche' non si azzera V
            return
        self._set_pav(n, False)
        mode = self.mode
        if mode in (1, 3):
            self._mac_frac(n, ry, rx, sub, long, uly, ulx, omc)
        elif mode == 0:
            self._mac_int(n, ry, rx, sub, long, uly, ulx, sf, omc, signed=True)
        else:
            self._mac_int(n, ry, rx, sub, long, uly, ulx, sf, omc, signed=False)
        self._set_flags(n)

    def _mac_frac(self, n, ry, rx, sub, long, uly, ulx, omc) -> None:
        if long:
            y, x = s32(ry), s32(rx)
        else:                                               # word: {Rn[31:16] o Rn[15:0], 0x0000}
            y = s32(((ry >> 16) if uly else ry) << 16)
            x = s32(((rx >> 16) if ulx else rx) << 16)
        product = (y * x) << 1                              # 64 bit (esatto in Python)
        if self.macsr & RT:                                 # arrotondamento convergente a 40 bit
            low, hi = product & 0xFF_FFFF, product >> 24
            if low > 0x80_0000 or (low == 0x80_0000 and hi & 1):
                hi += 1
        else:
            hi = product >> 24                              # troncamento
        # -1 * -1 = +1: il prodotto 2^63 viene esteso con zeri (resta positivo); in Python
        # e' gia' positivo, quindi hi = product[71:24] e' corretto in entrambi i casi.
        result = self.acc[n] - hi if sub else self.acc[n] + hi
        if not (-(1 << 47) <= result < (1 << 47)):          # overflow dei 48 bit
            self._set_pav(n, True)
            if omc:
                result = 0x007F_FFFF_FF00 if result > 0 else s48(0xFF80_0000_0000)
            else:
                result = s48(result)
        self.acc[n] = result

    def _mac_int(self, n, ry, rx, sub, long, uly, ulx, sf, omc, signed) -> None:
        def op(r: int, upper: bool) -> int:
            if long:
                return s32(r) if signed else u32(r)
            w = (r >> 16) & 0xFFFF if upper else r & 0xFFFF
            return (w - 0x1_0000 if w & 0x8000 else w) if signed else w
        product = op(ry, uly) * op(rx, ulx)
        sat = None
        if signed and not (-(1 << 39) <= product < (1 << 39)):
            self._set_pav(n, True)
            if omc:
                sat = (0x0000_7FFF_FFFF if product < 0 else s48(0xFFFF_8000_0000)) if sub else \
                      (s48(0xFFFF_8000_0000) if product < 0 else 0x0000_7FFF_FFFF)
        if not signed and product >> 40:
            self._set_pav(n, True)
            if omc:
                sat = 0 if sub else M48
        if sat is not None:
            self.acc[n] = sat
            return
        if sf == 1:
            product <<= 1
        elif sf == 3:
            product >>= 1
        result = self.acc[n] - product if sub else self.acc[n] + product
        lo, hi = (-(1 << 47), 1 << 47) if signed else (0, 1 << 48)
        if not (lo <= result < hi):
            self._set_pav(n, True)
            if omc:
                if signed:
                    result = 0x0000_7FFF_FFFF if result >= hi else s48(0xFFFF_8000_0000)
                else:
                    result = 0 if sub else M48
            else:
                result = s48(result) if signed else result & M48
        self.acc[n] = result

    # ------------------------------------------------------------ move da/verso EMAC

    def load_acc(self, n: int, value: int) -> None:
        """move.l Ry/#imm,ACCn: carica 32 bit; estensioni da segno (o zero se senza segno)."""
        mode = self.mode
        if mode in (1, 3):
            self.acc[n] = s32(value) << 8
        elif mode == 0:
            self.acc[n] = s32(value)
        else:
            self.acc[n] = u32(value)
        self._set_pav(n, False)
        self._set_flags(n)

    def store_acc(self, n: int) -> int:
        """move.l ACCn,Rx: valore a 32 bit, con rounding/saturazione secondo MACSR."""
        a, m = self.acc[n], self.macsr
        omc = bool(m & OMC)
        if self.mode in (1, 3):
            if m & SU:                                      # 16 bit arrotondati nella word bassa
                low, v = a & 0xFF_FFFF, a >> 24
                if low > 0x80_0000 or (low == 0x80_0000 and v & 1):
                    v += 1
                if omc and not (-0x8000 <= v < 0x8000):
                    v = 0x7FFF if v > 0 else -0x8000
                return v & 0xFFFF
            if m & RT:                                      # 32 bit arrotondati
                low, v = a & 0xFF, a >> 8
                if low > 0x80 or (low == 0x80 and v & 1):
                    v += 1
            else:
                v = a >> 8                                  # 32 bit troncati
            if omc and not (-(1 << 31) <= v < (1 << 31)):
                v = 0x7FFF_FFFF if v > 0 else -(1 << 31)
            return u32(v)
        if self.mode == 0:
            if omc and not (-(1 << 31) <= a < (1 << 31)):
                return 0x7FFF_FFFF if a > 0 else 0x8000_0000
            return u32(a)
        if omc and a >> 32:
            return 0xFFFF_FFFF
        return u32(a)

    def copy_acc(self, src: int, dst: int) -> None:
        self.acc[dst] = self.acc[src]
        self._set_pav(dst, self._pav(src))
        self._set_flags(dst)

    def clear_acc(self, n: int) -> None:
        self.acc[n] = 0
        self._set_pav(n, False)

    def load_macsr(self, value: int) -> None:
        self.macsr = value & 0xFFF

    def load_mask(self, value: int) -> None:
        self.mask = 0xFFFF_0000 | (value & 0xFFFF)

    def accext(self, pair: int) -> int:
        """move.l ACCext01/23,Rx: byte di estensione di due accumulatori."""
        out = 0
        for i, n in enumerate((2 * pair, 2 * pair + 1)):
            a = self.acc[n] & M48
            if self.mode in (1, 3):
                ext = ((a >> 40) << 8) | (a & 0xFF)          # {ACC[47:40], ACC[7:0]}
            else:
                ext = a >> 32                                # ACC[47:32]
            out |= (ext & 0xFFFF) << (16 * (1 - i))
        return out

    def load_accext(self, pair: int, value: int) -> None:
        for i, n in enumerate((2 * pair, 2 * pair + 1)):
            ext = (value >> (16 * (1 - i))) & 0xFFFF
            a = self.acc[n] & M48
            if self.mode in (1, 3):
                a = ((ext >> 8) << 40) | (a & 0xFF_FFFF_FF00) | (ext & 0xFF)
            else:
                a = (ext << 32) | (a & 0xFFFF_FFFF)
            self.acc[n] = s48(a)


# =============================================================================
# Adattatore per Unicorn: decodifica + esecuzione delle istruzioni EMAC
# =============================================================================

class EmacUnsupported(RuntimeError):
    pass


def _ureg(n: int) -> int:
    """Numero di registro a 4 bit (bit 3 = A/D) -> costante Unicorn."""
    from unicorn.m68k_const import UC_M68K_REG_A0, UC_M68K_REG_D0
    return (UC_M68K_REG_A0 if n & 8 else UC_M68K_REG_D0) + (n & 7)


def is_emac(op: int) -> bool:
    """Riconosce le parole che iniziano un'istruzione EMAC (linea A del ColdFire)."""
    if op & 0xF000 != 0xA000:
        return False
    if op & 0x0100 == 0:
        return True                                         # MAC / MSAC (con o senza load)
    return any((op & m) == v for m, v in (
        (0xF9B0, 0xA180), (0xF9FC, 0xA110), (0xF9C0, 0xA100), (0xFFC0, 0xA900),
        (0xFFF0, 0xA980), (0xFFFF, 0xA9C0), (0xFFC0, 0xAD00), (0xFFF0, 0xAD80),
        (0xFBC0, 0xAB00), (0xFBF0, 0xAB80)))


ILLEGAL = bytes.fromhex("4afc")                          # istruzione ILLEGAL del 68k
INTR_ILLEGAL = 4                                            # vettore "illegal instruction"


class _FastUc:
    """Accesso diretto alle funzioni C di Unicorn (uc_reg_read/write, uc_mem_read).

    Il binding Python ufficiale aggiunge 4-5 livelli di funzioni per ogni accesso: nei punti
    caldi (decine di migliaia di accessi per blocco audio) li saltiamo con ctypes.
    """

    def __init__(self, uc):
        import ctypes
        from unicorn.unicorn_py3.unicorn import uclib
        self._h = uc._uch
        self._buf = ctypes.c_uint32()
        self._ref = ctypes.byref(self._buf)
        self._mbuf = ctypes.create_string_buffer(4)
        self._rd, self._wr, self._mrd = uclib.uc_reg_read, uclib.uc_reg_write, uclib.uc_mem_read

    def read(self, reg: int) -> int:
        if self._rd(self._h, reg, self._ref):
            raise EmacUnsupported(f"uc_reg_read({reg}) fallita")
        return self._buf.value

    def write(self, reg: int, value: int) -> None:
        self._buf.value = value & 0xFFFF_FFFF
        if self._wr(self._h, reg, self._ref):
            raise EmacUnsupported(f"uc_reg_write({reg}) fallita")

    def read32(self, addr: int) -> int:
        if self._mrd(self._h, addr, self._mbuf, 4):
            raise EmacUnsupported(f"uc_mem_read({addr:08X}) fallita")
        return int.from_bytes(self._mbuf.raw, "big")


class UnicornEmac:
    """Aggancia l'EMAC Python a Unicorn con dei "breakpoint software".

    Su ogni indirizzo di istruzione EMAC (elenco esatto, vedi gen_emac_sites.py) la prima
    parola viene sostituita, nella memoria dell'EMULATORE, con ILLEGAL (0x4AFC). La CPU
    emulata gira a piena velocita'; quando incontra una di queste istruzioni scatta
    un'eccezione, noi eseguiamo l'istruzione originale in Python e saltiamo oltre.

    Per velocita', ogni istruzione viene decodificata una sola volta e trasformata in una
    piccola funzione ("closure") con registri e campi gia' risolti.
    """

    def __init__(self, uc, sites: list[int]):
        from unicorn import UC_HOOK_INTR
        from unicorn.m68k_const import UC_M68K_REG_PC
        self.uc = uc
        self.state = EmacState()
        self.count = 0
        self.error: Exception | None = None
        self.ops: dict[int, int] = {}
        self._compiled: dict[int, object] = {}
        self._pc = UC_M68K_REG_PC
        self.fast = _FastUc(uc)
        for a in sites:
            op = int.from_bytes(uc.mem_read(a, 2), "big")
            if not is_emac(op):
                raise EmacUnsupported(f"{a:08X}: {op:04X} non e' un'istruzione EMAC")
            self.ops[a] = op
            uc.mem_write(a, ILLEGAL)
        uc.hook_add(UC_HOOK_INTR, self._intr)

    def _intr(self, uc, intno: int, _ud) -> None:
        pc = self.fast.read(self._pc)
        fn = self._compiled.get(pc)
        try:
            if fn is None:
                op = self.ops.get(pc)
                if intno != INTR_ILLEGAL or op is None:
                    raise EmacUnsupported(f"eccezione {intno} inattesa a {pc:08X}")
                fn = self._compiled[pc] = self._compile(pc, op)
            n = fn()
        except Exception as e:                              # riportata da Engine dopo emu_stop
            self.error = e
            uc.emu_stop()
            return
        self.count += 1
        self.fast.write(self._pc, pc + n)

    # -- decodifica (una volta per indirizzo)

    def _u16(self, a: int) -> int:
        return int.from_bytes(self.uc.mem_read(a, 2), "big")

    def _u32(self, a: int) -> int:
        return int.from_bytes(self.uc.mem_read(a, 4), "big")

    def _compile(self, pc: int, op: int):
        """Ritorna una funzione senza argomenti che esegue l'istruzione e ne da' la lunghezza."""
        from unicorn.m68k_const import UC_M68K_REG_SR
        uc, s = self.uc, self.state
        rd, wr = self.fast.read, self.fast.write

        def src():                                          # sorgente dei move verso EMAC
            mode, reg = (op >> 3) & 7, op & 7
            if mode in (0, 1):
                r = _ureg(reg | (8 if mode else 0))
                return (lambda: rd(r) & 0xFFFF_FFFF), 2
            if mode == 7 and reg == 4:
                imm = self._u32(pc + 2)
                return (lambda: imm), 6
            raise EmacUnsupported(f"modo di indirizzamento {mode}/{reg} a {pc:08X}")

        if op & 0x0100 == 0:
            return self._compile_mac(pc, op)
        if (op & 0xF9B0) == 0xA180:                         # move.l ACCx,Rx / movclr.l
            acc, r, clear = (op >> 9) & 3, _ureg(op & 0xF), bool(op & 0x40)

            def f():
                wr(r, s.store_acc(acc))
                if clear:
                    s.clear_acc(acc)
                return 2
            return f
        if (op & 0xF9FC) == 0xA110:                         # move.l ACCy,ACCx
            a_src, a_dst = (op >> 9) & 3, op & 3
            return lambda: (s.copy_acc(a_src, a_dst), 2)[1]
        if (op & 0xF9C0) == 0xA100:                         # move.l <ea>,ACCx
            get, n = src()
            acc = (op >> 9) & 3
            return lambda: (s.load_acc(acc, get()), n)[1]
        if (op & 0xFFC0) == 0xA900:                         # move.l <ea>,MACSR
            get, n = src()
            return lambda: (s.load_macsr(get()), n)[1]
        if (op & 0xFFF0) == 0xA980:                         # move.l MACSR,Rx
            r = _ureg(op & 0xF)
            return lambda: (wr(r, s.macsr), 2)[1]
        if op == 0xA9C0:                                    # move.l MACSR,CCR
            def f():
                wr(UC_M68K_REG_SR, (rd(UC_M68K_REG_SR) & ~0x1F) | (s.macsr & 0xE))
                return 2
            return f
        if (op & 0xFFC0) == 0xAD00:                         # move.l <ea>,MASK
            get, n = src()
            return lambda: (s.load_mask(get()), n)[1]
        if (op & 0xFFF0) == 0xAD80:                         # move.l MASK,Rx
            r = _ureg(op & 0xF)
            return lambda: (wr(r, s.mask), 2)[1]
        if (op & 0xFBC0) == 0xAB00:                         # move.l <ea>,ACCext01/23
            get, n = src()
            pair = (op >> 10) & 1
            return lambda: (s.load_accext(pair, get()), n)[1]
        if (op & 0xFBF0) == 0xAB80:                         # move.l ACCext01/23,Rx
            r, pair = _ureg(op & 0xF), (op >> 10) & 1
            return lambda: (wr(r, s.accext(pair)), 2)[1]
        raise EmacUnsupported(f"istruzione EMAC {op:04X} a {pc:08X}")

    def _compile_mac(self, pc: int, op: int):
        uc, s = self.uc, self.state
        rd, wr, read32 = self.fast.read, self.fast.write, self.fast.read32
        ext = self._u16(pc + 2)
        sub, long, sf = bool(ext & 0x100), bool(ext & 0x800), (ext >> 9) & 3
        ulx, uly = bool(ext & 0x80), bool(ext & 0x40)
        mac = s.mac

        if op & 0x30 == 0:                                  # forma a registri
            if ext & 3:
                raise EmacUnsupported(f"MAC a doppio accumulatore a {pc:08X}")
            acc = ((op >> 7) & 1) | ((ext >> 3) & 2)
            r_y, r_x = _ureg(op & 0xF), _ureg(((op >> 9) & 7) | (8 if op & 0x40 else 0))

            def f():
                ry, rx = rd(r_y), rd(r_x)
                mac(acc, ry, rx, sub=sub, long=long, uly=uly, ulx=ulx, sf=sf)
                return 4
            return f

        # MAC con load. Il bit 7 dell'opcode e' l'INVERSO del lsb dell'accumulatore
        # (confermato da GNU objdump; Ghidra SLEIGH non lo inverte). I bit 3-0 dell'estensione
        # sono il registro Ry (QEMU li scambia per "doppio accumulatore" e solleva un'eccezione).
        acc = (((op >> 7) & 1) ^ 1) | ((ext >> 3) & 2)
        mode, an = (op >> 3) & 7, 8 | (op & 7)
        if mode not in (2, 3, 4, 5):
            raise EmacUnsupported(f"modo {mode} nel MAC con load a {pc:08X}")
        disp, length = 0, 4
        if mode == 5:
            d16 = self._u16(pc + 4)
            disp, length = (d16 - 0x10000 if d16 & 0x8000 else d16), 6
        use_mask = bool(ext & 0x20)
        u_an, u_rw = _ureg(an), _ureg(((op >> 9) & 7) | (8 if op & 0x40 else 0))
        r_y, r_x = _ureg(ext & 0xF), _ureg(ext >> 12)

        def f():
            ry, rx, a = rd(r_y), rd(r_x), rd(u_an)
            addr = a - 4 if mode == 4 else a + disp
            if use_mask:
                addr &= s.mask
            loaded = read32(addr & 0xFFFF_FFFF)
            # gli operandi si leggono PRIMA della scrittura del registro caricato
            mac(acc, ry, rx, sub=sub, long=long, uly=uly, ulx=ulx, sf=sf)
            wr(u_rw, loaded)
            if mode == 3:
                nxt = a + 4
                wr(u_an, ((nxt & s.mask) if use_mask else nxt) & 0xFFFF_FFFF)
            elif mode == 4:
                wr(u_an, addr & 0xFFFF_FFFF)
            return length
        return f
