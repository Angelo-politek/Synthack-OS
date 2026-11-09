"""Crea lo scheletro di una mod nuova: cartella, sorgente C, make_patch.py, scheda, README, prenotazioni, test.

    python tools/new_mod.py my-mod                 # mods/my-mod/ e tests/test_my_mod.py
    python tools/new_mod.py my-mod --size 0x2000   # piu' spazio nell'area mod (predefinito 0x800 = 2 KB)
    python mods/my-mod/make_patch.py               # compila e scrive patch.json (WSL, OS stock in firmware/)
    python -m pytest tests/test_my_mod.py tests/test_registry.py

Lo scheletro compila e passa i test cosi' com'e': una funzione nell'area mod, chiamata nell'emulatore. Non tocca
ancora l'OS: gli agganci si aggiungono in make_patch.py (docs/modding-guide.md, sezione 2).
Una machine (motore sulla CPU #2) parte da mods/sy-fm4 o mods/sampler: docs/modding-guide.md, sezione 7.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "tools" / "build"))
import registry  # noqa: E402

NAME = re.compile(r"^[a-z0-9][a-z0-9-]{0,39}$")


def free_space(size: int) -> tuple[int, int]:
    """Primo tratto libero di `size` byte nella zona dell'area mod per le mod nuove (allineato a 16)."""
    lo, hi = registry.COMMUNITY
    pos = lo
    for a, b, _, _ in sorted(registry.MODAREA):
        if b <= pos or a >= hi:
            continue
        if a - pos >= size:
            break
        pos = (b + 15) & ~15
    if pos + size > hi:
        raise SystemExit(f"non ci sono {size:#x} byte liberi nella zona delle mod nuove ({lo:#x}..{hi:#x}): "
                         "docs/registry.md")
    return pos, pos + size


C_SRC = '''/* SPDX-License-Identifier: GPL-2.0-or-later
 * {name}: TODO one line: what it does on the device.
 *
 * Linked in the mod area at the space claimed in claims.json. Variables in .data (DATA), no libgcc.
 * OS functions return in d0, pointers too: declare them with an integer result (sdk/synthack.h).
 */
#include "synthack.h"

static u32 {sym}_calls DATA = 0;

/* Example only: called by the test in the emulator. Replace it with your hook targets. */
u32 {sym}_hello(u32 x)
{{
    {sym}_calls++;
    return x + {sym}_calls;
}}
'''

MAKE_PATCH = '''"""Genera mods/{name}/patch.json (vedi {src}).

    python mods/{name}/make_patch.py       # richiede gcc m68k in WSL (CONTRIBUTING.md)
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools" / "build"))
import modkit  # noqa: E402


def main() -> None:
    m = modkit.Mod(__file__)
    code = m.compile(["{src}"])                  # nell'area mod, allo spazio di claims.json
    m.area(code, "{src}")
    # Agganci (docs/modding-guide.md, sezione 2). orig = le istruzioni sostituite, in esadecimale: il make_patch
    # si ferma se l'OS non le ha. Il tuo codice le rifa' prima di tornare.
    #   m.hook(0x400A6EE6, "2f0b2f0a246f000c", code["{sym}_target"], "what the hook does")
    #   m.hook(addr, orig, code["{sym}_target"], "what", call=True)     # jsr invece di jmp
    #   m.replace(addr, orig, new_bytes, "what")                        # dati: un puntatore, un testo
    m.write(description="TODO: cosa fa la mod e dove si aggancia.",
            requires=["modarea"], symbols={{k: v for k, v in sorted(code.items()) if k.startswith("{sym}_")}})


if __name__ == "__main__":
    main()
'''

README = '''# {name}

TODO one sentence: what the mod does on the device.

| Control | Action |
|---|---|
| TODO | TODO |

- Saved: TODO (kit, project, sound, nothing).
- Audio cost per block: TODO (instructions, cycles) or none.
- Tested on the device: no.

## How it works

TODO hooks and addresses (OS 1.42), what each one replaces.

Tests: `tests/test_{mod}.py`. Space and ids: [claims.json](claims.json).
'''

TEST = '''"""{name} (mods/{name}): TODO cosa controllano questi test."""

import json
import sys
from pathlib import Path

import pytest

pytest.importorskip("unicorn")

ROOT = Path(__file__).resolve().parents[1]
SY = ROOT / "firmware" / "Syntakt_OS1.42.syx"
PATCH = ROOT / "mods" / "{name}" / "patch.json"
pytestmark = pytest.mark.skipif(not SY.exists() or not PATCH.exists(), reason="OS stock o patch.json assente")
sys.path[:0] = [str(ROOT / "tools" / "emu"), str(ROOT / "tools" / "build")]


def symbols():
    return {{k: int(v, 16) for k, v in json.loads(PATCH.read_text(encoding="utf-8"))["symbols"].items()}}


def test_code_runs_in_the_emulator():
    import screens
    ui = screens.UI(["{name}"])                  # OS stock avviato + la mod e le sue dipendenze
    sym = symbols()
    assert ui.call(sym["{sym}_hello"], (40,)) == 41
    assert ui.call(sym["{sym}_hello"], (40,)) == 42
    assert ui.long(sym["{sym}_calls"]) == 2


def test_builds_with_every_other_mod(tmp_path):
    import build
    mods = sorted(p.parent for p in (ROOT / "mods").glob("*/patch.json") if p.parent.name != "mod-zero")
    info = build.build(SY, mods, tmp_path / "all.syx", log=lambda *_: None)
    assert "{name}" in info["mods"] and info["boot_margin"] >= 4096
'''


def main() -> int:
    ap = argparse.ArgumentParser(description="Crea lo scheletro di una mod nuova.")
    ap.add_argument("name", help="lettere minuscole, cifre, trattini: il nome della cartella in mods/")
    ap.add_argument("--size", type=lambda s: int(s, 0), default=0x800, help="byte nell'area mod (predefinito 0x800)")
    ap.add_argument("--title", default="", help="titolo della scheda sul sito")
    a = ap.parse_args()
    if not NAME.match(a.name):
        raise SystemExit("nome: lettere minuscole, cifre e trattini (come la cartella mods/<nome>)")
    d = REPO / "mods" / a.name
    mod = a.name.replace("-", "_")
    test = REPO / "tests" / f"test_{mod}.py"
    if d.exists() or test.exists():
        raise SystemExit(f"{d} o {test} esiste gia'")
    sym = "".join(w[0] for w in a.name.split("-") if w)[:4] if "-" in a.name else a.name[:4]
    sym = re.sub(r"[^a-z0-9]", "", sym) or "mod"
    if sym[0].isdigit():
        sym = "m" + sym
    lo, hi = free_space((a.size + 15) & ~15)
    src = f"{mod}.c"
    f = dict(name=a.name, mod=mod, sym=sym, src=src)
    d.mkdir(parents=True)
    w = lambda p, s: p.write_text(s, encoding="utf-8", newline="\n")
    w(d / src, C_SRC.format(**f))
    w(d / "make_patch.py", MAKE_PATCH.format(**f))
    w(d / "README.md", README.format(**f))
    w(d / "mod.json", json.dumps({"title": a.title or a.name, "kind": "feature", "status": "experimental",
                                   "summary": "TODO one sentence: what it does on the device."}, indent=2) + "\n")
    w(d / "claims.json", json.dumps({"modarea": [[f"{lo:#x}", f"{hi:#x}", "code and data"]]}, indent=2) + "\n")
    w(test, TEST.format(**f))
    print(f"mods/{a.name}/: {src}, make_patch.py, mod.json, README.md, claims.json (area mod {lo:#x}..{hi:#x})")
    print(f"tests/test_{mod}.py")
    print("Poi:")
    print(f"  python mods/{a.name}/make_patch.py")
    print(f"  python -m pytest tests/test_{mod}.py tests/test_registry.py tests/test_web_builder.py -k 'not same_syx'")
    print("  python tools/build/registry.py && python tools/build/budget.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
