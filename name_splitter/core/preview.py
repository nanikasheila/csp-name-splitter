from __future__ import annotations

from io import BytesIO
from pathlib import Path

from .config import GridConfig
from .errors import ImageReadError
from .grid import compute_cells


def build_preview_png(
    path: str | Path,
    grid: GridConfig,
    *,
    max_dim: int = 1600,
    line_color: tuple[int, int, int, int] = (255, 80, 40, 170),
) -> bytes:
    image_path = Path(path)
    if not image_path.exists():
        raise ImageReadError(f"Image not found: {image_path}")
    try:
        from PIL import Image, ImageDraw  # type: ignore
    except ImportError as exc:
        raise ImageReadError("Pillow is required to build previews") from exc

    try:
        with Image.open(image_path) as opened:
            image = opened.convert("RGBA")
    except Exception as exc:  # noqa: BLE001
        raise ImageReadError(f"Failed to read image: {image_path}") from exc
    width, height = image.size
    scale = 1.0
    if max(width, height) > max_dim:
        scale = max_dim / max(width, height)
        image = image.resize((int(width * scale), int(height * scale)))

    scaled_grid = GridConfig(
        rows=grid.rows,
        cols=grid.cols,
        order=grid.order,
        margin_px=max(0, int(round(grid.margin_px * scale))),
        gutter_px=max(0, int(round(grid.gutter_px * scale))),
    )
    cells = compute_cells(image.width, image.height, scaled_grid)

    draw = ImageDraw.Draw(image)
    for cell in cells:
        draw.rectangle((cell.x0, cell.y0, cell.x1, cell.y1), outline=line_color, width=2)

    buffer = BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


__all__ = ["build_preview_png"]
