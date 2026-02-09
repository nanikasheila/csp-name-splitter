from __future__ import annotations

from dataclasses import dataclass

from .config import GridConfig
from .errors import ConfigError


@dataclass(frozen=True)
class CellRect:
    index: int
    row: int
    col: int
    x0: int
    y0: int
    x1: int
    y1: int


def compute_cells(width: int, height: int, grid: GridConfig) -> list[CellRect]:
    if width <= 0 or height <= 0:
        raise ConfigError("Canvas width/height must be positive")

    # Use 4-direction margins if specified, otherwise fall back to legacy margin_px
    margin_left = grid.margin_left_px if grid.margin_left_px or grid.margin_right_px or grid.margin_top_px or grid.margin_bottom_px else grid.margin_px
    margin_right = grid.margin_right_px if grid.margin_left_px or grid.margin_right_px or grid.margin_top_px or grid.margin_bottom_px else grid.margin_px
    margin_top = grid.margin_top_px if grid.margin_left_px or grid.margin_right_px or grid.margin_top_px or grid.margin_bottom_px else grid.margin_px
    margin_bottom = grid.margin_bottom_px if grid.margin_left_px or grid.margin_right_px or grid.margin_top_px or grid.margin_bottom_px else grid.margin_px

    usable_w = width - margin_left - margin_right - (grid.cols - 1) * grid.gutter_px
    usable_h = height - margin_top - margin_bottom - (grid.rows - 1) * grid.gutter_px
    if usable_w <= 0 or usable_h <= 0:
        raise ConfigError("Grid margins/gutters exceed canvas size")

    base_w, remainder_w = divmod(usable_w, grid.cols)
    base_h, remainder_h = divmod(usable_h, grid.rows)

    col_widths = [base_w] * grid.cols
    row_heights = [base_h] * grid.rows
    col_widths[-1] += remainder_w
    row_heights[-1] += remainder_h

    col_positions = [margin_left]
    for col in range(1, grid.cols):
        prev = col_positions[-1] + col_widths[col - 1] + grid.gutter_px
        col_positions.append(prev)

    row_positions = [margin_top]
    for row in range(1, grid.rows):
        prev = row_positions[-1] + row_heights[row - 1] + grid.gutter_px
        row_positions.append(prev)

    if grid.order == "rtl_ttb":
        col_iter = list(reversed(range(grid.cols)))
    elif grid.order == "ltr_ttb":
        col_iter = list(range(grid.cols))
    else:
        raise ConfigError(f"Unknown grid order: {grid.order}")

    cells: list[CellRect] = []
    index = 0
    for row in range(grid.rows):
        for col in col_iter:
            x0 = col_positions[col]
            y0 = row_positions[row]
            x1 = x0 + col_widths[col]
            y1 = y0 + row_heights[row]
            cells.append(CellRect(index=index, row=row, col=col, x0=x0, y0=y0, x1=x1, y1=y1))
            index += 1
    return cells
