"""sample-manager (mods/sample-manager): la lista dei campioni lunghi sul dispositivo: disegno, tasti, ordine,
cancellazione dall'archivio (eMMC finta, come tests/test_long_samples.py), assegnazione alla traccia."""

import json
import math
import struct
import sys
from pathlib import Path

import pytest

pytest.importorskip("unicorn")

ROOT = Path(__file__).resolve().parents[1]
SY = ROOT / "firmware" / "Syntakt_OS1.42.syx"
MOD = ROOT / "mods" / "sample-manager"
PATCH = MOD / "patch.json"
pytestmark = pytest.mark.skipif(not SY.exists() or not PATCH.exists(), reason="OS stock o patch.json assente")
sys.path[:0] = [str(ROOT / "tools" / "emu"), str(ROOT / "tools" / "build"), str(ROOT / "tools" / "unpack"),
                str(ROOT / "tests")]

EV = 0x4FE0_6000
YES, NO, UP, DOWN = 12, 13, 14, 15


def sym_of(mod):
    return {k: int(v, 16) for k, v in json.loads((ROOT / "mods" / mod / "patch.json").read_text(
        encoding="utf-8"))["symbols"].items()}


@pytest.fixture(scope="module")
def m():
    """OS avviato con sample-manager e le sue dipendenze, eMMC finta con tre campioni lunghi nella lista."""
    import screens
    import test_long_samples as T
    from unicorn import UC_HOOK_CODE
    from unicorn.m68k_const import UC_M68K_REG_A7, UC_M68K_REG_D0, UC_M68K_REG_PC
    ui = screens.UI(["sample-manager"])
    ui.call(ui.sym["sfcore_bind"])
    disk = T.Disk()
    ui.disk = disk
    ui.put(T.MMC_READY, ">I", 1)
    ui.put(T.MMC_SECTORS, ">I", T.SECTORS)

    def ret(uc, d0):
        sp = uc.reg_read(UC_M68K_REG_A7)
        uc.reg_write(UC_M68K_REG_PC, struct.unpack(">I", uc.mem_read(sp, 4))[0])
        uc.reg_write(UC_M68K_REG_A7, sp + 4)
        uc.reg_write(UC_M68K_REG_D0, d0)

    def args(uc, n):
        return struct.unpack(f">{n}I", uc.mem_read(uc.reg_read(UC_M68K_REG_A7) + 4, 4 * n))

    def mmc(uc, pc, size, _):
        lba, n, buf = args(uc, 3)
        if pc == T.MMC_READ:
            uc.mem_write(buf, disk.read(lba, n))
        else:
            disk.write(lba, bytes(uc.mem_read(buf, n)))
        ret(uc, 0)

    def stream(uc, pc, size, _):
        _, off, n, dst = args(uc, 4)
        uc.mem_write(dst, ui.body[off:off + n])
        ret(uc, 0)
    for a in (T.MMC_READ, T.MMC_WRITE):
        ui.uc.hook_add(UC_HOOK_CODE, mmc, begin=a, end=a)
    ui.uc.mem_write(T.STREAM, b"\x4e\x75")
    ui.uc.hook_add(UC_HOOK_CODE, stream, begin=T.STREAM, end=T.STREAM)
    s = ui.sym
    io = s["core_hzfs_native_io"]
    assert ui.call(s["core_hzfs_ensure"], [io], count=400_000_000) == 1
    ui.uc.mem_write(T.TOTAL, struct.pack(">I", 256))                 # nessun campione stock
    for name, frames in ((b"kick", 4800), (b"pad", 48000), (b"vox", 24000)):
        head = bytearray(64)
        head[0:4] = b"SAMP"
        head[12:12 + len(name)] = name
        struct.pack_into(">I", head, 8, frames)
        ui.body = bytes(head) + bytes(2 * frames)
        ui.uc.mem_write(T.SCRATCH, name + bytes(1))
        assert ui.call(s["core_hzfs_put"], [io, T.SCRATCH, len(ui.body), 0, T.STREAM, 0, T.SCRATCH + 64],
                       count=2_000_000_000) == 1
    ui.call(s["ls_plan"], count=400_000_000)
    ui.call(s["ls_project_new"])
    ui.sm = sym_of("sample-manager")
    return ui


def names(m):
    n = m.long(m.sym["ls_table"] + 4)
    return [bytes(m.uc.mem_read(m.sym["ls_names"] + 16 * i, 16)).split(b"\0")[0] for i in range(n)]


def key(m, code, down=1, func=0):
    m.uc.mem_write(EV, bytes(12) + struct.pack(">II", code, down | (2 if func else 0)))
    return m.call(m.sm["smgr_key"], [0, EV], count=2_000_000_000)


def note(m):
    return bytes(m.uc.mem_read(m.sm["smgr_note"], 32)).split(b"\0")[0]


def test_row_and_module_are_wired(m):
    import modarea_layout as M
    import registry
    about = sym_of("about")
    row = struct.unpack(">4I", m.uc.mem_read(m.sm["smgr_row"], 16))
    assert all(row)                                                  # le quattro callback della riga SAMPLES
    spec = json.loads((ROOT / "mods" / "about" / "patch.json").read_text(encoding="utf-8"))
    blob = bytes.fromhex(next(p for p in spec["patches"] if p.get("append") and p["len"] > 100)["hex"])
    assert struct.pack(">I", m.sm["smgr_row"]) in blob, "mods/about va rigenerata dopo sample-manager"
    slot = next(s for s, who in registry.SFCORE_SLOTS.items() if who == "sample-manager")
    assert m.long(M.RAM + registry.SFCORE_TABLE + 4 * slot) == m.sm["smgr_module"]
    assert m.long(m.sym["sfcore_status"] + 4 * slot) == 1 and about["about_settings"]


def test_list_is_drawn(m, tmp_path):
    import screens
    assert names(m) == [b"kick", b"pad", b"vox"]
    fb = m.paint(m.sm["smgr_paint"])
    assert 700 < sum(bin(b).count("1") for b in fb) < 3500
    screens.png(fb, tmp_path / "samples.png")
    m.put(m.sm["smgr_cursor"], ">I", 1)
    assert m.paint(m.sm["smgr_paint"]) != fb                         # il cursore si vede


def test_keys_only_while_open(m):
    m.put(m.sm["smgr_open"], ">I", 0)
    assert key(m, DOWN) == 0 and key(m, YES) == 0
    m.put(m.sm["smgr_open"], ">I", 1)
    m.put(m.sm["smgr_cursor"], ">I", 0)
    assert key(m, DOWN) == 1 and m.long(m.sm["smgr_cursor"]) == 1
    assert key(m, DOWN) == 1 and key(m, DOWN) == 1 and m.long(m.sm["smgr_cursor"]) == 2     # si ferma in fondo
    assert key(m, UP) == 1 and m.long(m.sm["smgr_cursor"]) == 1
    assert key(m, 5) == 1 and key(m, 5, 0) == 1                      # un altro tasto: nostro
    assert key(m, 9) == 0 and key(m, 11) == 0                        # trasporto all'OS
    assert key(m, NO) == 1 and m.long(m.sm["smgr_open"]) == 0
    assert key(m, NO, 0) == 1 and key(m, NO, 0) == 0


def test_move_changes_the_project_order(m):
    m.put(m.sm["smgr_open"], ">I", 1)
    m.put(m.sm["smgr_cursor"], ">I", 0)
    before = [m.call(m.sym["ls_id_at"], [i]) for i in range(3)]
    assert key(m, DOWN, func=1) == 1                                 # kick scende di un posto
    assert names(m) == [b"pad", b"kick", b"vox"] and m.long(m.sm["smgr_cursor"]) == 1
    assert [m.call(m.sym["ls_id_at"], [i]) for i in range(3)] == [before[1], before[0], before[2]]
    assert key(m, UP, func=1) == 1                                   # e torna su
    assert names(m) == [b"kick", b"pad", b"vox"] and m.long(m.sm["smgr_cursor"]) == 0
    assert key(m, UP, func=1) == 1 and names(m) == [b"kick", b"pad", b"vox"]   # in cima: niente


def test_delete_needs_two_presses_and_leaves_a_hole(m):
    import test_long_samples as T
    s = m.sym
    m.put(m.sm["smgr_open"], ">I", 1)
    m.put(m.sm["smgr_cursor"], ">I", 1)                              # pad
    gone = m.call(s["ls_id_at"], [1])
    assert key(m, NO, func=1) == 1 and b"AGAIN" in note(m)
    assert names(m) == [b"kick", b"pad", b"vox"]                     # una pressione: niente
    assert key(m, NO, func=1) == 1 and note(m) == b"DELETED"
    assert names(m) == [b"kick", b"", b"vox"]                        # la posizione resta, vuota
    assert m.call(s["ls_id_at"], [1]) == 0 and m.long(s["ls_table"] + 8 + 8 * 1 + 4) == 0
    assert m.uc.mem_read(0x1000_0788 + 1, 1)[0] == 0xFF              # la CPU delle voci non lo suona piu'
    # l'archivio: il catalogo ha due file, quello cancellato non c'e'
    fs = T.SCRATCH + 0x400
    assert m.call(s["core_hzfs_open"], [fs, s["core_hzfs_native_io"]], count=400_000_000) == 1
    assert m.call(s["core_hzfs_count"], [fs]) == 2
    ids = []
    for i in range(2):
        assert m.call(s["core_hzfs_entry"], [fs, i, T.SCRATCH + 0x800]) == 1
        ids.append(m.long(T.SCRATCH + 0x800))
    m.call(s["core_hzfs_close"], [fs])
    assert gone not in ids
    assert key(m, NO, func=1) == 1 and note(m) == b"EMPTY POSITION"  # sulla posizione vuota


def test_assign_puts_the_sampler_on_the_active_track(m):
    import idspace_layout as I
    s = m.sym
    m.put(m.sm["smgr_open"], ">I", 1)
    m.put(m.sm["smgr_cursor"], ">I", 2)                              # vox
    assert key(m, YES) == 1
    assert note(m).startswith(b"SAMPLE > TRACK ")
    track = note(m)[-1] - ord("1")
    brain = m.call(0x4016_E9C8)
    model = m.call(0x4000_F04C, [brain + 0x130, track])
    sound = m.call(m.long(m.long(model) + 0x28), [model])
    assert m.uc.mem_read(sound + 0xA2, 1)[0] == 44                   # SAMPLER
    samp = m.long(I.TABLE + 52 * 504 + 32)                           # SAMP: parola del Sound
    data = m.call(m.long(m.long(sound) + 0x28), [sound]) if False else None
    assert m.call(s["sm_long_samp"], [2]) == 2                       # nessuno stock: posizione = valore
    m.put(m.sm["smgr_cursor"], ">I", 1)                              # la posizione vuota
    assert key(m, YES) == 1 and note(m) == b"EMPTY POSITION"
