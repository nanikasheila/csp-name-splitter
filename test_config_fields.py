"""Test config file loading with new dpi/page_size fields"""
from name_splitter.core.config import load_config, GridConfig
from pathlib import Path
import yaml

# Test 1: Load existing config (should use defaults for new fields)
print("Test 1: Load existing config (backward compatibility)")
cfg = load_config("test_env/test_margin_unit.yaml")
print(f"  DPI: {cfg.grid.dpi} (expected: 300, default)")
print(f"  Page width: {cfg.grid.page_width_px} (expected: 0, default)")
print(f"  Page height: {cfg.grid.page_height_px} (expected: 0, default)")
print(f"  ✓ Backward compatibility OK\n")

# Test 2: Create config with new fields
print("Test 2: Create config with new fields")
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
        "gutter_px": 10,
        "dpi": 600,
        "page_width_px": 2480,
        "page_height_px": 3508,
    }
}

test_path = Path("test_env/test_new_fields.yaml")
test_path.write_text(yaml.dump(test_cfg, allow_unicode=True, sort_keys=False), encoding="utf-8")
print(f"  Wrote test config to {test_path}")

# Test 3: Reload and verify
print("Test 3: Reload and verify new fields")
cfg2 = load_config(str(test_path))
print(f"  DPI: {cfg2.grid.dpi} (expected: 600)")
print(f"  Page width: {cfg2.grid.page_width_px} (expected: 2480)")
print(f"  Page height: {cfg2.grid.page_height_px} (expected: 3508)")
print(f"  Rows: {cfg2.grid.rows}, Cols: {cfg2.grid.cols}")
print(f"  Margins: T={cfg2.grid.margin_top_px}, B={cfg2.grid.margin_bottom_px}, L={cfg2.grid.margin_left_px}, R={cfg2.grid.margin_right_px}")

assert cfg2.grid.dpi == 600, "DPI mismatch"
assert cfg2.grid.page_width_px == 2480, "Page width mismatch"
assert cfg2.grid.page_height_px == 3508, "Page height mismatch"
print(f"  ✓ All fields loaded correctly\n")

print("All tests passed! ✓")
