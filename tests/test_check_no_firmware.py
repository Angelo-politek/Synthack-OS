from check_no_firmware import check_blob


def test_text_files_pass():
    assert check_blob("docs/firmware-format.md", b"Il container ELE3 ...") is None
    assert check_blob("tools/unpack/eft.py", b"print('hi')\n") is None


def test_forbidden_extensions():
    for p in ("firmware/Syntakt.syx", "x/section_7_blob.bin", "a.RAW"):
        assert check_blob(p, b"") is not None


def test_elektron_sysex_header_rejected_whatever_the_name():
    assert check_blob("innocuo.txt", b"\xf0\x00\x20\x3c\x10\x00") is not None


def test_binary_with_container_magic_rejected():
    assert check_blob("data.dat", b"\x00\x01ELE3\x00") is not None


def test_large_binary_rejected_small_binary_ok():
    assert check_blob("icon.png", b"\x89PNG\x00" + b"x" * 100) is None
    assert check_blob("big.dat", b"\x00" * (256 * 1024 + 1)) is not None
