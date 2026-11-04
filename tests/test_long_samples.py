"""long-samples (Synfact's HZFS on OS 1.42): eMMC double, catalogues, put, plan, pages sent to CPU #2, slot guard.

The eMMC primitives of the OS (0x4010F612 read, 0x4010F7F8 write: lba, bytes, buffer) are replaced by a Python
disk. Synfact's own code writes the catalogues and the file (core_hzfs_ensure, core_hzfs_put); our plan and page
map are then checked against that disk, page by page, as the OS uploader (0x40082F90) would ask for them.
"""

import struct
import sys
from pathlib import Path

import pytest

pytest.importorskip("unicorn")

ROOT = Path(__file__).resolve().parent
SY = ROOT.parent / "firmware" / "Syntakt_OS1.42.syx"
pytestmark = pytest.mark.skipif(not SY.exists(), reason="OS stock assente")
sys.path[:0] = [str(ROOT.parent / "tools" / "emu")]

MMC_READ, MMC_WRITE = 0x4010_F612, 0x4010_F7F8
MMC_READY, MMC_SECTORS = 0x444B_A6FC, 0x444B_A720
SECTORS = 0x40_0000                          # 2 GB card
IMAGE, TOTAL, PAGE_NOW = 0x4D84_F2C5, 0x4D84_F2C1, 0x41BB_F424
CPU2_POOL = 0x4004_F750
STREAM = 0x4FE0_8000                         # rts: callback of core_hzfs_put, served from Python
SCRATCH = 0x4FE0_9000


class Disk:
    def __init__(self):
        self.s = {}

    def read(self, lba, n):
        out = bytearray()
        for k in range((n + 511) // 512):
            out += self.s.get(lba + k, bytes(512))
        return bytes(out[:n])

    def write(self, lba, data):
        for k in range(0, len(data), 512):
            self.s[lba + k // 512] = bytes(data[k:k + 512]).ljust(512, b"\0")


@pytest.fixture(scope="module")
def m():
    import screens
    from unicorn import UC_HOOK_CODE
    from unicorn.m68k_const import UC_M68K_REG_A7, UC_M68K_REG_D0, UC_M68K_REG_PC
    ui = screens.UI(["long-samples", "sampler"])
    disk = Disk()
    ui.disk = disk
    ui.put(MMC_READY, ">I", 1)
    ui.put(MMC_SECTORS, ">I", SECTORS)

    def ret(uc, d0):
        sp = uc.reg_read(UC_M68K_REG_A7)
        uc.reg_write(UC_M68K_REG_PC, struct.unpack(">I", uc.mem_read(sp, 4))[0])
        uc.reg_write(UC_M68K_REG_A7, sp + 4)
        uc.reg_write(UC_M68K_REG_D0, d0)

    def args(uc, n):
        sp = uc.reg_read(UC_M68K_REG_A7)
        return struct.unpack(f">{n}I", uc.mem_read(sp + 4, 4 * n))

    def mmc(uc, pc, size, _):
        lba, n, buf = args(uc, 3)
        if lba + (n + 511) // 512 > SECTORS:
            return ret(uc, 0xFFFF_FFFF)
        if pc == MMC_READ:
            uc.mem_write(buf, disk.read(lba, n))
        else:
            disk.write(lba, bytes(uc.mem_read(buf, n)))
        ret(uc, 0)

    def stream(uc, pc, size, _):                    # int f(ctx, offset, size, dst): bytes of ui.body
        _, off, n, dst = args(uc, 4)
        uc.mem_write(dst, ui.body[off:off + n])
        ret(uc, 0)
    for a in (MMC_READ, MMC_WRITE):
        ui.uc.hook_add(UC_HOOK_CODE, mmc, begin=a, end=a)
    ui.uc.mem_write(STREAM, b"\x4e\x75")
    ui.uc.hook_add(UC_HOOK_CODE, stream, begin=STREAM, end=STREAM)
    return ui


def samp(frames, f1=500, f2=3000):
    import math
    pcm = [int(12000 * math.sin(2 * math.pi * (f1 if i < frames // 2 else f2) * i / 48000)) for i in range(frames)]
    head = bytearray(64)
    head[0:4] = b"SAMP"
    struct.pack_into(">I", head, 8, frames)
    head[12:20] = b"pad-12s\0"
    return bytes(head) + struct.pack(f">{frames}h", *pcm)


def test_ensure_put_plan_and_pages(m):
    s = m.sym
    io = s["core_hzfs_native_io"]
    assert m.call(s["core_hzfs_ensure"], [io], count=400_000_000) == 1           # disco vuoto: cataloghi creati
    assert any(lba >= 0x30000000 // 512 for lba in m.disk.s)                     # solo nella zona alta
    assert not any(lba < 0x30000000 // 512 for lba in m.disk.s)
    frames = 12 * 48000                                                          # 12 s, oltre i 5 s stock
    m.body = samp(frames)
    m.uc.mem_write(SCRATCH, b"pad-12s\0")
    r = m.call(s["core_hzfs_put"], [io, SCRATCH, len(m.body), 0, STREAM, 0, SCRATCH + 64], count=2_000_000_000)
    assert r == 1, r
    # il catalogo scritto dal codice C, come lo legge il caricatore del web builder (web-builder/test/samples.test.ts)
    fixture = ROOT.parent / "web-builder" / "test" / "fixtures" / "hzfs-catalogue.bin"
    cats = [m.disk.read(k * 0x80000 // 512, 0x200) for k in (0x600, 0x601)]
    cat = next(c for c in cats if c[:4] == b"HZFS" and struct.unpack(">I", c[12:16])[0] == 1)
    size = struct.unpack(">I", cat[36:40])[0]
    want = cat[:size]
    if not fixture.exists():
        fixture.parent.mkdir(parents=True, exist_ok=True)
        fixture.write_bytes(want)
    assert fixture.read_bytes() == want
    # immagine stock: un solo campione da 4800 nello slot 1
    stock = 4 * 64 + 2 * 4800
    m.uc.mem_write(TOTAL, struct.pack(">I", stock))
    m.call(s["ls_plan"], count=400_000_000)
    assert m.long(s["ls_status"]) == 1
    sp = (stock + 2047) // 2048
    tab = struct.unpack(">4I", m.uc.mem_read(s["ls_table"], 16))
    assert tab[0] == 0x5348_4C53 and tab[1] == 1
    assert tab[2] == CPU2_POOL + (sp + 1) * 2048 + 64 and tab[3] == frames
    pages = (len(m.body) + 2047) // 2048
    assert m.call(s["ls_count"]) == (sp + 1 + pages) * 2048
    got = bytearray()
    for n in range(sp + 1 + pages):
        m.put(PAGE_NOW, ">I", n)
        off = m.call(s["ls_map"])
        assert struct.unpack(">H", m.uc.mem_read(0x1000_000C, 2))[0] == n
        src = (IMAGE + off) & 0xFFFF_FFFF
        if n < sp:
            assert off == n << 11                                                # pagine stock: come l'OS
        elif n == sp:
            assert bytes(m.uc.mem_read(src, 16)) == struct.pack(">4I", *tab)     # la tabella
        else:
            got += m.uc.mem_read(src, 2048)
    assert bytes(got[:len(m.body)]) == m.body                                    # il file, come sulla eMMC


def test_no_long_samples_leaves_the_upload_stock(m):
    s = m.sym
    m.disk.s.clear()                                                             # nessun catalogo
    m.uc.mem_write(TOTAL, struct.pack(">I", 1000))
    m.call(s["ls_plan"], count=400_000_000)
    assert m.call(s["ls_count"]) == 1000
    m.put(PAGE_NOW, ">I", 0)
    assert m.call(s["ls_map"]) == 0


def test_stock_slot_guard(m):
    """core_sample_write_guard (Synfact): uno slot stock oltre 5 s, o fuori dal confine dello slot, e' rifiutato
    prima di scrivere."""
    s = m.sym
    info, out = SCRATCH + 0x100, SCRATCH + 0x200

    def guard(address, size):
        m.uc.mem_write(info, bytes(0x7C))
        m.put(info + 12, ">II", address, size)
        m.uc.mem_write(out, bytes(32))
        return m.call(s["core_sample_write_guard"], [0, info, out])
    assert guard(0x0040_0000, 64 + 480_000) == 0                                 # 5 s nello slot 1: all'OS
    assert guard(0x0040_0000, 64 + 480_002) == 1                                 # oltre: rifiutato
    assert guard(0x0048_0000 + 512, 1000) == 1                                   # fuori dal confine
    assert guard(0x0100_0000 + 0x2000_0000, 1000) == 0                           # altro: non nostro


def test_route_of_a_high_window(m):
    """core_high_route (Synfact): /samples/(8185 + k) per le finestre della zona alta, come le chiede il loro tool."""
    s = m.sym
    path, out = SCRATCH + 0x300, SCRATCH + 0x400
    m.put(MMC_READY, ">I", 1)

    def route(text):
        m.uc.mem_write(path + 8, text.encode() + b"\0")
        m.put(path, ">I", path + 8)                                              # std::string: puntatore ai byte
        m.uc.mem_write(out, bytes(0x90))
        return m.call(s["core_high_route"], [0, path, out])
    k = 0x602                                                                    # prima finestra dei dati
    assert route(f"/samples/{8185 + k}") == 1
    assert m.uc.mem_read(out, 1)[0] == 1                                         # risultato valido
    info = out + 8
    assert struct.unpack(">I", m.uc.mem_read(info + 12, 4))[0] == k << 19         # indirizzo sulla eMMC
    assert route("/samples/12") == 0                                             # slot stock: all'OS
    assert route(f"/samples/{8185 + 0x5FF}") == 0                                # sotto la zona alta


def test_header_for_the_sampler(m):
    """'LSHD' all'inizio dell'area di long-samples (registro): il SAMPLER (CPU #1) vi trova tabella e nomi."""
    sys.path.insert(0, str(ROOT.parent / "tools" / "build"))
    import modarea_layout
    import registry
    hdr = modarea_layout.RAM + next(a for a, b, who, _ in registry.MODAREA if who == "long-samples")
    assert hdr == m.sym["ls_header"]
    magic, table, names = struct.unpack(">3I", m.uc.mem_read(hdr, 12))
    assert magic == 0x4C53_4844 and table == m.sym["ls_table"]
    s = m.sym
    m.disk.s.clear()
    io = s["core_hzfs_native_io"]
    assert m.call(s["core_hzfs_ensure"], [io], count=400_000_000) == 1
    m.body = samp(11 * 48000)
    m.uc.mem_write(SCRATCH, b"MagMag Vocal 175\0")
    assert m.call(s["core_hzfs_put"], [io, SCRATCH, len(m.body), 0, STREAM, 0, SCRATCH + 64],
                  count=2_000_000_000) == 1
    m.uc.mem_write(TOTAL, struct.pack(">I", 256))
    m.call(s["ls_plan"], count=400_000_000)
    assert bytes(m.uc.mem_read(names, 16)).split(b"\0")[0] == b"MagMag Vocal 17"   # 15 caratteri + 0
    assert struct.unpack(">I", m.uc.mem_read(table + 12, 4))[0] == 11 * 48000
