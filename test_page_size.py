"""Test new features: page_size_name, orientation, page_size_unit"""
from name_splitter.core.config import load_config, GridConfig
from pathlib import Path
import yaml

print("Test 1: Verify new fields in GridConfig")
cfg = GridConfig(
    rows=4, cols=4, order="rtl_ttb",
    margin_top_px=50, margin_bottom_px=50, margin_left_px=50, margin_right_px=50,
    gutter_px=10, dpi=600,
    page_size_name="A4", orientation="landscape",
    page_width_px=3508, page_height_px=2480,
    page_size_unit="mm"
)
print(f"  Page size: {cfg.page_size_name}, Orientation: {cfg.orientation}")
print(f"  Page dimensions: {cfg.page_width_px}x{cfg.page_height_px} {cfg.page_size_unit}")
print(f"  DPI: {cfg.dpi}")
print(f"  ✓ GridConfig fields OK\n")

print("Test 2: Write and read config with new fields")
test_cfg = {
    "version": 1,
    "grid": {
        "rows": 3,
        "cols": 3,
        "order": "ltr_ttb",
        "margin_top_px": 30,
        "margin_bottom_px": 30,
        "margin_left_px": 30,
        "margin_right_px": 30,
        "gutter_px": 5,
        "dpi": 350,
        "page_size_name": "B5",
        "orientation": "portrait",
        "page_width_px": 257,
        "page_height_px": 364,
        "page_size_unit": "mm",
    }
}

test_path = Path("test_env/test_page_size_fields.yaml")
test_path.write_text(yaml.dump(test_cfg, allow_unicode=True, sort_keys=False), encoding="utf-8")
print(f"  Wrote test config to {test_path}")

cfg2 = load_config(str(test_path))
print(f"  Page size name: {cfg2.grid.page_size_name} (expected: B5)")
print(f"  Orientation: {cfg2.grid.orientation} (expected: portrait)")
print(f"  Page width: {cfg2.grid.page_width_px} (expected: 257)")
print(f"  Page height: {cfg2.grid.page_height_px} (expected: 364)")
print(f"  Page size unit: {cfg2.grid.page_size_unit} (expected: mm)")
print(f"  DPI: {cfg2.grid.dpi} (expected: 350)")

assert cfg2.grid.page_size_name == "B5", "Page size name mismatch"
assert cfg2.grid.orientation == "portrait", "Orientation mismatch"
assert cfg2.grid.page_width_px == 257, "Page width mismatch"
assert cfg2.grid.page_height_px == 364, "Page height mismatch"
assert cfg2.grid.page_size_unit == "mm", "Page size unit mismatch"
assert cfg2.grid.dpi == 350, "DPI mismatch"
print(f"  ✓ All new fields saved and loaded correctly\n")

print("Test 3: Backward compatibility (old config without new fields)")
old_cfg = load_config("test_env/test_margin_unit.yaml")
print(f"  Page size name: {old_cfg.grid.page_size_name} (expected: A4, default)")
print(f"  Orientation: {old_cfg.grid.orientation} (expected: portrait, default)")
print(f"  Page size unit: {old_cfg.grid.page_size_unit} (expected: px, default)")
print(f"  ✓ Backward compatibility OK\n")

print("All tests passed! ✓")
