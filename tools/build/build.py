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

Patch accodate ("append": true, solo "hex"): byte NUOVI oltre la fine della sezione stock (area
mod, vedi mods/modarea); lo spazio tra la fine stock e "addr" viene riempito di zeri. Non hanno
impronta (non sostituiscono byte Elektron). Solo nella sezione 3: per la sezione 7 il limite del
caricatore della CPU #2 non e' ancora noto.

Dipendenze: una mod dichiara "requires": ["modarea", ...]. Le mod richieste e non indicate vengono
aggiunte da sole (cercate tra le cartelle indicate, poi in mods/), prima di chi le richiede.

Area mod compressa: se modarea dichiara "compress": "shlz", i byte accodati (da "img" in poi)
vengono sostituiti dal loro flusso SHLZ (lz.py), che il rilocatore decomprime in RAM all'avvio.

Controllo di avvio (bootcheck.py): il bootstrap decomprime la sezione 3 quasi sul posto; se il
margine scende sotto bootcheck.MIN_MARGIN l'immagine non si avvierebbe e il build la scarta.
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

sys.path.insert(0, str(Path(__file__).resolve().parent))
import bootcheck  # noqa: E402
import lz  # noqa: E402

sys.path.insert(0, str(REPO / "tools" / "splash"))
import render  # noqa: E402

LOAD_ADDR = 0x4000_0400                 # sezioni 3 e 7 si caricano qui (vedi docs/)
PATCHABLE = {3, 7}
APPENDABLE = {3}                        # sezione 7: limite del caricatore della CPU #2 da trovare (modarea7)
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
    append: bool = False

    @property
    def offset(self) -> int:
        return self.addr - LOAD_ADDR

    @property
    def end(self) -> int:
        return self.offset + len(self.data)


def read_spec(moddir: Path) -> dict:
    return json.loads((Path(moddir) / "patch.json").read_text(encoding="utf-8"))


def resolve(moddirs: list[Path], search: tuple[Path, ...] = (REPO / "mods",)) -> tuple[list[Path], list[str]]:
    """Cartelle delle mod in ordine (prima le dipendenze) e nomi delle mod aggiunte perche' richieste."""
    given: dict[str, Path] = {}
    for d in moddirs:
        name = read_spec(d)["name"]
        if name in given and Path(given[name]).resolve() != Path(d).resolve():
            raise BuildError(f"mod {name} indicata due volte ({given[name]}, {d})")
        given[name] = Path(d)

    def find(name: str) -> Path:
        if name in given:
            return given[name]
        for root in search:
            d = Path(root) / name
            if (d / "patch.json").exists() and read_spec(d)["name"] == name:
                return d
        raise BuildError(f"dipendenza {name} non trovata (cercata tra le mod indicate e in {[str(r) for r in search]})")

    order: list[Path] = []
    added: list[str] = []
    state: dict[str, str] = {}

    def visit(name: str, chain: list[str]) -> None:
        if state.get(name) == "fatto":
            return
        if state.get(name) == "in corso":
            raise BuildError("dipendenze circolari: " + " -> ".join(chain + [name]))
        state[name] = "in corso"
        d = find(name)
        for req in read_spec(d).get("requires", []):
            visit(req, chain + [name])
        state[name] = "fatto"
        order.append(d)
        if name not in given:
            added.append(name)

    for name in given:
        visit(name, [])
    return order, added


def named_splash(spec: dict, name: str) -> dict:
    """La splash con un nome in piccolo sotto la versione: ridisegna il logo dentro la prima patch
    (posizione e orientamento dichiarati nel layout di mods/splash/patch.json)."""
    lay, first = spec["layout"], spec["patches"][0]
    data = bytearray.fromhex(first["hex"])
    a, n = lay["logo_offset"], lay["logo_len"]
    bm = render.Bitmap.from_bytes_syntakt(bytes(data[a:a + n])).flipped(lay["flip"])
    render.draw_name(bm, name, lay["name_y"])
    data[a:a + n] = bm.flipped(lay["flip"]).to_bytes_syntakt()
    return {**spec, "patches": [{**first, "hex": data.hex()}, *spec["patches"][1:]]}


def load_mod(moddir: Path, os_version: str, splash_name: str = "") -> list[Patch]:
    spec = read_spec(moddir)
    name = spec["name"]
    if name == "splash" and render.clean_name(splash_name):
        spec = named_splash(spec, splash_name)
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
        if p.get("append"):
            if "hex" not in p:
                raise BuildError(f"{name}[{i}]: una patch accodata vuole 'hex'")
            patches.append(Patch(name, p["section"], int(p["addr"], 16), data, "", append=True))
        else:
            patches.append(Patch(name, p["section"], int(p["addr"], 16), data, p["expect_sha256"].lower()))
    return patches


def mod_area(moddirs: list[Path]) -> dict | None:
    """Disposizione dell'area mod compressa, se una delle mod (modarea) la dichiara."""
    for d in moddirs:
        lay = json.loads((Path(d) / "patch.json").read_text(encoding="utf-8")).get("layout", {})
        if lay.get("compress") == "shlz":
            return {"img": int(lay["img"], 16), "size": int(lay["size"], 16)}
    return None


def expected_area(patches: list[Patch], area: dict) -> bytes:
    """Immagine dell'area mod ricostruita dalle sole patch accodate (zeri negli spazi)."""
    img = bytearray()
    for p in patches:
        if p.append:
            a = p.addr - area["img"]
            if len(img) < a + len(p.data):
                img.extend(bytes(a + len(p.data) - len(img)))
            img[a:a + len(p.data)] = p.data
    return bytes(img)


def apply_patches(sections: dict[int, bytearray], patches: list[Patch]) -> None:
    """Applica le patch verificando impronte e sovrapposizioni. Modifica 'sections' sul posto."""
    taken: dict[int, list[Patch]] = {}
    stock_len = {s: len(b) for s, b in sections.items()}
    for p in patches:
        sec = sections.get(p.section)
        if sec is None:
            raise BuildError(f"{p.mod}: sezione {p.section} non caricata")
        for q in taken.get(p.section, []):
            if p.offset < q.end and q.offset < p.end:
                raise BuildError(f"{p.mod} e {q.mod} modificano gli stessi byte ({p.addr:#x})")
        if p.append:
            if p.section not in APPENDABLE:
                raise BuildError(f"{p.mod}: patch accodata alla sezione {p.section}: per ora solo la sezione 3 "
                                 f"(il limite del caricatore della CPU #2 non e' ancora noto)")
            if p.offset < stock_len[p.section]:
                raise BuildError(f"{p.mod}: patch accodata a {p.addr:#x} dentro la sezione stock")
        else:
            if p.offset < 0 or p.end > stock_len[p.section]:
                raise BuildError(f"{p.mod}: {p.addr:#x} fuori dalla sezione {p.section}")
            found = sha256(bytes(sec[p.offset:p.end]))
            if found != p.expect_sha256:
                raise BuildError(f"{p.mod}: a {p.addr:#x} i byte originali non sono quelli attesi "
                                 f"(OS diverso o file modificato)")
        taken.setdefault(p.section, []).append(p)
    for p in patches:
        sec = sections[p.section]
        if p.end > len(sec):
            sec.extend(bytes(p.end - len(sec)))
        sec[p.offset:p.end] = p.data


def build(stock: Path, moddirs: list[Path], out: Path, log=print, splash_name: str = "") -> dict:
    info = eft.info(stock)
    if "Syntakt" not in info.device or not info.checksums_ok:
        raise BuildError(f"{stock}: non e' un OS Syntakt valido")
    version = info.version
    if STOCK_SHA256.get(version) != sha256(Path(stock).read_bytes()):
        raise BuildError(f"{stock}: non e' l'OS stock {version} atteso (impronta diversa)")
    moddirs, added = resolve(moddirs)
    if added:
        log(f"  dipendenze aggiunte: {', '.join(added)}")
    patches = [p for d in moddirs for p in load_mod(d, version, splash_name)]
    needed = sorted({p.section for p in patches})

    with tempfile.TemporaryDirectory(prefix="syntakt-build-") as tmp:
        tmp = Path(tmp)
        files = eft.unpack(stock, tmp / "stock", ids=needed)
        original = {s: files[s].read_bytes() for s in needed}
        sections = {s: bytearray(b) for s, b in original.items()}
        apply_patches(sections, patches)
        area = mod_area(moddirs)
        image = None
        if area and 3 in sections and len(sections[3]) > area["img"] - LOAD_ADDR:
            sec = sections[3]
            off = area["img"] - LOAD_ADDR
            image = bytes(sec[off:])                       # area mod come la vedra' la RAM
            if len(image) > area["size"]:
                raise BuildError(f"area mod: {len(image)} B, piu' dei {area['size']} B in RAM")
            del sec[off:]
            sec.extend(lz.compress(image))
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
        size, margin = bootcheck.check(out)
        if margin < bootcheck.MIN_MARGIN:
            out.unlink()
            raise BuildError(f"la sezione 3 non si decomprimerebbe all'avvio: margine {margin} B "
                             f"(minimo {bootcheck.MIN_MARGIN}); la Syntakt resterebbe sul logo")
        log(f"  avvio: margine di decompressione {margin} B (minimo {bootcheck.MIN_MARGIN})")
        all_ids = [s.id for s in info.sections]
        a = eft.unpack(stock, tmp / "a", ids=all_ids)
        b = eft.unpack(out, tmp / "b", ids=all_ids)
        for sid in all_ids:
            old, new = a[sid].read_bytes(), b[sid].read_bytes()
            if sid not in needed:
                if old != new:
                    raise BuildError(f"la sezione {sid} e' cambiata ma nessuna patch la tocca")
                continue
            mine = [p for p in patches if p.section == sid]
            allowed = {i for p in mine for i in range(p.offset, p.end)}
            diff = [i for i in range(len(old)) if i >= len(new) or old[i] != new[i]]
            if image is not None and sid == 3:              # area compressa: confronto dopo la decompressione
                off = area["img"] - LOAD_ADDR
                if lz.decompress(bytes(new[off:])) != expected_area(mine, area):
                    raise BuildError("area mod: il flusso compresso non riproduce le patch accodate")
                tail = [i for i in range(len(old), off) if new[i]]
            else:
                tail = [i for i in range(len(old), len(new)) if new[i] and i not in allowed]
            if len(new) < len(old) or not set(diff) <= allowed or tail:
                raise BuildError(f"sezione {sid}: modifiche fuori dalle patch dichiarate")
            if len(new) > len(old) and not any(p.append for p in mine):
                raise BuildError(f"sezione {sid}: allungata senza patch accodate")
            log(f"  sezione {sid}: {len(diff)} byte modificati, tutti dentro le patch"
                + (f"; accodati {len(new) - len(old)} byte (area mod)" if len(new) > len(old) else ""))

    manifest = {
        "os": version,
        "stock_sha256": STOCK_SHA256[version],
        "mods": [json.loads((Path(d) / "patch.json").read_text(encoding="utf-8"))["name"] for d in moddirs],
        "output": out.name,
        "output_sha256": sha256(out.read_bytes()),
        "boot_margin": margin,
    }
    if render.clean_name(splash_name):
        manifest["splash_name"] = render.clean_name(splash_name)
    out.with_suffix(".json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return manifest


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--stock", type=Path, required=True, help="OS stock scaricato da elektron.se")
    ap.add_argument("mods", type=Path, nargs="+", help="cartelle mods/<nome>")
    ap.add_argument("-o", "--out", type=Path, required=True)
    ap.add_argument("--name", default="", help="nome sulla splash d'avvio, sotto la versione (A-Z 0-9 . -)")
    a = ap.parse_args(argv)
    try:
        m = build(a.stock, a.mods, a.out, splash_name=a.name)
    except (BuildError, eft.EftError) as e:
        print(f"BUILD FALLITO: {e}", file=sys.stderr)
        return 1
    print(f"OK {a.out}  mods={m['mods']}  sha256={m['output_sha256'][:16]}...")
    return 0


if __name__ == "__main__":
    sys.exit(main())
