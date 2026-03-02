"""first_run フィールドのテスト。

Why: 初回起動ガイダンス機能が正しく動作するためには first_run フラグの
     デフォルト値・設定・永続化が保証されなければならない。
How: AppSettings dataclass の単体テストと、save/load の統合テストで検証する。
"""
from __future__ import annotations

import json
import tempfile
from pathlib import Path
from unittest.mock import patch

from name_splitter.app.app_settings import AppSettings, load_app_settings, save_app_settings


def test_app_settings_first_run_default_true() -> None:
    """AppSettings() のデフォルトで first_run が True であること。"""
    settings = AppSettings()
    assert settings.first_run is True


def test_app_settings_first_run_can_be_set_false() -> None:
    """AppSettings(first_run=False) で first_run が False になること。"""
    settings = AppSettings(first_run=False)
    assert settings.first_run is False


def test_load_app_settings_missing_first_run_defaults_true() -> None:
    """first_run キーなしの JSON から読み込んでも first_run == True になること。

    Why: 既存ユーザーの設定ファイルには first_run が存在しない。
         アップグレード後に初回起動ガイダンスを表示しないよう
         デフォルト True でフォールバックすることを確認する。
    """
    # first_run を含まない設定 JSON を用意
    data_without_first_run = {
        "window_width": 1200,
        "window_height": 850,
        "theme_mode": "light",
        "recent_configs": [],
        "recent_inputs": [],
        "auto_open_output": True,
    }
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".json", delete=False, encoding="utf-8"
    ) as f:
        json.dump(data_without_first_run, f)
        tmp_path = Path(f.name)

    try:
        with patch("name_splitter.app.app_settings._settings_path", return_value=tmp_path):
            settings = load_app_settings()
        assert settings.first_run is True
    finally:
        tmp_path.unlink(missing_ok=True)


def test_save_and_load_preserves_first_run() -> None:
    """save → load で first_run=False が保持されること。

    Why: first_run を False に更新して保存した後、次回起動時に
         再び True に戻らないことを保証する。
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir) / "app_settings.json"

        with patch("name_splitter.app.app_settings._settings_path", return_value=tmp_path):
            settings = AppSettings(first_run=False)
            save_app_settings(settings)
            loaded = load_app_settings()

        assert loaded.first_run is False
