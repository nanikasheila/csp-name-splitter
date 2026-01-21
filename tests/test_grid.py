import unittest

from name_splitter.core.config import GridConfig
from name_splitter.core.grid import compute_cells


class GridTests(unittest.TestCase):
    def test_compute_cells_ltr(self) -> None:
        grid = GridConfig(rows=2, cols=2, order="ltr_ttb", margin_px=0, gutter_px=0)
        cells = compute_cells(4, 4, grid)
        self.assertEqual(len(cells), 4)
        self.assertEqual((cells[0].x0, cells[0].y0, cells[0].x1, cells[0].y1), (0, 0, 2, 2))
        self.assertEqual((cells[1].x0, cells[1].y0, cells[1].x1, cells[1].y1), (2, 0, 4, 2))
        self.assertEqual((cells[2].x0, cells[2].y0, cells[2].x1, cells[2].y1), (0, 2, 2, 4))
        self.assertEqual((cells[3].x0, cells[3].y0, cells[3].x1, cells[3].y1), (2, 2, 4, 4))

    def test_compute_cells_rtl(self) -> None:
        grid = GridConfig(rows=1, cols=3, order="rtl_ttb", margin_px=0, gutter_px=0)
        cells = compute_cells(9, 3, grid)
        self.assertEqual([cell.x0 for cell in cells], [6, 3, 0])

    def test_compute_cells_with_margin_gutter(self) -> None:
        grid = GridConfig(rows=1, cols=2, order="ltr_ttb", margin_px=1, gutter_px=1)
        cells = compute_cells(7, 3, grid)
        self.assertEqual((cells[0].x0, cells[0].x1), (1, 3))
        self.assertEqual((cells[1].x0, cells[1].x1), (4, 6))


if __name__ == "__main__":
    unittest.main()
