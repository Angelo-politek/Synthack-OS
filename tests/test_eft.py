"""Test del wrapper che NON richiedono firmware."""

import pytest

import eft

# Output sintetico nel formato di report_summary() di elektron-firmware-tool.
# Numeri inventati: nessun dato reale del firmware.
SAMPLE = """\
device    : Syntakt (0x00)
version   : 9.99
container : ELE3, 1000 B
sections  :
  id 1   FPGA          100 B
  id 2   bootstrap     200 B
  id 3   MAIN OS       300 B
  id 5   meta           10 B (raw)
  id 7   blob          400 B
checksums : ok
"""


def test_parse_info():
    i = eft.parse_info(SAMPLE)
    assert i.device == "Syntakt (0x00)"
    assert i.version == "9.99"
    assert i.container.startswith("ELE3")
    assert i.checksums_ok
    assert [s.id for s in i.sections] == [1, 2, 3, 5, 7]
    assert i.section(3).name == "MAIN OS"
    assert i.section(5).raw and not i.section(7).raw
    assert i.section(7).size == 400


def test_parse_info_mismatch():
    assert not eft.parse_info(SAMPLE.replace("checksums : ok", "checksums : MISMATCH")).checksums_ok


@pytest.mark.skipif(eft.os.name != "nt", reason="percorsi Windows")
def test_to_wsl_path():
    assert eft.to_wsl_path(r"C:\Users\x\f.syx") == "/mnt/c/Users/x/f.syx"
    assert eft.to_wsl_path(r"D:\a b\c") == "/mnt/d/a b/c"


@pytest.mark.parametrize("sid", sorted(eft.PROTECTED_SECTIONS))
def test_repack_refuses_protected_sections(tmp_path, sid):
    with pytest.raises(eft.EftError, match="protette"):
        eft.repack(tmp_path / "in.syx", tmp_path / "out.syx", replace={sid: tmp_path / "x"})
