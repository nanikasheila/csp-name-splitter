import unittest
from pathlib import Path
import tempfile
import os

from name_splitter.core.config import GridConfig, load_config
from name_splitter.app.gui_utils import mm_to_px


class ConfigTests(unittest.TestCase):
    def test_mm_to_px_conversion(self) -> None:
        """Test millimeter to pixel conversion at various DPI settings."""
        # 25.4mm = 1 inch, so at 300 DPI, 25.4mm should be 300px
        self.assertEqual(mm_to_px(25.4, 300), 300)
        
        # At 350 DPI (common for print), 10mm should be approximately 138px
        result_350 = mm_to_px(10, 350)
        expected_350 = round(10 * 350 / 25.4)  # ≈ 138
        self.assertEqual(result_350, expected_350)
        
        # At 72 DPI (screen), 25.4mm should be 72px
        self.assertEqual(mm_to_px(25.4, 72), 72)
        
        # Fractional mm values should round to nearest pixel
        self.assertEqual(mm_to_px(5.0, 300), round(5.0 * 300 / 25.4))  # ≈ 59

    def test_grid_config_with_margin_unit(self) -> None:
        """Test GridConfig with margin_unit field."""
        grid_px = GridConfig(
            rows=2,
            cols=2,
            margin_px=10,
            margin_unit="px"
        )
        self.assertEqual(grid_px.margin_unit, "px")
        self.assertEqual(grid_px.margin_px, 10)
        
        grid_mm = GridConfig(
            rows=2,
            cols=2,
            margin_px=10,  # These are still stored in px after conversion
            margin_unit="mm"
        )
        self.assertEqual(grid_mm.margin_unit, "mm")
        self.assertEqual(grid_mm.margin_px, 10)

    def test_grid_config_individual_margins_with_unit(self) -> None:
        """Test GridConfig with individual margins and unit."""
        grid = GridConfig(
            rows=2,
            cols=2,
            margin_px=0,
            margin_top_px=5,
            margin_bottom_px=10,
            margin_left_px=15,
            margin_right_px=20,
            margin_unit="mm"
        )
        self.assertEqual(grid.margin_unit, "mm")
        self.assertEqual(grid.margin_top_px, 5)
        self.assertEqual(grid.margin_bottom_px, 10)
        self.assertEqual(grid.margin_left_px, 15)
        self.assertEqual(grid.margin_right_px, 20)

    def test_load_config_with_margin_unit(self) -> None:
        """Test loading config file with margin_unit field."""
        yaml_content = """
version: 1
input:
  image_path: "test.png"
grid:
  rows: 3
  cols: 3
  order: ltr_ttb
  margin_px: 5
  margin_top_px: 10
  margin_bottom_px: 8
  margin_left_px: 6
  margin_right_px: 7
  margin_unit: mm
  gutter_px: 2
merge:
  group_rules: []
  layer_rules: []
  include_hidden_layers: false
output:
  out_dir: "output"
  page_basename: "page_{page:03d}"
  layer_stack: ["flat"]
  raster_ext: "png"
  container: "png"
  layout: "layers"
limits:
  max_dim_px: 30000
  on_exceed: "error"
"""
        # Create temporary config file
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False, encoding='utf-8') as f:
            f.write(yaml_content)
            temp_path = f.name
        
        try:
            config = load_config(temp_path)
            self.assertEqual(config.grid.rows, 3)
            self.assertEqual(config.grid.cols, 3)
            self.assertEqual(config.grid.margin_px, 5)
            self.assertEqual(config.grid.margin_top_px, 10)
            self.assertEqual(config.grid.margin_bottom_px, 8)
            self.assertEqual(config.grid.margin_left_px, 6)
            self.assertEqual(config.grid.margin_right_px, 7)
            self.assertEqual(config.grid.margin_unit, "mm")
            self.assertEqual(config.grid.gutter_px, 2)
        finally:
            os.unlink(temp_path)


if __name__ == "__main__":
    unittest.main()
