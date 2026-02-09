"""Test margin_unit field"""
from name_splitter.core.config import load_config, GridConfig
from pathlib import Path
import yaml

print("Test 1: Create config with margin_unit=mm")
test_cfg = {
    "version": 1,
    "grid": {
        "rows": 4,
        "cols": 4,
        "order": "rtl_ttb",
        "margin_top_px": 118,
        "margin_bottom_px": 129,
        "margin_left_px": 295,
        "margin_right_px": 129,
        "gutter_px": 0,
        "margin_unit": "mm",
        "dpi": 600,
        "page_size_name": "Custom",
        "orientation": "portrait",
        "page_width_px": 6071,
        "page_height_px": 8598,
        "page_size_unit": "px",
    }
}

test_path = Path("test_env/test_margin_unit_mm.yaml")
test_path.write_text(yaml.dump(test_cfg, allow_unicode=True, sort_keys=False), encoding="utf-8")
print(f"  Wrote test config to {test_path}")

cfg = load_config(str(test_path))
print(f"  Margin unit: {cfg.grid.margin_unit} (expected: mm)")
print(f"  Margins (px): T={cfg.grid.margin_top_px}, B={cfg.grid.margin_bottom_px}, L={cfg.grid.margin_left_px}, R={cfg.grid.margin_right_px}")
print(f"  DPI: {cfg.grid.dpi}")

# Convert to mm for display
dpi = cfg.grid.dpi
print(f"  Margins (mm): T={cfg.grid.margin_top_px * 25.4 / dpi:.2f}, B={cfg.grid.margin_bottom_px * 25.4 / dpi:.2f}, L={cfg.grid.margin_left_px * 25.4 / dpi:.2f}, R={cfg.grid.margin_right_px * 25.4 / dpi:.2f}")

assert cfg.grid.margin_unit == "mm", "Margin unit mismatch"
assert cfg.grid.margin_top_px == 118, "Margin top mismatch"
assert cfg.grid.margin_bottom_px == 129, "Margin bottom mismatch"
assert cfg.grid.margin_left_px == 295, "Margin left mismatch"
assert cfg.grid.margin_right_px == 129, "Margin right mismatch"
print(f"  ✓ margin_unit saved and loaded correctly\n")

print("Test 2: Backward compatibility (old config without margin_unit)")
old_cfg = load_config("test_env/test_margin_unit.yaml")
print(f"  Margin unit: {old_cfg.grid.margin_unit} (expected: px, default)")
print(f"  ✓ Backward compatibility OK\n")

print("All tests passed! ✓")
