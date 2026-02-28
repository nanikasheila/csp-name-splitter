"""Test page_size_name, orientation, page_size_unit fields.

Why: ページサイズプリセット（A4/B5等）と向き・単位フィールドの追加時に
     config の読み書きが正しく動作することを保証する必要がある。
How: GridConfig を直接構築して属性を検証し、config ファイル経由の往復も
     テストする。旧 config の後方互換性でデフォルト値を確認する。
"""
from pathlib import Path

import yaml

from name_splitter.core.config import GridConfig, load_config


def test_grid_config_page_size_fields() -> None:
    """GridConfig accepts page_size_name / orientation / page_size_unit."""
    cfg = GridConfig(
        rows=4, cols=4, order="rtl_ttb",
        margin_top_px=50, margin_bottom_px=50,
        margin_left_px=50, margin_right_px=50,
        gutter_px=10, dpi=600,
        page_size_name="A4", orientation="landscape",
        page_width_px=3508, page_height_px=2480,
        page_size_unit="mm",
    )
    assert cfg.page_size_name == "A4"
    assert cfg.orientation == "landscape"
    assert cfg.page_size_unit == "mm"
    assert cfg.page_width_px == 3508
    assert cfg.page_height_px == 2480


def test_page_size_fields_round_trip(tmp_path: Path) -> None:
    """Page size fields survive config write-read cycle."""
    config_data = {
        "version": 1,
        "grid": {
            "rows": 3, "cols": 3, "order": "ltr_ttb",
            "margin_top_px": 30, "margin_bottom_px": 30,
            "margin_left_px": 30, "margin_right_px": 30,
            "gutter_px": 5, "dpi": 350,
            "page_size_name": "B5", "orientation": "portrait",
            "page_width_px": 257, "page_height_px": 364,
            "page_size_unit": "mm",
        },
    }
    config_path = tmp_path / "page_size.yaml"
    config_path.write_text(
        yaml.dump(config_data, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    cfg = load_config(str(config_path))
    assert cfg.grid.page_size_name == "B5"
    assert cfg.grid.orientation == "portrait"
    assert cfg.grid.page_width_px == 257
    assert cfg.grid.page_height_px == 364
    assert cfg.grid.page_size_unit == "mm"
    assert cfg.grid.dpi == 350


def test_page_size_backward_compatibility(tmp_path: Path) -> None:
    """Old config without page size fields uses defaults."""
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
    assert cfg.grid.page_size_name == "A4"
    assert cfg.grid.orientation == "portrait"
    assert cfg.grid.page_size_unit == "px"
