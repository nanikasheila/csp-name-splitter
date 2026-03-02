"""Tests for B-1: Output DPI control.

Why: Verify that output_dpi controls post-crop image resizing and
     DPI metadata embedding. Ensures backward compatibility when dpi=0.
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
from name_splitter.core.merge import apply_merge_rules
from name_splitter.core.render import render_pages


def _make_simple_scene(
    width: int = 4,
    height: int = 2,
) -> tuple[tuple[LayerNode, ...], ImageInfo]:
    """Create a minimal scene for render tests."""
    pixels = [
        [(i * 10, i * 10, i * 10, 255) for i in range(width)]
        for _ in range(height)
    ]
    image = ImageData(width=width, height=height, pixels=pixels)
    layers = (
        LayerNode(
            name="BG",
            kind="layer",
            visible=True,
            pixels=LayerPixels(bbox=(0, 0, width, height), image=image),
        ),
    )
    info = ImageInfo(width=width, height=height)
    return layers, info


class TestOutputDpiZeroPassthrough(unittest.TestCase):
    """output_dpi=0 should not resize (backward compatible)."""

    def test_no_resize_when_dpi_zero(self) -> None:
        layers, info = _make_simple_scene(4, 2)
        cfg = Config(
            grid=GridConfig(rows=1, cols=2, order="ltr_ttb", margin_px=0, gutter_px=0, dpi=300),
            merge=MergeConfig(layer_rules=(MergeRule(layer_name="BG", output_layer="bg"),)),
            output=OutputConfig(raster_ext="ppm", layer_stack=("bg",), output_dpi=0),
        )
        cells = compute_cells(info.width, info.height, cfg.grid)
        merge_result = apply_merge_rules(layers, cfg.merge, canvas_size=(4, 2))
        with tempfile.TemporaryDirectory() as tmp:
            pages = render_pages(Path(tmp), info, cells, cfg, [0, 1], merge_result)
            self.assertEqual(len(pages), 2)
            for page in pages:
                path = page.layer_paths["bg"]
                w, h = _read_ppm_size(path)
                # Each cell is 2x2 (4 wide / 2 cols), no resize
                self.assertEqual(w, 2)
                self.assertEqual(h, 2)


class TestOutputDpiResize(unittest.TestCase):
    """output_dpi > 0 should resize output images."""

    def test_resize_halves_dimensions(self) -> None:
        """300dpi source → 150dpi output should halve dimensions."""
        layers, info = _make_simple_scene(4, 2)
        cfg = Config(
            grid=GridConfig(rows=1, cols=2, order="ltr_ttb", margin_px=0, gutter_px=0, dpi=300),
            merge=MergeConfig(layer_rules=(MergeRule(layer_name="BG", output_layer="bg"),)),
            output=OutputConfig(raster_ext="png", layer_stack=("bg",), output_dpi=150),
        )
        cells = compute_cells(info.width, info.height, cfg.grid)
        merge_result = apply_merge_rules(layers, cfg.merge, canvas_size=(4, 2))
        with tempfile.TemporaryDirectory() as tmp:
            pages = render_pages(Path(tmp), info, cells, cfg, [0, 1], merge_result)
            self.assertEqual(len(pages), 2)
            for page in pages:
                path = page.layer_paths["bg"]
                from PIL import Image
                with Image.open(path) as img:
                    # Original cell: 2x2, scale=150/300=0.5 → 1x1
                    self.assertEqual(img.size, (1, 1))

    def test_same_dpi_no_resize(self) -> None:
        """output_dpi == source dpi should not resize."""
        layers, info = _make_simple_scene(4, 2)
        cfg = Config(
            grid=GridConfig(rows=1, cols=2, order="ltr_ttb", margin_px=0, gutter_px=0, dpi=300),
            merge=MergeConfig(layer_rules=(MergeRule(layer_name="BG", output_layer="bg"),)),
            output=OutputConfig(raster_ext="ppm", layer_stack=("bg",), output_dpi=300),
        )
        cells = compute_cells(info.width, info.height, cfg.grid)
        merge_result = apply_merge_rules(layers, cfg.merge, canvas_size=(4, 2))
        with tempfile.TemporaryDirectory() as tmp:
            pages = render_pages(Path(tmp), info, cells, cfg, [0, 1], merge_result)
            for page in pages:
                path = page.layer_paths["bg"]
                w, h = _read_ppm_size(path)
                self.assertEqual(w, 2)
                self.assertEqual(h, 2)

    def test_dpi_metadata_embedded_in_png(self) -> None:
        """PNG output should contain DPI metadata."""
        layers, info = _make_simple_scene(4, 2)
        cfg = Config(
            grid=GridConfig(rows=1, cols=2, order="ltr_ttb", margin_px=0, gutter_px=0, dpi=300),
            merge=MergeConfig(layer_rules=(MergeRule(layer_name="BG", output_layer="bg"),)),
            output=OutputConfig(raster_ext="png", layer_stack=("bg",), output_dpi=350),
        )
        cells = compute_cells(info.width, info.height, cfg.grid)
        merge_result = apply_merge_rules(layers, cfg.merge, canvas_size=(4, 2))
        with tempfile.TemporaryDirectory() as tmp:
            pages = render_pages(Path(tmp), info, cells, cfg, [0], merge_result)
            path = pages[0].layer_paths["bg"]
            from PIL import Image
            with Image.open(path) as img:
                dpi_info = img.info.get("dpi")
                self.assertIsNotNone(dpi_info)
                # Pillow returns DPI as tuple of floats
                self.assertAlmostEqual(dpi_info[0], 350.0, delta=1.0)
                self.assertAlmostEqual(dpi_info[1], 350.0, delta=1.0)


class TestImageDataResize(unittest.TestCase):
    """Tests for ImageData.resize() method."""

    def test_resize_identity(self) -> None:
        """Same dimensions should return self."""
        img = ImageData(width=2, height=2, pixels=[
            [(255, 0, 0, 255), (0, 255, 0, 255)],
            [(0, 0, 255, 255), (255, 255, 0, 255)],
        ])
        result = img.resize(2, 2)
        self.assertIs(result, img)

    def test_resize_downscale(self) -> None:
        """Downscale should produce smaller image."""
        img = ImageData(width=4, height=4, pixels=[
            [(100, 100, 100, 255)] * 4 for _ in range(4)
        ])
        result = img.resize(2, 2)
        self.assertEqual(result.width, 2)
        self.assertEqual(result.height, 2)

    def test_resize_upscale(self) -> None:
        """Upscale should produce larger image."""
        img = ImageData(width=2, height=2, pixels=[
            [(50, 50, 50, 255)] * 2 for _ in range(2)
        ])
        result = img.resize(4, 4)
        self.assertEqual(result.width, 4)
        self.assertEqual(result.height, 4)

    def test_resize_zero_returns_blank(self) -> None:
        """Zero or negative dimensions should return 1x1 blank."""
        img = ImageData(width=2, height=2, pixels=[
            [(50, 50, 50, 255)] * 2 for _ in range(2)
        ])
        result = img.resize(0, 0)
        self.assertEqual(result.width, 1)
        self.assertEqual(result.height, 1)


class TestImageDataSaveDpi(unittest.TestCase):
    """Tests for ImageData.save() with dpi kwarg."""

    def test_save_png_with_dpi(self) -> None:
        """Saving with dpi > 0 should embed DPI metadata."""
        img = ImageData(width=2, height=2, pixels=[
            [(100, 100, 100, 255)] * 2 for _ in range(2)
        ])
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "test.png"
            img.save(path, dpi=300)
            from PIL import Image
            with Image.open(path) as pil_img:
                dpi_info = pil_img.info.get("dpi")
                self.assertIsNotNone(dpi_info)
                self.assertAlmostEqual(dpi_info[0], 300.0, delta=1.0)

    def test_save_png_without_dpi(self) -> None:
        """Saving with dpi=0 should not embed DPI metadata."""
        img = ImageData(width=2, height=2, pixels=[
            [(100, 100, 100, 255)] * 2 for _ in range(2)
        ])
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "test.png"
            img.save(path, dpi=0)
            from PIL import Image
            with Image.open(path) as pil_img:
                # No DPI key, or default (72, 72) depending on Pillow version
                dpi_info = pil_img.info.get("dpi")
                if dpi_info is not None:
                    # Should NOT be 300
                    self.assertNotAlmostEqual(dpi_info[0], 300.0, delta=1.0)


def _read_ppm_size(path: Path) -> tuple[int, int]:
    """Read width/height from a PPM P3 header."""
    with path.open("r", encoding="utf-8") as f:
        if f.readline().strip() != "P3":
            raise AssertionError("Not a P3 PPM file")
        line = f.readline().strip()
        while line.startswith("#") or not line:
            line = f.readline().strip()
        w, h = line.split()
        return int(w), int(h)


if __name__ == "__main__":
    unittest.main()
