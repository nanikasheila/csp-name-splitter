"""Tests for name_splitter.core.job module.

Why: job.py orchestrates image loading, grid computation, and rendering.
     Tests verify the pipeline, cancel logic, and helper functions.
How: Mocks heavy I/O (image_read, render_pages) to test orchestration
     logic in isolation.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from name_splitter.core.config import Config, GridConfig, LimitsConfig, OutputConfig
from name_splitter.core.errors import LimitExceededError
from name_splitter.core.image_read import ImageInfo
from name_splitter.core.job import (
    CancelToken,
    JobResult,
    ProgressEvent,
    _enforce_limits,
    _resolve_out_dir,
    _select_pages,
)


# ------------------------------------------------------------------
# CancelToken
# ------------------------------------------------------------------

class TestCancelToken:
    def test_initial_state_is_not_cancelled(self) -> None:
        token = CancelToken()
        assert token.cancelled is False

    def test_cancel_sets_flag(self) -> None:
        token = CancelToken()
        token.cancel()
        assert token.cancelled is True


# ------------------------------------------------------------------
# ProgressEvent
# ------------------------------------------------------------------

class TestProgressEvent:
    def test_fields(self) -> None:
        event = ProgressEvent(phase="render", done=3, total=10, message="ok")
        assert event.phase == "render"
        assert event.done == 3
        assert event.total == 10
        assert event.message == "ok"

    def test_default_message(self) -> None:
        event = ProgressEvent(phase="load", done=0, total=1)
        assert event.message == ""


# ------------------------------------------------------------------
# _select_pages
# ------------------------------------------------------------------

class TestSelectPages:
    def test_all_pages_when_none(self) -> None:
        result = _select_pages(16, None)
        assert result == list(range(16))

    def test_single_page(self) -> None:
        result = _select_pages(16, 3)
        assert result == [2]

    def test_first_page(self) -> None:
        result = _select_pages(4, 1)
        assert result == [0]

    def test_last_page(self) -> None:
        result = _select_pages(4, 4)
        assert result == [3]

    def test_raises_for_zero(self) -> None:
        with pytest.raises(ValueError, match="must be between"):
            _select_pages(4, 0)

    def test_raises_for_out_of_range(self) -> None:
        with pytest.raises(ValueError, match="must be between"):
            _select_pages(4, 5)


# ------------------------------------------------------------------
# _resolve_out_dir
# ------------------------------------------------------------------

class TestResolveOutDir:
    def _make_cfg(self, out_dir: str = "") -> Config:
        return Config(output=OutputConfig(out_dir=out_dir))

    def test_override_takes_priority(self) -> None:
        cfg = self._make_cfg(out_dir="/from/config")
        result = _resolve_out_dir("input.png", cfg, "/override")
        assert result == Path("/override")

    def test_config_out_dir_used_when_no_override(self) -> None:
        cfg = self._make_cfg(out_dir="/from/config")
        result = _resolve_out_dir("input.png", cfg, None)
        assert result == Path("/from/config")

    def test_derives_from_input_when_no_config(self) -> None:
        cfg = self._make_cfg(out_dir="")
        result = _resolve_out_dir("my_image.png", cfg, None)
        assert result == Path("my_image_pages")


# ------------------------------------------------------------------
# _enforce_limits
# ------------------------------------------------------------------

class TestEnforceLimits:
    def test_within_limits_passes(self) -> None:
        info = ImageInfo(width=1000, height=800)
        cfg = Config(limits=LimitsConfig(max_dim_px=2000))
        _enforce_limits(info, cfg)

    def test_exceeds_width_raises(self) -> None:
        info = ImageInfo(width=3000, height=100)
        cfg = Config(limits=LimitsConfig(max_dim_px=2000))
        with pytest.raises(LimitExceededError, match="exceeds limit"):
            _enforce_limits(info, cfg)

    def test_exceeds_height_raises(self) -> None:
        info = ImageInfo(width=100, height=3000)
        cfg = Config(limits=LimitsConfig(max_dim_px=2000))
        with pytest.raises(LimitExceededError, match="exceeds limit"):
            _enforce_limits(info, cfg)

    def test_exact_limit_passes(self) -> None:
        info = ImageInfo(width=2000, height=2000)
        cfg = Config(limits=LimitsConfig(max_dim_px=2000))
        _enforce_limits(info, cfg)
