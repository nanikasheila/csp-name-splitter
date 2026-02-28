"""Test px/mm unit conversion arithmetic.

Why: ページサイズ・マージンの mm↔px 変換が正確であることを保証する必要がある。
How: 既知の DPI で px→mm→px の往復変換を行い、誤差が 1px 以内であることを
     アサートする。
"""


def test_px_to_mm_conversion() -> None:
    """px -> mm conversion at 600dpi produces expected values."""
    dpi = 600
    width_px = 6071
    height_px = 8598
    width_mm = width_px * 25.4 / dpi
    height_mm = height_px * 25.4 / dpi
    # Why: B4 @600dpi is approximately 257mm x 364mm
    assert abs(width_mm - 257.0) < 1.0
    assert abs(height_mm - 364.0) < 1.0


def test_mm_to_px_conversion() -> None:
    """mm -> px conversion at 600dpi produces expected values."""
    dpi = 600
    width_mm = 257.0
    height_mm = 364.0
    width_px = int(width_mm * dpi / 25.4)
    height_px = int(height_mm * dpi / 25.4)
    assert abs(width_px - 6071) <= 1
    assert abs(height_px - 8598) <= 1


def test_px_mm_round_trip() -> None:
    """px -> mm -> px round trip stays within 1px tolerance."""
    dpi = 600
    original_px = 6071
    mm_val = original_px * 25.4 / dpi
    back_to_px = int(mm_val * dpi / 25.4)
    assert abs(original_px - back_to_px) <= 1
