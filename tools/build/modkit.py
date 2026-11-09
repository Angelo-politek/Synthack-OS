"""Parti comuni dei make_patch.py: compilare per il ColdFire, agganciare l'OS, scrivere patch.json.

    import modkit
    m = modkit.Mod(__file__)                                 # mods/<nome>/make_patch.py
    code = m.compile(["hello.c"])                            # nell'area mod, allo spazio prenotato dalla mod
    m.area(code, "hello.c")
    m.hook(0x400A6EE6, "2f0b2f0a246f000c", code["ks_wr"], what="kit block -> file: jmp ks_wr")
    m.write(description="...", requires=["modarea"], symbols=["ks_wr"])

Richiede binutils e gcc m68k in WSL (CONTRIBUTING.md) e l'OS stock in firmware/. Ogni aggancio porta i byte
originali attesi: su un OS diverso il make_patch si ferma, e il patch.json ne tiene l'impronta per la build.
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
sys.path[:0] = [str(REPO / "tools" / "unpack"), str(HERE)]
import eft  # noqa: E402
import modarea_layout  # noqa: E402
import registry  # noqa: E402

OS = "1.42"
LOAD = 0x4000_0400                      # indirizzo della sezione 3 in RAM
TOOLS = "~/tools/m68k/root"             # binutils e gcc m68k scompattati in WSL (CONTRIBUTING.md)
CFLAGS = "-mcpu=54418 -Os -ffreestanding -fno-builtin -nostdlib -fno-pic -fno-common -Wall -Wextra"
ENV = f"R={TOOLS}; export LD_LIBRARY_PATH=$R/usr/lib/x86_64-linux-gnu; "
BIN = "$R/usr/bin/m68k-linux-gnu-"
GCC = f"{BIN}gcc-13 -B$R/usr/libexec/gcc/m68k-linux-gnu/13/ -B{BIN}"
JMP, JSR, NOP = 0x4EF9, 0x4EB9, 0x4E71


class ModError(SystemExit):
    pass


def sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def wsl(cmd: str) -> str:
    r = subprocess.run(["wsl.exe", "-e", "bash", "-lc", cmd], capture_output=True, text=True)
    if r.returncode:
        raise ModError(f"comando WSL fallito:\n{cmd}\n{r.stderr}")
    return r.stdout + r.stderr


class Code(dict):
    """Codice compilato: i simboli come chiavi (code["nome"] = indirizzo), piu' .blob e .base."""
    blob: bytes
    base: int


class Mod:
    def __init__(self, make_patch_file: str, stock: Path | None = None):
        self.here = Path(make_patch_file).resolve().parent
        self.name = self.here.name
        self.patches: list[dict] = []
        stock = stock or REPO / "firmware" / f"Syntakt_OS{OS}.syx"
        if not stock.exists():
            raise ModError(f"manca {stock}: vedi firmware/README.md")
        self._stock = stock
        self._sec: dict[int, bytes] = {}

    # ---------------------------------------------------------------- OS stock
    def section(self, n: int = 3) -> bytes:
        if n not in self._sec:
            self._sec[n] = eft.unpack(self._stock, REPO / "unpacked" / self._stock.stem, ids=[n])[n].read_bytes()
        return self._sec[n]

    def stock(self, addr: int, n: int) -> bytes:
        """n byte dell'OS stock (sezione 3) all'indirizzo addr."""
        return self.section()[addr - LOAD:addr - LOAD + n]

    # ---------------------------------------------------------------- spazio prenotato
    def space(self, index: int = 0) -> tuple[int, int]:
        """(inizio, fine) dello spazio index-esimo che il registro da' alla mod nell'area mod, come offset."""
        rows = sorted((a, b) for a, b, who, _ in registry.MODAREA if who == self.name)
        if index >= len(rows):
            raise ModError(f"{self.name}: nessuno spazio nell'area mod: mods/{self.name}/claims.json "
                           "(python tools/new_mod.py lo scrive)")
        return rows[index]

    # ---------------------------------------------------------------- compilazione
    def compile(self, sources: list[str], base: int | None = None, end: int | None = None, cflags: str = CFLAGS,
                defs: dict[str, int] | None = None, entry: str | None = None, sections: str | None = None) -> Code:
        """Compila e collega i sorgenti (.S, .c) a `base` (indirizzo in RAM; senza: lo spazio della mod nell'area
        mod). defs: simboli per l'assemblatore (--defsym) e macro per il C (-D). Niente .bss, niente libgcc."""
        if base is None:
            lo, hi = self.space()
            base, end = modarea_layout.RAM + lo, modarea_layout.RAM + hi
        defs = defs or {}
        with tempfile.TemporaryDirectory(prefix=f"{self.name}-") as tmp:
            tmp = Path(tmp)
            for f in [*(REPO / "sdk").glob("*.h"), *self.here.iterdir()]:     # sdk/synthack.h accanto ai sorgenti
                if f.suffix in (".S", ".s", ".c", ".h"):
                    shutil.copy(f, tmp / f.name)
            env = ENV + f"cd {eft.to_wsl_path(tmp)}; "
            objs, c = [], False
            for k, src in enumerate(sources):
                obj = f"o{k}.o"
                if src.endswith(".c"):
                    c = True
                    d = " ".join(f"-D{n}={v:#x}u" for n, v in defs.items())
                    warn = wsl(env + f"{GCC} {cflags} {d} -c {src} -o {obj}")
                    if "warning" in warn:
                        raise ModError(warn)
                else:
                    d = " ".join(f"--defsym {n}={v}" for n, v in defs.items())
                    wsl(env + f"{BIN}as -mcpu=54418 {d} {src} -o {obj}")
                objs.append(obj)
            e = f"-e {entry or hex(base)} "           # senza, ld cerca _start
            wsl(env + f"{BIN}ld -N -Ttext={base:#x} {e}-o m.elf {' '.join(objs)}")
            if wsl(env + f"{BIN}nm -u m.elf").strip():
                raise ModError(f"{self.name}: simboli esterni (libgcc?) non permessi:\n" + wsl(env + f"{BIN}nm -u m.elf"))
            for line in wsl(env + f"{BIN}size -A m.elf").splitlines():
                parts = line.split()
                if len(parts) >= 2 and parts[0] in (".bss", ".sbss") and int(parts[1]):
                    raise ModError(f"{self.name}: {parts[0]} di {parts[1]} B: le variabili vanno in .data "
                                   '(__attribute__((section(".data"))))')
            keep = sections or ("-j .text -j .rodata -j .data" if c else "-j .text -j .data")
            wsl(env + f"{BIN}objcopy -O binary {keep} m.elf m.bin")
            code = Code()
            for line in wsl(env + f"{BIN}nm m.elf").splitlines():
                parts = line.split()
                if len(parts) == 3:
                    code[parts[2]] = int(parts[0], 16)
            code.blob, code.base = (tmp / "m.bin").read_bytes(), base
        if end is not None and base + len(code.blob) > end:
            raise ModError(f"{self.name}: non ci sta: {len(code.blob)} B in {end - base} B")
        return code

    # ---------------------------------------------------------------- patch
    def area(self, code: Code, what: str) -> None:
        """Il codice compilato, accodato all'immagine dell'area mod."""
        off = code.base - modarea_layout.RAM
        self.patches.append({"section": 3, "addr": f"{modarea_layout.IMG + off:#010X}", "len": len(code.blob),
                             "append": True, "hex": code.blob.hex(), "ram": f"{code.base:#010x}",
                             "what": f"(area mod) {what}"})

    def replace(self, addr: int, orig: str, new: bytes, what: str) -> None:
        """Sostituisce len(new) byte dell'OS; orig: i byte attesi, in esadecimale."""
        old = self.stock(addr, len(new))
        if old.hex() != orig.lower():
            raise ModError(f"{self.name}: {addr:#x}: byte inattesi {old.hex()} (attesi {orig})")
        self.patches.append({"section": 3, "addr": f"{addr:#010X}", "len": len(new), "expect_sha256": sha(old),
                             "hex": new.hex(), "what": what})

    def hook(self, addr: int, orig: str, target: int, what: str, call: bool = False) -> None:
        """jmp (call=True: jsr) a target al posto delle istruzioni in addr, il resto a nop. orig: tutte le
        istruzioni sostituite (almeno 6 byte, numero pari): il codice di target le rifa' prima di tornare."""
        n = len(orig) // 2
        if n < 6 or n % 2:
            raise ModError(f"{self.name}: {addr:#x}: un aggancio sostituisce almeno 6 byte, in numero pari")
        self.replace(addr, orig, struct.pack(">HI", JSR if call else JMP, target) + struct.pack(">H", NOP) * ((n - 6) // 2),
                     what)

    # ---------------------------------------------------------------- uscita
    def write(self, description: str, requires: list[str] | None = None, symbols: dict[str, int] | None = None,
              extra: dict | None = None) -> None:
        spec: dict = {"name": self.name, "os": OS}
        if requires:
            spec["requires"] = requires
        spec["description"] = description
        spec["generated_by"] = f"mods/{self.name}/make_patch.py"
        if symbols:
            spec["symbols"] = {k: f"{v:#010x}" for k, v in symbols.items()}
        spec.update(extra or {})
        spec["patches"] = self.patches
        (self.here / "patch.json").write_text(json.dumps(spec, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        size = sum(p["len"] for p in self.patches if p.get("append"))
        print(f"mods/{self.name}/patch.json: {len(self.patches)} patch, {size} B nell'area mod")
