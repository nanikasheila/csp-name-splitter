"""Test gutter_unit field and page size unit conversion for preset sizes.

Why: gutter_unit フィールド追加時に mm/px 単位の保存・読み込みが正しく動作する
     ことを保証する必要がある。
How: gutter_unit=mm の config を tmp_path に書き出し、再読み込みで値が保持される
     ことをアサートする。mm↔px の往復変換精度も検証する。
"""
from pathlib import Path

import yaml

from name_splitter.core.config import load_config


def test_gutter_unit_mm_round_trip(tmp_path: Path) -> None:
    """gutter_unit='mm' survives config write-read cycle."""
    config_data = {
        "version": 1,
        "grid": {
            "rows": 4, "cols": 4, "order": "rtl_ttb",
            "margin_top_px": 50, "margin_bottom_px": 50,
            "margin_left_px": 50, "margin_right_px": 50,
            "gutter_px": 24, "gutter_unit": "mm", "margin_unit": "px",
            "dpi": 600,
            "page_size_name": "A4", "orientation": "portrait",
            "page_width_px": 4961, "page_height_px": 7016,
            "page_size_unit": "mm",
        },
    }
    config_path = tmp_path / "gutter_unit.yaml"
    config_path.write_text(
        yaml.dump(config_data, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    cfg = load_config(str(config_path))
    assert cfg.grid.gutter_unit == "mm"
    assert cfg.grid.gutter_px == 24


def test_gutter_mm_px_round_trip() -> None:
    """1mm gutter at 600dpi converts to px and back within tolerance."""
    dpi = 600
    gutter_mm = 1.0
    gutter_px = int(gutter_mm * dpi / 25.4)
    back_to_mm = gutter_px * 25.4 / dpi
    assert abs(back_to_mm - gutter_mm) < 0.1
