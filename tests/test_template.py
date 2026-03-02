"""Tests for name_splitter.core.template module.

Why: template.py generates grid template images and provides
     paper-size calculations. Tests verify utility functions and
     template generation with various configurations.
How: Tests pure functions directly and validates generated PNG
     bytes/files are non-empty and correctly structured.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from name_splitter.core.config import GridConfig
from name_splitter.core.errors import ConfigError
from name_splitter.core.template import (
    PAPER_SIZES_MM,
    TemplateStyle,
    build_template_preview_png,
    compute_page_size_px,
    generate_template_png,
    mm_to_px,
    parse_hex_color,
)


# ------------------------------------------------------------------
# mm_to_px
# ------------------------------------------------------------------

class TestMmToPx:
    def test_1mm_at_300dpi(self) -> None:
        # Why: 1mm at 300dpi ≈ 11.81 → rounds to 12
        assert mm_to_px(1.0, 300) == 12

    def test_25_4mm_equals_dpi(self) -> None:
        # Why: 25.4mm = 1 inch = exactly DPI pixels
        assert mm_to_px(25.4, 600) == 600

    def test_zero_mm(self) -> None:
        assert mm_to_px(0.0, 300) == 0


# ------------------------------------------------------------------
# compute_page_size_px
# ------------------------------------------------------------------

class TestComputePageSizePx:
    def test_a4_portrait(self) -> None:
        w, h = compute_page_size_px("A4", 300)
        # Why: A4 is 210×297mm → 2480×3508 at 300dpi
        assert w == mm_to_px(210.0, 300)
        assert h == mm_to_px(297.0, 300)

    def test_a4_landscape(self) -> None:
        w, h = compute_page_size_px("A4", 300, orientation="landscape")
        assert w == mm_to_px(297.0, 300)
        assert h == mm_to_px(210.0, 300)

    def test_b5_portrait(self) -> None:
        w, h = compute_page_size_px("B5", 600)
        assert w == mm_to_px(182.0, 600)
        assert h == mm_to_px(257.0, 600)

    def test_unknown_size_raises(self) -> None:
        with pytest.raises(ValueError, match="Unknown paper size"):
            compute_page_size_px("Letter", 300)

    def test_case_insensitive(self) -> None:
        w1, h1 = compute_page_size_px("a4", 300)
        w2, h2 = compute_page_size_px("A4", 300)
        assert (w1, h1) == (w2, h2)


# ------------------------------------------------------------------
# parse_hex_color
# ------------------------------------------------------------------

class TestParseHexColor:
    def test_six_digit_hex(self) -> None:
        assert parse_hex_color("#FF8040") == (255, 128, 64, 255)

    def test_three_digit_hex(self) -> None:
        assert parse_hex_color("#F80") == (255, 136, 0, 255)

    def test_without_hash(self) -> None:
        assert parse_hex_color("00FF00") == (0, 255, 0, 255)

    def test_custom_alpha(self) -> None:
        assert parse_hex_color("#000000", alpha=128) == (0, 0, 0, 128)

    def test_invalid_length_raises(self) -> None:
        with pytest.raises(ValueError, match="RRGGBB"):
            parse_hex_color("#1234")


# ------------------------------------------------------------------
# generate_template_png
# ------------------------------------------------------------------

class TestGenerateTemplatePng:
    def test_creates_file(self, tmp_path: Path) -> None:
        output = tmp_path / "tpl.png"
        grid = GridConfig(rows=2, cols=2)
        style = TemplateStyle()
        result = generate_template_png(output, 200, 300, grid, style, dpi=300)
        assert result.exists()
        assert result.stat().st_size > 0

    def test_creates_parent_dirs(self, tmp_path: Path) -> None:
        output = tmp_path / "sub" / "dir" / "tpl.png"
        grid = GridConfig(rows=1, cols=1)
        style = TemplateStyle()
        result = generate_template_png(output, 100, 100, grid, style, dpi=300)
        assert result.exists()


# ------------------------------------------------------------------
# build_template_preview_png
# ------------------------------------------------------------------

class TestBuildTemplatePreviewPng:
    def test_returns_png_bytes(self) -> None:
        grid = GridConfig(rows=2, cols=2)
        style = TemplateStyle()
        data = build_template_preview_png(200, 300, grid, style, dpi=300)
        assert isinstance(data, bytes)
        assert len(data) > 0
        # Why: PNG magic bytes
        assert data[:4] == b"\x89PNG"

    def test_raises_for_zero_dimensions(self) -> None:
        grid = GridConfig(rows=2, cols=2)
        style = TemplateStyle()
        with pytest.raises(ConfigError, match="positive"):
            build_template_preview_png(0, 300, grid, style, dpi=300)

    def test_respects_max_dim(self) -> None:
        grid = GridConfig(rows=1, cols=1)
        style = TemplateStyle()
        data = build_template_preview_png(
            4000, 3000, grid, style, dpi=300, max_dim=800
        )
        assert isinstance(data, bytes)
        assert len(data) > 0
