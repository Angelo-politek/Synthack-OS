"""Genera mods/sample-manager/patch.json (vedi sample_manager.c).

    python mods/sample-manager/make_patch.py       # richiede gcc m68k in WSL (CONTRIBUTING.md)

Usa indirizzi di long-samples, sampler e idspace (dai loro patch.json): rigenerare dopo di loro, e mods/about dopo
questa (about aggiunge la riga SAMPLES leggendo smgr_row).
"""

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(REPO / "tools" / "build"))
import idspace_layout  # noqa: E402
import modkit  # noqa: E402
import registry  # noqa: E402

SLOT = next(s for s, who in registry.SFCORE_SLOTS.items() if who == "sample-manager")
EXTERN = {"LS_TABLE": ("long-samples", "ls_table"), "LS_NAMES": ("long-samples", "ls_names"),
          "LS_ID_AT": ("long-samples", "ls_id_at"), "LS_SWAP": ("long-samples", "ls_swap"),
          "LS_FORGET": ("long-samples", "ls_forget"), "HZFS_REMOVE": ("long-samples", "core_hzfs_remove"),
          "HZFS_IO": ("long-samples", "core_hzfs_native_io"), "SM_LONG_SAMP": ("sampler", "sm_long_samp")}


def externs() -> dict[str, int]:
    out = {"IDS_TABLE": idspace_layout.TABLE}
    for macro, (mod, name) in EXTERN.items():
        sym = json.loads((REPO / "mods" / mod / "patch.json").read_text(encoding="utf-8"))["symbols"]
        if name not in sym:
            raise SystemExit(f"{mod}: simbolo {name} non esportato")
        out[macro] = int(sym[name], 16)
    return out


def main() -> None:
    m = modkit.Mod(__file__)
    code = m.compile(["sample_manager.c"], defs=externs())
    m.area(code, "sample_manager.c")
    m.word(registry.SFCORE_TABLE + 4 * SLOT, code["smgr_module"], f"tabella dei moduli di sfcore, posto {SLOT}")
    m.write(description="Riga SAMPLES nel menu delle impostazioni (aggiunta da about): la lista dei campioni lunghi "
                        "del progetto; assegna alla traccia, sposta, cancella.",
            requires=["modarea", "sfcore", "idspace", "long-samples", "sampler", "about"],
            symbols={k: v for k, v in sorted(code.items()) if k.startswith("smgr_")})


if __name__ == "__main__":
    main()
