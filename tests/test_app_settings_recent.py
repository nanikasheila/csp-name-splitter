"""Tests for recent-file tracking in AppSettings (A-2).

Why: The recent-files feature allows quick reuse of previously used
     image and config file paths via dropdown menus.
How: Tests verify add_recent_input/config methods for correct ordering,
     deduplication, max-size cap, and path-existence filtering.
"""
from __future__ import annotations

from pathlib import Path

from name_splitter.app.app_settings import AppSettings


class TestRecentInput:
    """Tests for add_recent_input and recent_inputs list."""

    def test_add_recent_input_prepends(self) -> None:
        """TC-A2-001: New path is prepended to the list."""
        s = AppSettings()
        s.add_recent_input("/a.png")
        s.add_recent_input("/b.png")
        assert s.recent_inputs[0] == "/b.png"
        assert s.recent_inputs[1] == "/a.png"

    def test_add_recent_input_deduplicates(self) -> None:
        """TC-A2-003: Re-adding existing path moves it to front, no dupes."""
        s = AppSettings()
        s.add_recent_input("/a.png")
        s.add_recent_input("/b.png")
        s.add_recent_input("/a.png")
        assert s.recent_inputs == ["/a.png", "/b.png"]

    def test_add_recent_input_max_5_items(self) -> None:
        """TC-A2-004: Adding a 6th item drops the oldest."""
        s = AppSettings()
        for i in range(6):
            s.add_recent_input(f"/{i}.png")
        assert len(s.recent_inputs) == 5
        assert s.recent_inputs[0] == "/5.png"
        assert "/0.png" not in s.recent_inputs

    def test_add_recent_input_exactly_5_no_truncation(self) -> None:
        """TC-A2-005: 5 items are all retained (boundary)."""
        s = AppSettings()
        for i in range(5):
            s.add_recent_input(f"/{i}.png")
        assert len(s.recent_inputs) == 5


class TestRecentConfig:
    """Tests for add_recent_config."""

    def test_add_recent_config_prepends(self) -> None:
        """TC-A2-002: New config path is prepended."""
        s = AppSettings()
        s.add_recent_config("/a.yaml")
        s.add_recent_config("/b.yaml")
        assert s.recent_configs[0] == "/b.yaml"


class TestRecentValidation:
    """Tests for filtering out non-existent paths."""

    def test_filter_nonexistent_paths(self, tmp_path: Path) -> None:
        """TC-A2-006: Non-existent paths are excluded from valid list."""
        real_file = tmp_path / "real.png"
        real_file.touch()
        ghost = str(tmp_path / "ghost.png")

        s = AppSettings()
        s.add_recent_input(str(real_file))
        s.add_recent_input(ghost)

        valid = [p for p in s.recent_inputs if Path(p).exists()]
        assert str(real_file) in valid
        assert ghost not in valid

    def test_all_missing_returns_empty(self) -> None:
        """TC-A2-007: All paths missing → empty valid list."""
        s = AppSettings()
        s.add_recent_input("/nonexistent/a.png")
        s.add_recent_input("/nonexistent/b.png")
        valid = [p for p in s.recent_inputs if Path(p).exists()]
        assert valid == []

    def test_empty_list_returns_empty(self) -> None:
        """TC-A2-008: Empty recent list → empty valid list."""
        s = AppSettings()
        valid = [p for p in s.recent_inputs if Path(p).exists()]
        assert valid == []

    def test_order_preserved_after_filter(self, tmp_path: Path) -> None:
        """TC-A2-009: MRU order preserved after filtering."""
        f1 = tmp_path / "first.png"
        f2 = tmp_path / "second.png"
        f1.touch()
        f2.touch()

        s = AppSettings()
        s.add_recent_input(str(f1))
        s.add_recent_input("/ghost.png")
        s.add_recent_input(str(f2))

        valid = [p for p in s.recent_inputs if Path(p).exists()]
        assert valid == [str(f2), str(f1)]
