"""Tests for preset management in AppSettings (A-1).

Why: Presets allow users to save and reuse named configurations.
     These tests verify CRUD operations, persistence, and backward
     compatibility with older settings files that lack the presets field.
How: Tests exercise AppSettings methods directly with in-memory
     instances and round-trip through save/load with tmp_path patching.
"""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from name_splitter.app.app_settings import (
    AppSettings,
    load_app_settings,
    save_app_settings,
)


class TestPresetSave:
    """Tests for save_preset."""

    def test_save_preset_stores_named_entry(self) -> None:
        """TC-A1-001: Saving a preset adds it to the presets list."""
        settings = AppSettings()
        settings.save_preset("My Preset", {"rows": 4, "cols": 4})
        assert len(settings.presets) == 1
        assert settings.presets[0]["name"] == "My Preset"

    def test_save_multiple_presets_list_grows(self) -> None:
        """TC-A1-010: Saving 3 different presets results in list length 3."""
        settings = AppSettings()
        for i in range(3):
            settings.save_preset(f"Preset {i}", {"rows": i + 1})
        assert len(settings.presets) == 3

    def test_save_preset_same_name_overwrites(self) -> None:
        """TC-A1-004: Saving with same name overwrites (no duplicates)."""
        settings = AppSettings()
        settings.save_preset("P", {"rows": 2})
        settings.save_preset("P", {"rows": 4})
        names = [p["name"] for p in settings.presets]
        assert names.count("P") == 1
        assert settings.get_preset("P") == {"rows": 4}


class TestPresetLoad:
    """Tests for get_preset and get_preset_names."""

    def test_load_preset_returns_saved_data(self) -> None:
        """TC-A1-002: get_preset returns the config dict saved earlier."""
        settings = AppSettings()
        data = {"rows": 3, "cols": 2, "page_size": "B5"}
        settings.save_preset("Doujin B5", data)
        loaded = settings.get_preset("Doujin B5")
        assert loaded == data

    def test_load_nonexistent_preset_returns_none(self) -> None:
        """TC-A1-006: get_preset for missing name returns None."""
        settings = AppSettings()
        assert settings.get_preset("nope") is None

    def test_get_preset_names_returns_ordered_list(self) -> None:
        """Preset names are returned in insertion order."""
        settings = AppSettings()
        settings.save_preset("Alpha", {"a": 1})
        settings.save_preset("Beta", {"b": 2})
        assert settings.get_preset_names() == ["Alpha", "Beta"]


class TestPresetDelete:
    """Tests for delete_preset."""

    def test_delete_preset_removes_entry(self) -> None:
        """TC-A1-003: Deleting an existing preset removes it."""
        settings = AppSettings()
        settings.save_preset("X", {"rows": 1})
        settings.delete_preset("X")
        assert settings.get_preset("X") is None
        assert len(settings.presets) == 0

    def test_delete_preset_when_empty_is_safe(self) -> None:
        """TC-A1-007: Deleting from empty presets raises no error."""
        settings = AppSettings()
        settings.delete_preset("ghost")  # no-op, no exception

    def test_delete_preset_nonexistent_name_is_safe(self) -> None:
        """TC-A1-008: Deleting non-existent name from non-empty list is safe."""
        settings = AppSettings()
        settings.save_preset("A", {"rows": 1})
        settings.delete_preset("B")
        assert len(settings.presets) == 1


class TestPresetPersistence:
    """Tests for preset round-trip through save/load."""

    def test_preset_round_trip_via_save_load(self, tmp_path: Path) -> None:
        """TC-A1-011: Presets survive save → load cycle."""
        settings_file = tmp_path / "app_settings.json"

        with patch(
            "name_splitter.app.app_settings._settings_path",
            return_value=settings_file,
        ):
            s = AppSettings()
            s.save_preset("RT", {"rows": 5, "cols": 3})
            save_app_settings(s)

            loaded = load_app_settings()
            assert loaded.get_preset_names() == ["RT"]
            assert loaded.get_preset("RT") == {"rows": 5, "cols": 3}

    def test_load_without_presets_field_uses_default(self, tmp_path: Path) -> None:
        """TC-A1-009: Old settings JSON without presets field loads fine."""
        settings_file = tmp_path / "app_settings.json"
        settings_file.write_text(
            json.dumps({"window_width": 1000, "theme_mode": "dark"}),
            encoding="utf-8",
        )

        with patch(
            "name_splitter.app.app_settings._settings_path",
            return_value=settings_file,
        ):
            loaded = load_app_settings()
            assert loaded.presets == []
            assert loaded.window_width == 1000
