"""Passo 1 dell'harness: mappa di memoria e caricamento della sezione 7."""

import pytest

pytest.importorskip("unicorn")

import memmap  # noqa: E402

SEC7 = memmap.default_section7()
pytestmark = pytest.mark.skipif(not SEC7.exists(), reason=f"firmware stock assente: {SEC7}")


@pytest.fixture(scope="module")
def section7():
    return memmap.load_section7(SEC7)


def test_regions_do_not_overlap():
    rs = sorted(memmap.REGIONS, key=lambda r: r.base)
    for a, b in zip(rs, rs[1:]):
        assert a.base + a.size <= b.base, (a, b)


def test_section_fits_and_header_points_to_entry(section7):
    uc = memmap.new_cpu(section7)
    end = memmap.LOAD_ADDR + len(section7)
    assert end == 0x4005DF10                      # fine sezione = fine copie SRAM
    assert int.from_bytes(uc.mem_read(memmap.LOAD_ADDR, 4), "big") == memmap.ENTRY
    # all'entry: lea (4,sp),a0  (41EF 0004)
    assert bytes(uc.mem_read(memmap.ENTRY, 4)) == bytes.fromhex("41ef0004")
    # 0x40000404: RTE, il gestore d'eccezione "vuoto"
    assert bytes(uc.mem_read(0x40000404, 2)) == bytes.fromhex("4e73")


def test_sram_copies_match_source(section7):
    uc = memmap.new_cpu(section7)
    memmap.copy_data_to_sram(uc)
    for start, end, dst in memmap.SRAM_COPIES:
        assert uc.mem_read(dst, end - start) == uc.mem_read(start, end - start)
    # la sinusoide del workbench (offset 0x53E50 nella sezione) finisce a 0x80004B70
    src = memmap.LOAD_ADDR + 0x53E50
    assert uc.mem_read(0x80004B70, 64) == uc.mem_read(src, 64)


def test_rejects_wrong_section(tmp_path):
    bad = tmp_path / "section_7_blob.raw"
    bad.write_bytes(b"\x00" * 16)
    with pytest.raises(memmap.EmuError):
        memmap.load_section7(bad)
