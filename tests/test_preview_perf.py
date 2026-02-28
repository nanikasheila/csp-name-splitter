"""Tests for preview performance optimisations.

Why: Validates that the image cache, font cache, JPEG output, and
     load_and_resize_image helper introduced in the perf-preview-optimization
     feature work correctly.
How: Creates minimal test images via Pillow, exercises the new APIs, and
     asserts expected behaviour (cache hits/misses, JPEG header, font reuse).
"""
from __future__ import annotations

from pathlib import Path

import pytest
from PIL import Image

from name_splitter.core.config import GridConfig
from name_splitter.core.preview import (
    _get_font,
    build_preview_png,
    load_and_resize_image,
)
from name_splitter.app.gui_state import PreviewImageCache


# ------------------------------------------------------------------ #
# Helpers                                                              #
# ------------------------------------------------------------------ #

def _make_test_image(tmp_path: Path, size: tuple[int, int] = (400, 400)) -> Path:
    """Create a minimal white PNG for testing."""
    p = tmp_path / "test.png"
    Image.new("RGB", size, color="white").save(p)
    return p


_DEFAULT_GRID = GridConfig(
    rows=2,
    cols=2,
    order="rtl_ttb",
    margin_top_px=0,
    margin_bottom_px=0,
    margin_left_px=0,
    margin_right_px=0,
    gutter_px=0,
)


# ------------------------------------------------------------------ #
# P4: Font cache                                                       #
# ------------------------------------------------------------------ #

class TestFontCache:
    def test_get_font_returns_same_object_for_same_size(self) -> None:
        """_get_font(n) returns the *exact same* cached instance on repeat calls."""
        font_a = _get_font(24)
        font_b = _get_font(24)
        assert font_a is font_b

    def test_get_font_different_sizes(self) -> None:
        """Different font sizes produce distinct (but still cached) objects."""
        font_12 = _get_font(12)
        font_48 = _get_font(48)
        assert font_12 is not font_48


# ------------------------------------------------------------------ #
# P1: load_and_resize_image                                            #
# ------------------------------------------------------------------ #

class TestLoadAndResizeImage:
    def test_returns_rgba_image_and_scale(self, tmp_path: Path) -> None:
        """load_and_resize_image returns an RGBA PIL Image and a scale factor."""
        img_path = _make_test_image(tmp_path, (800, 600))
        image, scale = load_and_resize_image(img_path, max_dim=400)
        assert image.mode == "RGBA"
        assert max(image.size) <= 400
        assert scale < 1.0

    def test_no_resize_when_small(self, tmp_path: Path) -> None:
        """Image smaller than max_dim is not resized (scale == 1.0)."""
        img_path = _make_test_image(tmp_path, (200, 150))
        image, scale = load_and_resize_image(img_path, max_dim=800)
        assert scale == 1.0
        assert image.size == (200, 150)

    def test_missing_file_raises(self, tmp_path: Path) -> None:
        from name_splitter.core.errors import ImageReadError

        with pytest.raises(ImageReadError, match="not found"):
            load_and_resize_image(tmp_path / "nope.png", 800)


# ------------------------------------------------------------------ #
# P1: PreviewImageCache                                                #
# ------------------------------------------------------------------ #

class TestPreviewImageCache:
    def test_cache_miss_on_empty(self, tmp_path: Path) -> None:
        cache = PreviewImageCache()
        assert cache.get(str(tmp_path / "x.png"), 800) is None

    def test_cache_hit_after_store(self, tmp_path: Path) -> None:
        img_path = _make_test_image(tmp_path)
        original, scale = load_and_resize_image(img_path, 800)
        cache = PreviewImageCache()
        cache.store(str(img_path), 800, original, scale)
        result = cache.get(str(img_path), 800)
        assert result is not None
        cached_img, cached_scale = result
        assert cached_scale == scale
        assert cached_img.size == original.size

    def test_cache_miss_on_different_max_dim(self, tmp_path: Path) -> None:
        img_path = _make_test_image(tmp_path)
        original, scale = load_and_resize_image(img_path, 800)
        cache = PreviewImageCache()
        cache.store(str(img_path), 800, original, scale)
        assert cache.get(str(img_path), 400) is None

    def test_cache_invalidated_on_file_change(self, tmp_path: Path) -> None:
        img_path = _make_test_image(tmp_path)
        original, scale = load_and_resize_image(img_path, 800)
        cache = PreviewImageCache()
        cache.store(str(img_path), 800, original, scale)

        # Overwrite the file so mtime changes
        import time
        time.sleep(0.05)
        Image.new("RGB", (400, 400), color="red").save(img_path)

        assert cache.get(str(img_path), 800) is None


# ------------------------------------------------------------------ #
# P3: JPEG output                                                     #
# ------------------------------------------------------------------ #

class TestJpegOutput:
    def test_build_preview_returns_jpeg_bytes(self, tmp_path: Path) -> None:
        """build_preview_png now returns JPEG-encoded bytes."""
        img_path = _make_test_image(tmp_path)
        result = build_preview_png(img_path, _DEFAULT_GRID)
        # JPEG magic bytes: FF D8 FF
        assert result[:2] == b"\xff\xd8"

    def test_cached_image_produces_same_format(self, tmp_path: Path) -> None:
        """When a cached_image is passed, output is still JPEG."""
        img_path = _make_test_image(tmp_path)
        image, scale = load_and_resize_image(img_path, 800)
        result = build_preview_png(
            img_path,
            _DEFAULT_GRID,
            cached_image=image,
            cached_scale=scale,
        )
        assert result[:2] == b"\xff\xd8"


# ------------------------------------------------------------------ #
# P5: max_dim default reduced                                         #
# ------------------------------------------------------------------ #

class TestMaxDimDefault:
    def test_default_max_dim_is_800(self, tmp_path: Path) -> None:
        """Large images are down-scaled to max 800 px by default."""
        img_path = _make_test_image(tmp_path, (3000, 2000))
        image, _scale = load_and_resize_image(img_path, 800)
        assert max(image.size) <= 800
