"""Genera mods/fastmix/patch.json (vedi fastmix.S).

    python mods/fastmix/make_patch.py         # richiede binutils m68k in WSL (CONTRIBUTING.md)
"""

import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools" / "build"))
import modarea_layout  # noqa: E402
import modkit  # noqa: E402

OFFSET = 0xF000                         # nell'area mod, dopo la linea di ritardo di fx3
SMOOTH, SMOOTH_ORIG, SMOOTH_BACK = 0x4009_79D6, "2a3c7c290000204b2c3c03d70000", 0x4009_7A2A
SMOOTH_HOOK = False                     # vedi main(): il gancio dello smussamento costa piu' di quanto risparmia


def main() -> None:
    m = modkit.Mod(__file__)
    base = modarea_layout.RAM + OFFSET
    code = m.compile(["fastmix.S"], base=base, end=modarea_layout.RAM + modarea_layout.SIZE, bss=True, emac=True)
    m.area(code, "fastmix.S")
    m.hook(0x4008_EF8C, "4fefffd0702048d7", code["fm_sum10"], "somma a 10 canali: jmp fm_sum10 ; nop")
    m.hook(0x4008_F024, "4fefffd448d77cfc", code["fm_sum9"], "somma a 9 canali: jmp fm_sum9 ; nop")
    m.hook(0x4008_F0B6, "4fefffd848d73cfc", code["fm_sum8"], "somma a 8 canali: jmp fm_sum8 ; nop")
    old = m.stock(SMOOTH, 14)
    if old.hex() != SMOOTH_ORIG:
        raise SystemExit(f"{SMOOTH:#x}: byte inattesi {old.hex()}")
    # 2026-11-04: smussamento non agganciato. Sul dispositivo (cpu-meter, tools/emu/cycles.py tarato) costa piu'
    # di quanto risparmia: -5 300 istruzioni ma una copia di 1.9 KB degli ingressi in DDR, 117 righe di cache
    # mancate a ogni blocco. fm_smooth resta nel blob (tests/test_fastmix.py lo prova ancora contro l'OS).
    if SMOOTH_HOOK:
        m.replace(SMOOTH, SMOOTH_ORIG,
                  struct.pack(">HIHIH", modkit.JSR, code["fm_smooth"], modkit.JMP, SMOOTH_BACK, modkit.NOP),
                  "smussamento dei parametri: jsr fm_smooth ; jmp 0x40097A2A ; nop")
    m.write(description="Routine dell'interrupt audio riscritte piu' veloci con lo stesso risultato: somme dei bus "
                        "senza i canali a guadagno nullo e senza la rampa quando i guadagni sono fermi.",
            requires=["modarea"], symbols={k: v for k, v in sorted(code.items()) if k.startswith("fm_")},
            emac_sites=code.emac)


if __name__ == "__main__":
    main()
