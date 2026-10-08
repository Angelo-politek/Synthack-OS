import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools" / "splash"))
import render  # noqa: E402


def test_bitmap_size_and_packing():
    bm = render.Bitmap.blank()
    bm.set(0, 0)
    bm.set(127, 63)
    raw = bm.to_bytes_rowmajor()
    assert len(raw) == 128 * 64 // 8
    assert raw[0] == 0x80 and raw[-1] == 0x01


def test_underscores_join_into_a_line():
    bm = render.Bitmap.blank()
    render.draw_art(bm, ["___"], 3, 6, 0, 0)
    assert bm.px[5][:9] == [1] * 9 and not any(bm.px[0])
