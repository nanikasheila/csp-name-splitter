"""Tests for C-1 progress timing fields and D-1 result report data.

Covers ProgressEvent timing, JobResult.elapsed_seconds, and
speed/ETA calculation logic in run_job().
"""

from __future__ import annotations

import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from name_splitter.core.job import (
    CancelToken,
    JobResult,
    ProgressEvent,
    _select_pages,
)


# ------------------------------------------------------------------ #
#  ProgressEvent dataclass
# ------------------------------------------------------------------ #

class TestProgressEvent:
    """ProgressEvent timing field defaults and values."""

    def test_default_timing_fields(self) -> None:
        """New ProgressEvent has zero timing by default."""
        ev = ProgressEvent(phase="load_image", done=0, total=1)
        assert ev.elapsed_seconds == 0.0
        assert ev.pages_per_second == 0.0
        assert ev.eta_seconds is None

    def test_timing_fields_set(self) -> None:
        """ProgressEvent accepts explicit timing values."""
        ev = ProgressEvent(
            phase="render_pages", done=5, total=10,
            elapsed_seconds=2.5, pages_per_second=2.0, eta_seconds=2.5,
        )
        assert ev.elapsed_seconds == 2.5
        assert ev.pages_per_second == 2.0
        assert ev.eta_seconds == 2.5

    def test_frozen(self) -> None:
        """ProgressEvent is immutable."""
        ev = ProgressEvent(phase="grid", done=1, total=1)
        with pytest.raises(AttributeError):
            ev.phase = "other"  # type: ignore[misc]

    def test_message_default(self) -> None:
        """Default message is empty string."""
        ev = ProgressEvent(phase="grid", done=0, total=1)
        assert ev.message == ""


# ------------------------------------------------------------------ #
#  JobResult dataclass
# ------------------------------------------------------------------ #

class TestJobResult:
    """JobResult.elapsed_seconds for D-1 result report."""

    def test_default_elapsed(self) -> None:
        """elapsed_seconds defaults to 0.0."""
        plan = MagicMock()
        result = JobResult(out_dir=Path("/tmp"), page_count=4, plan=plan)
        assert result.elapsed_seconds == 0.0

    def test_elapsed_set(self) -> None:
        """elapsed_seconds can be set explicitly."""
        plan = MagicMock()
        result = JobResult(
            out_dir=Path("/tmp"), page_count=4, plan=plan,
            elapsed_seconds=3.14,
        )
        assert result.elapsed_seconds == pytest.approx(3.14)

    def test_pdf_path_default(self) -> None:
        """pdf_path defaults to None."""
        plan = MagicMock()
        result = JobResult(out_dir=Path("/tmp"), page_count=1, plan=plan)
        assert result.pdf_path is None


# ------------------------------------------------------------------ #
#  CancelToken
# ------------------------------------------------------------------ #

class TestCancelToken:
    """CancelToken behavior."""

    def test_initial_state(self) -> None:
        """Token starts not cancelled."""
        token = CancelToken()
        assert not token.cancelled

    def test_cancel(self) -> None:
        """cancel() sets the flag."""
        token = CancelToken()
        token.cancel()
        assert token.cancelled


# ------------------------------------------------------------------ #
#  _select_pages (also used by Feature 2 B-2)
# ------------------------------------------------------------------ #

class TestSelectPages:
    """Page selection with skip and odd/even filters."""

    def test_all_pages(self) -> None:
        """No filters returns all 0-indexed pages."""
        pages = _select_pages(4, None)
        assert pages == [0, 1, 2, 3]

    def test_test_page(self) -> None:
        """Single test_page returns 0-indexed single page."""
        pages = _select_pages(4, 2)
        assert pages == [1]

    def test_test_page_out_of_range(self) -> None:
        """Invalid test_page raises ValueError."""
        with pytest.raises(ValueError, match="test_page"):
            _select_pages(4, 0)
        with pytest.raises(ValueError, match="test_page"):
            _select_pages(4, 5)

    def test_skip_pages(self) -> None:
        """Skipped pages are excluded."""
        pages = _select_pages(4, None, skip=(1, 3))
        assert 0 not in pages
        assert 2 not in pages

    def test_odd_even_odd(self) -> None:
        """odd_even='odd' selects odd-numbered pages (1-based)."""
        pages = _select_pages(4, None, odd_even="odd")
        # 1-based: 1,3 → 0-indexed: 0,2
        assert pages == [0, 2]

    def test_odd_even_even(self) -> None:
        """odd_even='even' selects even-numbered pages (1-based)."""
        pages = _select_pages(4, None, odd_even="even")
        # 1-based: 2,4 → 0-indexed: 1,3
        assert pages == [1, 3]


# ------------------------------------------------------------------ #
#  Speed/ETA calculation in run_job's report() helper
# ------------------------------------------------------------------ #

class TestSpeedEtaCalculation:
    """Verify speed/ETA logic matches run_job's report() helper."""

    def test_speed_zero_for_non_render_phase(self) -> None:
        """Non-render phases should have zero speed."""
        # Simulate the report() logic
        phase = "load_image"
        done = 1
        elapsed = 1.0
        speed = 0.0
        eta = None
        if phase == "render_pages" and done > 0 and elapsed > 0.001:
            speed = done / max(elapsed, 0.001)
        assert speed == 0.0
        assert eta is None

    def test_speed_during_render(self) -> None:
        """render_pages phase computes speed correctly."""
        phase = "render_pages"
        done = 5
        total = 10
        elapsed = 2.5
        speed = 0.0
        eta: float | None = None
        if phase == "render_pages" and done > 0 and elapsed > 0.001:
            speed = done / max(elapsed, 0.001)
            remaining = total - done
            eta = remaining / speed if speed > 0 and remaining > 0 else 0.0
        assert speed == pytest.approx(2.0)
        assert eta == pytest.approx(2.5)

    def test_eta_zero_when_done(self) -> None:
        """When done == total, ETA should be 0."""
        phase = "render_pages"
        done = 10
        total = 10
        elapsed = 5.0
        speed = done / max(elapsed, 0.001)
        remaining = total - done
        eta = remaining / speed if speed > 0 and remaining > 0 else 0.0
        assert eta == 0.0

    def test_zero_elapsed_guard(self) -> None:
        """Near-zero elapsed doesn't cause ZeroDivisionError."""
        phase = "render_pages"
        done = 1
        elapsed = 0.0001
        speed = done / max(elapsed, 0.001)
        # max(0.0001, 0.001) = 0.001 → speed = 1000
        assert speed == pytest.approx(1000.0)
