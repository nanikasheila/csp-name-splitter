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

from dataclasses import dataclass, field
import math
from pathlib import Path
import sqlite3
import struct

from PIL import Image

from .clip_editor import ClipEditor
from .clip_reader import ClipDocument
from .clip_schema import column_names, merge_schema, table_names
from .container import open_sqlite_bytes
from .errors import CspFormatError
from .split_plan import CellTransform, PlannedContent, PlannedPage
from .text_attributes import split_attribute_array, transform_text_attributes
from .vector import select_vector_objects, transform_vector_data

SCHEMA_TABLES = ("Layer", "Canvas", "VectorObjectList", "BrushStyleManager", "BrushStyle")
# Vector objects refer to brush styles by id, so these rows keep their ids.
SHARED_TABLES = ("BrushStyleManager", "BrushStyle")
TEXT_BLOBS = ("TextLayerAttributes",)
TEXT_ARRAYS = ("TextLayerAttributesArray", "TextLayerAddAttributesV01")


@dataclass
class PageResult:
    path: Path
    layer_ids: list[int] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def write_page(template: str | Path, sheet: ClipDocument, page: PlannedPage, output: str | Path) -> PageResult:
    """Write ``page`` of ``sheet`` into a copy of ``template`` saved as ``output``."""
    editor = ClipEditor(template)
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
