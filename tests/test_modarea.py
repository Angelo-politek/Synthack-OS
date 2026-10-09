"""Mod modarea: all'avvio il flusso SHLZ accodato alla sezione 3 viene decompresso in RAM a 0x46000000.

Costruisce il .syx (modarea + master-comp + readable-values), lo rispacchetta, carica la sezione 3
risultante come farebbe il bootloader ed esegue da 0x400004B2 fino al ritorno nel codice originale
(0x400004BA).
"""

import json
import struct
import sys
from pathlib import Path

import pytest

pytest.importorskip("unicorn")
from unicorn import UC_ARCH_M68K, UC_HOOK_CODE, UC_MODE_BIG_ENDIAN, Uc  # noqa: E402
from unicorn.m68k_const import (UC_CPU_M68K_ANY, UC_M68K_REG_A1, UC_M68K_REG_A2, UC_M68K_REG_A3,  # noqa: E402
                                UC_M68K_REG_A7, UC_M68K_REG_D0, UC_M68K_REG_D2, UC_M68K_REG_D4,
                                UC_M68K_REG_D7, UC_M68K_REG_SR)

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "tools" / "unpack"), str(ROOT / "tools" / "build")]
import build  # noqa: E402
import eft  # noqa: E402
import lz  # noqa: E402

STOCK = ROOT / "firmware" / "Syntakt_OS1.41.syx"
MODS = [ROOT / "mods" / m for m in ("modarea", "vparams", "master-comp", "readable-values", "beat-repeat", "fx3")]
pytestmark = pytest.mark.skipif(not STOCK.exists() or not all((m / "patch.json").exists() for m in MODS),
                                reason="firmware stock o patch assenti")
LOAD = 0x4000_0400
LAYOUT = json.loads((ROOT / "mods" / "modarea" / "patch.json").read_text(encoding="utf-8"))["layout"]
IMG, RAM, SIZE = (int(LAYOUT[k], 16) for k in ("img", "ram", "size"))


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


def boot(sec3):
    uc = Uc(UC_ARCH_M68K, UC_MODE_BIG_ENDIAN, cpu=UC_CPU_M68K_ANY)
    uc.mem_map(0x4000_0000, 0x0040_0000)
    uc.mem_write(LOAD, sec3)
    uc.mem_map(0x4600_0000, 0x2_0000)
    uc.mem_write(RAM, b"\xA5" * SIZE + b"\x5A" * 16)           # RAM sporca: l'area va azzerata
    uc.mem_map(0x47FF_0000, 0x1_0000)
    uc.reg_write(UC_M68K_REG_SR, 0x2700)
    sp = 0x4800_0000 - 0x100
    uc.reg_write(UC_M68K_REG_A7, sp)
    regs = {UC_M68K_REG_A1: 0xA1A1_A1A1, UC_M68K_REG_A2: 0xA2A2_A2A2, UC_M68K_REG_A3: 0xA3A3_A3A3,
            UC_M68K_REG_D0: 0xD0D0_D0D0, UC_M68K_REG_D2: 0xD2D2_D2D2}
    for r, v in regs.items():
        uc.reg_write(r, v)
    for r, v in zip(range(UC_M68K_REG_D4, UC_M68K_REG_D7 + 1), (4, 5, 6, 7)):
        uc.reg_write(r, v)
    count = [0]
    uc.hook_add(UC_HOOK_CODE, lambda *_: count.__setitem__(0, count[0] + 1))
    uc.emu_start(0x4000_04B2, 0x4000_04BA, count=5_000_000)
    return uc, sp, regs, count[0]


def test_boot_hook_decompresses_mod_area_and_resumes(built):
    sec3, _ = built
    uc, sp, regs, n = boot(sec3)
    img = area_image()
    ram = bytes(uc.mem_read(RAM, SIZE + 16))
    assert ram[:len(img)] == img
    assert not any(ram[len(img):SIZE])                          # resto dell'area azzerato
    assert ram[SIZE:] == b"\x5A" * 16                           # niente scritture oltre l'area
    for r, v in regs.items():
        assert uc.reg_read(r) & 0xFFFFFFFF == v                 # registri del chiamante
    assert uc.reg_read(UC_M68K_REG_A7) == sp - 16               # come lea -16(sp),sp
    assert struct.unpack(">4I", uc.mem_read(sp - 16, 16)) == (4, 5, 6, 7)   # movem d4-d7
    assert n < 400_000                                          # < 2 ms a 250 MHz: avvio invariato


def test_without_stream_area_is_only_cleared(built):
    sec3, stock = built
    uc, _, _, _ = boot(sec3[:IMG - LOAD] + b"NONE" + bytes(12))
    assert not any(uc.mem_read(RAM, SIZE))
