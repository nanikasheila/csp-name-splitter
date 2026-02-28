"""Test config file loading with new dpi/page_size fields.

Why: Config に dpi/page_width_px/page_height_px を追加した際の後方互換性と
     往復読み書きの正当性を確認する必要がある。
How: 既存 config の読み込みでデフォルト値を検証し、新フィールド付き config の
     書き込み→再読み込みで値が保持されることをアサートする。
"""
from pathlib import Path

import yaml

from name_splitter.core.config import load_config


def test_backward_compatibility_defaults(tmp_path: Path) -> None:
    """Existing config without new fields uses default values."""
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
    assert cfg.grid.dpi == 300
    assert cfg.grid.page_width_px == 0
    assert cfg.grid.page_height_px == 0


def test_new_fields_round_trip(tmp_path: Path) -> None:
    """Config with dpi/page dimensions survives write-read cycle."""
    config_data = {
        "version": 1,
        "grid": {
            "rows": 4, "cols": 4, "order": "rtl_ttb",
            "margin_top_px": 50, "margin_bottom_px": 50,
            "margin_left_px": 50, "margin_right_px": 50,
            "gutter_px": 10, "dpi": 600,
            "page_width_px": 2480, "page_height_px": 3508,
        },
    }
    config_path = tmp_path / "new_fields.yaml"
    config_path.write_text(
        yaml.dump(config_data, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    cfg = load_config(str(config_path))
    assert cfg.grid.dpi == 600
    assert cfg.grid.page_width_px == 2480
    assert cfg.grid.page_height_px == 3508
