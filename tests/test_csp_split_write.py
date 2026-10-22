"""Tests for writing page .clip files and the .cmc work from a name sheet.

Why: Stages 3 and 4 copy layers from a sheet into a page template and list
     the pages in a .cmc. Only CSP can confirm a file opens, but these tests
     check that what we write reads back with the planned layers, positions,
     sizes and page order, and that the input files are never changed.
"""
from __future__ import annotations

import hashlib
import io
from pathlib import Path
import sqlite3
import struct

from PIL import Image, ImageChops
import pytest

from csp_fixtures import (
    OPEN,
    VECTOR_BRUSH_SIZE,
    FixtureLayer,
    build_clip,
    build_cmc,
    build_text_attributes,
    rectangle,
)
from name_splitter.app.cli import main
from name_splitter.csp import read_clip, read_cmc
from name_splitter.csp.clip_editor import ClipEditor
from name_splitter.csp.cmc_writer import write_cmc
from name_splitter.csp.container import open_sqlite_bytes, read_csf_container
from name_splitter.csp.page_writer import write_page
from name_splitter.csp.split_plan import plan_sheet
from name_splitter.csp.text_attributes import build_tlv, parse_text_attributes, parse_tlv

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
    preview = Image.new("RGBA", (SHEET_W // 2, SHEET_H // 2), (255, 255, 255, 255))
    preview.paste((255, 0, 0, 255), (645, 145, 655, 155))  # the sketch dot, rendered at half size
    folder = tmp_path / "sheet"
    folder.mkdir()
    return build_clip(folder / "sheet.clip", SHEET_W, SHEET_H, layers, preview=preview, double_page=True,
                      editable=True)


@pytest.fixture()
def template_path(tmp_path: Path) -> Path:
    blank = Image.new("RGBA", (PAGE_W, PAGE_H), (0, 0, 0, 0))
    folder = tmp_path / "template"
    folder.mkdir()
    story = build_tlv([(0x0B, struct.pack("<4I", 1, 0, len("作品 3話"), 26)), (0x20, struct.pack("<i", 900))])
    layers = [FixtureLayer(main_id=2, name="用紙", layer_type=1584), FixtureLayer(main_id=3, name="レイヤー 1", image=blank),
              FixtureLayer(main_id=4, name="(作品情報)", layer_type=800, text="作品 3話", text_attributes=story)]
    preview = Image.new("RGBA", (PAGE_W // 2, PAGE_H // 2), (255, 255, 255, 255))
    return build_clip(folder / "page.clip", PAGE_W, PAGE_H, layers, preview=preview, editable=True)


def _canvas_value(path: Path, column: str) -> object:
    database = open_sqlite_bytes(read_csf_container(path).sqlite_bytes)
    return database.execute(f"SELECT {column} FROM Canvas").fetchone()[0]


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

    # The page thumbnail shows the cell's part of the sheet preview (half size here).
    assert document.preview_png is not None
    thumbnail = Image.open(io.BytesIO(document.preview_png)).convert("RGB")
    red = Image.new("RGB", thumbnail.size, (255, 0, 0))
    mask = Image.eval(ImageChops.difference(thumbnail, red).convert("L"), lambda value: 255 if value < 40 else 0)
    rx0, ry0, rx1, ry1 = mask.getbbox() or (0, 0, 0, 0)
    assert abs((rx0 + rx1) / 2 - (1300 * scale + dx) / 2) <= 2 and abs((ry0 + ry1) / 2 - (300 * scale + dy) / 2) <= 2


def test_write_page_scales_text(tmp_path: Path, sheet_path: Path, template_path: Path) -> None:
    sheet = read_clip(sheet_path)
    plan = plan_sheet(sheet, PAGE_W, PAGE_H, fit="cell")
    page = next(page for page in plan.pages if any(content.name == "セリフ" for content in page.contents))
    result = write_page(template_path, sheet, page, tmp_path / "text.clip", page_index=5,
                        canvas_values={"ComicStoryStoryName": "第4話", "NoSuchColumn": 1})
    document = read_clip(result.path)
    text_layer = next(layer for layer in document.iter_layers() if layer.name == "セリフ")
    database = open_sqlite_bytes(document.container.sqlite_bytes)
    blob = database.execute("SELECT TextLayerAttributes FROM Layer WHERE MainId = ?",
                            (text_layer.main_id,)).fetchone()[0]
    attributes = parse_text_attributes(bytes(blob))
    assert attributes.font_size_pt == pytest.approx(4.0 * page.transform.scale, abs=0.01)
    assert _canvas_page(result.path) == (5, 0)
    assert _canvas_value(result.path, "ComicStoryStoryName") == "第4話"


def test_write_cmc_lists_pages_in_order(tmp_path: Path, template_path: Path) -> None:
    project_template = build_cmc(tmp_path / "template" / "work.cmc", ["page0001.clip"])
    before = _digest(project_template)
    out = tmp_path / "out"
    out.mkdir()
    pages = []
    for number in (3, 1, 2):
        page = out / f"page{number:04d}.clip"
        page.write_bytes(template_path.read_bytes())
        pages.append(page)
    work = write_cmc(project_template, pages, out / "new.cmc")
    project = read_cmc(work)
    assert [page.file_name for page in project.pages] == ["page0003.clip", "page0001.clip", "page0002.clip"]
    assert project.max_canvas_file_index == 3
    assert project.story_name == "Story"
    assert _digest(project_template) == before
    with pytest.raises(ValueError):
        write_cmc(project_template, [template_path], out / "bad.cmc")
    with pytest.raises(ValueError):
        write_cmc(project_template, [], out / "empty.cmc")


def test_split_cli_writes_work(tmp_path: Path, sheet_path: Path, template_path: Path,
                               capsys: pytest.CaptureFixture[str]) -> None:
    build_cmc(sheet_path.parent / "name.cmc", ["sheet.clip"])
    inputs = {path: _digest(path) for path in (sheet_path, template_path, sheet_path.parent / "name.cmc")}
    out = tmp_path / "work"
    code = main(["split", str(sheet_path), "--template", str(template_path), "--out-dir", str(out),
                 "--fit", "cell", "--cmc", "第1話", "--story-index", "12"])
    assert code == 0, capsys.readouterr().err
    project = read_cmc(out / "第1話.cmc")
    assert [page.file_name for page in project.pages] == [f"page{number:04d}.clip" for number in range(1, 5)]
    assert [_canvas_page(out / page.file_name)[0] for page in project.pages] == [0, 1, 2, 3]
    # Story info comes from the work's .cmc, not from the template page.
    assert _canvas_value(out / "page0001.clip", "ComicStoryStoryName") == "Story"
    # --story-index overrides the episode number in the work and every page.
    assert _canvas_value(out / "page0004.clip", "ComicStoryStoryIndex") == 12
    # The 作品情報 text CSP displays follows the new episode number.
    database = open_sqlite_bytes(read_csf_container(out / "page0001.clip").sqlite_bytes)
    string, attributes = database.execute(
        "SELECT TextLayerString, TextLayerAttributes FROM Layer WHERE ComicStoryInfoType = 1").fetchone()
    assert bytes(string).decode("utf-8") == "作品 12話"
    runs = dict(parse_tlv(bytes(attributes)))[0x0B]
    assert struct.unpack("<4I", runs) == (1, 0, len("作品 12話"), 26)
    with sqlite3.connect(out / "第1話.cmc") as work:
        assert work.execute("SELECT ComicStoryStoryIndex FROM Project").fetchone()[0] == 12
    assert all(_digest(path) == digest for path, digest in inputs.items())


def test_split_cli_refuses_input_folders(sheet_path: Path, template_path: Path) -> None:
    code = main(["split", str(sheet_path), "--template", str(template_path), "--out-dir", str(sheet_path.parent)])
    assert code == 2
    # --cmc without a template .cmc next to the sheet
    code = main(["split", str(sheet_path), "--template", str(template_path),
                 "--out-dir", str(sheet_path.parent.parent / "out"), "--cmc", "x"])
    assert code == 2
