"""Tests for Quick Run (last_run_config) in AppSettings (A-3).

Why: Quick Run lets users re-execute the previous split configuration
     on a new image with one click. The last_run_config field must
     persist across app restarts and handle missing/corrupt data safely.
How: Tests verify default state, round-trip persistence, and backward
     compatibility with older settings files.
"""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

from name_splitter.app.app_settings import (
    AppSettings,
    load_app_settings,
    save_app_settings,
)


class TestLastRunConfig:
    """Tests for last_run_config field."""

    def test_default_is_none(self) -> None:
        """TC-A3-001: Default last_run_config is None."""
        s = AppSettings()
        assert s.last_run_config is None

    def test_save_and_load_round_trip(self, tmp_path: Path) -> None:
        """TC-A3-002: last_run_config survives save → load cycle."""
        settings_file = tmp_path / "app_settings.json"

        with patch(
            "name_splitter.app.app_settings._settings_path",
            return_value=settings_file,
        ):
            s = AppSettings()
            s.last_run_config = {"rows": 4, "cols": 4, "dpi": 300}
            save_app_settings(s)

            loaded = load_app_settings()
            assert loaded.last_run_config == {"rows": 4, "cols": 4, "dpi": 300}

    def test_has_config_false_when_none(self) -> None:
        """TC-A3-003: No last_run_config → falsy check."""
        s = AppSettings()
        assert not s.last_run_config

    def test_has_config_true_when_set(self) -> None:
        """TC-A3-004: With config → truthy check."""
        s = AppSettings()
        s.last_run_config = {"rows": 2}
        assert s.last_run_config

    def test_backward_compat_without_field(self, tmp_path: Path) -> None:
        """TC-A3-005: Old JSON without last_run_config loads safely."""
        settings_file = tmp_path / "app_settings.json"
        settings_file.write_text(
            json.dumps({"window_width": 1100}),
            encoding="utf-8",
        )

        with patch(
            "name_splitter.app.app_settings._settings_path",
            return_value=settings_file,
        ):
            loaded = load_app_settings()
            assert loaded.last_run_config is None

    def test_corrupt_last_run_config_loads_safely(self, tmp_path: Path) -> None:
        """TC-A3-006: Non-dict last_run_config doesn't crash load."""
        settings_file = tmp_path / "app_settings.json"
        settings_file.write_text(
            json.dumps({"last_run_config": "not-a-dict"}),
            encoding="utf-8",
        )

        with patch(
            "name_splitter.app.app_settings._settings_path",
            return_value=settings_file,
        ):
            loaded = load_app_settings()
            # Should load without exception; value may be the string
            assert loaded is not None

    def test_nested_data_preserved(self, tmp_path: Path) -> None:
        """TC-A3-007: Nested dict structures survive round-trip."""
        settings_file = tmp_path / "app_settings.json"
        nested = {
            "grid": {"rows": 4, "cols": 4},
            "margins": {"top": 10, "bottom": 10},
        }

        with patch(
            "name_splitter.app.app_settings._settings_path",
            return_value=settings_file,
        ):
            s = AppSettings()
            s.last_run_config = nested
            save_app_settings(s)

            loaded = load_app_settings()
            assert loaded.last_run_config == nested
