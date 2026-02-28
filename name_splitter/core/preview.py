from __future__ import annotations

from functools import lru_cache
from io import BytesIO
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFont

from .config import GridConfig
from .errors import ImageReadError
from .grid import compute_cells


# ------------------------------------------------------------------
# P4: Font cache — avoid repeated OS font-system lookups
# ------------------------------------------------------------------

@lru_cache(maxsize=16)
def _get_font(font_size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont | None:
    """Load a font for the given size, cached across calls.

    Why: ImageFont.truetype performs OS font-system I/O on every call.
         Preview is regenerated frequently, but the font size changes
         only when the cell dimensions change.
    How: lru_cache keyed on font_size. Falls back to load_default when
         TrueType is unavailable; returns None if all attempts fail.
    """
    try:
        return ImageFont.truetype("arial.ttf", font_size)
    except Exception:  # noqa: BLE001
        try:
            return ImageFont.load_default()
        except Exception:  # noqa: BLE001
            return None


# ------------------------------------------------------------------
# P1 helper: Load and resize image (can be skipped via external cache)
# ------------------------------------------------------------------

def load_and_resize_image(
    path: str | Path, max_dim: int
) -> tuple[Image.Image, float]:
    """Read an image from disk, convert to RGBA, and down-scale for preview.

    Why: Disk I/O + RGBA conversion + resize is the single most expensive
         step in the preview pipeline. Separating it lets callers cache
         the result across preview rebuilds when only grid settings change.
    How: Opens with PIL, converts to RGBA, computes scale factor from
         max_dim, and resizes if needed. Returns both the image and the
         applied scale.

    Returns:
        (PIL Image in RGBA, scale factor applied)
    Raises:
        ImageReadError: if file not found or unreadable
    """
    image_path = Path(path)
    if not image_path.exists():
        raise ImageReadError(f"Image not found: {image_path}")
    try:
        with Image.open(image_path) as opened:
            image = opened.convert("RGBA")
    except Exception as exc:  # noqa: BLE001
        raise ImageReadError(f"Failed to read image: {image_path}") from exc

    width, height = image.size
    scale = 1.0
    if max(width, height) > max_dim:
        scale = max_dim / max(width, height)
        image = image.resize(
            (int(width * scale), int(height * scale)), Image.Resampling.LANCZOS
        )
    return image, scale


# ------------------------------------------------------------------
# Main preview builder
# ------------------------------------------------------------------

def build_preview_png(
    path: str | Path,
    grid: GridConfig,
    *,
    max_dim: int = 800,
    line_color: tuple[int, int, int, int] = (255, 80, 40, 170),
    line_width: int = 1,
    show_page_numbers: bool = True,
    page_number_color: tuple[int, int, int, int] = (255, 255, 255, 255),
    page_number_bg_color: tuple[int, int, int, int] = (0, 0, 0, 200),
    cached_image: Any | None = None,
    cached_scale: float | None = None,
) -> bytes:
    """Build a JPEG preview of the source image with grid overlay.

    Why: Users need immediate visual feedback when adjusting grid/margin
         settings. A fast preview loop is critical for usability.
    How: Accepts an optional pre-loaded/resized image (from
         PreviewImageCache) to skip the expensive I/O + resize step.
         Draws grid lines and page numbers, then encodes to JPEG for
         faster compression and smaller data-URI payloads.

    Args:
        path:               Source image file path.
        grid:               Grid configuration for cell computation.
        max_dim:            Maximum dimension for the preview image.
        line_color:         RGBA colour for grid lines.
        line_width:         Pixel width of grid lines.
        show_page_numbers:  Whether to render page index labels.
        page_number_color:  RGBA colour for page number text.
        page_number_bg_color: RGBA colour for page number background.
        cached_image:       Pre-loaded PIL Image (RGBA, resized) from cache.
        cached_scale:       Scale factor corresponding to cached_image.

    Returns:
        JPEG image bytes suitable for embedding in a data URI.
    """
    # P1: Use cached image if available; otherwise load from disk
    if cached_image is not None and cached_scale is not None:
        image = cached_image.copy()
        scale = cached_scale
    else:
        image, scale = load_and_resize_image(path, max_dim)

    scaled_grid = GridConfig(
        rows=grid.rows,
        cols=grid.cols,
        order=grid.order,
        margin_px=max(0, int(round(grid.margin_px * scale))),
        margin_top_px=max(0, int(round(grid.margin_top_px * scale))),
        margin_bottom_px=max(0, int(round(grid.margin_bottom_px * scale))),
        margin_left_px=max(0, int(round(grid.margin_left_px * scale))),
        margin_right_px=max(0, int(round(grid.margin_right_px * scale))),
        gutter_px=max(0, int(round(grid.gutter_px * scale))),
    )
    cells = compute_cells(image.width, image.height, scaled_grid)

    draw = ImageDraw.Draw(image)

    # Grid lines — fixed width regardless of scale
    for cell in cells:
        draw.rectangle(
            (cell.x0, cell.y0, cell.x1, cell.y1),
            outline=line_color,
            width=line_width,
        )

    # Page numbers
    if show_page_numbers and cells:
        avg_cell_size = (
            (cells[0].x1 - cells[0].x0) + (cells[0].y1 - cells[0].y0)
        ) / 2
        font_size = max(12, min(48, int(avg_cell_size * 0.15)))
        font = _get_font(font_size)

        if font:
            for cell in cells:
                text = str(cell.index + 1)

                try:
                    bbox = draw.textbbox((0, 0), text, font=font)
                    text_width = bbox[2] - bbox[0]
                    text_height = bbox[3] - bbox[1]
                except Exception:  # noqa: BLE001
                    try:
                        text_width, text_height = draw.textsize(text, font=font)  # type: ignore[attr-defined]
                    except Exception:  # noqa: BLE001
                        continue

                cell_cx = (cell.x0 + cell.x1) // 2
                cell_cy = (cell.y0 + cell.y1) // 2
                text_x = cell_cx - text_width // 2
                text_y = cell_cy - text_height // 2

                padding = max(4, font_size // 4)
                draw.rectangle(
                    [
                        text_x - padding,
                        text_y - padding,
                        text_x + text_width + padding,
                        text_y + text_height + padding,
                    ],
                    fill=page_number_bg_color,
                )
                draw.text(
                    (text_x, text_y), text, fill=page_number_color, font=font
                )

    # P3: JPEG output — lossy but 3-5× faster than PNG for preview
    buffer = BytesIO()
    rgb_image = image.convert("RGB")
    rgb_image.save(buffer, format="JPEG", quality=85)
    return buffer.getvalue()


__all__ = ["build_preview_png", "load_and_resize_image"]
