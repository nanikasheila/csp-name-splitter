"""Edit a CSP-made .clip template: add layers, write pixels, save.

Why: Stage 3 writes page files without reimplementing everything CSP stores.
     A page saved by CSP (empty, with the work's settings) is used as the
     template, and layers are added by copying rows the way CSP links them.
How: Rows are copied with :class:`RowCopier`, which follows the id links
     listed in ``ParamScheme`` (for example Layer → Mipmap → MipmapInfo →
     Offscreen), gives every copied row a new ``MainId`` from ``ElemScheme``
     and copies external chunks under new ids. New layers get the render
     offscreens of the template's own raster layer, so their size always
     matches the page canvas.
"""
from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
import sqlite3
import uuid

from PIL import Image

from .clip_schema import OWNER_CANVAS, OWNER_LAYER, allocate_id, column_infos, column_names, external_columns
from .container import open_sqlite_bytes, read_csf_container
from .container_writer import assemble_container, head_file_id
from .errors import CspFormatError
from .offscreen import parse_offscreen_attribute
from .offscreen_writer import encode_offscreen_image

PayloadHook = Callable[[str, str, bytes], bytes]
LAYER_TYPE_RASTER = 1
# Columns that would tie a copied layer to data we do not copy (yet).
DROPPED_LAYER_LINKS = ("LayerLayerMaskMipmap", "LayerLayerMaskThumbnail", "ResizableOriginalMipmap",
                       "ComicFrameLineMipmap", "FirstLayerObject", "Manager3D", "Manager3DOd",
                       "SpecialRulerManager", "StreamLineIndex", "VoiceSpeakParam", "RulerVectorIndex",
                       "TimeLineOriginalMipmap", "TimeLineOriginalMaskMipmap")


def new_external_id() -> str:
    return "extrnlid" + uuid.uuid4().hex.upper()


def new_layer_uuid() -> str:
    """A layer uuid in CSP's 10-4-4-4-10 hex form."""
    text = uuid.uuid4().hex
    return f"{text[:10]}-{text[10:14]}-{text[14:18]}-{text[18:22]}-{text[22:32]}"


class RowCopier:
    """Copy rows (and everything they link to) from one database to another."""

    def __init__(self, source: sqlite3.Connection, source_payload: Callable[[str], bytes | None],
                 editor: "ClipEditor", payload_hook: PayloadHook | None = None) -> None:
        self.source = source
        self.source_payload = source_payload
        self.editor = editor
        self.payload_hook = payload_hook
        self.owner_layer = 0
        self.skip: set[tuple[str, str]] = set()
        self._done: dict[tuple[str, int], int] = {}
        self._externals = external_columns(source)

    def copy(self, table: str, main_id: int) -> int:
        """Copy row ``main_id`` of ``table``; return its new id in the target."""
        key = (table, main_id)
        if key in self._done:
            return self._done[key]
        row = self.source.execute(f'SELECT * FROM "{table}" WHERE MainId = ?', (main_id,)).fetchone()
        if row is None:
            raise CspFormatError(f"{table} {main_id} not found")
        new_id = allocate_id(self.editor.db, table)
        self._done[key] = new_id
        values = dict(zip(row.keys(), tuple(row)))
        self.editor.insert_row(table, self.translate(table, values, new_id))
        return new_id

    def translate(self, table: str, values: dict[str, object], new_id: int) -> dict[str, object]:
        """Rewrite ids, owner columns and external ids of one row."""
        infos = column_infos(self.source, table)
        result: dict[str, object] = {}
        for column, value in values.items():
            if column == "_PW_ID":
                continue
            info = infos.get(column)
            if column == "MainId":
                value = new_id
            elif (table, column) in self.skip:
                pass
            elif info is not None and info.owner_type == OWNER_CANVAS:
                value = self.editor.canvas_id
            elif info is not None and info.owner_type == OWNER_LAYER:
                value = self.owner_layer
            elif info is not None and info.link_table and isinstance(value, int) and value:
                value = self.copy(info.link_table, value)
            elif (table, column) in self._externals and isinstance(value, bytes) and value:
                value = self._copy_external(table, column, value.decode("ascii"))
            result[column] = value
        return result

    def _copy_external(self, table: str, column: str, external_id: str) -> bytes:
        new_id = new_external_id()
        payload = self.source_payload(external_id)
        if payload is not None:
            if self.payload_hook is not None:
                payload = self.payload_hook(table, column, payload)
            self.editor.externals[new_id] = payload
        return new_id.encode("ascii")


class ClipEditor:
    """A .clip template opened for editing (the template file is not changed)."""

    def __init__(self, template: str | Path) -> None:
        container = read_csf_container(template)
        self.db = open_sqlite_bytes(container.sqlite_bytes)
        self.file_id = head_file_id(container)
        ordered = sorted(container.external_chunks.items(), key=lambda item: item[1].header_offset)
        self.externals: dict[str, bytes] = {}
        for external_id, _ in ordered:
            payload = container.external_payload(external_id)
            if payload is not None:
                self.externals[external_id] = payload
        canvas = self.db.execute("SELECT MainId, CanvasRootFolder FROM Canvas").fetchone()
        self.canvas_id = int(canvas[0])
        self.root_id = int(canvas[1])

    # --- rows -------------------------------------------------------------
    def insert_row(self, table: str, values: dict[str, object]) -> None:
        columns = [column for column in values if column in set(column_names(self.db, table))]
        names = ", ".join(f'"{column}"' for column in columns)
        marks = ", ".join("?" for _ in columns)
        self.db.execute(f'INSERT INTO "{table}" ({names}) VALUES ({marks})', [values[c] for c in columns])

    def layer_row(self, layer_id: int) -> sqlite3.Row:
        row: sqlite3.Row | None = self.db.execute("SELECT * FROM Layer WHERE MainId = ?", (layer_id,)).fetchone()
        if row is None:
            raise CspFormatError(f"Layer {layer_id} not found in template")
        return row

    def update_layer(self, layer_id: int, **values: object) -> None:
        known = set(column_names(self.db, "Layer"))
        for column, value in values.items():
            if column in known:
                self.db.execute(f'UPDATE Layer SET "{column}" = ? WHERE MainId = ?', (value, layer_id))

    # --- layer tree ---------------------------------------------------------
    def children(self, folder_id: int) -> list[int]:
        result = []
        child = int(self.layer_row(folder_id)["LayerFirstChildIndex"] or 0)
        while child:
            result.append(child)
            child = int(self.layer_row(child)["LayerNextIndex"] or 0)
        return result

    def append_to_folder(self, folder_id: int, layer_id: int, *, below: int | None = None) -> None:
        """Put ``layer_id`` at the top of ``folder_id`` (or right below ``below``)."""
        siblings = self.children(folder_id)
        position = siblings.index(below) if below in siblings else len(siblings)
        siblings.insert(position, layer_id)
        self.update_layer(folder_id, LayerFirstChildIndex=siblings[0])
        for index, sibling in enumerate(siblings):
            following = siblings[index + 1] if index + 1 < len(siblings) else 0
            self.update_layer(sibling, LayerNextIndex=following)

    def first_raster_layer(self) -> int:
        """The template's raster layer, whose offscreens new layers reuse."""
        row = self.db.execute("SELECT MainId FROM Layer WHERE LayerType = ? ORDER BY MainId LIMIT 1",
                              (LAYER_TYPE_RASTER,)).fetchone()
        if row is None:
            raise CspFormatError("Template has no raster layer to copy offscreens from")
        return int(row[0])

    # --- adding layers -------------------------------------------------------
    def add_layer(self, source: sqlite3.Connection, source_payload: Callable[[str], bytes | None],
                  layer_id: int, *, row_hook: Callable[[dict[str, object]], None] | None = None,
                  payload_hook: PayloadHook | None = None) -> int:
        """Copy one layer row (without children) from ``source``; return the new id.

        The copy gets fresh render offscreens cloned from the template, no
        mask, offset (0, 0), and is not yet linked into the tree.
        """
        row = source.execute("SELECT * FROM Layer WHERE MainId = ?", (layer_id,)).fetchone()
        if row is None:
            raise CspFormatError(f"Source layer {layer_id} not found")
        new_id = allocate_id(self.db, "Layer")
        copier = RowCopier(source, source_payload, self, payload_hook)
        copier.owner_layer = new_id
        copier.skip = {("Layer", column) for column in
                       ("LayerRenderMipmap", "LayerRenderThumbnail", "LayerNextIndex", "LayerFirstChildIndex")}
        values = dict(zip(row.keys(), tuple(row)))
        for column in DROPPED_LAYER_LINKS:
            if column in values:
                values[column] = 0
        values = copier.translate("Layer", values, new_id)
        mipmap, thumbnail = self._clone_render_offscreens(new_id)
        values.update(LayerRenderMipmap=mipmap, LayerRenderThumbnail=thumbnail, LayerNextIndex=0,
                      LayerFirstChildIndex=0, LayerOffsetX=0, LayerOffsetY=0, LayerRenderOffscrOffsetX=0,
                      LayerRenderOffscrOffsetY=0, LayerMaskOffsetX=0, LayerMaskOffsetY=0,
                      LayerMaskOffscrOffsetX=0, LayerMaskOffscrOffsetY=0, LayerSelect=0,
                      LayerUuid=new_layer_uuid())
        if row_hook is not None:
            row_hook(values)
        self.insert_row("Layer", values)
        return new_id

    def _clone_render_offscreens(self, owner: int) -> tuple[int, int]:
        template = self.layer_row(self.first_raster_layer())
        copier = RowCopier(self.db, self.externals.get, self)
        copier.owner_layer = owner
        mipmap = copier.copy("Mipmap", int(template["LayerRenderMipmap"]))
        thumbnail = copier.copy("LayerThumbnail", int(template["LayerRenderThumbnail"]))
        return mipmap, thumbnail

    # --- pixels ---------------------------------------------------------------
    def set_layer_image(self, layer_id: int, image: Image.Image, position: tuple[int, int] = (0, 0)) -> None:
        """Store ``image`` placed at ``position`` (canvas px) as the layer's pixels, all zoom levels."""
        row = self.layer_row(layer_id)
        origin_x = int(row["LayerOffsetX"] or 0) + int(row["LayerRenderOffscrOffsetX"] or 0)
        origin_y = int(row["LayerOffsetY"] or 0) + int(row["LayerRenderOffscrOffsetY"] or 0)
        levels = self._mipmap_levels(int(row["LayerRenderMipmap"]))
        base_attribute = levels[0][1]
        base = parse_offscreen_attribute(base_attribute)
        full = Image.new("RGBA", (base.width, base.height), (0, 0, 0, 0))
        full.paste(image.convert("RGBA"), (position[0] - origin_x, position[1] - origin_y))
        for offscreen_id, attribute, external in levels:
            parameters = parse_offscreen_attribute(attribute)
            level_image = full if (parameters.width, parameters.height) == full.size else full.resize(
                (parameters.width, parameters.height), Image.Resampling.BOX)
            if not external:
                external = new_external_id()
                self.db.execute("UPDATE Offscreen SET BlockData = ? WHERE MainId = ?",
                                (external.encode("ascii"), offscreen_id))
            self.externals[external] = encode_offscreen_image(level_image, parameters)

    def _mipmap_levels(self, mipmap_id: int) -> list[tuple[int, bytes, str]]:
        info = self.db.execute("SELECT BaseMipmapInfo FROM Mipmap WHERE MainId = ?", (mipmap_id,)).fetchone()
        if info is None:
            raise CspFormatError(f"Mipmap {mipmap_id} not found")
        levels = []
        info_id = int(info[0])
        while info_id:
            offscreen_id, next_id = self.db.execute(
                "SELECT Offscreen, NextIndex FROM MipmapInfo WHERE MainId = ?", (info_id,)).fetchone()
            attribute, block = self.db.execute(
                "SELECT Attribute, BlockData FROM Offscreen WHERE MainId = ?", (offscreen_id,)).fetchone()
            levels.append((int(offscreen_id), bytes(attribute), bytes(block).decode("ascii") if block else ""))
            info_id = int(next_id or 0)
        return levels

    # --- saving ---------------------------------------------------------------
    def save(self, path: str | Path) -> Path:
        """Write the edited file; unreferenced external chunks are dropped."""
        referenced = self._referenced_externals()
        externals = [(key, payload) for key, payload in self.externals.items() if key in referenced]
        data = assemble_container(self.db, externals, self.file_id)
        output = Path(path)
        output.write_bytes(data)
        return output

    def _referenced_externals(self) -> set[str]:
        referenced: set[str] = set()
        for table, column in external_columns(self.db):
            if table not in {str(r[0]) for r in self.db.execute("SELECT name FROM sqlite_master")}:
                continue
            if column not in column_names(self.db, table):
                continue
            for (value,) in self.db.execute(f'SELECT "{column}" FROM "{table}"'):
                if isinstance(value, bytes) and value:
                    referenced.add(value.decode("ascii"))
        return referenced
