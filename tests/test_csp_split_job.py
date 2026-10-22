"""Tests for the shared split job and the GUI tab's controller (no Flet needed)."""
from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
import sqlite3
from types import SimpleNamespace

import pytest

from csp_fixtures import build_cmc
from test_csp_split_write import _digest, sheet_path, template_path  # noqa: F401 (fixtures)

from name_splitter.app.gui_csp import CspSplitController, CspSplitFields
from name_splitter.csp.split_job import SplitOptions, find_cmc_template, prepare_split, run_split


def _story_index(work: Path) -> int:
    with sqlite3.connect(work) as database:
        return int(database.execute("SELECT ComicStoryStoryIndex FROM Project").fetchone()[0])


def test_prepare_split_checks_inputs(tmp_path: Path, sheet_path: Path, template_path: Path) -> None:
    out = tmp_path / "out"
    with pytest.raises(ValueError):
        prepare_split(SplitOptions(sheet_path, template_path, out, fit="nope"))
    with pytest.raises(FileNotFoundError):
        prepare_split(SplitOptions(tmp_path / "missing.clip", template_path, out))
    with pytest.raises(ValueError):  # writing next to the inputs could overwrite them
        prepare_split(SplitOptions(sheet_path, template_path, sheet_path.parent))
    with pytest.raises(ValueError):  # a work needs a template .cmc
        prepare_split(SplitOptions(sheet_path, template_path, out, cmc_name="第1話"))
    prepared = prepare_split(SplitOptions(sheet_path, template_path, out, fit="cell"))
    assert len(prepared.plan.pages) == 4
    assert not out.exists()  # preparing writes nothing


def test_run_split_reports_progress_and_cancels(tmp_path: Path, sheet_path: Path, template_path: Path) -> None:
    build_cmc(sheet_path.parent / "name.cmc", ["sheet.clip"])
    assert find_cmc_template(sheet_path) == sheet_path.parent / "name.cmc"
    before = {path: _digest(path) for path in (sheet_path, template_path)}
    prepared = prepare_split(SplitOptions(sheet_path, template_path, tmp_path / "work", cmc_name="第1話",
                                          fit="cell", story_index=2))
    seen: list[tuple[int, int, str]] = []
    result = run_split(prepared, on_page=lambda done, total, path: seen.append((done, total, path.name)))
    assert seen == [(n, 4, f"page{n:04d}.clip") for n in range(1, 5)]
    assert result.cmc == tmp_path / "work" / "第1話.cmc"
    assert _story_index(result.cmc) == 2
    assert {path: _digest(path) for path in before} == before

    stopped = run_split(prepare_split(SplitOptions(sheet_path, template_path, tmp_path / "stop", fit="cell")),
                        on_page=lambda *_: None, cancelled=lambda: len(list((tmp_path / "stop").glob("*.clip"))) >= 1)
    assert stopped.cancelled and len(stopped.pages) == 1 and stopped.cmc is None


class FakeUi:
    def __init__(self) -> None:
        self.logs: list[str] = []
        self.status = ""
        self.progress: tuple[int, int] | None = None
        self.preview: bytes | None = None

    def add_log(self, message: str) -> None:
        self.logs.append(message)

    def set_status(self, message: str) -> None:
        self.status = message

    def set_progress(self, done: int, total: int) -> None:
        self.progress = (done, total)

    def set_preview_png(self, png: bytes) -> None:
        self.preview = png

    def flush(self) -> None:
        pass

    def flush_from_thread(self) -> None:
        pass


def _fields(**values: object) -> CspSplitFields:
    def control(value: object = "") -> SimpleNamespace:
        return SimpleNamespace(value=value, disabled=False)

    names = ("sheet_field", "template_field", "out_dir_field", "make_work_field", "work_name_field",
             "cmc_template_field", "story_index_field", "fit_field", "order_field", "first_page_field",
             "plan_btn", "run_btn", "cancel_btn", "summary_text")
    defaults: dict[str, object] = {"make_work_field": True, "fit_field": "cell", "order_field": "rtl_ttb",
                                   "first_page_field": "1"}
    return CspSplitFields(**{name: control(values.get(name, defaults.get(name, ""))) for name in names})


def _run_now(job: Callable[[], None]) -> None:
    job()


def test_controller_fills_in_and_writes(tmp_path: Path, sheet_path: Path, template_path: Path) -> None:
    build_cmc(sheet_path.parent / "name.cmc", ["sheet.clip"])
    fields = _fields(sheet_field=str(sheet_path), template_field=str(template_path), story_index_field="3")
    ui = FakeUi()
    controller = CspSplitController(fields, ui, run_thread=_run_now)
    controller.on_sheet_change()
    assert fields.cmc_template_field.value == str(sheet_path.parent / "name.cmc")
    assert fields.work_name_field.value == "sheet"
    assert fields.out_dir_field.value == str(tmp_path / "sheet_ページ")

    controller.on_plan()
    assert ui.preview is not None and ui.preview.startswith(b"\x89PNG")
    assert fields.summary_text.value.startswith("4 ページ")

    controller.on_run()
    out = tmp_path / "sheet_ページ"
    assert sorted(path.name for path in out.iterdir()) == [f"page{n:04d}.clip" for n in range(1, 5)] + ["sheet.cmc"]
    assert _story_index(out / "sheet.cmc") == 3
    assert ui.progress == (4, 4) and "完了" in ui.status
    assert not fields.run_btn.disabled and fields.cancel_btn.disabled


def test_controller_reports_bad_input(sheet_path: Path, template_path: Path) -> None:
    ui = FakeUi()
    fields = _fields(sheet_field=str(sheet_path), template_field=str(template_path),
                     out_dir_field=str(sheet_path.parent / "out"), first_page_field="x")
    CspSplitController(fields, ui, run_thread=_run_now).on_run()
    assert ui.logs and "整数" in ui.logs[-1]
    fields.first_page_field.value = "1"
    fields.template_field.value = ""
    CspSplitController(fields, ui, run_thread=_run_now).on_plan()
    assert "空ページ" in ui.status
    assert not (sheet_path.parent / "out").exists()
