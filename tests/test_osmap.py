"""Port 1.41 -> 1.42: la mappa degli indirizzi (tools/build/osmap.py) e il port dei sorgenti (port_source.py).

Senza firmware: le regole del port sui testi. Con le due immagini stock in firmware/: la tabella nel repo e'
quella che si ricava allineandole, e le variabili si spostano come dicono gli operandi delle istruzioni.
"""

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools" / "build"))
import osmap  # noqa: E402
import port_source as P  # noqa: E402

BOTH = all((ROOT / "firmware" / f"Syntakt_OS{v}.syx").exists() for v in ("1.41", "1.42"))


def test_known_places_move_as_measured():
    assert osmap.addr(0x4008_FB04, "1.42") == 0x4008_FB7C     # mixer: +0x78
    assert osmap.addr(0x4022_D59C, "1.42") == 0x4022_D83C     # descrittori dei parametri: +0x2A0
    assert osmap.addr(0x41B9_F7E8, "1.42") == 0x41BA_07E8     # BSS: +0x1000
    assert osmap.addr(0x444E_38D0, "1.42") == 0x444E_48D0     # heap (area mod)
    assert osmap.addr(0x8000_DFD0, "1.42") == 0x8000_DFD0     # SRAM: invariata
    assert osmap.addr(0x4034_8000, "1.42") == 0x4034_9000     # area mod accodata


def test_changed_code_is_refused():
    gap = next((a, b) for (_, a, _), (b, _, _) in zip(osmap.table("1.42")[1], osmap.table("1.42")[1][1:]) if b - a > 64)
    with pytest.raises(osmap.Unmapped):
        osmap.addr((gap[0] + gap[1]) // 2 & ~1, "1.42")


def test_source_port_keeps_style_and_c_suffixes():
    text = "#define OBJS 0x41B9FA24u\nX = 0x4008_FB04\nQ30 = 0x4000_0000\nlea 0x41b9f7e8,%a0\n"
    new, changes, unmapped = P.port_text(text, "1.42")
    assert new == "#define OBJS 0x41BA0A24u\nX = 0x4008_FB7C\nQ30 = 0x4000_0000\nlea 0x41ba07e8,%a0\n"
    assert len(changes) == 3 and not unmapped


def test_hex_strings_translate_the_operand_not_the_opcode():
    new, _ = P.port_hex_strings('ORIG = "42b941b9f894"; JSR = "4eb940096890"; MOV = "203c401c7fa8"', "1.42")
    assert new == 'ORIG = "42b941ba0894"; JSR = "4eb940096908"; MOV = "203c401c8248"'


@pytest.mark.skipif(not BOTH, reason="servono gli OS stock 1.41 e 1.42")
def test_table_is_what_the_stock_images_give():
    assert osmap.generate("1.42") == osmap.table("1.42")[1]
