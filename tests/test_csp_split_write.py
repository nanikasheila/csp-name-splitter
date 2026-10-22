"""Tests for writing page .clip files from a name sheet.

Why: Stage 3 copies layers from a sheet into a page template. Only CSP can
     confirm a file opens, but these tests check that what we write reads
     back with the planned layers, positions and sizes, and that the input
     files are never changed.
"""
from __future__ import annotations

import hashlib
from pathlib import Path

from PIL import Image
import pytest

from csp_fixtures import (
    OPEN,
    VECTOR_BRUSH_SIZE,
    FixtureLayer,
    build_clip,
    build_text_attributes,
    rectangle,
)
from name_splitter.csp import read_clip
from name_splitter.csp.clip_editor import ClipEditor
from name_splitter.csp.container import open_sqlite_bytes, read_csf_container
from name_splitter.csp.page_writer import write_page
from name_splitter.csp.split_plan import plan_sheet
from name_splitter.csp.text_attributes import parse_text_attributes

SHEET_W, SHEET_H = 1600, 600
PAGE_W, PAGE_H = 400, 560
RIGHT_SPREAD = [rectangle(840, 40, 1560, 560), rectangle(860, 60, 1190, 540), rectangle(1210, 60, 1540, 540)]


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


@pytest.fixture()
def sheet_path(tmp_path: Path) -> Path:
    sketch = Image.new("RGBA", (SHEET_W, SHEET_H), (0, 0, 0, 0))
    sketch.paste((0, 0, 0, 255), (1290, 290, 1310, 310))
    layers = [
        FixtureLayer(main_id=2, name="用紙", layer_type=1584),
        FixtureLayer(main_id=10, name="テンプレート", layer_type=0, folder=1, children=[
            FixtureLayer(main_id=11, name="右", layer_type=0, vector_objects=RIGHT_SPREAD),
            FixtureLayer(main_id=12, name="左", layer_type=0, offset=(-800, 0), vector_objects=RIGHT_SPREAD),
        ]),
        FixtureLayer(main_id=20, name="下描き", image=sketch),
        FixtureLayer(main_id=30, name="ネーム", layer_type=0, folder=1, children=[
            FixtureLayer(main_id=21, name="線", layer_type=0, vector_objects=[(OPEN, [(1250, 100), (1500, 500)])]),
        ]),
        FixtureLayer(main_id=23, name="セリフ", layer_type=0, text="あ",
                     text_attributes=build_text_attributes((900, 100, 960, 300), 4.0)),
    ]
    folder = tmp_path / "sheet"
    folder.mkdir()
    return build_clip(folder / "sheet.clip", SHEET_W, SHEET_H, layers, double_page=True, editable=True)


@pytest.fixture()
def template_path(tmp_path: Path) -> Path:
    blank = Image.new("RGBA", (PAGE_W, PAGE_H), (0, 0, 0, 0))
    folder = tmp_path / "template"
    folder.mkdir()
    layers = [FixtureLayer(main_id=2, name="用紙", layer_type=1584), FixtureLayer(main_id=3, name="レイヤー 1", image=blank)]
    return build_clip(folder / "page.clip", PAGE_W, PAGE_H, layers, editable=True)


def _canvas_page(path: Path) -> tuple[int, int]:
    database = open_sqlite_bytes(read_csf_container(path).sqlite_bytes)
    index, left = database.execute("SELECT ComicPageIndex, ComicIsLeftPage FROM Canvas").fetchone()
    return int(index), int(left)


def test_editor_adds_layer_with_pixels(tmp_path: Path, template_path: Path) -> None:
    before = _digest(template_path)
    editor = ClipEditor(template_path)
    source = open_sqlite_bytes(read_csf_container(template_path).sqlite_bytes)
    new_id = editor.add_layer(source, editor.externals.get, editor.first_raster_layer(),
                              row_hook=lambda values: values.update(LayerName="追加"))
    editor.append_to_folder(editor.root_id, new_id)
    editor.set_layer_image(new_id, Image.new("RGBA", (20, 10), (255, 0, 0, 255)), (100, 200))
    output = editor.save(tmp_path / "out.clip")
    assert _digest(template_path) == before
    document = read_clip(output)
    layer = document.find_layer(new_id)
    assert layer.name == "追加"
    assert [child.name for child in document.root.children][-1] == "追加"
    pixels = document.render_layer_pixels(layer)
    assert pixels is not None and pixels.getbbox() == (100, 200, 120, 210)
    # The template's own layer keeps its (empty) pixels.
    original = document.render_layer_pixels(document.find_layer(3))
    assert original is not None and original.getbbox() is None


def test_write_page_copies_planned_layers(tmp_path: Path, sheet_path: Path, template_path: Path) -> None:
    sheet = read_clip(sheet_path)
    plan = plan_sheet(sheet, PAGE_W, PAGE_H, fit="cell")
    page = plan.pages[0]
    result = write_page(template_path, sheet, page, tmp_path / "page0001.clip")
    document = read_clip(result.path)
    names = {layer.name: layer for layer in document.iter_layers()}
    assert {"下描き", "ネーム", "線"} <= set(names)
    assert "テンプレート" not in names and "セリフ" not in names  # the text is on the next page
    assert names["線"] in names["ネーム"].children

    scale, dx, dy = page.transform.scale, page.transform.dx, page.transform.dy
    pixels = document.render_layer_pixels(names["下描き"])
    assert pixels is not None
    x0, y0, x1, y1 = pixels.getbbox() or (0, 0, 0, 0)
    assert abs((x0 + x1) / 2 - (1300 * scale + dx)) <= 2 and abs((y0 + y1) / 2 - (300 * scale + dy)) <= 2

    line = document.vector_objects(names["線"])[0]
    assert line.points[0] == pytest.approx((1250 * scale + dx, 100 * scale + dy))
    assert line.brush_size == pytest.approx(VECTOR_BRUSH_SIZE * scale)
    assert _canvas_page(result.path) == (0, 1)


def test_write_page_scales_text(tmp_path: Path, sheet_path: Path, template_path: Path) -> None:
    sheet = read_clip(sheet_path)
    plan = plan_sheet(sheet, PAGE_W, PAGE_H, fit="cell")
    page = next(page for page in plan.pages if any(content.name == "セリフ" for content in page.contents))
    result = write_page(template_path, sheet, page, tmp_path / "text.clip", page_index=5)
    document = read_clip(result.path)
    text_layer = next(layer for layer in document.iter_layers() if layer.name == "セリフ")
    database = open_sqlite_bytes(document.container.sqlite_bytes)
    blob = database.execute("SELECT TextLayerAttributes FROM Layer WHERE MainId = ?",
                            (text_layer.main_id,)).fetchone()[0]
    attributes = parse_text_attributes(bytes(blob))
    assert attributes.font_size_pt == pytest.approx(4.0 * page.transform.scale, abs=0.01)
    assert _canvas_page(result.path) == (5, 0)
