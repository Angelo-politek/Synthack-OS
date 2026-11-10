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
    fixture = ROOT.parent / "web-builder" / "test" / "fixtures" / "hzfs-catalogue.hex"   # testo: i .bin non entrano nel repo
    cats = [m.disk.read(k * 0x80000 // 512, 0x200) for k in (0x600, 0x601)]
    cat = next(c for c in cats if c[:4] == b"HZFS" and struct.unpack(">I", c[12:16])[0] == 1)
    size = struct.unpack(">I", cat[36:40])[0]
    want = cat[:size]
    assert bytes.fromhex(fixture.read_text(encoding="ascii")) == want
    # immagine stock: un solo campione da 4800 nello slot 1
    stock = 4 * 64 + 2 * 4800
    m.uc.mem_write(TOTAL, struct.pack(">I", stock))
    m.call(s["ls_project_new"])                                                  # nessuna lista del progetto
    m.call(s["ls_plan"], count=400_000_000)
    assert m.long(s["ls_status"]) == 1
    sp = (stock + 2047) // 2048
    tab = struct.unpack(">4I", m.uc.mem_read(s["ls_cpu2"], 16))
    assert struct.unpack(">4I", m.uc.mem_read(s["ls_table"], 16)) == tab         # lista = ordine di caricamento
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
    m.call(s["ls_project_new"])
    m.call(s["ls_plan"], count=400_000_000)
    assert bytes(m.uc.mem_read(names, 16)).split(b"\0")[0] == b"MagMag Vocal 17"   # 15 caratteri + 0
    assert struct.unpack(">I", m.uc.mem_read(table + 12, 4))[0] == 11 * 48000


def test_plan_follows_the_slot_map(m):
    """Le 64 associazioni del catalogo (+0x40, slot map di Synfact, scritte dalla pagina Samples del web builder):
    il piano segue quell'ordine; tutte a zero: l'ordine del catalogo."""
    import zlib
    s = m.sym
    io = s["core_hzfs_native_io"]
    m.disk.s.clear()
    assert m.call(s["core_hzfs_ensure"], [io], count=400_000_000) == 1
    for name, sec in ((b"first\0", 2), (b"second\0", 3)):
        m.body = samp(sec * 48000)
        m.uc.mem_write(SCRATCH, name)
        assert m.call(s["core_hzfs_put"], [io, SCRATCH, len(m.body), 0, STREAM, 0, SCRATCH + 64],
                      count=2_000_000_000) == 1
    m.uc.mem_write(TOTAL, struct.pack(">I", 256))

    def frames():                                         # ordine di caricamento (tabella della CPU #2)
        m.call(s["ls_plan"], count=400_000_000)
        n = struct.unpack(">I", m.uc.mem_read(s["ls_cpu2"] + 4, 4))[0]
        return [struct.unpack(">I", m.uc.mem_read(s["ls_cpu2"] + 12 + 8 * i, 4))[0] // 48000 for i in range(n)]
    assert frames() == [2, 3]
    cats = {k: bytearray(m.disk.read(k * 0x80000 // 512, 0x200)) for k in (0x600, 0x601)}
    k = max((k for k in cats if cats[k][:4] == b"HZFS"), key=lambda k: struct.unpack(">I", cats[k][8:12])[0])
    for k in (k,):                                        # associazione 0 -> id 2, nella copia piu' recente
        lba = k * 0x80000 // 512
        raw = cats[k]
        size = struct.unpack(">I", raw[36:40])[0]
        struct.pack_into(">I", raw, 0x40, 2)
        raw[32:36] = bytes(4)
        struct.pack_into(">I", raw, 32, zlib.crc32(bytes(raw[:size]), 0xFFFFFFFF) & 0xFFFFFFFF)
        m.disk.write(lba, bytes(raw))
    assert frames() == [3]                                # solo il secondo, alla posizione 1


def test_transfer_window(m):
    """A high window opens the OS's transfer window as the stock /samples/N does (write_started = 0x40007712, the
    samples service's function); the written catalogue closes it (the UI task sends it NO)."""
    from unicorn import UC_HOOK_CODE
    from unicorn.m68k_const import UC_M68K_REG_A7
    s = m.sym
    path, out = SCRATCH + 0x300, SCRATCH + 0x400
    m.put(MMC_READY, ">I", 1)

    stub = SCRATCH + 0x600                                   # a0 = the result, as at 0x400B8100
    m.uc.mem_write(stub, b"\x20\x7c" + struct.pack(">I", out) + b"\x4e\xf9" + struct.pack(">I", s["core_fs_route"]))

    def route(k):
        m.uc.mem_write(path + 8, f"/samples/{8185 + k}".encode() + b"\0")
        m.put(path, ">I", path + 8)
        m.uc.mem_write(out, bytes(0x90))
        assert m.call(stub, [0, path]) == out                # glue.S: Synfact's route, then ls_route_done
        return out + 8
    info = route(0x602)
    assert struct.unpack(">4I", m.uc.mem_read(info + 60, 16)) == (0x4000_7712, 0, 0x4016_DA7E, 0x4016_DA76)
    assert struct.unpack(">I", m.uc.mem_read(info + 76, 4))[0] == 0x602
    posted = []

    def post(uc, addr, size, _):
        fn = struct.unpack(">I", uc.mem_read(uc.reg_read(UC_M68K_REG_A7) + 8, 4))[0]
        posted.append(struct.unpack(">4I", uc.mem_read(fn, 16)))
    h = m.uc.hook_add(UC_HOOK_CODE, post, begin=0x4000_9DD8, end=0x4000_9DD8)
    try:
        m.call(0x4019_C3F4, [info + 60])                     # the raw writer opens (0x400B60B6)
        assert posted and posted[0][3] == 0x4000_796E        # the stock window, in the UI task
        views = m.call(0x4016_E044) + 64 + 20                # 0x40008392: the views shown

        def messages():
            found, n = [], m.long(views)
            while n != views:
                v = m.long(n + 8)
                if v and m.call(0x401B_A614, [v, 0x4024_1EBC, 0x401C_197C, 0]):
                    found.append(v)
                n = m.long(n)
            return found
        m.call(0x4000_796E, count=200_000_000)
        msg, = messages()
        assert sum(bin(b).count("1") for b in m.draw(msg)) > 300     # the window and its two lines
        posted.clear()
        m.call(m.long(info + 76 + 12), [info + 76, 0])       # a data window written: stays open
        assert not posted
        info = route(0x600)
        m.disk.s.clear()                                     # no catalogue: nothing for ls_refresh to send
        m.call(m.long(info + 76 + 12), [info + 76, 0])       # the catalogue written: closed in the UI task
        p, = posted
        m.uc.mem_write(SCRATCH, struct.pack(">4I", *p))
        closes = m.long(s["ls_transfer_closes"])
        m.call(p[3], [SCRATCH], count=200_000_000)
        assert m.uc.mem_read(msg + 48, 1)[0] == 1 and m.long(msg + 76) == 2   # closed, as by NO
        assert m.long(s["ls_transfer_closes"]) == closes + 1
        m.call(p[3], [SCRATCH], count=200_000_000)           # closing already: nothing
        assert m.long(s["ls_transfer_closes"]) == closes + 1
    finally:
        m.uc.hook_del(h)


def test_project_list(m):
    """The project's list of long samples (projstore, as Synfact's project pool keeps HZFS ids per position): a project
    without one gets the load order and keeps it (saved with the project); a saved list puts its files first, the
    others after; a file that is gone leaves its position empty. The voice CPU reads the positions in shared RAM."""
    import json
    s = m.sym
    io = s["core_hzfs_native_io"]
    rec = int(json.loads((ROOT.parent / "mods" / "projstore" / "patch.json").read_text())["layout"]["data"], 16)
    m.disk.s.clear()
    assert m.call(s["core_hzfs_ensure"], [io], count=400_000_000) == 1
    ids = []
    for name, sec in ((b"a\0", 2), (b"b\0", 3), (b"c\0", 4)):
        m.body = samp(sec * 48000)
        m.uc.mem_write(SCRATCH, name)
        assert m.call(s["core_hzfs_put"], [io, SCRATCH, len(m.body), 0, STREAM, 0, SCRATCH + 64],
                      count=2_000_000_000) == 1
        ids.append(m.long(SCRATCH + 64))
    m.uc.mem_write(TOTAL, struct.pack(">I", 256))

    def listed():
        n = m.long(s["ls_table"] + 4)
        return [m.long(s["ls_table"] + 12 + 8 * i) // 48000 for i in range(n)]

    def shared():
        magic, n = struct.unpack(">II", m.uc.mem_read(0x1000_0780, 8))
        return magic, list(m.uc.mem_read(0x1000_0788, n))

    def saved():
        assert bytes(m.uc.mem_read(rec, 2)) == b"LP"
        n = m.uc.mem_read(rec + 2, 1)[0]
        return list(struct.unpack(f">{n}H", m.uc.mem_read(rec + 4, 2 * n)))
    m.call(s["ls_plan"], count=400_000_000)            # boot plan first (the saved list may be another test's)
    applied = m.long(s["ls_applied"])
    m.call(0x4001_D16A, [m.project, 0xFFFF_FFFF], count=400_000_000)   # NEW PROJECT (hook): no list
    assert m.long(s["ls_applied"]) == applied + 1
    load = [m.long(s["ls_cpu2"] + 12 + 8 * i) // 48000 for i in range(3)]   # seconds of the files, load order
    assert sorted(load) == [2, 3, 4]
    sec = dict(zip((2, 3, 4), ids))
    assert listed() == load and saved() == [sec[x] for x in load]      # load order, kept with the project
    assert shared() == (0x4C53_4D31, [0, 1, 2])
    m.uc.mem_write(rec, b"LP\x02\x00" + struct.pack(">HH", sec[4], sec[2]))  # a project saved with [4 s, 2 s]
    m.call(s["ls_project_loaded"], [1])
    assert listed() == [4, 2, 3] and saved() == [sec[4], sec[2], sec[3]]     # the 3 s file after its list
    assert shared()[1] == [load.index(4), load.index(2), load.index(3)]
    m.uc.mem_write(rec, b"LP\x02\x00" + struct.pack(">HH", 999, sec[3]))      # a file it names is gone
    m.call(s["ls_project_loaded"], [1])
    rest = [x for x in load if x != 3]
    assert listed() == [0, 3] + rest and saved() == [999, sec[3]] + [sec[x] for x in rest]
    assert shared()[1] == [0xFF, load.index(3)] + [load.index(x) for x in rest]
    m.call(s["ls_project_loaded"], [0])                                 # load failed: list unchanged
    assert saved() == [999, sec[3]] + [sec[x] for x in rest]
    m.call(s["ls_project_new"])


@pytest.fixture(scope="module")
def voice(tmp_path_factory):
    """CPU #2 of a build with long-samples and sampler: the receiver at the end of the audio interrupt."""
    sys.path[:0] = [str(ROOT.parent / "tools" / "build"), str(ROOT.parent / "tools" / "unpack")]
    import build
    import eft
    import engine as eng
    t = tmp_path_factory.mktemp("ls7")
    build.build(SY, [ROOT.parent / "mods" / "long-samples", ROOT.parent / "mods" / "sampler"], t / "o.syx",
                log=lambda *_: None)
    e = eng.Engine(image=eft.unpack(t / "o.syx", t / "u", ids=[7])[7].read_bytes())
    e.boot(cold=True)
    return e


def link(m, e):
    """Shared RAM between the two emulators: when CPU #1 reads the answer word, CPU #2 runs one audio block on the
    window CPU #1 wrote (and the project's positions)."""
    from unicorn import UC_HOOK_MEM_READ
    import cli

    def answer(uc, access, addr, size, value, _):
        e.uc.mem_write(0x780, bytes(m.uc.mem_read(0x1000_0780, 0x48)))
        e.uc.mem_write(0x800, bytes(m.uc.mem_read(0x1000_0800, 0x400)))
        e.render_block(bytes(cli.make_params(44, 60)))
        m.uc.mem_write(0x1000_0818, bytes(e.uc.mem_read(0x818, 4)))
    return m.uc.hook_add(UC_HOOK_MEM_READ, answer, begin=0x1000_0818, end=0x1000_081B)


def test_hot_upload_plays_without_reboot(m, voice):
    """A file stored while the Syntakt runs goes to the voice CPU through the runtime window (upload.c -> engine/rx.c)
    and plays at once: SAMP 1 (no stock samples, the first long one) after ls_refresh, as after a web upload."""
    import math
    import cli
    s, e = m.sym, voice
    io = s["core_hzfs_native_io"]
    m.put(s["ls_up_fault"], ">I", 0)
    m.disk.s.clear()
    assert m.call(s["core_hzfs_ensure"], [io], count=400_000_000) == 1
    m.uc.mem_write(TOTAL, struct.pack(">I", 256))                     # no stock samples (as on the device)
    e.uc.mem_write(0x4404_F754, bytes(512))
    m.call(s["ls_plan"], count=400_000_000)                          # boot: no long samples yet
    m.call(s["ls_project_new"])
    assert m.long(s["ls_loaded"]) == 0
    frames = 24000
    pcm = [int(12000 * math.sin(2 * math.pi * 1000 * i / 48000)) for i in range(frames)]
    head = bytearray(64)
    head[0:4], head[12:16] = b"SAMP", b"rec1"
    struct.pack_into(">I", head, 8, frames)
    m.body = bytes(head) + struct.pack(f">{frames}h", *pcm)
    m.uc.mem_write(SCRATCH, b"rec1\0")
    assert m.call(s["core_hzfs_put"], [io, SCRATCH, len(m.body), 0, STREAM, 0, SCRATCH + 64],
                  count=2_000_000_000) == 1
    h = link(m, e)
    try:
        assert m.call(s["ls_refresh"], count=2_000_000_000) == 1
    finally:
        m.uc.hook_del(h)
    assert m.long(s["ls_up_fault"]) == 0 and m.long(s["ls_table"] + 4) == 1
    table = CPU2_POOL + 2048
    magic, n, ptr, got = struct.unpack(">4I", e.uc.mem_read(table, 16))
    assert (magic, n, got) == (0x5348_4C53, 1, frames) and ptr == m.long(s["ls_table"] + 8)
    assert bytes(e.uc.mem_read(ptr, 2 * frames)) == m.body[64:]
    words = [0x4000, 0x300, 0, 0, 0, 0x7800, 0, 0x6400]              # SAMP 1, ONESHOT
    p = bytearray(cli.make_params(44, 60))
    for k, w in enumerate(words):
        struct.pack_into(">h", p, 2 + 2 * k, w)
    e.uc.mem_write(0x640, struct.pack(">10h", 44, *words, 0))
    out = []
    for b in range(24):
        q = bytearray(p)
        if b in (0, 2):
            q[0x180] = 1
        out += e.render_block(bytes(q))[0]
    tail = out[256:]
    zc = sum(1 for i in range(1, len(tail)) if (tail[i - 1] < 0) != (tail[i] < 0))
    assert abs(zc / 2 / (len(tail) / 48000) - 1000) < 60              # the new sample, 1 kHz


def test_hot_upload_after_a_boot_with_long_samples(m, voice):
    """Come sulla macchina dell'utente: un campione lungo gia' caricato all'avvio e nella lista del progetto, poi un
    take del registratore (file nuovo, ls_refresh). Il nuovo deve suonare alla sua posizione, il vecchio alla sua.
    RC1 sulla macchina: il take compariva col nome ma vuoto; salvandone un altro suonavano tutti e due."""
    import math
    s, e = m.sym, voice
    io = s["core_hzfs_native_io"]
    m.put(s["ls_up_fault"], ">I", 0)
    m.disk.s.clear()
    assert m.call(s["core_hzfs_ensure"], [io], count=400_000_000) == 1
    m.uc.mem_write(TOTAL, struct.pack(">I", 256))
    e.uc.mem_write(0x4404_F754, bytes(512))

    def put(name, freq, frames):
        pcm = [int(12000 * math.sin(2 * math.pi * freq * i / 48000)) for i in range(frames)]
        head = bytearray(64)
        head[0:4] = b"SAMP"
        head[12:12 + len(name)] = name
        struct.pack_into(">I", head, 8, frames)
        m.body = bytes(head) + struct.pack(f">{frames}h", *pcm)
        m.uc.mem_write(SCRATCH, name + b"\0")
        assert m.call(s["core_hzfs_put"], [io, SCRATCH, len(m.body), 0, STREAM, 0, SCRATCH + 64],
                      count=2_000_000_000) == 1
        return m.body[64:]
    old = put(b"boot1", 500, 20000)
    m.call(s["ls_plan"], count=400_000_000)                          # avvio: un file
    m.call(s["ls_project_new"])
    assert m.long(s["ls_loaded"]) == 1
    for n in range(m.call(s["ls_count"]) // 2048):                   # l'invio dell'avvio, pagina per pagina
        m.put(PAGE_NOW, ">I", n)
        off = m.call(s["ls_map"])
        e.uc.mem_write(CPU2_POOL + n * 2048, bytes(m.uc.mem_read((IMAGE + off) & 0xFFFF_FFFF, 2048)))
    takes = [put(b"take1", 1000, 24000)]
    h = link(m, e)
    try:
        assert m.call(s["ls_refresh"], count=2_000_000_000) == 1
        takes.append(put(b"take2", 2000, 16000))
        assert m.call(s["ls_refresh"], count=2_000_000_000) == 1
    finally:
        m.uc.hook_del(h)
    assert m.long(s["ls_up_fault"]) == 0 and m.long(s["ls_table"] + 4) == 3
    e.uc.mem_write(0x780, bytes(m.uc.mem_read(0x1000_0780, 0x48)))
    table = CPU2_POOL + 2048
    magic, n = struct.unpack(">2I", e.uc.mem_read(table, 8))
    assert (magic, n) == (0x5348_4C53, 3)
    for pos, want in enumerate([old, *takes]):                       # posizione della lista -> file -> PCM sulla CPU #2
        k = m.uc.mem_read(0x1000_0788 + pos, 1)[0]
        ptr, frames = struct.unpack(">2I", e.uc.mem_read(table + 8 + 8 * k, 8))
        assert (ptr, frames) == struct.unpack(">2I", m.uc.mem_read(s["ls_table"] + 8 + 8 * pos, 8)), pos
        assert frames == len(want) // 2 and bytes(e.uc.mem_read(ptr, len(want))) == want, pos
