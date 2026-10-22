"""Tests for name-sheet page cell detection and the split plan.

Why: Stage 2 decides which page each part of a name sheet goes to. The
     synthetic sheet mirrors a real CSP name template: a double-page canvas
     whose halves each hold a spread outline with two page frames inside,
     drawn on two vector layers where one is a moved copy of the other.
"""
from __future__ import annotations

import json
from pathlib import Path

from PIL import Image
import pytest

from csp_fixtures import OPEN, FixtureLayer, build_clip, build_text_attributes, rectangle
from name_splitter.app.cli import main
from name_splitter.csp import read_clip
from name_splitter.csp.name_layout import Rect, detect_document_cells, detect_page_cells, find_rectangles
from name_splitter.csp.split_plan import centered_trim, fit_cell, fit_frame, plan_sheet

SHEET_W, SHEET_H = 1600, 600
RIGHT_SPREAD = [rectangle(840, 40, 1560, 560), rectangle(860, 60, 1190, 540), rectangle(1210, 60, 1540, 540)]


def _sheet_layers(extra: list[FixtureLayer]) -> list[FixtureLayer]:
    template = FixtureLayer(main_id=10, name="テンプレート", layer_type=0, folder=1, children=[
        FixtureLayer(main_id=11, name="右", layer_type=0, vector_objects=RIGHT_SPREAD),
        FixtureLayer(main_id=12, name="左", layer_type=0, offset=(-800, 0), vector_objects=RIGHT_SPREAD),
    ])
    return [FixtureLayer(main_id=2, name="用紙", layer_type=1584), template, *extra]


@pytest.fixture()
def sheet_path(tmp_path: Path) -> Path:
    sketch = Image.new("RGBA", (SHEET_W, SHEET_H), (0, 0, 0, 0))
    sketch.paste((0, 0, 0, 255), (1290, 290, 1310, 310))
    extra = [
        FixtureLayer(main_id=20, name="下描き", image=sketch),
        FixtureLayer(main_id=21, name="線", layer_type=0, vector_objects=[(OPEN, [(450, 100), (700, 500)])]),
        FixtureLayer(main_id=22, name="コマ", layer_type=0, vector_objects=[rectangle(60, 100, 380, 300)]),
        FixtureLayer(main_id=23, name="セリフ", layer_type=0, text="あ",
                     text_attributes=build_text_attributes((900, 100, 960, 300), 4.0)),
        FixtureLayer(main_id=24, name="フキダシ", layer_type=0, text="い",
                     text_attributes=build_text_attributes((-10, -50, 10, 50)),
                     vector_objects=[rectangle(1250, 350, 1350, 450), rectangle(450, 350, 550, 450)]),
        FixtureLayer(main_id=25, name="非表示", layer_type=0, visibility=0,
                     vector_objects=[(OPEN, [(450, 100), (700, 500)])]),
    ]
    return build_clip(tmp_path / "sheet.clip", SHEET_W, SHEET_H, _sheet_layers(extra), double_page=True)


def test_rectangles_apply_layer_offset(sheet_path: Path) -> None:
    rects = find_rectangles(read_clip(sheet_path))
    assert Rect(40, 40, 760, 560) in rects  # left copy moved by its layer offset
    assert Rect(840, 40, 1560, 560) in rects
    assert Rect(60, 100, 380, 300) in rects  # a free panel is still a rectangle


def test_cells_right_to_left(sheet_path: Path) -> None:
    cells = detect_document_cells(read_clip(sheet_path))
    assert [(cell.rect.x0, cell.rect.x1) for cell in cells] == [(1200, 1560), (840, 1200), (400, 760), (40, 400)]
    assert [cell.spread_side for cell in cells] == ["right", "left", "right", "left"]
    assert cells[0].frame == Rect(1210, 60, 1540, 540)


def test_cells_left_to_right(sheet_path: Path) -> None:
    cells = detect_document_cells(read_clip(sheet_path), order="ltr_ttb")
    assert [cell.rect.x0 for cell in cells] == [40, 400, 840, 1200]


def test_cells_rows_and_single_pages() -> None:
    pages = [Rect(x, y, x + 100, y + 140) for y in (10, 200) for x in (10, 120, 230)]
    cells = detect_page_cells(pages, 400, double_page=False)
    assert [(cell.rect.x0, cell.rect.y0) for cell in cells] == [
        (230, 10), (120, 10), (10, 10), (230, 200), (120, 200), (10, 200)]
    assert all(cell.frame is None for cell in cells)
    assert detect_page_cells([Rect(0, 0, 10, 10)], 100, double_page=False) == []
    with pytest.raises(ValueError):
        detect_page_cells(pages, 400, double_page=False, order="ttb")


def test_fit_cell_scales_uniformly_and_centres() -> None:
    transform = fit_cell(Rect(100, 50, 200, 190), 500, 700)
    assert transform.scale == pytest.approx(5.0)
    assert transform.map_box((100, 50, 200, 190)) == pytest.approx((0, 0, 500, 700))
    wide = fit_cell(Rect(0, 0, 100, 100), 200, 400)
    assert wide.map_box((0, 0, 100, 100)) == pytest.approx((0, 100, 200, 300))


def test_fit_frame_puts_inner_frame_on_trim() -> None:
    trim = centered_trim(800, 1000, 600, 800)
    assert trim == Rect(100, 100, 700, 900)
    transform = fit_frame(Rect(10, 20, 70, 100), trim)
    assert transform.scale == pytest.approx(10.0)
    assert transform.map_box((10, 20, 70, 100)) == pytest.approx((100, 100, 700, 900))


def test_plan_fits_frames_to_basic_frame(sheet_path: Path) -> None:
    trim = centered_trim(800, 1200, 700, 1000)
    basic = centered_trim(800, 1200, 600, 900, offset=(10, -20))
    plan = plan_sheet(read_clip(sheet_path), 800, 1200, trim=trim, basic=basic)
    assert plan.warnings == [w for w in plan.warnings if "24" in w]
    first = plan.pages[0]
    assert first.cell.frame is not None
    frame = first.cell.frame
    mapped = first.transform.map_box((frame.x0, frame.y0, frame.x1, frame.y1))
    # 330x480 frame on a 600x900 basic frame: width decides the scale, centred vertically.
    assert mapped[0] == pytest.approx(110) and mapped[2] == pytest.approx(710)
    assert (mapped[1] + mapped[3]) / 2 == pytest.approx(580)


def test_plan_fits_frames_to_trim(sheet_path: Path) -> None:
    trim = centered_trim(800, 1200, 600, 900)
    plan = plan_sheet(read_clip(sheet_path), 800, 1200, fit="trim", trim=trim,
                      basic=centered_trim(800, 1200, 400, 600))
    assert plan.warnings == [w for w in plan.warnings if "24" in w]
    first = plan.pages[0]
    assert first.cell.frame is not None
    frame = first.cell.frame
    mapped = first.transform.map_box((frame.x0, frame.y0, frame.x1, frame.y1))
    # 330x480 frame on a 600x900 trim: width decides the scale, centred vertically.
    assert mapped[0] == pytest.approx(100) and mapped[2] == pytest.approx(700)
    assert (mapped[1] + mapped[3]) / 2 == pytest.approx(600)


def test_plan_frame_fit_without_trim_falls_back(sheet_path: Path) -> None:
    plan = plan_sheet(read_clip(sheet_path), 800, 600)
    assert any("basic frame" in warning for warning in plan.warnings)
    assert plan.pages[0].transform == fit_cell(plan.pages[0].cell.rect, 800, 600)
    # Without a basic frame, the trim frame is used.
    trim = centered_trim(800, 600, 600, 500)
    plan = plan_sheet(read_clip(sheet_path), 800, 600, trim=trim)
    assert any("trim frame instead" in warning for warning in plan.warnings)
    assert plan.pages[0].transform == plan_sheet(read_clip(sheet_path), 800, 600, fit="trim",
                                                 trim=trim).pages[0].transform
    with pytest.raises(ValueError):
        plan_sheet(read_clip(sheet_path), 800, 600, fit="stretch")


def test_plan_assigns_contents(sheet_path: Path) -> None:
    plan = plan_sheet(read_clip(sheet_path), 800, 600, fit="cell")
    assert sorted(plan.template_layer_ids) == [11, 12]
    contents = {page.number: {(c.layer_id, c.items, c.whole_layer) for c in page.contents} for page in plan.pages}
    assert contents[1] == {(20, (), False), (24, (), True)}
    assert contents[2] == {(23, (0,), False)}
    assert contents[3] == {(21, (0,), False), (24, (), True)}
    assert contents[4] == {(22, (0,), False)}
    assert len(plan.warnings) == 1 and "24" in plan.warnings[0]
    raster = next(c for c in plan.pages[0].contents if c.layer_id == 20)
    assert raster.crop == (1200, 40, 1560, 560)
    text = next(c for c in plan.pages[1].contents if c.layer_id == 23)
    assert text.folder_path == ()


def test_plan_without_template_warns(tmp_path: Path) -> None:
    path = build_clip(tmp_path / "blank.clip", 300, 300, [FixtureLayer(main_id=2, name="用紙", layer_type=1584)])
    plan = plan_sheet(read_clip(path), 300, 300)
    assert plan.pages == [] and plan.warnings


def test_plan_cli_writes_json_and_preview(sheet_path: Path, tmp_path: Path) -> None:
    output, preview = tmp_path / "plan.json", tmp_path / "plan.png"
    exit_code = main(["plan", str(sheet_path), "--first-page", "3", "--output", str(output),
                      "--preview", str(preview), "--trim-size", "600x500"])
    assert exit_code == 0
    data = json.loads(output.read_text(encoding="utf-8"))
    assert data["page_size_px"] == [800, 600]
    assert data["fit"] == "basic" and data["trim_px"] == [100, 50, 700, 550] and data["basic_px"] is None
    assert [page["number"] for page in data["pages"]] == [3, 4, 5, 6]
    assert data["pages"][0]["contents"][0]["crop"] == [1200, 40, 1560, 560]
    assert preview.exists()
    assert main(["plan", str(sheet_path), "--output", str(output), "--basic-size", "500x400"]) == 0
    assert json.loads(output.read_text(encoding="utf-8"))["basic_px"] == [150, 100, 650, 500]


def test_plan_cli_rejects_bad_options(sheet_path: Path, tmp_path: Path) -> None:
    assert main(["plan", str(tmp_path / "missing.clip")]) == 2
    assert main(["plan", str(sheet_path), "--page-size", "big"]) == 2
    assert main(["plan", str(sheet_path), "--trim-size", "0x10"]) == 2
