"""Tests for PDF export functionality.

Covers: export_pdf(), container="pdf" config validation, CLI --pdf flag.
"""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from name_splitter.core.config import Config, OutputConfig, validate_config
from name_splitter.core.image_ops import ImageData
from name_splitter.core.pdf_export import export_pdf
from name_splitter.core.render import RenderedPage


def _create_test_png(directory: Path, name: str, width: int = 4, height: int = 4) -> Path:
    """Create a minimal PNG file for testing.

    Why: PDF export tests need actual image files on disk.
    How: Uses Pillow to create a small solid-color PNG.
    """
    from PIL import Image

    path = directory / name
    img = Image.new("RGBA", (width, height), (255, 0, 0, 128))
    img.save(path)
    return path


class TestExportPdf(unittest.TestCase):
    """Tests for the export_pdf function."""

    def test_single_page_produces_pdf(self) -> None:
        """Single rendered page produces a valid PDF file."""
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            png_path = _create_test_png(tmp_path, "page_001.png")
            page = RenderedPage(
                page_index=0,
                page_dir=tmp_path,
                layer_paths={"flat": png_path},
            )
            pdf_path = tmp_path / "output.pdf"

            result = export_pdf([page], pdf_path, layer_name="flat")

            self.assertEqual(result, pdf_path)
            self.assertTrue(pdf_path.exists())
            self.assertGreater(pdf_path.stat().st_size, 0)

    def test_multiple_pages_produces_multipage_pdf(self) -> None:
        """Multiple pages are combined into a single multi-page PDF."""
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            pages: list[RenderedPage] = []
            for i in range(3):
                png_path = _create_test_png(tmp_path, f"page_{i:03d}.png")
                pages.append(
                    RenderedPage(
                        page_index=i,
                        page_dir=tmp_path,
                        layer_paths={"flat": png_path},
                    )
                )
            pdf_path = tmp_path / "output.pdf"

            result = export_pdf(pages, pdf_path, layer_name="flat")

            self.assertTrue(result.exists())
            # Why: Verify PDF header to confirm valid format
            with open(pdf_path, "rb") as f:
                header = f.read(5)
            self.assertEqual(header, b"%PDF-")

    def test_rgba_converted_to_rgb(self) -> None:
        """RGBA images are converted to RGB with white background for PDF."""
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            # Why: RGBA with semi-transparent pixels should be composited on white
            from PIL import Image

            img = Image.new("RGBA", (2, 2), (255, 0, 0, 128))
            png_path = tmp_path / "page.png"
            img.save(png_path)

            page = RenderedPage(
                page_index=0,
                page_dir=tmp_path,
                layer_paths={"flat": png_path},
            )
            pdf_path = tmp_path / "output.pdf"

            result = export_pdf([page], pdf_path, layer_name="flat")

            self.assertTrue(result.exists())

    def test_empty_pages_raises_error(self) -> None:
        """Empty page list raises RuntimeError."""
        with tempfile.TemporaryDirectory() as tmp:
            pdf_path = Path(tmp) / "output.pdf"
            with self.assertRaises(RuntimeError) as ctx:
                export_pdf([], pdf_path, layer_name="flat")
            self.assertIn("No valid page images", str(ctx.exception))

    def test_missing_layer_skipped(self) -> None:
        """Pages without the requested layer are silently skipped."""
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            png_path = _create_test_png(tmp_path, "page.png")
            pages = [
                RenderedPage(
                    page_index=0,
                    page_dir=tmp_path,
                    layer_paths={"other_layer": png_path},
                ),
                RenderedPage(
                    page_index=1,
                    page_dir=tmp_path,
                    layer_paths={"flat": png_path},
                ),
            ]
            pdf_path = tmp_path / "output.pdf"

            result = export_pdf(pages, pdf_path, layer_name="flat")

            self.assertTrue(result.exists())

    def test_missing_image_file_raises_error(self) -> None:
        """FileNotFoundError raised when page image does not exist on disk."""
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            nonexistent = tmp_path / "does_not_exist.png"
            page = RenderedPage(
                page_index=0,
                page_dir=tmp_path,
                layer_paths={"flat": nonexistent},
            )
            pdf_path = tmp_path / "output.pdf"

            with self.assertRaises(FileNotFoundError):
                export_pdf([page], pdf_path, layer_name="flat")

    def test_output_directory_created(self) -> None:
        """Output directory is created if it does not exist."""
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            png_path = _create_test_png(tmp_path, "page.png")
            page = RenderedPage(
                page_index=0,
                page_dir=tmp_path,
                layer_paths={"flat": png_path},
            )
            nested_dir = tmp_path / "sub" / "dir"
            pdf_path = nested_dir / "output.pdf"

            result = export_pdf([page], pdf_path, layer_name="flat")

            self.assertTrue(nested_dir.exists())
            self.assertTrue(result.exists())

    def test_custom_dpi_accepted(self) -> None:
        """Custom DPI value is accepted without error."""
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            png_path = _create_test_png(tmp_path, "page.png")
            page = RenderedPage(
                page_index=0,
                page_dir=tmp_path,
                layer_paths={"flat": png_path},
            )
            pdf_path = tmp_path / "output.pdf"

            result = export_pdf([page], pdf_path, layer_name="flat", dpi=150)

            self.assertTrue(result.exists())


class TestContainerConfigValidation(unittest.TestCase):
    """Tests for container field validation in Config."""

    def test_container_pdf_is_valid(self) -> None:
        """container='pdf' passes validation."""
        cfg = Config(output=OutputConfig(container="pdf"))
        # Why: Should not raise — pdf is a valid container value
        validate_config(cfg)

    def test_container_png_is_valid(self) -> None:
        """container='png' passes validation."""
        cfg = Config(output=OutputConfig(container="png"))
        validate_config(cfg)

    def test_container_invalid_raises_error(self) -> None:
        """Invalid container value raises ConfigError."""
        from name_splitter.core.errors import ConfigError

        cfg = Config(output=OutputConfig(container="zip"))
        with self.assertRaises(ConfigError):
            validate_config(cfg)


class TestCliPdfFlag(unittest.TestCase):
    """Tests for CLI --pdf argument parsing."""

    def test_pdf_flag_in_parser(self) -> None:
        """--pdf flag is recognized by the CLI parser."""
        from name_splitter.app.cli import build_parser

        parser = build_parser()
        args = parser.parse_args(["test.png", "--pdf"])
        self.assertTrue(args.pdf)

    def test_no_pdf_flag_default(self) -> None:
        """Without --pdf, pdf defaults to False."""
        from name_splitter.app.cli import build_parser

        parser = build_parser()
        args = parser.parse_args(["test.png"])
        self.assertFalse(args.pdf)


if __name__ == "__main__":
    unittest.main()
