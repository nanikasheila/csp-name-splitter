"""Write one page .clip from a name sheet and its split plan.

Why: Stage 3 of the rebuild. Each planned page becomes a .clip that keeps
     the sheet's layers: raster parts are cropped and enlarged, vector and
     text layers are copied with their coordinates moved and scaled.
How: A CSP-made empty page of the same work is the template. The sheet's
     schema (vector tables, extra layer columns) and brush styles are added
     to it, then every planned content is copied in sheet order, inside the
     same folders as on the sheet.
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
import io
import math
from pathlib import Path
import re
import sqlite3
import struct

from PIL import Image

from .clip_editor import ClipEditor
from .clip_reader import ClipDocument, _build_canvas
from .clip_schema import column_names, merge_schema, table_names
from .container import open_sqlite_bytes
from .errors import CspFormatError
from .split_plan import CellTransform, PlannedContent, PlannedPage
from .text_attributes import (build_tlv, clear_render_cache, parse_tlv, split_attribute_array,
                              transform_text_attributes)
from .vector import select_vector_objects, transform_vector_data

# Not Canvas: a spread sheet has ComicStory/NombreRightLayerCreated columns, and a single right
# page that has them (as NULL) makes CSP rebuild its story info layers and mark the page modified.
SCHEMA_TABLES = ("Layer", "VectorObjectList", "BrushStyleManager", "BrushStyle")
# Vector objects refer to brush styles by id, so these rows keep their ids.
SHARED_TABLES = ("BrushStyleManager", "BrushStyle")
TEXT_BLOBS = ("TextLayerAttributes",)
TEXT_ARRAYS = ("TextLayerAttributesArray", "TextLayerAddAttributesV01")
PAGE_COLUMNS = ("ComicPageIndex", "ComicIsLeftPage")
# CropFrameOptionFlag bits CSP sets for a single left / right page (2 / 4; a spread has 17).
LEFT_PAGE_FLAG, RIGHT_PAGE_FLAG = 2, 4
NOMBRE_INFO = 2  # Layer.ComicStoryInfoType of the (ノンブル) layer
ATTR_BBOX, ATTR_BLOCK_SIZE, ATTR_QUAD = 0x2A, 0x3F, 0x40
RUN_TAG = 0x0B  # style runs of a text: u32 count, then (u32 start, u32 length, ...)


@dataclass
class PageResult:
    path: Path
    layer_ids: list[int] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def write_page(template: str | Path, sheet: ClipDocument, page: PlannedPage, output: str | Path,
               page_index: int | None = None, canvas_values: dict[str, object] | None = None) -> PageResult:
    """Write ``page`` of ``sheet`` into a copy of ``template`` saved as ``output``.

    ``page_index`` is the 0-based position of the page in the work (CSP's
    ``ComicPageIndex``, used for the ノンブル); it defaults to ``page.number - 1``.
    ``canvas_values`` overrides Canvas columns the template has (for example
    the work's ``ComicStory*`` settings from its .cmc).
    """
    editor = ClipEditor(template)
    editor.renew_ids()
    _set_page_index(editor.db, page.number - 1 if page_index is None else page_index)
    if canvas_values:
        old_index = _canvas_value(editor.db, "ComicStoryStoryIndex")
        _set_canvas_values(editor.db, canvas_values)
        new_index = canvas_values.get("ComicStoryStoryIndex")
        if isinstance(old_index, int) and isinstance(new_index, int) and old_index != new_index:
            _replace_story_index(editor.db, old_index, new_index)
    _update_nombre(editor.db)
    source = open_sqlite_bytes(sheet.container.sqlite_bytes)
    merge_schema(editor.db, source, list(SCHEMA_TABLES))
    _share_rows(editor.db, source)
    result = PageResult(path=Path(output))
    folders: dict[int, int] = {}
    for content in page.contents:
        parent = editor.root_id
        for folder_id in content.folder_ids:
            if folder_id not in folders:
                folders[folder_id] = editor.add_layer(source, sheet.container.external_payload, folder_id)
                editor.append_to_folder(parent, folders[folder_id])
            parent = folders[folder_id]
        new_id = _add_content(editor, source, sheet, content, page.transform, result.warnings)
        editor.append_to_folder(parent, new_id)
        result.layer_ids.append(new_id)
    _update_preview(editor.db, sheet, page)
    editor.save(output)
    return result


def _add_content(editor: ClipEditor, source: sqlite3.Connection, sheet: ClipDocument, content: PlannedContent,
                 transform: CellTransform, warnings: list[str]) -> int:
    layer = sheet.find_layer(content.layer_id)
    scale = transform.scale
    dx = transform.dx + layer.offset_x * scale
    dy = transform.dy + layer.offset_y * scale

    def payload_hook(table: str, column: str, payload: bytes) -> bytes:
        if table != "VectorObjectList":
            return payload
        if content.kind == "vector" and content.items:
            payload = select_vector_objects(payload, content.items)
        return transform_vector_data(payload, scale, dx, dy)

    def row_hook(values: dict[str, object]) -> None:
        for column in TEXT_BLOBS:
            blob = values.get(column)
            if isinstance(blob, bytes) and blob:
                values[column] = transform_text_attributes(blob, scale, dx, dy)
        for column in TEXT_ARRAYS:
            blob = values.get(column)
            if isinstance(blob, bytes) and blob:
                values[column] = _transform_array(blob, scale, dx, dy, column, warnings)

    new_id = editor.add_layer(source, sheet.container.external_payload, layer.main_id,
                              row_hook=row_hook, payload_hook=payload_hook)
    if content.kind == "raster" and content.crop is not None:
        image, position = _scaled_crop(sheet, content, transform)
        editor.set_layer_image(new_id, image, position)
    if content.kind == "text" and content.items and len(sheet.text_blocks(layer)) > 1:
        warnings.append(f"Text layer {layer.main_id}: only whole layers are copied; all blocks were kept")
    return new_id


def _scaled_crop(sheet: ClipDocument, content: PlannedContent,
                 transform: CellTransform) -> tuple[Image.Image, tuple[int, int]]:
    assert content.crop is not None
    x0, y0, x1, y1 = (math.floor(content.crop[0]), math.floor(content.crop[1]),
                      math.ceil(content.crop[2]), math.ceil(content.crop[3]))
    region = sheet.layer_pixels_in_box(sheet.find_layer(content.layer_id), (x0, y0, x1, y1))
    tx0, ty0, tx1, ty1 = transform.map_box((x0, y0, x1, y1))
    size = (max(round(tx1 - tx0), 1), max(round(ty1 - ty0), 1))
    return region.resize(size, Image.Resampling.LANCZOS), (round(tx0), round(ty0))


def _transform_array(blob: bytes, scale: float, dx: float, dy: float, column: str, warnings: list[str]) -> bytes:
    try:
        blocks = split_attribute_array(blob)
        moved = [transform_text_attributes(block, scale, dx, dy) for block in blocks]
    except CspFormatError:
        warnings.append(f"{column} has an unknown layout and was copied unchanged")
        return blob
    return b"".join(struct.pack("<I", len(block)) + block for block in moved)


def _set_page_index(db: sqlite3.Connection, index: int) -> None:
    """Set the page position and side (left / right) on the copied canvas.

    Why: CSP numbers pages and places the ノンブル from these columns.
    How: The side alternates with the index; the template's own pair gives
         the parity, so the binding direction and start side need no guess.
    """
    if not set(PAGE_COLUMNS) <= set(column_names(db, "Canvas")):
        return
    template_index, template_left = db.execute("SELECT ComicPageIndex, ComicIsLeftPage FROM Canvas").fetchone()
    left = bool(template_left) == ((index - int(template_index or 0)) % 2 == 0)
    db.execute("UPDATE Canvas SET ComicPageIndex = ?, ComicIsLeftPage = ?", (index, int(left)))
    if "CropFrameOptionFlag" in column_names(db, "Canvas"):
        flag = int(db.execute("SELECT CropFrameOptionFlag FROM Canvas").fetchone()[0] or 0)
        if flag & (LEFT_PAGE_FLAG | RIGHT_PAGE_FLAG):
            flag = (flag & ~(LEFT_PAGE_FLAG | RIGHT_PAGE_FLAG)) | (LEFT_PAGE_FLAG if left else RIGHT_PAGE_FLAG)
            db.execute("UPDATE Canvas SET CropFrameOptionFlag = ?", (flag,))
    if bool(template_left) != left:
        _mirror_nombre(db)


def _nombre_rows(db: sqlite3.Connection) -> list[sqlite3.Row]:
    if "ComicStoryInfoType" not in column_names(db, "Layer"):
        return []
    rows: list[sqlite3.Row] = db.execute("SELECT * FROM Layer WHERE ComicStoryInfoType = ?", (NOMBRE_INFO,)).fetchall()
    # A spread has a second pair for its right page; single pages (the only template we take) have one.
    return rows if len(rows) == 1 else []


def _mirror_nombre(db: sqlite3.Connection) -> None:
    """Move the (ノンブル) to the other side of the page.

    Why: The hidden ノンブル sits at the binding edge, which is on the other
         side for left and right pages. CSP moves it when it opens a page
         whose side differs from where the template had it, and then marks
         the page as modified.
    How: Mirrors the text block's bbox (TLV 0x2a) across the canvas width.
    """
    canvas_width = _build_canvas(db.execute("SELECT * FROM Canvas").fetchone()).width_px
    for row in _nombre_rows(db):
        offset = int(row["LayerOffsetX"] or 0)

        def mirror(x0: int, x1: int) -> tuple[int, int]:
            return canvas_width - (x1 + offset) - offset, canvas_width - (x0 + offset) - offset

        _edit_text_blocks(db, row, lambda items: _map_bbox_x(items, mirror))


def _update_nombre(db: sqlite3.Connection) -> None:
    """Write the page's own number into the (ノンブル) text.

    Why: The template's ノンブル shows the template's page number; CSP
         writes ``ComicStoryNombreStart + ComicPageIndex`` there.
    How: Replaces the text and its style run, and widens or narrows the block
         by the template's width per character, keeping the edge nearer to
         the page border in place (the binding edge).
    """
    columns = set(column_names(db, "Canvas"))
    if not {"ComicPageIndex", "ComicStoryNombreStart"} <= columns:
        return
    index, start = db.execute("SELECT ComicPageIndex, ComicStoryNombreStart FROM Canvas").fetchone()
    number = str(int(start if start is not None else 1) + int(index or 0))
    canvas_width = _build_canvas(db.execute("SELECT * FROM Canvas").fetchone()).width_px
    for row in _nombre_rows(db):
        old = bytes(row["TextLayerString"] or b"").decode("utf-8")
        if not old or old == number:
            continue
        offset = int(row["LayerOffsetX"] or 0)

        def resize(items: list[tuple[int, bytes]]) -> list[tuple[int, bytes]]:
            values = dict(items)
            if ATTR_BLOCK_SIZE not in values:
                return items
            width, height = struct.unpack("<2i", values[ATTR_BLOCK_SIZE])
            new_width = max(round(width * len(number) / len(old)), 1)

            def keep_border_edge(x0: int, x1: int) -> tuple[int, int]:
                if x0 + offset < canvas_width - (x1 + offset):
                    return x0, x0 + (x1 - x0) + new_width - width
                return x1 - (x1 - x0) - new_width + width, x1

            resized = []
            for tag, value in _map_bbox_x(items, keep_border_edge):
                if tag == ATTR_BLOCK_SIZE:
                    value = struct.pack("<2i", new_width, height)
                elif tag == ATTR_QUAD and len(value) == 32:
                    quad = list(struct.unpack("<8i", value))
                    for position in (2, 4):  # right-hand x of the quad, 1/100 px
                        quad[position] = quad[position] + (new_width - width) * 100
                    value = struct.pack("<8i", *quad)
                resized.append((tag, value))
            return resized

        db.execute("UPDATE Layer SET TextLayerString = ? WHERE MainId = ?", (number.encode("utf-8"), row["MainId"]))
        if isinstance(row["TextLayerAttributes"], bytes):
            db.execute("UPDATE Layer SET TextLayerAttributes = ? WHERE MainId = ?",
                       (_move_run_length(row["TextLayerAttributes"], len(number) - len(old)), row["MainId"]))
        _edit_text_blocks(db, db.execute("SELECT * FROM Layer WHERE MainId = ?", (row["MainId"],)).fetchone(),
                            resize)
        _drop_render_cache(db, int(row["MainId"]))


def _map_bbox_x(items: list[tuple[int, bytes]], change: Callable[[int, int], tuple[int, int]]) -> list[tuple[int, bytes]]:
    mapped = []
    for tag, value in items:
        if tag == ATTR_BBOX and len(value) == 16:
            x0, y0, x1, y1 = struct.unpack("<4i", value)
            x0, x1 = change(x0, x1)
            value = struct.pack("<4i", x0, y0, x1, y1)
        mapped.append((tag, value))
    return mapped


def _edit_text_blocks(db: sqlite3.Connection, row: sqlite3.Row,
                        edit: Callable[[list[tuple[int, bytes]]], list[tuple[int, bytes]]]) -> None:
    """Apply ``edit`` to the TLV items of every attribute blob of one text layer."""
    keys = row.keys()
    for column in TEXT_BLOBS + TEXT_ARRAYS:
        blob = row[column] if column in keys else None
        if not isinstance(blob, bytes) or not blob:
            continue
        if column in TEXT_BLOBS:
            value = build_tlv(edit(parse_tlv(blob)))
        else:
            blocks = split_attribute_array(blob)
            value = b"".join(struct.pack("<I", len(block)) + block
                             for block in (build_tlv(edit(parse_tlv(item))) for item in blocks))
        db.execute(f'UPDATE Layer SET "{column}" = ? WHERE MainId = ?', (value, row["MainId"]))


def _set_canvas_values(db: sqlite3.Connection, values: dict[str, object]) -> None:
    known = set(column_names(db, "Canvas"))
    for column, value in values.items():
        if column in known:
            db.execute(f'UPDATE Canvas SET "{column}" = ?', (value,))


def _canvas_value(db: sqlite3.Connection, column: str) -> object | None:
    if column not in column_names(db, "Canvas"):
        return None
    value: object = db.execute(f'SELECT "{column}" FROM Canvas').fetchone()[0]
    return value


def _replace_story_index(db: sqlite3.Connection, old: int, new: int) -> None:
    """Change the episode number written in the template's 作品情報 text layer.

    Why: CSP shows the text stored in the story info layer (for example
         "ユメノストラ 3話") rather than rebuilding it from the Canvas settings,
         so a template from another episode keeps showing that episode.
    How: Replaces "<old>話" with "<new>話" in ``TextLayerString``, moves
         the character count of its single style run (TLV 0x0b, u32 run
         count, u32 start, u32 length, ...) by the change in length, and
         clears the cached rendering of the text (TLV 0x32).
    """
    if "ComicStoryInfoType" not in column_names(db, "Layer"):
        return
    rows = db.execute("SELECT MainId, TextLayerString, TextLayerAttributes FROM Layer "
                      "WHERE ComicStoryInfoType = 1").fetchall()
    for layer_id, string, attributes in rows:
        if not isinstance(string, bytes):
            continue
        text = string.decode("utf-8")
        changed = re.sub(rf"(?<!\d){old}話", f"{new}話", text)
        if changed == text:
            continue
        values: dict[str, object] = {"TextLayerString": changed.encode("utf-8")}
        if isinstance(attributes, bytes):
            values["TextLayerAttributes"] = _move_run_length(attributes, len(changed) - len(text))
        for column, value in values.items():
            db.execute(f'UPDATE Layer SET "{column}" = ? WHERE MainId = ?', (value, layer_id))
        _drop_render_cache(db, layer_id)


def _drop_render_cache(db: sqlite3.Connection, layer_id: int) -> None:
    """Make CSP draw a story info / ノンブル text anew instead of its cached image.

    Why: CSP shows the image cached in the file (TLV 0x32 → Offscreen) rather
         than the text, so a changed text kept showing the template's
         "… 3話" or page number.
    """
    row = db.execute("SELECT * FROM Layer WHERE MainId = ?", (layer_id,)).fetchone()
    _edit_text_blocks(db, row, lambda items: parse_tlv(clear_render_cache(build_tlv(items))))


def _move_run_length(blob: bytes, delta: int) -> bytes:
    if not delta:
        return blob
    items = parse_tlv(blob)
    for position, (tag, value) in enumerate(items):
        if tag == RUN_TAG and len(value) >= 12 and struct.unpack_from("<I", value, 0)[0] == 1:
            length = struct.unpack_from("<I", value, 8)[0]
            items[position] = (tag, value[:8] + struct.pack("<I", max(length + delta, 0)) + value[12:])
    return build_tlv(items)


def _update_preview(db: sqlite3.Connection, sheet: ClipDocument, page: PlannedPage) -> None:
    """Draw the page's part of the sheet preview onto the page preview.

    Why: CSP shows ``CanvasPreview`` as the page thumbnail in a work's page
         list without opening the page; the template's preview is blank.
    How: The sheet preview was rendered by CSP, so cropping the cell from it
         and placing it with the cell transform gives a faithful thumbnail
         (the name frames inside the cell are included).
    """
    if "CanvasPreview" not in table_names(db) or not sheet.preview_png:
        return
    row = db.execute("SELECT rowid, ImageData FROM CanvasPreview ORDER BY rowid LIMIT 1").fetchone()
    canvas = db.execute("SELECT CanvasWidth, CanvasHeight, CanvasResolution, CanvasUnit FROM Canvas").fetchone()
    if row is None or not row[1]:
        return
    try:
        preview = Image.open(io.BytesIO(bytes(row[1]))).convert("RGBA")
        source = Image.open(io.BytesIO(sheet.preview_png)).convert("RGBA")
    except OSError:
        return
    page_width = _canvas_width_px(canvas)
    if page_width <= 0 or sheet.canvas.width_px <= 0:
        return
    to_preview = preview.width / page_width
    from_sheet = source.width / sheet.canvas.width_px
    cell = page.cell.rect
    crop = source.crop((round(cell.x0 * from_sheet), round(cell.y0 * from_sheet),
                        round(cell.x1 * from_sheet), round(cell.y1 * from_sheet)))
    x0, y0, x1, y1 = (value * to_preview for value in page.transform.map_box((cell.x0, cell.y0, cell.x1, cell.y1)))
    size = (max(round(x1 - x0), 1), max(round(y1 - y0), 1))
    preview.paste(crop.resize(size, Image.Resampling.LANCZOS), (round(x0), round(y0)))
    buffer = io.BytesIO()
    preview.save(buffer, format="PNG")
    db.execute("UPDATE CanvasPreview SET ImageData = ? WHERE rowid = ?", (buffer.getvalue(), row[0]))


def _canvas_width_px(row: tuple[float, float, float, int]) -> float:
    width, _, resolution, unit = row
    per_inch = {2: 25.4, 1: 2.54, 3: 1.0, 5: 72.0}.get(int(unit))
    return float(width) if per_inch is None else float(width) * float(resolution) / per_inch


def _share_rows(target: sqlite3.Connection, source: sqlite3.Connection) -> None:
    """Copy brush styles (keeping ids) when the template has none."""
    for table in SHARED_TABLES:
        if table not in table_names(source) or table not in table_names(target):
            continue
        if target.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0]:
            continue
        columns = [c for c in column_names(source, table) if c != "_PW_ID" and c in set(column_names(target, table))]
        names = ", ".join(f'"{c}"' for c in columns)
        marks = ", ".join("?" for _ in columns)
        for row in source.execute(f'SELECT {names} FROM "{table}"').fetchall():
            target.execute(f'INSERT INTO "{table}" ({names}) VALUES ({marks})', tuple(row))
        source_max = source.execute("SELECT MaxIndex FROM ElemScheme WHERE TableName = ?", (table,)).fetchone()
        if source_max is not None:
            target.execute("UPDATE ElemScheme SET MaxIndex = MAX(MaxIndex, ?) WHERE TableName = ?",
                           (int(source_max[0]), table))
    if "BrushStyleManager" in column_names(target, "Canvas") and "BrushStyleManager" in column_names(source, "Canvas"):
        manager = source.execute("SELECT BrushStyleManager FROM Canvas").fetchone()[0]
        current = target.execute("SELECT BrushStyleManager FROM Canvas").fetchone()[0]
        if not current:
            target.execute("UPDATE Canvas SET BrushStyleManager = ?", (manager,))
