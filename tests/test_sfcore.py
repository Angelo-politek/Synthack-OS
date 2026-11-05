"""sfcore (mods/sfcore): bus degli eventi e transazioni native di Synfact sulla 1.42.

- Siti: byte stock, servizi (adattatori audio/file/nativi installati solo se una mod li usa).
- Catene: dove una nostra mod ha gia' il sito di Synfact, sfcore sta sull'istruzione dopo e la mod gira prima
  (perf-fx, cpu-meter, fx3, long-samples, sampler); build con tutte le mod e tutti i servizi.
- Un modulo di prova (scritto a mano nell'area mod, posto 7 della tabella) iscritto a tutti gli eventi: gli eventi
  arrivano, chi rifiuta lascia lo stock, chi consuma ferma lo stock.
- Senza iscritti, e con iscritti che rifiutano: interrupt audio identico allo stock (SRAM intera), poche istruzioni.
- SRAM: l'OS non legge ne' scrive le code che il registro assegna ai port.
"""

import json
import struct
import sys
from pathlib import Path

import pytest

pytest.importorskip("unicorn")

ROOT = Path(__file__).resolve().parents[1]
SY = ROOT / "firmware" / "Syntakt_OS1.42.syx"
pytestmark = pytest.mark.skipif(not SY.exists(), reason="OS stock assente")
sys.path[:0] = [str(ROOT / "tools" / "emu"), str(ROOT / "tools" / "build"), str(ROOT / "tools" / "unpack")]
import modarea_layout as MA  # noqa: E402
import registry as R  # noqa: E402

SPEC = json.loads((ROOT / "mods" / "sfcore" / "patch.json").read_text(encoding="utf-8"))
SYM = {k: int(v, 16) for k, v in SPEC["symbols"].items()}
SERVICES = sorted({p["service"] for p in SPEC["patches"] if "service" in p})
TABLE = MA.RAM + R.SFCORE_TABLE
PROBE = MA.RAM + 0x3E000                       # libero nel registro: solo nei test
PROBE_SLOT = 7
EV = {"tick": 0, "draw": 1, "key": 2, "enc": 3, "render_in": 5, "fs_write": 8, "fs_written": 9, "main_mix": 10,
      "native": 11}


def probe(uc, events=EV, consume=0):
    """Modulo Synfact scritto a mano: un contatore per evento (+0x100 + 4 * evento) e uno per operazione nativa
    (+0x200 + 4 * op). I callback rendono la parola a +0xF0 (0 = rifiuta, 1 = consuma)."""
    code = bytearray()
    base = PROBE + 0xC00
    subs = []
    for name, e in events.items():
        subs.append((e, base + len(code)))
        if name == "native":
            code += bytes.fromhex("202f0004e588") + b"\x41\xf9" + struct.pack(">I", PROBE + 0x200)
            code += bytes.fromhex("52b0080052b9") + struct.pack(">I", PROBE + 0x100 + 4 * e) + bytes.fromhex("70004e75")
        else:
            code += b"\x52\xb9" + struct.pack(">I", PROBE + 0x100 + 4 * e)
            code += b"\x20\x39" + struct.pack(">I", PROBE + 0xF0) + b"\x4e\x75"
    sub = PROBE + 0xF00
    uc.mem_write(PROBE, struct.pack(">4I", PROBE + 0x30, 0xFFFF_FFFF, sub, len(subs)) + b"PROBE\0")
    uc.mem_write(sub, b"".join(struct.pack(">2I", e, f) for e, f in subs))
    uc.mem_write(base, bytes(code))
    uc.mem_write(PROBE + 0xF0, struct.pack(">I", consume))
    uc.mem_write(TABLE + 4 * PROBE_SLOT, struct.pack(">I", PROBE))


def counts(uc, events=EV):
    return {n: struct.unpack(">I", uc.mem_read(PROBE + 0x100 + 4 * e, 4))[0] for n, e in events.items()}


def native_counts(uc):
    v = struct.unpack(">22I", uc.mem_read(PROBE + 0x200, 88))
    return {op: n for op, n in enumerate(v) if n}


# ------------------------------------------------------------------ siti e catene (senza emulazione)
def test_sites_are_stock_and_audio_adapters_are_services():
    import build
    sec3 = build.eft.unpack(SY, ROOT / "unpacked" / SY.stem, ids=[3])[3].read_bytes()
    fixed = [p for p in SPEC["patches"] if not p.get("append")]
    assert len(fixed) == 21
    for p in fixed:
        a, n = int(p["addr"], 16), p["len"]
        assert build.sha256(sec3[a - 0x4000_0400:a - 0x4000_0400 + n]) == p["expect_sha256"]
    ui = {int(p["addr"], 16) for p in fixed if "service" not in p}
    assert ui == {0x4000_A220, 0x4000_A286, 0x4000_839E, 0x4000_B468}          # interfaccia: sempre
    assert SERVICES == ["sfcore:fs", "sfcore:main_mix", "sfcore:native", "sfcore:render_in"]


def test_chained_sites_follow_the_existing_hooks():
    """Il sito di Synfact e' gia' di una nostra mod: sfcore sta dove quella mod torna allo stock."""
    def blob(mod):
        sp = json.loads((ROOT / "mods" / mod / "patch.json").read_text(encoding="utf-8"))
        return b"".join(bytes.fromhex(p["hex"]) for p in sp["patches"] if p.get("append"))
    jmp = lambda a: b"\x4e\xf9" + struct.pack(">I", a)                          # noqa: E731
    assert jmp(0x4000_839E) in blob("perf-fx")                    # pf_ev, poi il dispatcher: core_key
    assert jmp(0x400A_38D6) in blob("cpu-meter")                  # dopo il prologo: core_render_in
    assert jmp(0x400B_620C) in blob("long-samples")               # scritture rifiutate: core_fs_write
    assert jmp(0x4002_559C) in blob("sampler")                    # machine: core_native_machine_select
    fx3 = json.loads((ROOT / "mods" / "fx3" / "patch.json").read_text(encoding="utf-8"))
    mix = next(p for p in fx3["patches"] if p.get("addr", "").upper() == "0X4008FB7C")
    assert mix["len"] == 10 and mix["hex"].startswith("4eb9")    # jsr, ritorna a 0x4008FB86: core_main_mix


def test_build_with_every_mod_and_every_service(tmp_path):
    """Nessun byte in comune con le altre mod, margine d'avvio ok, area mod nei 256 KB."""
    import bootcheck
    import build
    user = tmp_path / "sfcore-user"
    user.mkdir()
    (user / "patch.json").write_text(json.dumps({"name": "sfcore-user", "os": "1.42", "requires": ["sfcore"],
                                                 "uses": SERVICES, "patches": []}), encoding="utf-8")
    every = [ROOT / "mods" / p.parent.name for p in sorted((ROOT / "mods").glob("*/mod.json"))
             if p.parent.name != "mod-zero"]
    m = build.build(SY, every + [user], tmp_path / "o.syx", log=lambda *_: None)
    assert "sfcore" in m["mods"] and m["boot_margin"] >= bootcheck.MIN_MARGIN
    # senza chi li usa, gli adattatori non ci sono: la build e' quella di prima
    a = build.build(SY, every, tmp_path / "a.syx", log=lambda *_: None)
    assert "sfcore" not in a["mods"]


# ------------------------------------------------------------------ interfaccia
@pytest.fixture(scope="module")
def ui():
    import screens
    u = screens.UI(["sfcore", "perf-fx"], extra=probe)
    return u


def test_first_tick_binds_and_tick_is_delivered(ui):
    uc = ui.uc
    ctrl = 0x4FE0_4000
    uc.mem_write(ctrl, bytes(0x40))
    uc.mem_write(ctrl + 0x20, b"\x01")
    assert ui.call(SYM["core_tick"], [ctrl]) & 0xFF == 1         # il valore dello stock: ctrl->dirty
    st = struct.unpack(">8I", uc.mem_read(SYM["sfcore_status"], 32))
    assert st[PROBE_SLOT] == 1 and st[:PROBE_SLOT] == (0,) * PROBE_SLOT
    assert counts(uc)["tick"] == 1
    ui.call(SYM["core_tick"], [ctrl])
    assert counts(uc)["tick"] == 2                                # legato una volta sola
    lst = struct.unpack(">8I", uc.mem_read(SYM["ev_key"], 32))
    assert lst[0] and lst[1] == 0


def test_keys_go_through_perf_fx_then_sfcore(ui):
    """perf-fx resta il primo: pf_ev, poi il dispatcher dei tasti, dove sta core_key. Un iscritto che consuma
    ferma lo stock; i registri e lo stack tornano come prima."""
    uc = ui.uc
    ev = 0x4FE0_5000
    uc.mem_write(ev, bytes(32))
    uc.mem_write(ev + 12, struct.pack(">II", 0x0C, 1))           # YES premuto: perf-fx non lo trattiene
    uc.mem_write(PROBE + 0xF0, struct.pack(">I", 1))
    before = counts(uc)["key"]
    ui.call(ui.sym["pf_ev_hook"], [0x4FE0_6000, ev])
    assert counts(uc)["key"] == before + 1
    ui.call(SYM["core_enc"], [0x4FE0_6000, ev])
    assert counts(uc)["enc"] == 1
    uc.mem_write(PROBE + 0xF0, struct.pack(">I", 0))


def test_screens_unchanged_without_subscribers():
    import screens
    stock, mod = screens.UI([]), screens.UI(["sfcore"], uses=SERVICES)
    for tab in ("SRC", "FLTR", "AMP", "FX.TRIG"):
        assert stock.draw(stock.tab(tab)) == mod.draw(mod.tab(tab)), tab


# ------------------------------------------------------------------ interrupt audio
def run(mods, uses=(), extra=None, blocks=6):
    import isr
    m = isr.Isr(mods, uses=uses, extra=extra)
    if "sfcore" in m.mods:
        m.ui.call(SYM["sfcore_bind"])
    m.scene("max")
    st = m.run()
    m.fast(blocks)
    return m, st


def sram(m):
    return bytes(m.uc.mem_read(0x8000_0000, 0x1_0000))


def test_interrupt_identical_with_all_adapters_and_no_subscriber():
    s, a = run([])
    m, b = run(["sfcore"], SERVICES)
    assert sram(s) == sram(m)
    print("istruzioni:", a.n, b.n)
    assert b.n - a.n <= 120, (a.n, b.n)                         # tst.b e salto per adattatore: 94 (2026-11-05)


def test_events_delivered_and_declines_keep_the_stock_output():
    s, a = run([])
    m, b = run(["sfcore"], SERVICES, extra=probe)
    assert sram(s) == sram(m)
    n = counts(m.uc)
    blocks = 1 + 1 + 6 + 20 + 1                                  # run, scene (run, fast 20, run), fast 6: vedi run()
    assert n["render_in"] == n["main_mix"] >= 20, n
    ops = native_counts(m.uc)
    print("eventi:", n, "operazioni native:", ops, "istruzioni:", a.n, b.n)
    assert {3, 4, 16, 17} <= set(ops), ops                       # PUBLISH, TYPE, MODULATION, LFO
    assert ops[16] == ops[17] == n["render_in"]                  # una modulazione e un LFO per blocco
    assert blocks >= n["render_in"]


def test_chained_with_every_audio_mod():
    """Tutte le mod insieme, con e senza sfcore (tutti i servizi, modulo di prova che rifiuta): stessa uscita.
    cpu-meter misura ancora l'interrupt intero, fx3 mescola ancora (il suo gancio gira prima di core_main_mix)."""
    every = sorted(p.parent.name for p in (ROOT / "mods").glob("*/mod.json")
                   if p.parent.name not in ("mod-zero", "sfcore", "modulation-skip"))
    s, _ = run(every)
    m, _ = run(every + ["sfcore"], SERVICES, extra=probe)
    assert sram(s) == sram(m)
    assert counts(m.uc)["main_mix"] >= 20


# ------------------------------------------------------------------ SRAM
def test_os_never_touches_the_sram_tails():
    """Dopo la copia in SRAM dell'avvio (che le azzera), l'OS non legge ne' scrive le code del registro: avvio,
    costruttori, progetto nuovo, interrupt audio nelle tre scene."""
    import isr
    from unicorn import UC_HOOK_MEM_READ, UC_HOOK_MEM_WRITE
    from unicorn.m68k_const import UC_M68K_REG_PC
    seen = []

    def watch(uc):
        def hit(u, acc, a, n, v, d):
            pc = u.reg_read(UC_M68K_REG_PC)
            if not 0x4000_045C <= pc < 0x4000_04B2:
                seen.append((hex(pc), hex(a)))
        for lo, hi in R.SRAM_FREE:
            uc.hook_add(UC_HOOK_MEM_READ | UC_HOOK_MEM_WRITE, hit, begin=lo, end=hi - 1)
    m = isr.Isr([], extra=watch)
    for scene in ("rest", "typ", "max"):
        m.scene(scene)
        m.run()
    assert not seen, seen[:10]
