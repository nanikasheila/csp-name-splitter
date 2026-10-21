"""Build tiny synthetic .clip / .cmc files for tests.

Why: Real CSP files are large and contain the author's artwork, so they
     cannot live in the repository. These builders reproduce the structure
     observed in real files (see docs/formats/csp-file-format.md) with only
     the tables and columns the readers use.
"""
from __future__ import annotations

from dataclasses import dataclass, field
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


def build_clip(path: Path, width: int, height: int, layers: list[FixtureLayer], preview: bool = True) -> Path:
    """Write a minimal .clip file whose root folder contains ``layers``."""
    root = FixtureLayer(main_id=1, name="", layer_type=256, folder=1, children=layers)
    database = sqlite3.connect(":memory:")
    database.executescript(
        "CREATE TABLE Canvas(MainId, CanvasUnit, CanvasWidth, CanvasHeight, CanvasResolution,"
        " CanvasRootFolder, CanvasDoublePage);"
        "CREATE TABLE Layer(MainId, LayerName, LayerType, LayerFolder, LayerVisibility, LayerOpacity,"
        " LayerComposite, LayerOffsetX, LayerOffsetY, LayerClip, LayerLock, LayerNextIndex,"
        " LayerFirstChildIndex, LayerRenderMipmap, LayerLayerMaskMipmap, TextLayerString,"
        " ComicFrameLineMipmap);"
        "CREATE TABLE Mipmap(MainId, BaseMipmapInfo);"
        "CREATE TABLE MipmapInfo(MainId, Offscreen);"
        "CREATE TABLE Offscreen(MainId, Attribute, BlockData);"
        "CREATE TABLE ExternalChunk(ExternalID, Offset);"
        "CREATE TABLE CanvasPreview(ImageData);"
        "CREATE TABLE VectorObjectList(LayerId);"
    )
    database.execute("INSERT INTO Canvas VALUES(1, 0, ?, ?, 350.0, 1, 0)", (width, height))
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
            "INSERT INTO Layer VALUES(?,?,?,?,?,?,0,?,?,0,0,?,?,?,0,?,?)",
            (
                layer.main_id, layer.name, layer.layer_type, layer.folder, layer.visibility,
                layer.opacity, layer.offset[0], layer.offset[1], next_id, first_child, mipmap,
                layer.text.encode("utf-8") if layer.text is not None else None,
                99 if layer.is_frame else None,
            ),
        )
        if layer.is_vector:
            database.execute("INSERT INTO VectorObjectList VALUES(?)", (layer.main_id,))
    if preview:
        database.execute("INSERT INTO CanvasPreview VALUES(?)", (b"\x89PNG fake",),)
    return _write_container(path, database, externals)


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
