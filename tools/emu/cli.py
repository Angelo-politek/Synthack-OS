"""Riga di comando dell'harness: fa suonare una machine col motore audio ORIGINALE.

    python tools/emu/cli.py render --machine 5 --note 60 --seconds 0.5 -o out/emu/id05.wav
    python tools/emu/cli.py survey --seconds 0.5 -o out/emu      # un file per engine (12)

I parametri delle machine sono, per ora, tutti a meta' corsa (0x40): conosciamo la
STRUTTURA del blocco parametri, non ancora il significato di ogni byte.
"""

from __future__ import annotations

import argparse
import struct
import sys
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import engine as eng  # noqa: E402
from wav import SAMPLE_RATE, write_q31  # noqa: E402

MACHINE_MAP = 0x4001_4950      # mappa ID machine -> engine (46 byte), sezione 7
MACHINE_NAMES = 0x4022_AF88    # tabella (nome lungo, sigla) per ID, sezione 3 (OS 1.41)
N_MACHINES = 45
TRIG_LOAD, TRIG_NOTE = 0, 2    # il primo trig carica la machine, il secondo suona la nota


def make_params(machine: int, note: int, fill: int = 0x40) -> bytearray:
    p = bytearray(eng.PARAMS_SIZE)
    for t in range(eng.VOICES):
        p[20 * t:20 * t + 20] = bytes([fill]) * 20          # 20 B di parametri machine per traccia
        p[0xA0 + 8 * t:0xA0 + 8 * t + 8] = bytes([fill]) * 8
        p[0xE0 + 14 * t:0xE0 + 14 * t + 14] = bytes([fill]) * 14
    p[0] = machine                                           # traccia 0: tipo di machine
    struct.pack_into(">i", p, 0x150, note << 16)             # traccia 0: nota (semitoni << 16)
    return p


def render(machine: int, note: int, seconds: float) -> list[int]:
    e = eng.Engine()
    e.boot()
    params = make_params(machine, note)
    out: list[int] = []
    for b in range(int(seconds * SAMPLE_RATE / eng.BLOCK)):
        q = bytearray(params)
        if b in (TRIG_LOAD, TRIG_NOTE):
            q[0x180] = 0x01                                  # trig traccia 0
        out += e.render_block(bytes(q))[0]
    return out


def machine_to_engine() -> list[int]:
    e = eng.Engine()
    return list(e.uc.mem_read(MACHINE_MAP, 46))


def machine_names() -> list[str]:
    """Nomi delle machine per ID, letti dalla tabella di puntatori della sezione 3."""
    import memmap
    syx = memmap.REPO / "firmware" / "Syntakt_OS1.41.syx"
    sec3 = memmap.eft.unpack(syx, memmap.REPO / "unpacked" / syx.stem, ids=[3])[3].read_bytes()
    base = memmap.LOAD_ADDR                                  # anche la sezione 3 parte da 0x40000400

    def cstr(addr: int) -> str:
        o = addr - base
        return sec3[o:sec3.index(b"\x00", o)].decode("latin1").strip()

    t = MACHINE_NAMES - base
    return [cstr(int.from_bytes(sec3[t + 8 * k:t + 8 * k + 4], "big")) for k in range(N_MACHINES)]


def _survey_one(args: tuple[int, int, float, Path]) -> str:
    engine_id, machine, seconds, outdir, name = args
    t = time.time()
    samples = render(machine, 60, seconds)
    slug = name.lower().replace(" ", "_")
    path = outdir / f"engine{engine_id:02d}_id{machine:02d}_{slug}.wav"
    peak = write_q31(path, samples, normalize=True)
    return f"engine {engine_id:2d} (ID {machine:2d} {name}): picco {peak:6.1f} dBFS -> {path.name} ({time.time() - t:.0f}s)"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("render", help="una machine, una nota")
    r.add_argument("--machine", type=int, required=True, help="ID machine 0..45")
    r.add_argument("--note", type=int, default=60)
    r.add_argument("--seconds", type=float, default=0.5)
    r.add_argument("--raw", action="store_true", help="non normalizzare il volume")
    r.add_argument("-o", "--out", type=Path, required=True)
    s = sub.add_parser("survey", help="un file per ognuno dei 12 engine")
    s.add_argument("--seconds", type=float, default=0.5)
    s.add_argument("--jobs", type=int, default=4)
    s.add_argument("-o", "--out", type=Path, default=Path("out/emu"))
    a = ap.parse_args(argv)

    if a.cmd == "render":
        t = time.time()
        peak = write_q31(a.out, render(a.machine, a.note, a.seconds), normalize=not a.raw)
        print(f"{a.out}: picco {peak:.1f} dBFS ({time.time() - t:.0f}s)")
        return 0

    mapping = machine_to_engine()
    names = machine_names()
    first_id = {}
    for machine, engine_id in enumerate(mapping):
        first_id.setdefault(engine_id, machine)
    for engine_id in sorted(first_id):
        ids = [m for m, e in enumerate(mapping) if e == engine_id]
        print(f"engine {engine_id:2d} <- ID {ids[:3]}{'...' if len(ids) > 3 else ''} ({names[ids[0]]})")
    jobs = [(e, m, a.seconds, a.out, names[m]) for e, m in sorted(first_id.items())]
    with ProcessPoolExecutor(max_workers=a.jobs) as pool:
        for line in pool.map(_survey_one, jobs):
            print(line, flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
