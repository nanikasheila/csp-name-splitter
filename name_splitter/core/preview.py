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
    line_width: int = 1,
    show_page_numbers: bool = True,
    page_number_color: tuple[int, int, int, int] = (255, 255, 255, 255),
    page_number_bg_color: tuple[int, int, int, int] = (0, 0, 0, 200),
) -> bytes:
    """画像プレビューを生成（グリッド線とページ番号付き）"""
    image_path = Path(path)
    if not image_path.exists():
        raise ImageReadError(f"Image not found: {image_path}")
    try:
        from PIL import Image, ImageDraw, ImageFont
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
        margin_top_px=max(0, int(round(grid.margin_top_px * scale))),
        margin_bottom_px=max(0, int(round(grid.margin_bottom_px * scale))),
        margin_left_px=max(0, int(round(grid.margin_left_px * scale))),
        margin_right_px=max(0, int(round(grid.margin_right_px * scale))),
        gutter_px=max(0, int(round(grid.gutter_px * scale))),
    )
    cells = compute_cells(image.width, image.height, scaled_grid)

    draw = ImageDraw.Draw(image)
    
    # グリッド線を描画（スケールせず固定値で統一）
    for cell in cells:
        draw.rectangle((cell.x0, cell.y0, cell.x1, cell.y1), outline=line_color, width=line_width)
    
    # ページ番号を描画
    if show_page_numbers:
        # フォントサイズを画像サイズに応じて調整
        avg_cell_size = ((cells[0].x1 - cells[0].x0) + (cells[0].y1 - cells[0].y0)) / 2
        font_size = max(12, min(48, int(avg_cell_size * 0.15)))
        
        try:
            # デフォルトフォントを使用
            font: ImageFont.FreeTypeFont | ImageFont.ImageFont | None = ImageFont.truetype("arial.ttf", font_size)
        except Exception:  # noqa: BLE001
            try:
                font = ImageFont.load_default()
            except Exception:  # noqa: BLE001
                # フォント取得失敗時はページ番号を描画しない
                font = None
        
        if font:
            for cell in cells:
                page_num = cell.index + 1
                text = str(page_num)
                
                # テキストサイズを取得
                try:
                    bbox = draw.textbbox((0, 0), text, font=font)
                    text_width = bbox[2] - bbox[0]
                    text_height = bbox[3] - bbox[1]
                except Exception:  # noqa: BLE001
                    # textbboxが使えない場合はtextsizeを試す
                    try:
                        text_width, text_height = draw.textsize(text, font=font)  # type: ignore
                    except Exception:  # noqa: BLE001
                        continue
                
                # セルの中央に配置
                cell_center_x = (cell.x0 + cell.x1) // 2
                cell_center_y = (cell.y0 + cell.y1) // 2
                text_x = cell_center_x - text_width // 2
                text_y = cell_center_y - text_height // 2
                
                # 背景矩形を描画（視認性向上）
                padding = max(4, font_size // 4)
                bg_rect = [
                    text_x - padding,
                    text_y - padding,
                    text_x + text_width + padding,
                    text_y + text_height + padding,
                ]
                draw.rectangle(bg_rect, fill=page_number_bg_color)
                
                # ページ番号を描画
                draw.text((text_x, text_y), text, fill=page_number_color, font=font)

    buffer = BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


__all__ = ["build_preview_png"]
