"""auto_open_output のテスト。

Why: _auto_open_output は OS に依存する副作用（ファイラー起動）を持つため、
     モックを使って動作と非クラッシュ保証を単体テストする必要がある。
How: GuiHandlers._auto_open_output を MagicMock self で直接呼び出し、
     os.startfile / subprocess.Popen をパッチして観察する。
"""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

from name_splitter.app.app_settings import AppSettings
from name_splitter.app.gui_handlers import GuiHandlers


def _make_handlers() -> GuiHandlers:
    """テスト用の最小限 GuiHandlers インスタンスを生成する。

    Why: GuiHandlers は GUI ウィジェット参照を必要とするが、
         _auto_open_output は self を使わないため MagicMock で代替できる。
    """
    return GuiHandlers.__new__(GuiHandlers)  # type: ignore[return-value]


def test_app_settings_auto_open_default_true() -> None:
    """AppSettings() のデフォルトで auto_open_output が True であること。"""
    settings = AppSettings()
    assert settings.auto_open_output is True


def test_auto_open_output_calls_startfile_on_windows() -> None:
    """_auto_open_output が Windows 環境で os.startfile を呼び出すこと。"""
    handlers = _make_handlers()
    with tempfile.TemporaryDirectory() as tmpdir:
        with (
            patch.object(sys, "platform", "win32"),
            patch("name_splitter.app.gui_handlers.os.startfile", create=True) as mock_startfile,
            patch(
                "name_splitter.app.app_settings.load_app_settings",
                return_value=AppSettings(auto_open_output=True),
            ),
        ):
            GuiHandlers._auto_open_output(handlers, tmpdir)
            mock_startfile.assert_called_once_with(tmpdir)


def test_auto_open_output_skips_nonexistent_dir() -> None:
    """存在しないディレクトリを渡した場合は何もしないこと。

    Why: ジョブが出力先を生成しなかった場合でもクラッシュしてはならない。
    """
    handlers = _make_handlers()
    nonexistent = "/nonexistent/path/that/does/not/exist"
    with (
        patch.object(sys, "platform", "win32"),
        patch("name_splitter.app.gui_handlers.os.startfile", create=True) as mock_startfile,
    ):
        GuiHandlers._auto_open_output(handlers, nonexistent)
        mock_startfile.assert_not_called()


def test_auto_open_output_oserror_does_not_crash() -> None:
    """os.startfile が OSError を発生させても例外が伝播しないこと。

    Why: ファイラーの起動失敗は致命的エラーではなく、
         アプリはそのまま動作し続けるべきである。
    """
    handlers = _make_handlers()
    with tempfile.TemporaryDirectory() as tmpdir:
        with (
            patch.object(sys, "platform", "win32"),
            patch(
                "name_splitter.app.gui_handlers.os.startfile",
                create=True,
                side_effect=OSError("mock error"),
            ),
            patch(
                "name_splitter.app.app_settings.load_app_settings",
                return_value=AppSettings(auto_open_output=True),
            ),
        ):
            # 例外が外に出ないことを確認（クラッシュしない）
            GuiHandlers._auto_open_output(handlers, tmpdir)  # should not raise


def test_auto_open_output_disabled_by_setting() -> None:
    """auto_open_output=False の場合は os.startfile を呼ばないこと。

    Why: ユーザーが設定で自動オープンを無効にしている場合は何もしない。
    """
    handlers = _make_handlers()
    with tempfile.TemporaryDirectory() as tmpdir:
        with (
            patch.object(sys, "platform", "win32"),
            patch("name_splitter.app.gui_handlers.os.startfile", create=True) as mock_startfile,
            patch(
                "name_splitter.app.app_settings.load_app_settings",
                return_value=AppSettings(auto_open_output=False),
            ),
        ):
            GuiHandlers._auto_open_output(handlers, tmpdir)
            mock_startfile.assert_not_called()
