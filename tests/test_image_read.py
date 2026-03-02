"""Tests for name_splitter.core.image_read module.

Why: image_read.py handles image loading and metadata extraction.
     Tests verify correct behaviour for valid/invalid/missing files.
How: Uses Pillow to create temporary test images, then validates
     the read_image and read_image_document functions.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from PIL import Image

from name_splitter.core.errors import ImageReadError
from name_splitter.core.image_read import (
    ImageDocument,
    ImageInfo,
    read_image,
    read_image_document,
)


@pytest.fixture()
def png_path(tmp_path: Path) -> Path:
    """Create a minimal 4x3 RGBA PNG for testing."""
    img = Image.new("RGBA", (4, 3), (255, 0, 0, 255))
    path = tmp_path / "test.png"
    img.save(path, format="PNG")
    return path


@pytest.fixture()
def jpeg_path(tmp_path: Path) -> Path:
    """Create a minimal 6x5 RGB JPEG for testing."""
    img = Image.new("RGB", (6, 5), (0, 128, 255))
    path = tmp_path / "test.jpg"
    img.save(path, format="JPEG")
    return path


class TestReadImage:
    """Tests for read_image (metadata-only read)."""

    def test_returns_image_info_for_png(self, png_path: Path) -> None:
        info = read_image(png_path)
        assert isinstance(info, ImageInfo)
        assert info.width == 4
        assert info.height == 3

    def test_returns_image_info_for_jpeg(self, jpeg_path: Path) -> None:
        info = read_image(jpeg_path)
        assert info.width == 6
        assert info.height == 5

    def test_raises_for_missing_file(self, tmp_path: Path) -> None:
        with pytest.raises(ImageReadError, match="not found"):
            read_image(tmp_path / "no_such_image.png")

    def test_raises_for_corrupt_file(self, tmp_path: Path) -> None:
        bad = tmp_path / "corrupt.png"
        bad.write_bytes(b"not an image")
        with pytest.raises(ImageReadError, match="Failed to read"):
            read_image(bad)

    def test_accepts_string_path(self, png_path: Path) -> None:
        info = read_image(str(png_path))
        assert info.width == 4


class TestReadImageDocument:
    """Tests for read_image_document (full pixel read)."""

    def test_returns_document_with_pixels(self, png_path: Path) -> None:
        doc = read_image_document(png_path)
        assert isinstance(doc, ImageDocument)
        assert doc.info.width == 4
        assert doc.info.height == 3
        assert doc.image.width == 4
        assert doc.image.height == 3

    def test_raises_for_missing_file(self, tmp_path: Path) -> None:
        with pytest.raises(ImageReadError, match="not found"):
            read_image_document(tmp_path / "missing.png")

    def test_raises_for_corrupt_file(self, tmp_path: Path) -> None:
        bad = tmp_path / "bad.png"
        bad.write_bytes(b"\x00\x01\x02")
        with pytest.raises(ImageReadError, match="Failed to read"):
            read_image_document(bad)
