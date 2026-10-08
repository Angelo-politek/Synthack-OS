"""Mappa di memoria della CPU audio (ColdFire #2) e caricamento della sezione 7.

Tutti gli indirizzi qui sotto sono FATTI documentati in docs/ e
docs/emulation.md (verificati in Ghidra o sul reference manual MCF54418RM),
validi per Syntakt OS 1.41. Per questo il caricatore controlla l'hash della
sezione: su un altro OS gli indirizzi potrebbero non valere piu'.
"""

from __future__ import annotations

import hashlib
import sys
from dataclasses import dataclass
from pathlib import Path

from unicorn import UC_ARCH_M68K, UC_MODE_BIG_ENDIAN, Uc
from unicorn.m68k_const import UC_CPU_M68K_ANY

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "tools" / "unpack"))
import eft  # noqa: E402

# Sezione 7 di Syntakt OS 1.41 (stesso hash dichiarato da syntakt-firmware-workbench)
SECTION7_SHA256 = "daf6451cf9587c0b628e901b7bb6b25f4e2633d448c534c0c181dd35ec783bc2"

LOAD_ADDR = 0x40000400       # dove il bootloader copia la sezione 7
ENTRY = 0x40001070           # indirizzo di partenza (scritto nei primi 4 byte della sezione)


@dataclass(frozen=True)
class Region:
    name: str
    base: int
    size: int


REGIONS = (
    # RAM dual-port condivisa con la CPU #1 (lato CPU #2 parte da 0). Dimensione 🟡
    # (128 KB sul Digitone mk1 secondo digiemu): basta che contenga 0x1B0 + 0x400 B.
    Region("shared", 0x0000_0000, 0x0002_0000),
    # DDR2: codice + BSS + stack. L'entry imposta SP = 0x48000000, quindi mappiamo
    # 128 MB fino a quell'indirizzo escluso.
    Region("ddr", 0x4000_0000, 0x0800_0000),
    # SRAM interna da 64 KB (RAMBAR nella finestra 0x8000_0000, ref. manual cap. 6)
    Region("sram", 0x8000_0000, 0x0001_0000),
    # Periferiche: GPIO (0xEC09_xxxx) e moduli on-chip (0xFC0x_xxxx). Le letture e
    # scritture vengono intercettate da periph.py.
    Region("periph_ec", 0xEC00_0000, 0x0010_0000),
    Region("periph_fc", 0xFC00_0000, 0x0010_0000),
)

# Dati inizializzati che il codice di avvio copia dalla DDR alla SRAM (Modded-Cycles,
# notes/16; confermato da noi: la fine coincide con la fine della sezione).
SRAM_COPIES = (
    (0x4004_F6E0, 0x4005_7670, 0x8000_0000),
    (0x4005_7670, 0x4005_DF10, 0x8000_8000),
)


class EmuError(RuntimeError):
    pass


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def load_section7(path: Path) -> bytes:
    """Accetta il .syx stock oppure la sezione 7 gia' estratta (.raw)."""
    path = Path(path)
    if path.suffix.lower() == ".syx":
        outdir = REPO / "unpacked" / path.stem
        path = eft.unpack(path, outdir, ids=[7])[7]
    data = path.read_bytes()
    if sha256(data) != SECTION7_SHA256:
        raise EmuError(
            f"{path}: la sezione 7 non e' quella di Syntakt OS 1.41 "
            "(gli indirizzi dell'emulatore valgono solo per quella)"
        )
    return data


def default_section7() -> Path:
    raw = REPO / "unpacked" / "Syntakt_OS1.41" / "section_7_blob.raw"
    return raw if raw.exists() else REPO / "firmware" / "Syntakt_OS1.41.syx"


def new_cpu(section7: bytes) -> Uc:
    """CPU ColdFire con memoria mappata e sezione 7 caricata (nessuna istruzione eseguita)."""
    uc = Uc(UC_ARCH_M68K, UC_MODE_BIG_ENDIAN, cpu=UC_CPU_M68K_ANY)
    for r in REGIONS:
        uc.mem_map(r.base, r.size)
    uc.mem_write(LOAD_ADDR, section7)
    return uc


def copy_data_to_sram(uc: Uc) -> None:
    """Piano B: fa a mano le copie DDR -> SRAM che normalmente fa il codice di avvio."""
    for start, end, dst in SRAM_COPIES:
        uc.mem_write(dst, bytes(uc.mem_read(start, end - start)))


def region_of(addr: int) -> Region | None:
    return next((r for r in REGIONS if r.base <= addr < r.base + r.size), None)
