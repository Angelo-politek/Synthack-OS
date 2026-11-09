"""Controlli su una mod prima di unirla (per chi la scrive e per chi la rivede). Serve l'OS stock in firmware/.

    python tools/check_mod.py my-mod

1. patch.json riproducibile: make_patch.py lo riscrive uguale (il patch.json corrisponde ai sorgenti);
2. scheda, registro e prenotazioni (tests/test_web_builder.py, tests/test_registry.py, tests/test_os_abi.py);
3. i test della mod (tests/test_<nome>.py);
4. build con tutte le altre mod: impronte, sovrapposizioni, margine d'avvio;
5. docs/registry.md e web-builder/src/budget.json aggiornati.
Esce con 1 al primo controllo fallito. La suite completa resta `python -m pytest`.
"""

from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(REPO / "tools" / "build"), str(REPO / "tools" / "unpack")]


def run(what: str, *cmd: str) -> None:
    print(f"== {what}", flush=True)
    r = subprocess.run(cmd, cwd=REPO)
    if r.returncode:
        raise SystemExit(f"FALLITO: {what}")


def main() -> int:
    if len(sys.argv) != 2:
        raise SystemExit(__doc__)
    name = sys.argv[1].strip("/\\").split("/")[-1].split("\\")[-1]
    d = REPO / "mods" / name
    if not (d / "patch.json").exists():
        raise SystemExit(f"mods/{name}/patch.json non c'e'")
    py = sys.executable
    if (d / "make_patch.py").exists():
        before = (d / "patch.json").read_bytes()
        run("patch.json dai sorgenti", py, str(d / "make_patch.py"))
        if (d / "patch.json").read_bytes().replace(b"\r\n", b"\n") != before.replace(b"\r\n", b"\n"):
            raise SystemExit("FALLITO: make_patch.py scrive un patch.json diverso da quello della mod")
    run("scheda, registro, chiamate all'OS", py, "-m", "pytest", "-q", "tests/test_registry.py", "tests/test_os_abi.py",
        "tests/test_os_pointer_results.py", "tests/test_web_builder.py::test_every_mod_has_a_card")
    test = REPO / "tests" / f"test_{name.replace('-', '_')}.py"
    if not test.exists():
        raise SystemExit(f"FALLITO: manca {test.relative_to(REPO)}")
    run("test della mod", py, "-m", "pytest", "-q", str(test))
    print("== build con tutte le altre mod", flush=True)
    import build
    mods = sorted(p.parent for p in (REPO / "mods").glob("*/patch.json") if p.parent.name != "mod-zero")
    with tempfile.TemporaryDirectory(prefix="check-mod-") as t:
        info = build.build(REPO / "firmware" / "Syntakt_OS1.42.syx", mods, Path(t) / "all.syx", log=lambda *_: None)
    print(f"   {len(info['mods'])} mod, margine d'avvio {info['boot_margin']} B")
    run("docs/registry.md aggiornato", py, "tools/build/registry.py")
    run("budget.json aggiornato", py, "tools/build/budget.py")
    run("niente da aggiornare", "git", "diff", "--exit-code", "--stat", "docs/registry.md", "web-builder/src/budget.json")
    print(f"OK: {name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
