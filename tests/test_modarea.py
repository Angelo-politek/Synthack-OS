"""Mod modarea: all'avvio il flusso SHLZ accodato alla sezione 3 viene decompresso nel primo blocco dell'heap.

Costruisce il .syx con tutte le mod che usano l'area, lo rispacchetta, carica la sezione 3 risultante come
farebbe il bootloader ed esegue l'azzeramento del BSS (0x400004B2) fino al ritorno al chiamante. Poi usa
l'allocatore vero dell'OS (0x4010350C, free 0x40103712): la prima chiamata prenota l'area (indice 0), e
nessuna allocazione successiva ci finisce dentro o la tocca (issue #4: la RAM sopra il BSS, usata fino
alla v0.8.1, l'OS la usa a runtime).
"""

import json
import random
import struct
import sys
from pathlib import Path

import pytest

pytest.importorskip("unicorn")
from unicorn import UC_ARCH_M68K, UC_HOOK_MEM_WRITE, UC_MODE_BIG_ENDIAN, Uc  # noqa: E402
from unicorn.m68k_const import (UC_CPU_M68K_ANY, UC_M68K_REG_A1, UC_M68K_REG_A2, UC_M68K_REG_A3,  # noqa: E402
                                UC_M68K_REG_A7, UC_M68K_REG_D0, UC_M68K_REG_D2, UC_M68K_REG_D4,
                                UC_M68K_REG_D7, UC_M68K_REG_SR)

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "tools" / "unpack"), str(ROOT / "tools" / "build")]
import build  # noqa: E402
import eft  # noqa: E402
import lz  # noqa: E402
import modarea_layout as L  # noqa: E402

STOCK = ROOT / "firmware" / "Syntakt_OS1.41.syx"
MODS = [ROOT / "mods" / m for m in ("modarea", "vparams", "master-comp", "readable-values", "beat-repeat", "fx3")]
pytestmark = pytest.mark.skipif(not STOCK.exists() or not all((m / "patch.json").exists() for m in MODS),
                                reason="firmware stock o patch assenti")
LOAD = 0x4000_0400
SPEC = json.loads((ROOT / "mods" / "modarea" / "patch.json").read_text(encoding="utf-8"))
LAYOUT = SPEC["layout"]
IMG, RAM, SIZE = (int(LAYOUT[k], 16) for k in ("img", "ram", "size"))
BLOCK = int(LAYOUT["heap_block"], 16)
BSS_LO, BSS_HI = 0x4033_9000, 0x4556_5490
ALLOC, FREE = 0x4010_350C, 0x4010_3712
HEAP_LO, HEAP_HI = 0x444E_38C0, 0x454E_38C0
STACK, RET = 0x47FF_8000, 0x47FF_F000


def area_image():
    """Area mod attesa: le patch accodate di tutte le mod alle loro posizioni, zeri negli spazi."""
    img = bytearray()
    for m in MODS:
        for p in json.loads((m / "patch.json").read_text(encoding="utf-8"))["patches"]:
            if p.get("append"):
                a = int(p["addr"], 16) - IMG
                data = bytes.fromhex(p["hex"])
                img.extend(bytes(max(0, a + len(data) - len(img))))
                img[a:a + len(data)] = data
    return bytes(img)


def test_layout_is_the_first_heap_block():
    assert (RAM, SIZE, BLOCK) == (L.RAM, L.SIZE, L.HEAP_BLOCK)
    assert BLOCK == HEAP_LO and RAM == BLOCK + 0x10 and RAM + SIZE == BLOCK + 0x1_0000
    assert BSS_LO < RAM < RAM + SIZE < BSS_HI


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    t = tmp_path_factory.mktemp("modarea")
    out = t / "o.syx"
    build.build(STOCK, MODS, out, log=lambda *_: None)
    return eft.unpack(out, t / "u", ids=[3])[3].read_bytes(), eft.unpack(STOCK, t / "s", ids=[3])[3].read_bytes()


def test_section_grows_only_by_the_compressed_area(built):
    sec3, stock = built
    assert len(sec3) > len(stock)
    assert not any(sec3[len(stock):IMG - LOAD])                 # riempimento a zero fino all'area
    stream = sec3[IMG - LOAD:]
    assert stream[:4] == b"SHLZ"
    assert lz.decompress(stream) == area_image()
    assert len(stream) < len(area_image())
    assert len(area_image()) <= SIZE


def machine(sec3):
    uc = Uc(UC_ARCH_M68K, UC_MODE_BIG_ENDIAN, cpu=UC_CPU_M68K_ANY)
    uc.mem_map(0x4000_0000, 0x0560_0000)                        # immagine e BSS
    uc.mem_write(LOAD, sec3)
    uc.mem_map(0x47FF_0000, 0x1_0000)                           # stack
    uc.mem_write(RET, b"\x4e\x75")
    return uc


def boot(sec3):
    uc = machine(sec3)
    for a in (BSS_LO + 0x10_0000, RAM - 0x10, RAM + SIZE, BSS_HI - 0x10):
        uc.mem_write(a, b"\x5A" * 16)                           # RAM sporca: va azzerata
    uc.mem_write(RAM, b"\xA5" * SIZE)
    uc.mem_write(BSS_HI, b"\x77" * 16)                          # oltre il BSS: non si tocca
    uc.reg_write(UC_M68K_REG_SR, 0x2700)
    uc.reg_write(UC_M68K_REG_A7, STACK - 4)
    uc.mem_write(STACK - 4, struct.pack(">I", RET))
    regs = {UC_M68K_REG_A1: 0xA1A1_A1A1, UC_M68K_REG_A2: 0xA2A2_A2A2, UC_M68K_REG_A3: 0xA3A3_A3A3,
            UC_M68K_REG_D0: 0xD0D0_D0D0, UC_M68K_REG_D2: 0xD2D2_D2D2}
    for r, v in regs.items():
        uc.reg_write(r, v)
    for r, v in zip(range(UC_M68K_REG_D4, UC_M68K_REG_D7 + 1), (4, 5, 6, 7)):
        uc.reg_write(r, v)
    uc.emu_start(0x4000_04B2, RET, count=40_000_000)
    return uc, regs


def test_boot_decompresses_the_area_and_clears_the_rest_of_bss(built):
    sec3, _ = built
    uc, regs = boot(sec3)
    assert not any(uc.mem_read(BSS_LO, RAM - BSS_LO))            # tutto il BSS prima dell'area...
    assert not any(uc.mem_read(RAM + SIZE, BSS_HI - RAM - SIZE))  # ...e dopo
    img = area_image()
    ram = bytes(uc.mem_read(RAM, SIZE))
    assert ram[:len(img)] == img
    assert not any(ram[len(img):])                              # resto dell'area azzerato
    for a in (BSS_LO + 0x10_0000, RAM - 0x10, RAM + SIZE, BSS_HI - 0x10):
        assert not any(uc.mem_read(a, 16)), hex(a)              # BSS a zero intorno all'area
    assert uc.mem_read(BSS_HI, 16) == b"\x77" * 16
    for r, v in regs.items():
        assert uc.reg_read(r) & 0xFFFFFFFF == v                 # registri del chiamante
    for r, v in zip(range(UC_M68K_REG_D4, UC_M68K_REG_D7 + 1), (4, 5, 6, 7)):
        assert uc.reg_read(r) == v
    assert uc.reg_read(UC_M68K_REG_A7) == STACK                 # tornato al chiamante con rts


def test_without_stream_area_is_only_cleared(built):
    sec3, stock = built
    uc, _ = boot(sec3[:IMG - LOAD] + b"NONE" + bytes(12))
    assert not any(uc.mem_read(RAM, SIZE))


def call(uc, fn, *args):
    sp = STACK - 4 * (len(args) + 1)
    uc.mem_write(sp, struct.pack(f">{len(args) + 1}I", RET, *args))
    uc.reg_write(UC_M68K_REG_SR, 0x2700)
    uc.reg_write(UC_M68K_REG_A7, sp)
    uc.emu_start(fn, RET, count=2_000_000)
    return uc.reg_read(UC_M68K_REG_D0) & 0xFFFFFFFF


def test_first_allocation_reserves_the_area_and_no_other_block_touches_it(built):
    sec3, _ = built
    uc, _ = boot(sec3)
    img = area_image()
    block_var = int(SPEC["symbols"]["modarea_block"], 16)
    assert struct.unpack(">I", uc.mem_read(block_var, 4))[0] == 0
    writes = []
    uc.hook_add(UC_HOOK_MEM_WRITE, lambda u, acc, a, n, v, d: writes.append(a), begin=RAM, end=RAM + SIZE - 1)
    first = call(uc, ALLOC, 0x40)                               # prima allocazione dell'OS
    assert struct.unpack(">I", uc.mem_read(block_var, 4))[0] == BLOCK
    assert not BLOCK <= first < BLOCK + 0x1_0000
    rnd = random.Random(4)
    live = [first]
    for i in range(1500):
        if live and rnd.random() < 0.4:
            call(uc, FREE, live.pop(rnd.randrange(len(live))))
            continue
        size = rnd.choice([16, 40, 300, 4096, 0x1_0000, 0x4_0000, rnd.randrange(1, 0x2_0000)])
        p = call(uc, ALLOC, size)
        if p == 0:
            continue
        assert HEAP_LO <= p < HEAP_HI
        assert p + size <= BLOCK or p >= BLOCK + 0x1_0000, (hex(p), size)
        live.append(p)
    for p in live:
        call(uc, FREE, p)
    big = call(uc, ALLOC, 0x80_0000)                            # meta' heap: c'e' ancora (l'altra meta')
    assert big and not big <= BLOCK < big + 0x80_0000
    assert writes == []                                         # l'allocatore non ha mai scritto nell'area
    assert bytes(uc.mem_read(RAM, len(img))) == img
