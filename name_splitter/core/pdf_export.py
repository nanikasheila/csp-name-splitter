"""PDF export module — combine rendered page images into a single PDF.

Why: Users need a single PDF file containing all split pages for
     printing, sharing, or archiving, rather than many separate PNGs.
How: Uses Pillow's PDF save capability to merge page images into a
     multi-page PDF. Each page image is converted to RGB (PDF does not
     support RGBA) and appended in order.
"""
from __future__ import annotations

from pathlib import Path
from typing import Sequence

from .render import RenderedPage


def export_pdf(
    rendered_pages: Sequence[RenderedPage],
    output_path: Path,
    *,
    layer_name: str = "flat",
    dpi: int = 300,
    jpeg_quality: int = 90,
) -> Path:
    """Combine rendered page images into a single multi-page PDF.

    Why: Splitting produces many individual image files; a single PDF is
         more convenient for print workflows and document sharing.
    How: Opens each page's target layer image with Pillow, converts RGBA
         to RGB (white background), then saves as multi-page PDF using
         Pillow's ``save_all`` + ``append_images`` feature.

    Args:
        rendered_pages: Ordered list of rendered page results.
        output_path: Destination path for the PDF file.
        layer_name: Which layer to include in the PDF (default: "flat").
        dpi: Resolution metadata embedded in the PDF (default: 300).
        jpeg_quality: JPEG compression quality for embedded images (default: 90).

    Returns:
        The output_path where the PDF was written.

    Raises:
        RuntimeError: If Pillow is not installed or no valid pages found.
        FileNotFoundError: If a page image file does not exist.
    """
    try:
        from PIL import Image
    except ImportError as exc:
        raise RuntimeError("Pillow is required for PDF export") from exc

    rgb_images: list[Image.Image] = []
    for page in rendered_pages:
        image_path = page.layer_paths.get(layer_name)
        if image_path is None:
            continue
        if not image_path.exists():
            raise FileNotFoundError(f"Page image not found: {image_path}")
        img = Image.open(image_path)
        # Why: PDF format does not support alpha channel
        # How: Composite onto white background to convert RGBA → RGB
        if img.mode == "RGBA":
            background = Image.new("RGB", img.size, (255, 255, 255))
            background.paste(img, mask=img.split()[3])
            rgb_images.append(background)
        elif img.mode != "RGB":
            rgb_images.append(img.convert("RGB"))
        else:
            rgb_images.append(img)

    if not rgb_images:
        raise RuntimeError(
            f"No valid page images found for layer '{layer_name}'. "
            "Ensure pages have been rendered before exporting PDF."
        )

    output_path.parent.mkdir(parents=True, exist_ok=True)

    first_page = rgb_images[0]
    remaining_pages = rgb_images[1:]

    first_page.save(
        str(output_path),
        format="PDF",
        resolution=dpi,
        save_all=True,
        append_images=remaining_pages,
    )

    # Why: Pillow save may silently succeed without writing (e.g. disk full)
    # How: Verify output file exists and is non-empty after save
    resolved = output_path.resolve()
    if not resolved.exists():
        raise RuntimeError(
            f"PDF export completed without error but file was not created: {resolved}"
        )
    file_size = resolved.stat().st_size
    if file_size == 0:
        raise RuntimeError(
            f"PDF export created an empty file (0 bytes): {resolved}"
        )

    return output_path
