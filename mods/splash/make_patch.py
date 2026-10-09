"""Genera mods/splash/patch.json: splash "SyntHack <versione>" dopo l'animazione d'avvio ufficiale.

Come funziona (dettagli in docs/):
- il task dell'intro sceglie a caso una di 5 voci {segmenti...} con 5 istruzioni `pea <voce>`;
- creiamo 5 voci nuove = {animazione originale, splash_draw x N fotogrammi, fine} nello
  spazio libero 0x40338740..0x40339000 e facciamo puntare le 5 `pea` alle voci nuove;
- splash_draw (splash.S) copia il logo (1024 B, formato a colonne) nel framebuffer.

    python mods/splash/make_patch.py            # richiede binutils m68k in WSL (vedi CONTRIBUTING.md)
"""

from __future__ import annotations

import hashlib
import json
import shutil
import struct
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path[:0] = [str(REPO / "tools" / "unpack"), str(REPO / "tools" / "splash")]
import eft  # noqa: E402
import render  # noqa: E402

LOAD = 0x4000_0400
FREE_START, FREE_END = 0x4033_8740, 0x4033_9000     # riempimento del linker, vedi docs/memory-map.md
# (indirizzo dell'istruzione `pea`, voce originale a cui punta)
PEA_SITES = [(0x4008_7E90, 0x4029_A7C4), (0x4008_7EA4, 0x4029_A7B4), (0x4008_7EBA, 0x4029_A7A4),
             (0x4008_7ECC, 0x4029_A794), (0x4008_7ED4, 0x4029_A784)]
# L'intro gira a ~28 fotogrammi/s (PIT 3: prescaler 512, PMR 8593, bus ~125 MHz; vedi docs/memory-map.md).
# v0.1 AGGIUNGEVA 120 fotogrammi (~4,2 s) e la macchina si e' bloccata su "PREPARING SAMPLES":
# ora la durata totale resta quella originale, l'animazione ufficiale cede gli ultimi N fotogrammi.
SPLASH_FRAMES = 57                                  # ~2 s
# Orientamento dello schermo durante l'intro (v0.1 appariva capovolto): "none" | "v" | "h" | "vh"
FLIP = "v"
FIGLET_FONT, VERSION = "smslant", "v0.7.0"
WSL_BINUTILS = "~/tools/m68k/root"


def sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def assemble(src: Path, logo: bytes) -> bytes:
    with tempfile.TemporaryDirectory(prefix="splash-") as tmp:
        tmp = Path(tmp)
        shutil.copy(src, tmp / "splash.S")
        (tmp / "logo.bin").write_bytes(logo)
        w = eft.to_wsl_path(tmp)
        cmd = (f"R={WSL_BINUTILS}; export LD_LIBRARY_PATH=$R/usr/lib/x86_64-linux-gnu; cd {w} && "
               f"$R/usr/bin/m68k-linux-gnu-as -mcpu=54418 splash.S -o splash.o && "
               f"$R/usr/bin/m68k-linux-gnu-objcopy -O binary -j .text splash.o splash.bin")
        r = subprocess.run(["wsl.exe", "-e", "bash", "-lc", cmd], capture_output=True, text=True)
        if r.returncode:
            raise SystemExit(f"assemblaggio fallito:\n{r.stderr}")
        return (tmp / "splash.bin").read_bytes()


def main() -> None:
    stock = REPO / "firmware" / "Syntakt_OS1.41.syx"
    sec3 = eft.unpack(stock, REPO / "unpacked" / stock.stem, ids=[3])[3].read_bytes()
    u32 = lambda a: struct.unpack_from(">I", sec3, a - LOAD)[0]          # noqa: E731

    # 1. logo nel formato del framebuffer
    bm = render.compose(render.figlet("SyntHack", FIGLET_FONT), 3, 6, VERSION)
    bm.to_png(REPO / "out" / "splash" / "splash_final.png")          # come deve APPARIRE
    logo = bm.flipped(FLIP).to_bytes_syntakt()                         # come va SCRITTO in memoria

    # 2. codice + logo
    blob = bytearray(assemble(HERE / "splash.S", logo))
    if blob[-len(logo):] != logo:
        raise SystemExit("il logo non e' in coda al codice assemblato")
    code_addr = FREE_START
    while len(blob) % 8:
        blob.append(0)

    # 3. voci nuove: {originale, splash, fine}
    new_entries = []
    for pea_addr, entry in PEA_SITES:
        if sec3[pea_addr - LOAD:pea_addr - LOAD + 2] != b"\x48\x79" or u32(pea_addr + 2) != entry:
            raise SystemExit(f"a {pea_addr:#x} non c'e' 'pea {entry:#x}': OS diverso?")
        func, frames = u32(entry), u32(entry + 4)
        if u32(entry + 8) != 0:
            raise SystemExit(f"la voce {entry:#x} ha piu' di un segmento: formato inatteso")
        if frames <= SPLASH_FRAMES:
            raise SystemExit(f"la voce {entry:#x} dura solo {frames} fotogrammi")
        new_entries.append(FREE_START + len(blob))
        # stessa durata totale: l'animazione originale cede gli ultimi SPLASH_FRAMES fotogrammi
        blob += struct.pack(">IIIIII", func, frames - SPLASH_FRAMES, code_addr, SPLASH_FRAMES, 0, 0)

    end = FREE_START + len(blob)
    if end > FREE_END:
        raise SystemExit(f"non ci sta: {len(blob)} B, disponibili {FREE_END - FREE_START}")
    original = sec3[FREE_START - LOAD:end - LOAD]
    if any(original):
        raise SystemExit("lo spazio 'libero' non e' tutto a zero: OS diverso?")

    patches = [{"section": 3, "addr": f"{FREE_START:#010X}", "len": len(blob),
                "expect_sha256": sha(original), "hex": blob.hex(),
                "what": f"splash_draw + logo ({len(logo)} B) + 5 voci di animazione"}]
    for (pea_addr, entry), new in zip(PEA_SITES, new_entries):
        op = pea_addr + 2
        patches.append({"section": 3, "addr": f"{op:#010X}", "len": 4,
                        "expect_sha256": sha(sec3[op - LOAD:op + 4 - LOAD]),
                        "hex": struct.pack(">I", new).hex(),
                        "what": f"pea {entry:#x} -> pea {new:#x}"})
    spec = {"name": "splash", "os": "1.41",
            "description": f"Splash 'SyntHack {VERSION}' (figlet {FIGLET_FONT}) negli ultimi {SPLASH_FRAMES} "
                           f"fotogrammi dell'animazione d'avvio (durata totale invariata; flip={FLIP}).",
            "generated_by": "mods/splash/make_patch.py", "patches": patches}
    (HERE / "patch.json").write_text(json.dumps(spec, indent=2) + "\n", encoding="utf-8")
    print(f"patch.json: codice+logo+voci = {len(blob)} B a {FREE_START:#x}..{end:#x}; "
          f"5 pea reindirizzate; anteprima out/splash/splash_final.png")


if __name__ == "__main__":
    main()
