"""Test margin_unit field persistence.

Why: margin_unit フィールド追加時に mm/px 単位の config 保存・読み込みが
     正しく動作することを保証する必要がある。
How: margin_unit='mm' の config を tmp_path に書き出し、再読み込みで値が
     保持されることをアサートする。旧 config の後方互換性も検証する。
"""
from pathlib import Path

import yaml

from name_splitter.core.config import load_config


def test_margin_unit_mm_round_trip(tmp_path: Path) -> None:
    """margin_unit='mm' survives config write-read cycle."""
    config_data = {
        "version": 1,
        "grid": {
            "rows": 4, "cols": 4, "order": "rtl_ttb",
            "margin_top_px": 118, "margin_bottom_px": 129,
            "margin_left_px": 295, "margin_right_px": 129,
            "gutter_px": 0, "margin_unit": "mm", "dpi": 600,
            "page_size_name": "Custom", "orientation": "portrait",
            "page_width_px": 6071, "page_height_px": 8598,
            "page_size_unit": "px",
        },
    }
    config_path = tmp_path / "margin_unit_mm.yaml"
    config_path.write_text(
        yaml.dump(config_data, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    cfg = load_config(str(config_path))
    assert cfg.grid.margin_unit == "mm"
    assert cfg.grid.margin_top_px == 118
    assert cfg.grid.margin_bottom_px == 129
    assert cfg.grid.margin_left_px == 295
    assert cfg.grid.margin_right_px == 129


def test_margin_unit_default_is_px(tmp_path: Path) -> None:
    """Config without margin_unit defaults to px."""
    config_data = {
        "version": 1,
        "grid": {
            "rows": 4, "cols": 4, "order": "rtl_ttb",
            "margin_top_px": 100, "margin_bottom_px": 100,
            "margin_left_px": 100, "margin_right_px": 100,
            "gutter_px": 0,
        },
    }
    config_path = tmp_path / "old_config.yaml"
    config_path.write_text(
        yaml.dump(config_data, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    cfg = load_config(str(config_path))
    assert cfg.grid.margin_unit == "px"
