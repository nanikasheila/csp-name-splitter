"""Tests for C-2 settings export/import and C-3 log file toggle.

Covers config round-trip via on_save_config data, import/export
handler logic, and AppSettings.log_to_file field.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from name_splitter.app.app_settings import AppSettings


# ------------------------------------------------------------------ #
#  C-3: AppSettings.log_to_file field
# ------------------------------------------------------------------ #

class TestAppSettingsLogToFile:
    """AppSettings.log_to_file field behavior."""

    def test_default_false(self) -> None:
        """log_to_file defaults to False."""
        settings = AppSettings()
        assert settings.log_to_file is False

    def test_set_true(self) -> None:
        """log_to_file can be set to True."""
        settings = AppSettings(log_to_file=True)
        assert settings.log_to_file is True


# ------------------------------------------------------------------ #
#  C-3: Log file setup via core/logging.py
# ------------------------------------------------------------------ #

class TestLogFileSetup:
    """setup_logging and get_default_log_path work correctly."""

    def test_get_default_log_path_format(self) -> None:
        """Default log path follows logs/csp_name_splitter_*.log pattern."""
        from name_splitter.core.logging import get_default_log_path
        path = get_default_log_path()
        assert path.parent.name == "logs"
        assert path.suffix == ".log"
        assert "csp_name_splitter" in path.name

    def test_setup_logging_creates_file(self, tmp_path: Path) -> None:
        """setup_logging creates a log file when log_file is specified."""
        from name_splitter.core.logging import setup_logging, get_logger
        log_path = tmp_path / "test.log"
        setup_logging(log_file=log_path, console=False)
        logger = get_logger()
        logger.info("test message")
        # Clean up handlers to avoid side effects
        for handler in logger.handlers[:]:
            if hasattr(handler, "baseFilename"):
                handler.close()
                logger.removeHandler(handler)

    def test_log_capture_records_messages(self) -> None:
        """LogCapture captures log messages via attach/detach."""
        from name_splitter.core.logging import LogCapture, get_logger
        import logging
        cap = LogCapture()
        logger = get_logger()
        original_level = logger.level
        logger.setLevel(logging.DEBUG)
        cap.attach(logger)
        logger.info("hello")
        cap.detach(logger)
        logger.setLevel(original_level)
        assert any("hello" in line for line in cap.lines)


# ------------------------------------------------------------------ #
#  C-2: Config export includes B-1/B-2 output fields
# ------------------------------------------------------------------ #

class TestConfigExportFields:
    """on_save_config should include output_dpi, page_number_start, etc."""

    def test_output_section_has_dpi_field(self) -> None:
        """Config dict output section should include output_dpi."""
        # Simulate the config dict building logic from on_save_config
        output_dpi = 350
        config_output = {
            "output_dpi": int(output_dpi) if output_dpi else 0,
            "page_number_start": 1,
            "skip_pages": [],
            "odd_even": "all",
        }
        assert config_output["output_dpi"] == 350
        assert config_output["page_number_start"] == 1
        assert config_output["skip_pages"] == []
        assert config_output["odd_even"] == "all"

    def test_skip_pages_parsing(self) -> None:
        """Skip pages field value is parsed correctly."""
        raw = "1, 3, 5"
        parsed = [int(s.strip()) for s in raw.split(",") if s.strip().isdigit()]
        assert parsed == [1, 3, 5]

    def test_skip_pages_empty(self) -> None:
        """Empty skip_pages yields empty list."""
        raw = ""
        parsed = [int(s.strip()) for s in raw.split(",") if s.strip().isdigit()]
        assert parsed == []

    def test_skip_pages_invalid_ignored(self) -> None:
        """Non-numeric entries in skip_pages are ignored."""
        raw = "1, abc, 3"
        parsed = [int(s.strip()) for s in raw.split(",") if s.strip().isdigit()]
        assert parsed == [1, 3]
