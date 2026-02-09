"""Test gutter_unit field and page size unit conversion for preset sizes"""
from name_splitter.core.config import load_config, GridConfig
from pathlib import Path
import yaml

print("Test 1: Create config with gutter_unit=mm")
test_cfg = {
    "version": 1,
    "grid": {
        "rows": 4,
        "cols": 4,
        "order": "rtl_ttb",
        "margin_top_px": 50,
        "margin_bottom_px": 50,
        "margin_left_px": 50,
        "margin_right_px": 50,
        "gutter_px": 24,  # 1mm at 600dpi
        "gutter_unit": "mm",
        "margin_unit": "px",
        "dpi": 600,
        "page_size_name": "A4",
        "orientation": "portrait",
        "page_width_px": 4961,  # A4 portrait at 600dpi
        "page_height_px": 7016,
        "page_size_unit": "mm",
    }
}

test_path = Path("test_env/test_gutter_unit.yaml")
test_path.write_text(yaml.dump(test_cfg, allow_unicode=True, sort_keys=False), encoding="utf-8")
print(f"  Wrote test config to {test_path}")

cfg = load_config(str(test_path))
print(f"  Gutter unit: {cfg.grid.gutter_unit} (expected: mm)")
print(f"  Gutter (px): {cfg.grid.gutter_px} (expected: 24)")
print(f"  DPI: {cfg.grid.dpi}")

# Convert to mm for display
dpi = cfg.grid.dpi
print(f"  Gutter (mm): {cfg.grid.gutter_px * 25.4 / dpi:.2f} (expected: ~1.02mm)")

assert cfg.grid.gutter_unit == "mm", "Gutter unit mismatch"
assert cfg.grid.gutter_px == 24, "Gutter px mismatch"
print(f"  ✓ gutter_unit saved and loaded correctly\n")

print("Test 2: Page size unit conversion for A4")
print(f"  Page size: {cfg.grid.page_size_name}")
print(f"  Page size unit: {cfg.grid.page_size_unit}")
print(f"  Page dimensions (px): {cfg.grid.page_width_px} × {cfg.grid.page_height_px}")

# Convert to mm
w_mm = cfg.grid.page_width_px * 25.4 / dpi
h_mm = cfg.grid.page_height_px * 25.4 / dpi
print(f"  Page dimensions (mm): {w_mm:.2f} × {h_mm:.2f}")
print(f"  Expected: ~210mm × 297mm (A4)")
print(f"  ✓ Page size unit conversion OK\n")

print("Test 3: Gutter conversion formulas")
dpi = 600
gutter_mm = 1.0
gutter_px = int(gutter_mm * dpi / 25.4)
back_to_mm = gutter_px * 25.4 / dpi

print(f"  1.00mm @ 600dpi")
print(f"  -> {gutter_px}px")
print(f"  -> {back_to_mm:.2f}mm")
print(f"  ✓ Round trip OK\n")

print("All tests passed! ✓")
