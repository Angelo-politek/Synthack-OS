"""Costruisce un .syx Syntakt+ applicando le mod all'OS stock dell'utente.

    python tools/build/build.py --stock firmware/Syntakt_OS1.41.syx mods/mod-zero -o out/build/syntakt_plus.syx

Il repo non contiene byte Elektron: una patch dice DOVE scrivere, l'IMPRONTA (SHA-256) dei
byte originali che si aspetta di trovare li', e i byte NUOVI (nostri). Il build si ferma se
l'impronta non coincide (OS sbagliato o patch che si sovrappongono).

Formato di mods/<nome>/patch.json:
    {
      "name": "mod-zero",
      "description": "...",
      "os": "1.41",
      "patches": [
        {"section": 3, "addr": "0x4024F897", "len": 11,
         "expect_sha256": "<impronta dei byte originali>",
         "ascii": "SYNTHACK IN"}            # oppure "hex": "4e71..."
      ]
    }
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "tools" / "unpack"))
import eft  # noqa: E402

LOAD_ADDR = 0x4000_0400                 # sezioni 3 e 7 si caricano qui (vedi docs/re-journal.md)
PATCHABLE = {3, 7}
STOCK_SHA256 = {"1.41": "8e2488f462c4a5656396a895f113bcd415e9900fa8709340dccf45d4cb9ed19e"}


class BuildError(RuntimeError):
    pass


def sha256(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


@dataclass(frozen=True)
class Patch:
    mod: str
    section: int
    addr: int
    data: bytes
    expect_sha256: str

    @property
    def offset(self) -> int:
        return self.addr - LOAD_ADDR

    @property
    def end(self) -> int:
        return self.offset + len(self.data)


def load_mod(moddir: Path, os_version: str) -> list[Patch]:
    spec = json.loads((Path(moddir) / "patch.json").read_text(encoding="utf-8"))
    name = spec["name"]
    if spec.get("os") != os_version:
        raise BuildError(f"{name}: scritta per OS {spec.get('os')}, non per {os_version}")
    patches = []
    for i, p in enumerate(spec["patches"]):
        if "ascii" in p:
            data = p["ascii"].encode("ascii")
        elif "hex" in p:
            data = bytes.fromhex(p["hex"].replace(" ", ""))
        else:
            raise BuildError(f"{name}[{i}]: serve 'ascii' o 'hex'")
        if len(data) != p["len"]:
            raise BuildError(f"{name}[{i}]: {len(data)} byte nuovi ma 'len' = {p['len']}")
        if p["section"] not in PATCHABLE:
            raise BuildError(f"{name}[{i}]: sezione {p['section']} non modificabile (solo {sorted(PATCHABLE)})")
        patches.append(Patch(name, p["section"], int(p["addr"], 16), data, p["expect_sha256"].lower()))
    return patches


def apply_patches(sections: dict[int, bytearray], patches: list[Patch]) -> None:
    """Applica le patch verificando impronte e sovrapposizioni. Modifica 'sections' sul posto."""
    taken: dict[int, list[Patch]] = {}
    for p in patches:
        sec = sections.get(p.section)
        if sec is None:
            raise BuildError(f"{p.mod}: sezione {p.section} non caricata")
        if p.offset < 0 or p.end > len(sec):
            raise BuildError(f"{p.mod}: {p.addr:#x} fuori dalla sezione {p.section}")
        for q in taken.get(p.section, []):
            if p.offset < q.end and q.offset < p.end:
                raise BuildError(f"{p.mod} e {q.mod} modificano gli stessi byte ({p.addr:#x})")
        found = sha256(bytes(sec[p.offset:p.end]))
        if found != p.expect_sha256:
            raise BuildError(f"{p.mod}: a {p.addr:#x} i byte originali non sono quelli attesi "
                             f"(OS diverso o file modificato)")
        taken.setdefault(p.section, []).append(p)
    for p in patches:
        sections[p.section][p.offset:p.end] = p.data


def build(stock: Path, moddirs: list[Path], out: Path, log=print) -> dict:
    info = eft.info(stock)
    if "Syntakt" not in info.device or not info.checksums_ok:
        raise BuildError(f"{stock}: non e' un OS Syntakt valido")
    version = info.version
    if STOCK_SHA256.get(version) != sha256(Path(stock).read_bytes()):
        raise BuildError(f"{stock}: non e' l'OS stock {version} atteso (impronta diversa)")
    patches = [p for d in moddirs for p in load_mod(d, version)]
    needed = sorted({p.section for p in patches})

    with tempfile.TemporaryDirectory(prefix="syntakt-build-") as tmp:
        tmp = Path(tmp)
        files = eft.unpack(stock, tmp / "stock", ids=needed)
        original = {s: files[s].read_bytes() for s in needed}
        sections = {s: bytearray(b) for s, b in original.items()}
        apply_patches(sections, patches)
        replaced = {}
        for s in needed:
            f = tmp / f"section_{s}.patched"
            f.write_bytes(sections[s])
            replaced[s] = f
        out = Path(out)
        out.parent.mkdir(parents=True, exist_ok=True)
        eft.repack(stock, out, replace=replaced)

        # --- verifiche sul risultato
        built = eft.info(out)
        if not built.checksums_ok or built.version != version:
            raise BuildError("il .syx prodotto non passa la verifica dei checksum")
        all_ids = [s.id for s in info.sections]
        a = eft.unpack(stock, tmp / "a", ids=all_ids)
        b = eft.unpack(out, tmp / "b", ids=all_ids)
        for sid in all_ids:
            old, new = a[sid].read_bytes(), b[sid].read_bytes()
            if sid not in needed:
                if old != new:
                    raise BuildError(f"la sezione {sid} e' cambiata ma nessuna patch la tocca")
                continue
            diff = [i for i in range(len(old)) if old[i] != new[i]]
            allowed = {i for p in patches if p.section == sid for i in range(p.offset, p.end)}
            if len(old) != len(new) or not set(diff) <= allowed:
                raise BuildError(f"sezione {sid}: modifiche fuori dalle patch dichiarate")
            log(f"  sezione {sid}: {len(diff)} byte modificati, tutti dentro le patch")

    manifest = {
        "os": version,
        "stock_sha256": STOCK_SHA256[version],
        "mods": [json.loads((Path(d) / "patch.json").read_text(encoding="utf-8"))["name"] for d in moddirs],
        "output": out.name,
        "output_sha256": sha256(out.read_bytes()),
    }
    out.with_suffix(".json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return manifest


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--stock", type=Path, required=True, help="OS stock scaricato da elektron.se")
    ap.add_argument("mods", type=Path, nargs="+", help="cartelle mods/<nome>")
    ap.add_argument("-o", "--out", type=Path, required=True)
    a = ap.parse_args(argv)
    try:
        m = build(a.stock, a.mods, a.out)
    except (BuildError, eft.EftError) as e:
        print(f"BUILD FALLITO: {e}", file=sys.stderr)
        return 1
    print(f"OK {a.out}  mods={m['mods']}  sha256={m['output_sha256'][:16]}...")
    return 0


if __name__ == "__main__":
    sys.exit(main())
