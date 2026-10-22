"""Read and move the attributes of a CSP text layer.

Why: Text layers store no pixels in name sheets; CSP lays the text out
     again from ``TextLayerString`` and ``TextLayerAttributes``. Splitting a
     sheet into pages needs each text's position and font size so it can be
     assigned to a page and moved / scaled there.
How: ``TextLayerAttributes`` is a little-endian TLV list
     (``u32 id, u32 size, bytes``). Observed ids:

         0x20  i32 font size × 100 (pt)
         0x2a  i32 bbox[4] (x0, y0, x1, y1), canvas px before LayerOffset
         0x39  font name (u16 ?, u16 len, UTF-8, u16 len, PostScript name)
         0x3f  i32 text block size (w, h) in px
         0x40  i32 quad[8] in 1/100 px, relative to the text anchor

     ``TextLayerAttributesArray`` repeats ``u32 size + TLV list`` for every
     text block of a layer that has several (balloons). In files with
     balloons the bbox of most blocks is relative to something not yet
     identified (likely the balloon), so only layers whose bbox is absolute
     can be moved safely; see docs/formats/csp-file-format.md.
"""
from __future__ import annotations

from dataclasses import dataclass
import math
import struct

from .errors import CspFormatError

ATTR_FONT_SIZE = 0x20
ATTR_BBOX = 0x2A
ATTR_FONT_NAME = 0x39
ATTR_BLOCK_SIZE = 0x3F
ATTR_QUAD = 0x40
FONT_SIZE_UNIT = 100

TLV_HEAD = struct.Struct("<II")
BBox = tuple[int, int, int, int]


@dataclass(frozen=True)
class TextAttributes:
    """The decoded subset of one text block's attributes."""

    bbox: BBox | None
    font_size_pt: float | None
    font_name: str | None


def parse_tlv(blob: bytes) -> list[tuple[int, bytes]]:
    """Split a TLV attribute blob into ``(id, value)`` pairs, in order."""
    items: list[tuple[int, bytes]] = []
    position = 0
    while position < len(blob):
        if position + TLV_HEAD.size > len(blob):
            raise CspFormatError(f"Truncated text attribute at {position}")
        attribute_id, size = TLV_HEAD.unpack_from(blob, position)
        start = position + TLV_HEAD.size
        if start + size > len(blob):
            raise CspFormatError(f"Text attribute 0x{attribute_id:x} exceeds the blob")
        items.append((attribute_id, blob[start:start + size]))
        position = start + size
    return items


def build_tlv(items: list[tuple[int, bytes]]) -> bytes:
    """Inverse of :func:`parse_tlv`."""
    return b"".join(TLV_HEAD.pack(attribute_id, len(value)) + value for attribute_id, value in items)


def parse_text_attributes(blob: bytes) -> TextAttributes:
    """Decode the bbox, font size and font name of one text block."""
    values = dict(parse_tlv(blob))
    bbox_raw = values.get(ATTR_BBOX)
    size_raw = values.get(ATTR_FONT_SIZE)
    return TextAttributes(
        bbox=_unpack_bbox(bbox_raw) if bbox_raw and len(bbox_raw) == 16 else None,
        font_size_pt=struct.unpack("<i", size_raw)[0] / FONT_SIZE_UNIT if size_raw and len(size_raw) == 4 else None,
        font_name=_font_name(values.get(ATTR_FONT_NAME)),
    )


def split_attribute_array(blob: bytes) -> list[bytes]:
    """Split ``TextLayerAttributesArray`` into per-block TLV blobs."""
    blocks: list[bytes] = []
    position = 0
    while position < len(blob):
        if position + 4 > len(blob):
            raise CspFormatError("Truncated text attribute array")
        size = struct.unpack_from("<I", blob, position)[0]
        start = position + 4
        if start + size > len(blob):
            raise CspFormatError("Text attribute array entry exceeds the blob")
        blocks.append(blob[start:start + size])
        position = start + size
    return blocks


def transform_text_attributes(blob: bytes, scale: float, dx: float, dy: float) -> bytes:
    """Return ``blob`` with its bbox mapped to ``p * scale + d`` and sizes scaled.

    Why: A text block moves with its page cell; its font grows with the
         cell so the page keeps the proportions of the name sheet.
    How: Rewrites ids 0x2a (bbox), 0x20 (font size), 0x3f (block size) and
         0x40 (quad). Everything else is copied unchanged.
    """
    if scale <= 0:
        raise ValueError("scale must be positive")
    items: list[tuple[int, bytes]] = []
    for attribute_id, value in parse_tlv(blob):
        if attribute_id == ATTR_BBOX and len(value) == 16:
            x0, y0, x1, y1 = _unpack_bbox(value)
            value = struct.pack(
                "<4i",
                math.floor(x0 * scale + dx), math.floor(y0 * scale + dy),
                math.ceil(x1 * scale + dx), math.ceil(y1 * scale + dy),
            )
        elif attribute_id in (ATTR_FONT_SIZE, ATTR_BLOCK_SIZE, ATTR_QUAD) and value and len(value) % 4 == 0:
            numbers = struct.unpack(f"<{len(value) // 4}i", value)
            value = struct.pack(f"<{len(numbers)}i", *(round(number * scale) for number in numbers))
        items.append((attribute_id, value))
    return build_tlv(items)


def _unpack_bbox(value: bytes) -> BBox:
    x0, y0, x1, y1 = struct.unpack("<4i", value)
    return (x0, y0, x1, y1)


def _font_name(value: bytes | None) -> str | None:
    if not value or len(value) < 4:
        return None
    length = struct.unpack_from("<H", value, 2)[0]
    if 4 + length > len(value):
        return None
    return value[4:4 + length].decode("utf-8", errors="replace")
