"""Tests for B-2: Page number customization.

Why: Verify _select_pages skip/odd_even filtering and
     page number offset in render output naming.
"""
import tempfile
import unittest
from pathlib import Path

from name_splitter.core.config import (
    Config,
    GridConfig,
    MergeConfig,
    MergeRule,
    OutputConfig,
)
from name_splitter.core.grid import compute_cells
from name_splitter.core.image_ops import ImageData
from name_splitter.core.image_read import ImageInfo, LayerNode, LayerPixels
from name_splitter.core.job import _select_pages
from name_splitter.core.merge import apply_merge_rules
from name_splitter.core.render import render_pages


class TestSelectPagesBasic(unittest.TestCase):
    """_select_pages with no filtering should return all pages."""

    def test_all_pages(self) -> None:
        result = _select_pages(5, None)
        self.assertEqual(result, [0, 1, 2, 3, 4])

    def test_test_page(self) -> None:
        """test_page takes priority over everything."""
        result = _select_pages(5, 3, skip=(1, 2), odd_even="even")
        self.assertEqual(result, [2])

    def test_test_page_out_of_range(self) -> None:
        with self.assertRaises(ValueError):
            _select_pages(5, 6)
        with self.assertRaises(ValueError):
            _select_pages(5, 0)


class TestSelectPagesSkip(unittest.TestCase):
    """Skip pages filtering (1-based)."""

    def test_skip_single(self) -> None:
        result = _select_pages(5, None, skip=(1,))
        self.assertEqual(result, [1, 2, 3, 4])

    def test_skip_multiple(self) -> None:
        result = _select_pages(5, None, skip=(1, 3, 5))
        self.assertEqual(result, [1, 3])

    def test_skip_out_of_range_ignored(self) -> None:
        """Pages outside range should be silently ignored."""
        result = _select_pages(3, None, skip=(0, 4, 99))
        self.assertEqual(result, [0, 1, 2])

    def test_skip_all(self) -> None:
        result = _select_pages(3, None, skip=(1, 2, 3))
        self.assertEqual(result, [])


class TestSelectPagesOddEven(unittest.TestCase):
    """Odd/even filtering based on 1-based position in remaining pages."""

    def test_odd_only(self) -> None:
        # 5 pages: positions 1,2,3,4,5 → odd = 1,3,5 → indices 0,2,4
        result = _select_pages(5, None, odd_even="odd")
        self.assertEqual(result, [0, 2, 4])

    def test_even_only(self) -> None:
        # 5 pages: positions 1,2,3,4,5 → even = 2,4 → indices 1,3
        result = _select_pages(5, None, odd_even="even")
        self.assertEqual(result, [1, 3])

    def test_all_unchanged(self) -> None:
        result = _select_pages(4, None, odd_even="all")
        self.assertEqual(result, [0, 1, 2, 3])

    def test_skip_then_odd(self) -> None:
        """Skip first, then odd/even applied to remaining list."""
        # 5 pages, skip page 2 → remaining [0,2,3,4]
        # odd positions (1,3) of remaining → [0, 3]
        result = _select_pages(5, None, skip=(2,), odd_even="odd")
        self.assertEqual(result, [0, 3])

    def test_skip_then_even(self) -> None:
        # 5 pages, skip page 1 → remaining [1,2,3,4]
        # even positions (2,4) of remaining → [2, 4]
        result = _select_pages(5, None, skip=(1,), odd_even="even")
        self.assertEqual(result, [2, 4])


class TestPageNumberOffset(unittest.TestCase):
    """page_number_start offsets output directory names."""

    def test_start_from_3(self) -> None:
        """page_number_start=3 should produce page_003, page_004, ..."""
        image = ImageData(
            width=4,
            height=2,
            pixels=[[(10, 10, 10, 255)] * 4 for _ in range(2)],
        )
        layers = (
            LayerNode(
                name="BG",
                kind="layer",
                visible=True,
                pixels=LayerPixels(bbox=(0, 0, 4, 2), image=image),
            ),
        )
        info = ImageInfo(width=4, height=2)
        cfg = Config(
            grid=GridConfig(rows=1, cols=2, order="ltr_ttb", margin_px=0, gutter_px=0),
            merge=MergeConfig(layer_rules=(MergeRule(layer_name="BG", output_layer="bg"),)),
            output=OutputConfig(
                raster_ext="ppm",
                layer_stack=("bg",),
                page_number_start=3,
            ),
        )
        cells = compute_cells(info.width, info.height, cfg.grid)
        merge_result = apply_merge_rules(layers, cfg.merge, canvas_size=(4, 2))
        with tempfile.TemporaryDirectory() as tmp:
            pages = render_pages(Path(tmp), info, cells, cfg, [0, 1], merge_result)
            self.assertEqual(len(pages), 2)
            # First page: index=1, offset=2, display=3
            self.assertIn("page_003", str(pages[0].page_dir))
            # Second page: index=2, offset=2, display=4
            self.assertIn("page_004", str(pages[1].page_dir))

    def test_default_start_from_1(self) -> None:
        """Default page_number_start=1 should produce page_001, page_002."""
        image = ImageData(
            width=4,
            height=2,
            pixels=[[(10, 10, 10, 255)] * 4 for _ in range(2)],
        )
        layers = (
            LayerNode(
                name="BG",
                kind="layer",
                visible=True,
                pixels=LayerPixels(bbox=(0, 0, 4, 2), image=image),
            ),
        )
        info = ImageInfo(width=4, height=2)
        cfg = Config(
            grid=GridConfig(rows=1, cols=2, order="ltr_ttb", margin_px=0, gutter_px=0),
            merge=MergeConfig(layer_rules=(MergeRule(layer_name="BG", output_layer="bg"),)),
            output=OutputConfig(raster_ext="ppm", layer_stack=("bg",)),
        )
        cells = compute_cells(info.width, info.height, cfg.grid)
        merge_result = apply_merge_rules(layers, cfg.merge, canvas_size=(4, 2))
        with tempfile.TemporaryDirectory() as tmp:
            pages = render_pages(Path(tmp), info, cells, cfg, [0, 1], merge_result)
            self.assertIn("page_001", str(pages[0].page_dir))
            self.assertIn("page_002", str(pages[1].page_dir))


class TestOutputConfigValidation(unittest.TestCase):
    """Validation of new OutputConfig fields."""

    def test_negative_output_dpi_raises(self) -> None:
        from name_splitter.core.config import validate_config
        cfg = Config(
            output=OutputConfig(output_dpi=-1),
        )
        with self.assertRaises(Exception):
            validate_config(cfg)

    def test_zero_output_dpi_ok(self) -> None:
        from name_splitter.core.config import validate_config
        cfg = Config(
            output=OutputConfig(output_dpi=0),
        )
        # Should not raise
        validate_config(cfg)

    def test_invalid_odd_even_raises(self) -> None:
        from name_splitter.core.config import validate_config
        cfg = Config(
            output=OutputConfig(odd_even="invalid"),
        )
        with self.assertRaises(Exception):
            validate_config(cfg)


if __name__ == "__main__":
    unittest.main()
