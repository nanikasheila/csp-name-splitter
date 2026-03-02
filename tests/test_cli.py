"""Tests for name_splitter.app.cli module.

Why: cli.py is the main entry point. Tests verify argument parsing,
     error handling, and exit codes without running actual image
     processing.
How: Tests build_parser directly and exercise main() with mocked
     run_job to avoid I/O.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from name_splitter.app.cli import build_parser, main


# ------------------------------------------------------------------
# build_parser
# ------------------------------------------------------------------

class TestBuildParser:
    def test_input_image_positional(self) -> None:
        parser = build_parser()
        args = parser.parse_args(["image.png"])
        assert args.input_image == "image.png"

    def test_config_option(self) -> None:
        parser = build_parser()
        args = parser.parse_args(["img.png", "--config", "c.yaml"])
        assert args.config_path == "c.yaml"

    def test_out_dir_option(self) -> None:
        parser = build_parser()
        args = parser.parse_args(["img.png", "--out-dir", "./out"])
        assert args.out_dir == "./out"

    def test_page_option(self) -> None:
        parser = build_parser()
        args = parser.parse_args(["img.png", "--page", "5"])
        assert args.test_page == 5

    def test_pdf_flag(self) -> None:
        parser = build_parser()
        args = parser.parse_args(["img.png", "--pdf"])
        assert args.pdf is True

    def test_gui_flag(self) -> None:
        parser = build_parser()
        args = parser.parse_args(["--gui"])
        assert args.gui is True

    def test_no_args(self) -> None:
        parser = build_parser()
        args = parser.parse_args([])
        assert args.input_image is None
        assert args.gui is False


# ------------------------------------------------------------------
# main() exit codes
# ------------------------------------------------------------------

class TestMainExitCodes:
    def test_no_input_image_returns_2(self) -> None:
        # Why: No input image and no config → error exit
        code = main([])
        assert code == 2

    def test_missing_image_returns_2(self, tmp_path: Path) -> None:
        code = main([str(tmp_path / "nonexistent.png")])
        assert code == 2

    def test_bad_config_returns_2(self, tmp_path: Path) -> None:
        bad_cfg = tmp_path / "bad.yaml"
        bad_cfg.write_text("version: 999\n", encoding="utf-8")
        img = tmp_path / "img.png"
        img.write_bytes(b"")
        code = main(["--config", str(bad_cfg), str(img)])
        assert code == 2

    @patch("name_splitter.app.cli.run_job")
    def test_successful_run_returns_0(
        self, mock_run_job: MagicMock, tmp_path: Path
    ) -> None:
        # Why: When run_job succeeds, main should return 0
        from name_splitter.core.render import RenderPlan

        img = tmp_path / "img.png"
        # Create a valid minimal PNG
        from PIL import Image
        Image.new("RGB", (4, 4)).save(img)

        plan = RenderPlan(out_dir=tmp_path, manifest_path=tmp_path / "plan.yaml")
        mock_run_job.return_value = MagicMock(
            plan=plan, page_count=1, pdf_path=None
        )
        code = main([str(img)])
        assert code == 0
        mock_run_job.assert_called_once()

    @patch("name_splitter.app.cli.run_job")
    def test_runtime_error_returns_1(
        self, mock_run_job: MagicMock, tmp_path: Path
    ) -> None:
        from PIL import Image

        img = tmp_path / "img.png"
        Image.new("RGB", (4, 4)).save(img)

        mock_run_job.side_effect = RuntimeError("Job failed")
        code = main([str(img)])
        assert code == 1
