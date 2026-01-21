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

    usable_w = width - 2 * grid.margin_px - (grid.cols - 1) * grid.gutter_px
    usable_h = height - 2 * grid.margin_px - (grid.rows - 1) * grid.gutter_px
    if usable_w <= 0 or usable_h <= 0:
        raise ConfigError("Grid margins/gutters exceed canvas size")

    base_w, remainder_w = divmod(usable_w, grid.cols)
    base_h, remainder_h = divmod(usable_h, grid.rows)

    col_widths = [base_w] * grid.cols
    row_heights = [base_h] * grid.rows
    col_widths[-1] += remainder_w
    row_heights[-1] += remainder_h

    col_positions = [grid.margin_px]
    for col in range(1, grid.cols):
        prev = col_positions[-1] + col_widths[col - 1] + grid.gutter_px
        col_positions.append(prev)

    row_positions = [grid.margin_px]
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
