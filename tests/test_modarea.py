"""Mod modarea: l'aggancio all'avvio copia il blocco accodato alla sezione 3 in RAM a 0x46000000.

Costruisce il .syx (modarea + master-comp), lo rispacchetta, carica la sezione 3 risultante come
farebbe il bootloader ed esegue da 0x400004B2 fino al ritorno nel codice originale (0x400004BA).
"""

import json
import struct
import sys
from pathlib import Path

import pytest

pytest.importorskip("unicorn")
from unicorn import UC_ARCH_M68K, UC_MODE_BIG_ENDIAN, Uc  # noqa: E402
from unicorn.m68k_const import (UC_CPU_M68K_ANY, UC_M68K_REG_A1, UC_M68K_REG_A7,  # noqa: E402
                                UC_M68K_REG_D4, UC_M68K_REG_D7, UC_M68K_REG_SR)

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "tools" / "unpack"), str(ROOT / "tools" / "build")]
import build  # noqa: E402
import eft  # noqa: E402

STOCK = ROOT / "firmware" / "Syntakt_OS1.41.syx"
MODS = [ROOT / "mods" / m for m in ("modarea", "master-comp")]
pytestmark = pytest.mark.skipif(not STOCK.exists() or not all((m / "patch.json").exists() for m in MODS),
                                reason="firmware stock o patch assenti")
LOAD = 0x4000_0400


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    t = tmp_path_factory.mktemp("modarea")
    out = t / "o.syx"
    build.build(STOCK, MODS, out, log=lambda *_: None)
    return eft.unpack(out, t / "u", ids=[3])[3].read_bytes(), eft.unpack(STOCK, t / "s", ids=[3])[3].read_bytes()


def test_section_grows_only_by_the_mod_area(built):
    sec3, stock = built
    lay = json.loads((ROOT / "mods" / "modarea" / "patch.json").read_text(encoding="utf-8"))["layout"]
    img = int(lay["img"], 16)
    assert len(sec3) > len(stock)
    assert not any(sec3[len(stock):img - LOAD])                 # riempimento a zero
    spec = json.loads((ROOT / "mods" / "master-comp" / "patch.json").read_text(encoding="utf-8"))
    ap = [p for p in spec["patches"] if p.get("append")][0]
    a = int(ap["addr"], 16) - LOAD
    assert sec3[a:a + ap["len"]] == bytes.fromhex(ap["hex"])


def test_boot_hook_copies_mod_area_and_resumes(built):
    sec3, _ = built
    uc = Uc(UC_ARCH_M68K, UC_MODE_BIG_ENDIAN, cpu=UC_CPU_M68K_ANY)
    uc.mem_map(0x4000_0000, 0x0040_0000)
    uc.mem_write(LOAD, sec3)
    uc.mem_map(0x4600_0000, 0x1_0000)
    uc.mem_map(0x47FF_0000, 0x1_0000)
    uc.reg_write(UC_M68K_REG_SR, 0x2700)
    sp = 0x4800_0000 - 0x100
    uc.reg_write(UC_M68K_REG_A7, sp)
    uc.reg_write(UC_M68K_REG_A1, 0xA1A1_A1A1)
    for r, v in zip(range(UC_M68K_REG_D4, UC_M68K_REG_D7 + 1), (4, 5, 6, 7)):
        uc.reg_write(r, v)
    uc.emu_start(0x4000_04B2, 0x4000_04BA, count=100_000)
    assert bytes(uc.mem_read(0x4600_0000, 0x8000)) == sec3[0x4034_8000 - LOAD:0x4035_0000 - LOAD].ljust(0x8000, b"\0")
    assert uc.reg_read(UC_M68K_REG_A1) == 0xA1A1_A1A1                         # registri del chiamante
    assert uc.reg_read(UC_M68K_REG_A7) == sp - 16                              # come lea -16(sp),sp
    assert struct.unpack(">4I", uc.mem_read(sp - 16, 16)) == (4, 5, 6, 7)       # movem d4-d7
