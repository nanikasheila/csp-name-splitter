"""Build tiny synthetic .clip / .cmc files for tests.

Why: Real CSP files are large and contain the author's artwork, so they
     cannot live in the repository. These builders reproduce the structure
     observed in real files (see docs/formats/csp-file-format.md) with only
     the tables and columns the readers use.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import io
from pathlib import Path
import sqlite3
import struct
import tempfile
import zlib

from PIL import Image

BLOCK = 256


@dataclass
class FixtureLayer:
    main_id: int
    name: str
    layer_type: int = 1
    folder: int = 0
    visibility: int = 1
    opacity: int = 256
    offset: tuple[int, int] = (0, 0)
    text: str | None = None
    is_vector: bool = False
    is_frame: bool = False
    image: Image.Image | None = None
    gray: bool = False
    children: list["FixtureLayer"] = field(default_factory=list)
    vector_objects: list[tuple[int, list[tuple[float, float]]]] | None = None
    text_attributes: bytes | None = None
    text_attribute_array: list[bytes] | None = None


VECTOR_HEADER_SIZE = 92
VECTOR_POINT_SIZE = 88
VECTOR_BRUSH_SIZE = 4.0
CLOSED = 0x1111
OPEN = 0x11


def build_vector_payload(objects: list[tuple[int, list[tuple[float, float]]]]) -> bytes:
    """Encode ``(flags, points)`` objects in the observed VectorData layout."""
    body = b""
    for flags, points in objects:
        xs = [point[0] for point in points]
        ys = [point[1] for point in points]
        bbox = (int(min(xs)) - 2, int(min(ys)) - 2, int(max(xs)) + 2, int(max(ys)) + 2)
        header = struct.pack(">6I4i", VECTOR_HEADER_SIZE, 76, VECTOR_POINT_SIZE, VECTOR_POINT_SIZE,
                             len(points), flags, *bbox)
        brush = struct.pack(">dI", VECTOR_BRUSH_SIZE, 0)
        body += header.ljust(VECTOR_HEADER_SIZE - len(brush), b"\0") + brush
        for x, y in points:
            point = struct.pack(">2d4i", x, y, int(x) - 2, int(y) - 2, int(x) + 2, int(y) + 2)
            body += point.ljust(VECTOR_POINT_SIZE, b"\0")
    return struct.pack(">II", 0, len(body)) + body


def rectangle(x0: float, y0: float, x1: float, y1: float) -> tuple[int, list[tuple[float, float]]]:
    return CLOSED, [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]


def build_text_attributes(bbox: tuple[int, int, int, int], font_size_pt: float = 12.0,
                          font_name: str = "Font") -> bytes:
    """Encode the TLV attributes the text reader decodes (plus one unknown id)."""
    name = font_name.encode("utf-8")
    items = [
        (0x0B, b"\x01\x02"),
        (0x20, struct.pack("<i", round(font_size_pt * 100))),
        (0x2A, struct.pack("<4i", *bbox)),
        (0x39, struct.pack("<HH", 1, len(name)) + name + struct.pack("<H", 0)),
        (0x3F, struct.pack("<2i", bbox[2] - bbox[0], bbox[3] - bbox[1])),
    ]
    return b"".join(struct.pack("<II", key, len(value)) + value for key, value in items)


def _utf16_name(name: str) -> bytes:
    return struct.pack(">I", len(name)) + name.encode("utf-16-be")


def build_attribute(width: int, height: int, gray: bool) -> bytes:
    blocks_x, blocks_y = -(-width // BLOCK), -(-height // BLOCK)
    kind, color_planes = (17, 1) if gray else (33, 4)
    params = [width, height, blocks_x, blocks_y, kind, 1, color_planes, color_planes + 1]
    return struct.pack(">IIII", 16, 102, 42, 0) + _utf16_name("Parameter") + struct.pack(">8I", *params)


def build_block_payload(image: Image.Image, gray: bool) -> bytes:
    """Encode an RGBA image as CSP block records (alpha plane + color planes)."""
    rgba = image.convert("RGBA")
    width, height = rgba.size
    blocks_x, blocks_y = -(-width // BLOCK), -(-height // BLOCK)
    records = b""
    checksums: list[int] = []
    for index in range(blocks_x * blocks_y):
        row, column = divmod(index, blocks_x)
        tile = Image.new("RGBA", (BLOCK, BLOCK), (0, 0, 0, 0))
        tile.paste(rgba.crop((column * BLOCK, row * BLOCK, (column + 1) * BLOCK, (row + 1) * BLOCK)))
        alpha = tile.getchannel("A").tobytes()
        if gray:
            color = tile.convert("L").tobytes()
        else:
            color = tile.convert("RGB").tobytes("raw", "BGRX")
        raw = alpha + color
        has_data = tile.getchannel("A").getbbox() is not None
        body = struct.pack(">IIIII", index, len(raw), BLOCK, BLOCK, int(has_data))
        checksum = 0
        if has_data:
            compressed = zlib.compress(raw)
            data = struct.pack("<I", len(compressed)) + compressed
            checksum = zlib.adler32(data)
            body += struct.pack(">I", len(data)) + data
        body += _utf16_name("BlockDataEndChunk")
        head = _utf16_name("BlockDataBeginChunk")
        records += struct.pack(">I", 4 + len(head) + len(body)) + head + body
        checksums.append(checksum)
    count = blocks_x * blocks_y
    status = _utf16_name("BlockStatus") + struct.pack(">III", 12, count, 4) + struct.pack(f">{count}I", *([1] * count))
    sums = _utf16_name("BlockCheckSum") + struct.pack(">III", 12, count, 4) + struct.pack(f">{count}I", *checksums)
    content = records + status + sums
    return struct.pack(">Q", len(content)) + content


def _flatten(layers: list[FixtureLayer]) -> list[FixtureLayer]:
    result: list[FixtureLayer] = []
    for layer in layers:
        result.append(layer)
        result.extend(_flatten(layer.children))
    return result


def build_clip(path: Path, width: int, height: int, layers: list[FixtureLayer], preview: bool | Image.Image = True,
               double_page: bool = False, editable: bool = False) -> Path:
    """Write a minimal .clip file whose root folder contains ``layers``.

    ``editable`` adds what the writers need from a CSP file: the schema
    tables (ParamScheme, ElemScheme, ExternalTableAndColumnName), layer
    thumbnails, mipmap chains and the page position columns.
    """
    root = FixtureLayer(main_id=1, name="", layer_type=256, folder=1, children=layers)
    database = sqlite3.connect(":memory:")
    database.executescript(
        "CREATE TABLE Canvas(MainId, CanvasUnit, CanvasWidth, CanvasHeight, CanvasResolution,"
        " CanvasRootFolder, CanvasDoublePage);"
        "CREATE TABLE Layer(MainId, LayerName, LayerType, LayerFolder, LayerVisibility, LayerOpacity,"
        " LayerComposite, LayerOffsetX, LayerOffsetY, LayerClip, LayerLock, LayerNextIndex,"
        " LayerFirstChildIndex, LayerRenderMipmap, LayerLayerMaskMipmap, TextLayerString,"
        " ComicFrameLineMipmap, TextLayerAttributes, TextLayerAttributesArray,"
        " LayerRenderOffscrOffsetX, LayerRenderOffscrOffsetY);"
        "CREATE TABLE Mipmap(MainId, BaseMipmapInfo);"
        "CREATE TABLE MipmapInfo(MainId, Offscreen);"
        "CREATE TABLE Offscreen(MainId, Attribute, BlockData);"
        "CREATE TABLE ExternalChunk(ExternalID, Offset);"
        "CREATE TABLE CanvasPreview(ImageData);"
        "CREATE TABLE VectorObjectList(MainId, LayerId, VectorData);"
    )
    database.execute("INSERT INTO Canvas VALUES(1, 0, ?, ?, 350.0, 1, ?)", (width, height, int(double_page)))
    externals: list[tuple[str, bytes]] = []
    all_layers = [root] + _flatten(layers)
    for position, layer in enumerate(all_layers):
        siblings = _siblings_of(root, layer)
        next_id = 0
        if siblings is not None:
            index = siblings.index(layer)
            next_id = siblings[index + 1].main_id if index + 1 < len(siblings) else 0
        first_child = layer.children[0].main_id if layer.children else 0
        mipmap = 0
        if layer.image is not None:
            mipmap = 1000 + position
            external_id = f"extrnlid{position:032X}"
            database.execute("INSERT INTO Mipmap VALUES(?, ?)", (mipmap, mipmap))
            database.execute("INSERT INTO MipmapInfo VALUES(?, ?)", (mipmap, mipmap))
            database.execute(
                "INSERT INTO Offscreen VALUES(?, ?, ?)",
                (mipmap, build_attribute(*layer.image.size, layer.gray), external_id.encode()),
            )
            externals.append((external_id, build_block_payload(layer.image, layer.gray)))
        database.execute(
            "INSERT INTO Layer VALUES(?,?,?,?,?,?,0,?,?,0,0,?,?,?,0,?,?,?,?,0,0)",
            (
                layer.main_id, layer.name, layer.layer_type, layer.folder, layer.visibility,
                layer.opacity, layer.offset[0], layer.offset[1], next_id, first_child, mipmap,
                layer.text.encode("utf-8") if layer.text is not None else None,
                99 if layer.is_frame else None,
                layer.text_attributes,
                _attribute_array(layer.text_attribute_array),
            ),
        )
        if layer.is_vector or layer.vector_objects is not None:
            vector_id = None
            if layer.vector_objects is not None:
                vector_id = f"extrnlidV{position:031X}"
                externals.append((vector_id, build_vector_payload(layer.vector_objects)))
            database.execute(
                "INSERT INTO VectorObjectList VALUES(?, ?, ?)",
                (layer.main_id, layer.main_id, vector_id.encode() if vector_id else None),
            )
    if isinstance(preview, Image.Image):
        buffer = io.BytesIO()
        preview.save(buffer, format="PNG")
        database.execute("INSERT INTO CanvasPreview VALUES(?)", (buffer.getvalue(),))
    elif preview:
        database.execute("INSERT INTO CanvasPreview VALUES(?)", (b"\x89PNG fake",),)
    if editable:
        _add_editing_schema(database)
        if double_page:  # CSP adds these for the second page's story info on spreads only
            database.executescript(
                "ALTER TABLE Canvas ADD COLUMN ComicStoryRightLayerCreated;"
                "ALTER TABLE Canvas ADD COLUMN ComicNombreRightLayerCreated;"
                "UPDATE Canvas SET ComicStoryRightLayerCreated = 1, ComicNombreRightLayerCreated = 1;")
    return _write_container(path, database, externals)


# (table, column, link table, owner type) as CSP lists them in ParamScheme.
EDITING_SCHEME = [
    ("Layer", "LayerRenderMipmap", "Mipmap", 0),
    ("Layer", "LayerRenderThumbnail", "LayerThumbnail", 0),
    ("Layer", "VectorNormalStrokeIndex", "VectorObjectList", 0),
    ("Mipmap", "BaseMipmapInfo", "MipmapInfo", 0),
    ("Mipmap", "LayerId", "", 4),
    ("MipmapInfo", "Offscreen", "Offscreen", 0),
    ("MipmapInfo", "LayerId", "", 4),
    ("Offscreen", "LayerId", "", 4),
    ("LayerThumbnail", "LayerId", "", 4),
    ("VectorObjectList", "LayerId", "", 4),
]


def _add_editing_schema(database: sqlite3.Connection) -> None:
    database.executescript(
        "ALTER TABLE Canvas ADD COLUMN ComicPageIndex;"
        "ALTER TABLE Canvas ADD COLUMN ComicIsLeftPage;"
        "ALTER TABLE Canvas ADD COLUMN ComicStoryStoryName;"
        "ALTER TABLE Canvas ADD COLUMN ComicStoryStoryIndex;"
        "UPDATE Canvas SET ComicPageIndex = 0, ComicIsLeftPage = 1, ComicStoryStoryName = 'Template',"
        " ComicStoryStoryIndex = 3;"
        "ALTER TABLE Layer ADD COLUMN LayerRenderThumbnail;"
        "ALTER TABLE Layer ADD COLUMN LayerUuid;"
        "UPDATE Layer SET LayerUuid = 'fixture-layer-' || MainId;"
        "ALTER TABLE Layer ADD COLUMN VectorNormalStrokeIndex;"
        "ALTER TABLE Layer ADD COLUMN ComicStoryInfoType;"
        "UPDATE Layer SET ComicStoryInfoType = 1 WHERE LayerType = 800;"
        "UPDATE Layer SET VectorNormalStrokeIndex = (SELECT MainId FROM VectorObjectList v WHERE v.LayerId = Layer.MainId);"
        "ALTER TABLE Mipmap ADD COLUMN LayerId;"
        "ALTER TABLE MipmapInfo ADD COLUMN LayerId;"
        "ALTER TABLE MipmapInfo ADD COLUMN NextIndex;"
        "ALTER TABLE Offscreen ADD COLUMN LayerId;"
        "CREATE TABLE LayerThumbnail(MainId, LayerId);"
        "CREATE TABLE ParamScheme(TableName, LabelName, LinkTable, OwnerType);"
        "CREATE TABLE ElemScheme(TableName, ElemType, MaxIndex);"
        "CREATE TABLE ExternalTableAndColumnName(TableName, ColumnName);"
        "INSERT INTO ExternalTableAndColumnName VALUES('Offscreen', 'BlockData'), ('VectorObjectList', 'VectorData');"
    )
    database.executemany("INSERT INTO ParamScheme VALUES(?, ?, ?, ?)", EDITING_SCHEME)
    for layer_id, mipmap in database.execute("SELECT MainId, LayerRenderMipmap FROM Layer").fetchall():
        if mipmap:
            database.execute("INSERT INTO LayerThumbnail VALUES(?, ?)", (mipmap, layer_id))
            database.execute("UPDATE Layer SET LayerRenderThumbnail = ? WHERE MainId = ?", (mipmap, layer_id))
            for table in ("Mipmap", "MipmapInfo", "Offscreen"):
                database.execute(f"UPDATE {table} SET LayerId = ? WHERE MainId = ?", (layer_id, mipmap))
    database.execute("UPDATE MipmapInfo SET NextIndex = 0")
    for table in ("Layer", "Mipmap", "MipmapInfo", "Offscreen", "LayerThumbnail", "VectorObjectList"):
        top = database.execute(f"SELECT COALESCE(MAX(MainId), 0) FROM {table}").fetchone()[0]
        database.execute("INSERT INTO ElemScheme VALUES(?, 0, ?)", (table, top))


def _attribute_array(blocks: list[bytes] | None) -> bytes | None:
    if blocks is None:
        return None
    return b"".join(struct.pack("<I", len(block)) + block for block in blocks)


def _siblings_of(root: FixtureLayer, target: FixtureLayer) -> list[FixtureLayer] | None:
    for layer in [root] + _flatten(root.children):
        if target in layer.children:
            return layer.children
    return None


def _write_container(path: Path, database: sqlite3.Connection, externals: list[tuple[str, bytes]]) -> Path:
    chunks = [b"CHNKHead" + struct.pack(">Q", 40) + bytes(40)]
    offset = 24 + len(chunks[0])
    for external_id, payload in externals:
        database.execute("INSERT INTO ExternalChunk VALUES(?, ?)", (external_id, offset))
        body = struct.pack(">Q", 40) + external_id.encode() + payload
        chunk = b"CHNKExta" + struct.pack(">Q", len(body)) + body
        chunks.append(chunk)
        offset += len(chunk)
    database.commit()
    with tempfile.TemporaryDirectory() as folder:
        db_path = Path(folder) / "db.sqlite"
        target = sqlite3.connect(db_path)
        database.backup(target)
        target.close()
        sqlite_bytes = db_path.read_bytes()
    chunks.append(b"CHNKSQLi" + struct.pack(">Q", len(sqlite_bytes)) + sqlite_bytes)
    chunks.append(b"CHNKFoot" + struct.pack(">Q", 0))
    body = b"".join(chunks)
    path.write_bytes(b"CSFCHUNK" + struct.pack(">QQ", 24 + len(body), 24) + body)
    return path


def build_cmc(path: Path, page_files: list[str], order: list[int] | None = None) -> Path:
    """Write a minimal .cmc whose pages link to ``page_files`` in ``order``."""
    order = order or list(range(len(page_files)))
    database = sqlite3.connect(path)
    database.executescript(
        "CREATE TABLE Project(ProjectInternalVersion, ProjectRootCanvasNode, ComicStoryStoryName,"
        " ComicStoryAuthorName, ComicBindPosition, ComicStartPage, ComicCoverExist, MaxCanvasFileIndex,"
        " DefaultPageUnit, DefaultPageWidth, DefaultPageHeight, DefaultPageResolution,"
        " DefaultPageDoublePage, DefaultPageTemplateName);"
        "CREATE TABLE CanvasNode(MainId, Type, NextIndex, FirstChildIndex, PageFlag, Memo, LinkPath);"
    )
    database.execute(
        "INSERT INTO Project VALUES('1.1.0', 1, 'Story', 'Author', 1, 1, 0, ?, 2, 182.0, 257.0, 600.0, 0, '')",
        (len(page_files),),
    )
    database.execute("ALTER TABLE Project ADD COLUMN ComicStoryStoryIndex DEFAULT 3")
    node_ids = [index + 2 for index in range(len(page_files))]
    sequence = [node_ids[index] for index in order]
    database.execute("INSERT INTO CanvasNode VALUES(1, 0, 0, ?, 0, '', NULL)", (sequence[0],))
    for position, node_id in enumerate(sequence):
        next_id = sequence[position + 1] if position + 1 < len(sequence) else 0
        file_name = page_files[node_id - 2]
        database.execute(
            "INSERT INTO CanvasNode VALUES(?, 2, ?, 0, 0, '', ?)", (node_id, next_id, f".:{file_name}")
        )
    database.commit()
    database.close()
    return path
