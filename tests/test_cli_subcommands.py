"""Tests for CLI subcommands: template and batch (A-4).

Why: The CLI must support template generation and batch processing
     via subcommands while maintaining backward compatibility with
     the original positional-argument image-split interface.
How: Tests exercise argument parsing, subcommand dispatch, and
     backward compatibility. Core operations are mocked to isolate
     CLI logic from I/O.
"""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from name_splitter.app.cli import (
    _build_subcommand_parser,
    build_parser,
    main,
)


class TestTemplateSubcommand:
    """Tests for the 'template' CLI subcommand."""

    def test_template_subcommand_parses(self) -> None:
        """TC-A4-001: 'template' is recognized as a subcommand."""
        parser = _build_subcommand_parser()
        args = parser.parse_args(["template"])
        assert args.subcommand == "template"

    def test_template_output_path_option(self) -> None:
        """TC-A4-002: --output sets output_path."""
        parser = _build_subcommand_parser()
        args = parser.parse_args(["template", "--output", "out.png"])
        assert args.output_path == "out.png"

    def test_template_page_size_option(self) -> None:
        """TC-A4-003: --page-size is parsed correctly."""
        parser = _build_subcommand_parser()
        args = parser.parse_args(["template", "--page-size", "B5"])
        assert args.page_size == "B5"

    def test_template_rows_cols_options(self) -> None:
        """TC-A4-004: --rows and --cols parse as integers."""
        parser = _build_subcommand_parser()
        args = parser.parse_args(["template", "--rows", "3", "--cols", "2"])
        assert args.rows == 3
        assert args.cols == 2

    def test_template_help_exits_0(self) -> None:
        """TC-A4-017: template --help exits with code 0."""
        parser = _build_subcommand_parser()
        with pytest.raises(SystemExit) as exc_info:
            parser.parse_args(["template", "--help"])
        assert exc_info.value.code == 0

    def test_template_zero_rows_returns_2(self) -> None:
        """Validation: rows=0 returns exit code 2."""
        result = main(["template", "--rows", "0", "--cols", "4"])
        assert result == 2

    def test_template_negative_cols_returns_2(self) -> None:
        """Validation: cols=-1 returns exit code 2."""
        result = main(["template", "--rows", "4", "--cols", "-1"])
        assert result == 2


class TestBatchSubcommand:
    """Tests for the 'batch' CLI subcommand."""

    def test_batch_subcommand_parses(self) -> None:
        """TC-A4-007: 'batch' with input_dir is recognized."""
        parser = _build_subcommand_parser()
        args = parser.parse_args(["batch", "/some/dir"])
        assert args.subcommand == "batch"
        assert args.input_dir == "/some/dir"

    def test_batch_missing_dir_exits(self) -> None:
        """TC-A4-008: batch without input_dir exits with error."""
        parser = _build_subcommand_parser()
        with pytest.raises(SystemExit) as exc_info:
            parser.parse_args(["batch"])
        assert exc_info.value.code == 2

    def test_batch_nonexistent_dir_returns_error(self, tmp_path: Path) -> None:
        """TC-A4-009: Non-existent directory returns exit code 2."""
        fake_dir = str(tmp_path / "nope")
        result = main(["batch", fake_dir])
        assert result == 2

    def test_batch_help_exits_0(self) -> None:
        """TC-A4-018: batch --help exits with code 0."""
        parser = _build_subcommand_parser()
        with pytest.raises(SystemExit) as exc_info:
            parser.parse_args(["batch", "--help"])
        assert exc_info.value.code == 0


class TestBackwardCompatibility:
    """Tests for backward compatibility with the original CLI interface."""

    def test_no_subcommand_positional_arg_still_works(self) -> None:
        """TC-A4-014: image.png without subcommand parses as input_image."""
        parser = build_parser()
        args = parser.parse_args(["image.png"])
        assert args.input_image == "image.png"

    def test_no_args_returns_error(self) -> None:
        """TC-A4-015: No arguments returns exit code 2."""
        result = main([])
        assert result == 2

    def test_gui_flag_still_parsed(self) -> None:
        """TC-A4-003: --gui flag is still recognized."""
        parser = build_parser()
        args = parser.parse_args(["--gui"])
        assert args.gui is True

    def test_help_exits_0(self) -> None:
        """TC-A4-016: --help exits with code 0."""
        with pytest.raises(SystemExit) as exc_info:
            build_parser().parse_args(["--help"])
        assert exc_info.value.code == 0
