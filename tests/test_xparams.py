"""xparams (mods/xparams): indici logici 0x36..0x3d di ogni traccia salvati, con i p-lock e verso la CPU #2.

- Il codice viene da SY FM4 (Rxuting, MIT): i siti della sezione 3, riportati alla 1.40A, hanno le impronte del suo
  patcher (tests/test_sy_fm4.py, RXUTING); qui i byte nuovi.
- CPU #1: la build vera; l'azzeramento del BSS di modarea chiama xp_boot dalla lista di avvio e le tabelle di slot e
  lane valgono come nell'originale; la copia per blocco verso la RAM condivisa e il suo costo.
"""

import json
import struct
import sys
from pathlib import Path

import pytest

pytest.importorskip("unicorn")

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "tests"), str(ROOT / "tools" / "emu"), str(ROOT / "tools" / "build"),
                str(ROOT / "tools" / "unpack")]
import build  # noqa: E402
import eft  # noqa: E402
import modarea_layout as M  # noqa: E402
import registry  # noqa: E402

STOCK = ROOT / "firmware" / "Syntakt_OS1.42.syx"
pytestmark = pytest.mark.skipif(not STOCK.exists(), reason="firmware stock assente")
SPEC = json.loads((ROOT / "mods" / "xparams" / "patch.json").read_text(encoding="utf-8"))
SYM = {k: int(v, 16) for k, v in SPEC["symbols"].items()}
LOAD = 0x4000_0400


@pytest.fixture(scope="module")
def stock():
    f = eft.unpack(STOCK, ROOT / "unpacked" / STOCK.stem, ids=[3])
    return f[3].read_bytes()


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    t = tmp_path_factory.mktemp("xparams")
    out = t / "o.syx"
    build.build(STOCK, [ROOT / "mods" / "xparams"], out, log=lambda *_: None)
    return eft.unpack(out, t / "u", ids=[3])[3].read_bytes()


def test_boot_list_fills_the_storage_tables(built, stock):
    import test_modarea as MA
    uc, _ = MA.boot(built)
    slot = next(n for n, who in registry.BOOT_SLOTS.items() if who == "xparams")
    assert struct.unpack(">I", uc.mem_read(M.RAM + M.BOOT_LIST + 4 * slot, 4))[0] == SYM["xp_boot"]
    lix2phys = struct.unpack_from(">54I", stock, 0x4023_4344 - LOAD)
    phys2lix = struct.unpack_from(">54I", stock, 0x4023_441C - LOAD)
    l2p = struct.unpack(">71I", uc.mem_read(SYM["xp_sound_l2p"], 4 * 71))
    p2l = struct.unpack(">71I", uc.mem_read(SYM["xp_sound_p2l"], 4 * 71))
    lane = struct.unpack(">71I", uc.mem_read(SYM["xp_lane_of_lix"], 4 * 71))
    assert l2p[:54] == lix2phys and p2l[:54] == phys2lix and lane[:54] == lix2phys
    assert l2p[54:] == p2l[54:] == tuple(range(54, 71))
    assert lane[54:62] == tuple(range(0x50, 0x58)) and set(lane[62:]) == {0xFF}


def test_stock_sound_without_a_machine_hook_stays_zero(built):
    """Senza una machine registrata (xp_on_empty) gli indici extra di un suono stock restano a zero."""
    import test_modarea as MA
    uc, _ = MA.boot(built)
    sound, storage = 0x47FF_0000, 0x47FF_1000
    uc.mem_write(sound, b"\xEE" * 0x100)
    uc.mem_write(storage, bytes(0x1C) + struct.pack(">62H", *range(1, 63)))
    MA.call(uc, SYM["xp_load_params"], sound, storage)
    lix = struct.unpack(">62H", uc.mem_read(sound + 20, 124))
    p2l = struct.unpack(">62I", uc.mem_read(SYM["xp_sound_p2l"], 4 * 62))
    assert all(lix[p2l[p]] == p + 1 for p in range(62))                  # slot -> indice logico
    uc.mem_write(storage + 0x1C + 2 * 0x36, bytes(16))
    MA.call(uc, SYM["xp_load_params"], sound, storage)
    assert not any(uc.mem_read(sound + 20 + 2 * 0x36, 16))


def test_cpu1_cost_per_block(built):
    """xp_dma_wait a ogni blocco audio della CPU #1: attesa dell'eDMA (gia' finita) e copia degli indici extra."""
    import budget
    import test_modarea as MA
    from unicorn import UC_HOOK_CODE
    from unicorn.m68k_const import UC_M68K_REG_A7, UC_M68K_REG_SR
    uc, _ = MA.boot(built)
    uc.mem_map(0x1000_0000, 0x2_0000)
    uc.mem_map(0x8000_0000, 0x1_0000)
    uc.mem_map(0xFC00_0000, 0x10_0000)
    n = [0]
    uc.hook_add(UC_HOOK_CODE, lambda *a: n.__setitem__(0, n[0] + 1))
    uc.reg_write(UC_M68K_REG_SR, 0x2700)
    uc.reg_write(UC_M68K_REG_A7, MA.STACK - 4)
    uc.mem_write(MA.STACK - 4, struct.pack(">I", MA.RET))
    uc.mem_write(0x8000_21B0, bytes(range(256)) * 8)
    uc.emu_start(SYM["xp_dma_wait"], MA.RET, count=100_000)
    print("xp_dma_wait:", n[0])
    assert n[0] <= budget.AUDIO_CPU["xparams"], n[0]
    got = struct.unpack(">64H", uc.mem_read(0x1000_0700, 128))
    seq = struct.unpack(">1024H", uc.mem_read(0x8000_21B0, 2048))
    assert got == tuple(seq[0xE + t * 0x47 + 0x36 + k] for t in range(8) for k in range(8))
