from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
from pathlib import Path

from .config import GridConfig
from .errors import ConfigError
from .grid import compute_cells

PAPER_SIZES_MM: dict[str, tuple[float, float]] = {
    "A4": (210.0, 297.0),
    "A5": (148.0, 210.0),
    "B4": (257.0, 364.0),
    "B5": (182.0, 257.0),
}


@dataclass(frozen=True)
class TemplateStyle:
    grid_color: tuple[int, int, int, int] = (255, 80, 40, 170)
    grid_width: int = 1
    finish_color: tuple[int, int, int, int] = (255, 255, 255, 200)
    finish_width: int = 2
    finish_width_mm: float = 0.0
    finish_height_mm: float = 0.0
    finish_offset_x_mm: float = 0.0
    finish_offset_y_mm: float = 0.0
    draw_finish: bool = True
    basic_color: tuple[int, int, int, int] = (0, 170, 255, 200)
    basic_width: int = 2
    basic_width_mm: float = 0.0
    basic_height_mm: float = 0.0
    basic_offset_x_mm: float = 0.0
    basic_offset_y_mm: float = 0.0
    draw_basic: bool = True


def mm_to_px(mm: float, dpi: int) -> int:
    return int(round(mm * dpi / 25.4))


def compute_page_size_px(size_name: str, dpi: int, orientation: str = "portrait") -> tuple[int, int]:
    key = size_name.strip().upper()
    if key not in PAPER_SIZES_MM:
        raise ValueError(f"Unknown paper size: {size_name}")
    width_mm, height_mm = PAPER_SIZES_MM[key]
    if orientation == "landscape":
        width_mm, height_mm = height_mm, width_mm
    width_px = mm_to_px(width_mm, dpi)
    height_px = mm_to_px(height_mm, dpi)
    return width_px, height_px


def parse_hex_color(value: str, alpha: int = 255) -> tuple[int, int, int, int]:
    raw = value.strip().lstrip("#")
    if len(raw) == 3:
        raw = "".join(char * 2 for char in raw)
    if len(raw) != 6:
        raise ValueError("Color must be in #RRGGBB format")
    r = int(raw[0:2], 16)
    g = int(raw[2:4], 16)
    b = int(raw[4:6], 16)
    alpha = max(0, min(255, int(alpha)))
    return (r, g, b, alpha)


def generate_template_png(
    output_path: str | Path,
    width_px: int,
    height_px: int,
    grid: GridConfig,
    style: TemplateStyle,
    dpi: int,
    show_page_numbers: bool = False,
) -> Path:
    """テンプレートPNGを生成（実際の作業用、デフォルトでページ番号非表示）"""
    image = _render_template_image(width_px, height_px, grid, style, dpi, show_page_numbers)
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    image.save(output_path, format="PNG")
    return output_path


def build_template_preview_png(
    width_px: int,
    height_px: int,
    grid: GridConfig,
    style: TemplateStyle,
    dpi: int,
    *,
    max_dim: int = 1600,
    show_page_numbers: bool = True,
) -> bytes:
    """テンプレートプレビューを生成（デフォルトでページ番号表示）"""
    if width_px <= 0 or height_px <= 0:
        raise ConfigError("Template width/height must be positive")
    scale = 1.0
    if max(width_px, height_px) > max_dim:
        scale = max_dim / max(width_px, height_px)
    scaled_width = max(1, int(round(width_px * scale)))
    scaled_height = max(1, int(round(height_px * scale)))
    scaled_dpi = max(1, int(round(dpi * scale)))
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
    scaled_style = TemplateStyle(
        grid_color=style.grid_color,
        grid_width=_scale_width(style.grid_width, scale),
        finish_color=style.finish_color,
        finish_width=_scale_width(style.finish_width, scale),
        finish_width_mm=style.finish_width_mm,
        finish_height_mm=style.finish_height_mm,
        finish_offset_x_mm=style.finish_offset_x_mm,
        finish_offset_y_mm=style.finish_offset_y_mm,
        draw_finish=style.draw_finish,
        basic_color=style.basic_color,
        basic_width=_scale_width(style.basic_width, scale),
        basic_width_mm=style.basic_width_mm,
        basic_height_mm=style.basic_height_mm,
        basic_offset_x_mm=style.basic_offset_x_mm,
        basic_offset_y_mm=style.basic_offset_y_mm,
        draw_basic=style.draw_basic,
    )
    image = _render_template_image(scaled_width, scaled_height, scaled_grid, scaled_style, scaled_dpi, show_page_numbers)
    buffer = BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def _scale_width(value: int, scale: float) -> int:
    if value <= 0:
        return 0
    return max(1, int(round(value * scale)))


def _render_template_image(
    width_px: int,
    height_px: int,
    grid: GridConfig,
    style: TemplateStyle,
    dpi: int,
    show_page_numbers: bool = True,
):
    if width_px <= 0 or height_px <= 0:
        raise ConfigError("Template width/height must be positive")
    try:
        from PIL import Image, ImageDraw, ImageFont  # type: ignore
    except ImportError as exc:
        raise RuntimeError("Pillow is required to generate template images") from exc

    canvas = Image.new("RGBA", (width_px, height_px), (0, 0, 0, 0))
    draw = ImageDraw.Draw(canvas)

    cells = compute_cells(width_px, height_px, grid)

    if style.draw_finish and style.finish_width > 0 and style.finish_color[3] > 0:
        for cell in cells:
            rect = _frame_rect(
                cell,
                style.finish_width_mm,
                style.finish_height_mm,
                style.finish_offset_x_mm,
                style.finish_offset_y_mm,
                dpi,
            )
            if rect:
                _draw_rect(
                    draw,
                    rect[0],
                    rect[1],
                    rect[2],
                    rect[3],
                    width_px,
                    height_px,
                    style.finish_color,
                    style.finish_width,
                )

    if style.draw_basic and style.basic_width > 0 and style.basic_color[3] > 0:
        for cell in cells:
            rect = _frame_rect(
                cell,
                style.basic_width_mm,
                style.basic_height_mm,
                style.basic_offset_x_mm,
                style.basic_offset_y_mm,
                dpi,
            )
            if rect:
                _draw_rect(
                    draw,
                    rect[0],
                    rect[1],
                    rect[2],
                    rect[3],
                    width_px,
                    height_px,
                    style.basic_color,
                    style.basic_width,
                )

    if style.grid_width > 0 and style.grid_color[3] > 0:
        for cell in cells:
            _draw_rect(
                draw,
                cell.x0,
                cell.y0,
                cell.x1,
                cell.y1,
                width_px,
                height_px,
                style.grid_color,
                style.grid_width,
            )

    # ページ番号を描画
    if show_page_numbers and cells:
        avg_cell_size = ((cells[0].x1 - cells[0].x0) + (cells[0].y1 - cells[0].y0)) / 2
        font_size = max(12, min(72, int(avg_cell_size * 0.08)))
        
        try:
            font = ImageFont.truetype("arial.ttf", font_size)
        except Exception:  # noqa: BLE001
            try:
                font = ImageFont.load_default()
            except Exception:  # noqa: BLE001
                font = None
        
        if font:
            page_number_color = (50, 50, 50, 255)
            page_number_bg_color = (255, 255, 255, 220)
            
            for cell in cells:
                page_num = cell.index + 1
                text = str(page_num)
                
                try:
                    bbox = draw.textbbox((0, 0), text, font=font)
                    text_width = bbox[2] - bbox[0]
                    text_height = bbox[3] - bbox[1]
                except Exception:  # noqa: BLE001
                    try:
                        text_width, text_height = draw.textsize(text, font=font)  # type: ignore
                    except Exception:  # noqa: BLE001
                        continue
                
                cell_center_x = (cell.x0 + cell.x1) // 2
                cell_center_y = (cell.y0 + cell.y1) // 2
                text_x = cell_center_x - text_width // 2
                text_y = cell_center_y - text_height // 2
                
                padding = max(6, font_size // 3)
                bg_rect = [
                    text_x - padding,
                    text_y - padding,
                    text_x + text_width + padding,
                    text_y + text_height + padding,
                ]
                draw.rectangle(bg_rect, fill=page_number_bg_color)
                draw.text((text_x, text_y), text, fill=page_number_color, font=font)

    return canvas


def _draw_rect(draw, x0: int, y0: int, x1: int, y1: int, width: int, height: int, color, line_width: int) -> None:
    if line_width <= 0:
        return
    left = max(0, min(width - 1, int(x0)))
    top = max(0, min(height - 1, int(y0)))
    right = max(0, min(width - 1, int(x1) - 1))
    bottom = max(0, min(height - 1, int(y1) - 1))
    if right < left or bottom < top:
        return
    draw.rectangle((left, top, right, bottom), outline=color, width=line_width)


def _frame_rect(
    cell,
    width_mm: float,
    height_mm: float,
    offset_x_mm: float,
    offset_y_mm: float,
    dpi: int,
) -> tuple[int, int, int, int] | None:
    if width_mm <= 0 or height_mm <= 0:
        return None
    cell_w = cell.x1 - cell.x0
    cell_h = cell.y1 - cell.y0
    frame_w = mm_to_px(width_mm, dpi)
    frame_h = mm_to_px(height_mm, dpi)
    if frame_w <= 0 or frame_h <= 0:
        return None
    offset_x = mm_to_px(offset_x_mm, dpi)
    offset_y = mm_to_px(offset_y_mm, dpi)
    left = int(round(cell.x0 + (cell_w - frame_w) / 2 + offset_x))
    top = int(round(cell.y0 + (cell_h - frame_h) / 2 + offset_y))
    right = left + frame_w
    bottom = top + frame_h
    return left, top, right, bottom


__all__ = [
    "PAPER_SIZES_MM",
    "TemplateStyle",
    "mm_to_px",
    "compute_page_size_px",
    "parse_hex_color",
    "generate_template_png",
    "build_template_preview_png",
]
