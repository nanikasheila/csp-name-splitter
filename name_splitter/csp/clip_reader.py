"""Read the layer structure and raster pixels of a CLIP STUDIO .clip file.

Why: The original goal of this tool is to split a name (storyboard) drawn in
     CSP while keeping its layers. That needs the .clip layer tree (names,
     folders, visibility, opacity, offsets) and the pixels of raster layers.
How: Opens the CSF container, reads the ``Canvas`` and ``Layer`` tables of
     the embedded SQLite database, rebuilds the tree from the
     first-child / next-sibling links, and decodes raster pixels on demand.
     Everything is read-only.

Layer tree notes:
    ``Canvas.CanvasRootFolder`` is the root folder's ``Layer.MainId``.
    ``LayerFirstChildIndex`` and ``LayerNextIndex`` hold MainIds (0 = none).
    Siblings are listed from bottom to top (the paper layer comes first).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import sqlite3

from PIL import Image

from .container import CsfContainer, open_sqlite_bytes, read_csf_container
from .errors import CspFormatError
from .offscreen import OffscreenParameters, decode_offscreen_image, parse_offscreen_attribute

LAYER_TYPE_RASTER = 1
LAYER_TYPE_ROOT = 256
LAYER_TYPE_STORY_INFO = 800
LAYER_TYPE_PAPER = 1584
LAYER_FOLDER_FLAG = 1
LAYER_VISIBLE_FLAG = 1
FULL_OPACITY = 256
MAX_LAYER_DEPTH = 64

CANVAS_UNIT_NAMES = {0: "px", 1: "cm", 2: "mm", 3: "inch", 5: "pt"}


@dataclass(frozen=True)
class ClipCanvas:
    """Canvas (page) settings stored in a .clip file."""

    width: float
    height: float
    unit: str
    resolution: float
    width_px: int
    height_px: int
    is_double_page: bool


@dataclass(frozen=True)
class ClipLayer:
    """One layer or folder in a .clip layer tree."""

    main_id: int
    name: str
    kind: str
    layer_type: int
    visible: bool
    opacity: float
    composite: int
    offset_x: int
    offset_y: int
    clipping: bool
    locked: bool
    has_mask: bool
    render_mipmap: int
    mask_mipmap: int
    text: str | None = None
    children: tuple["ClipLayer", ...] = field(default=())

    @property
    def is_folder(self) -> bool:
        return self.kind in ("folder", "frame_folder", "root")


@dataclass(frozen=True)
class ClipDocument:
    """Parsed .clip file: canvas settings, layer tree and preview."""

    path: Path
    canvas: ClipCanvas
    root: ClipLayer
    preview_png: bytes | None
    container: CsfContainer = field(repr=False)

    def iter_layers(self) -> list[ClipLayer]:
        """Return all layers depth-first, bottom to top (root excluded)."""
        result: list[ClipLayer] = []
        stack = [iter(self.root.children)]
        while stack:
            layer = next(stack[-1], None)
            if layer is None:
                stack.pop()
                continue
            result.append(layer)
            if layer.children:
                stack.append(iter(layer.children))
        return result

    def find_layer(self, main_id: int) -> ClipLayer:
        for layer in self.iter_layers():
            if layer.main_id == main_id:
                return layer
        raise CspFormatError(f"Layer {main_id} not found in {self.path}")

    def render_layer_pixels(self, layer: ClipLayer) -> Image.Image | None:
        """Decode the stored pixels of a layer, or None if none are stored.

        Vector and text layers usually have no stored pixels: CSP redraws
        them from their own data when the file is opened.
        """
        return _decode_mipmap(self.container, layer.render_mipmap)

    def layer_pixel_parameters(self, layer: ClipLayer) -> OffscreenParameters | None:
        """Return the offscreen geometry of a layer's render image."""
        attribute, _ = _base_offscreen(self.container, layer.render_mipmap)
        return None if attribute is None else parse_offscreen_attribute(attribute)


def read_clip(path: str | Path) -> ClipDocument:
    """Read a .clip file's canvas, layer tree and preview image."""
    container = read_csf_container(path)
    connection = open_sqlite_bytes(container.sqlite_bytes)
    try:
        canvas_row = connection.execute("SELECT * FROM Canvas").fetchone()
        if canvas_row is None:
            raise CspFormatError(f"Canvas row not found: {path}")
        canvas = _build_canvas(canvas_row)
        root = _build_layer_tree(connection, int(canvas_row["CanvasRootFolder"]))
        preview = _read_preview(connection)
    finally:
        connection.close()
    return ClipDocument(path=Path(path), canvas=canvas, root=root, preview_png=preview, container=container)


def _build_canvas(row: sqlite3.Row) -> ClipCanvas:
    unit = CANVAS_UNIT_NAMES.get(int(row["CanvasUnit"]), f"unit{row['CanvasUnit']}")
    width = float(row["CanvasWidth"])
    height = float(row["CanvasHeight"])
    resolution = float(row["CanvasResolution"])
    return ClipCanvas(
        width=width,
        height=height,
        unit=unit,
        resolution=resolution,
        width_px=_to_pixels(width, unit, resolution),
        height_px=_to_pixels(height, unit, resolution),
        is_double_page=bool(row["CanvasDoublePage"]) if "CanvasDoublePage" in row.keys() else False,
    )


def _to_pixels(value: float, unit: str, resolution: float) -> int:
    per_inch = {"px": None, "mm": 25.4, "cm": 2.54, "inch": 1.0, "pt": 72.0}.get(unit)
    if per_inch is None:
        return round(value)
    return round(value * resolution / per_inch)


def _optional(row: sqlite3.Row, column: str) -> object | None:
    return row[column] if column in row.keys() else None


def _classify_layer(row: sqlite3.Row, vector_layer_ids: set[int]) -> str:
    layer_type = int(row["LayerType"])
    if layer_type == LAYER_TYPE_ROOT:
        return "root"
    if layer_type == LAYER_TYPE_PAPER:
        return "paper"
    if layer_type == LAYER_TYPE_STORY_INFO:
        return "story_info"
    if layer_type == LAYER_TYPE_RASTER:
        return "raster"
    if int(row["LayerFolder"] or 0) & LAYER_FOLDER_FLAG:
        return "frame_folder" if _optional(row, "ComicFrameLineMipmap") else "folder"
    if _optional(row, "TextLayerString") is not None:
        return "text"
    if int(row["MainId"]) in vector_layer_ids:
        return "vector"
    return "other"


def _decode_text(value: object | None) -> str | None:
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return value if isinstance(value, str) else None


def _build_layer_tree(connection: sqlite3.Connection, root_id: int) -> ClipLayer:
    rows = {int(row["MainId"]): row for row in connection.execute("SELECT * FROM Layer")}
    vector_ids: set[int] = set()
    has_vector_table = connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='VectorObjectList'"
    ).fetchone()
    if has_vector_table:
        vector_ids = {int(r[0]) for r in connection.execute("SELECT LayerId FROM VectorObjectList")}
    if root_id not in rows:
        raise CspFormatError(f"Root folder {root_id} not found in Layer table")

    def build(main_id: int, depth: int, seen: set[int]) -> ClipLayer:
        if depth > MAX_LAYER_DEPTH:
            raise CspFormatError("Layer tree is nested too deeply")
        row = rows[main_id]
        children: list[ClipLayer] = []
        child_id = int(row["LayerFirstChildIndex"] or 0)
        while child_id:
            if child_id in seen or child_id not in rows:
                raise CspFormatError(f"Broken layer link to {child_id}")
            seen.add(child_id)
            children.append(build(child_id, depth + 1, seen))
            child_id = int(rows[child_id]["LayerNextIndex"] or 0)
        return ClipLayer(
            main_id=main_id,
            name=str(row["LayerName"] or ""),
            kind=_classify_layer(row, vector_ids),
            layer_type=int(row["LayerType"]),
            visible=bool(int(row["LayerVisibility"] or 0) & LAYER_VISIBLE_FLAG),
            opacity=int(row["LayerOpacity"]) / FULL_OPACITY,
            composite=int(row["LayerComposite"] or 0),
            offset_x=int(row["LayerOffsetX"] or 0),
            offset_y=int(row["LayerOffsetY"] or 0),
            clipping=bool(row["LayerClip"]),
            locked=bool(row["LayerLock"]),
            has_mask=bool(row["LayerLayerMaskMipmap"]),
            render_mipmap=int(row["LayerRenderMipmap"] or 0),
            mask_mipmap=int(row["LayerLayerMaskMipmap"] or 0),
            text=_decode_text(_optional(row, "TextLayerString")),
            children=tuple(children),
        )

    return build(root_id, 0, {root_id})


def _read_preview(connection: sqlite3.Connection) -> bytes | None:
    row = connection.execute("SELECT ImageData FROM CanvasPreview LIMIT 1").fetchone()
    return bytes(row[0]) if row and row[0] else None


def _base_offscreen(container: CsfContainer, mipmap_id: int) -> tuple[bytes | None, bytes | None]:
    """Return (Attribute, external payload) of the 100% mipmap level."""
    if not mipmap_id:
        return None, None
    connection = open_sqlite_bytes(container.sqlite_bytes)
    try:
        row = connection.execute(
            "SELECT o.Attribute, o.BlockData FROM Mipmap m "
            "JOIN MipmapInfo i ON i.MainId = m.BaseMipmapInfo "
            "JOIN Offscreen o ON o.MainId = i.Offscreen WHERE m.MainId = ?",
            (mipmap_id,),
        ).fetchone()
    finally:
        connection.close()
    if row is None:
        raise CspFormatError(f"Mipmap {mipmap_id} has no base offscreen")
    attribute, block_data = row
    external_id = bytes(block_data).decode("ascii") if block_data else ""
    return bytes(attribute), container.external_payload(external_id)


def _decode_mipmap(container: CsfContainer, mipmap_id: int) -> Image.Image | None:
    attribute, payload = _base_offscreen(container, mipmap_id)
    if attribute is None:
        return None
    return decode_offscreen_image(attribute, payload)
