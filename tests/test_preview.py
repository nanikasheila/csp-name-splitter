"""Preview generation smoke test.

Why: プレビュー機能がサンプル画像から PNG バイト列を生成できることを保証する。
How: テスト用の最小画像を生成し、build_preview_png が非空のバイト列を返すことを
     検証する。
"""
import pytest

from name_splitter.core.config import GridConfig

try:
    from name_splitter.core.preview import build_preview_png
    HAS_PREVIEW = True
except ImportError:
    HAS_PREVIEW = False


@pytest.mark.skipif(not HAS_PREVIEW, reason="preview module unavailable")
def test_build_preview_returns_bytes(tmp_path: "Path") -> None:
    """build_preview_png produces non-empty PNG bytes from a test image."""
    from pathlib import Path
    from PIL import Image

    # Why: サンプル画像に依存せず CI でも実行可能にする
    test_image = tmp_path / "test.png"
    img = Image.new("RGB", (400, 400), color="white")
    img.save(test_image)

    grid = GridConfig(
        rows=2, cols=2, order="rtl_ttb",
        margin_top_px=0, margin_bottom_px=0,
        margin_left_px=0, margin_right_px=0,
        gutter_px=0,
    )
    result = build_preview_png(test_image, grid, show_page_numbers=True)
    assert isinstance(result, bytes)
    assert len(result) > 0
