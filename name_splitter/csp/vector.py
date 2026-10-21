"""Read and move the vector objects of a CSP vector layer (``VectorData``).

Why: Vector layers (ネーム frames, lines, balloons) store no pixels; CSP
     redraws them from ``VectorObjectList.VectorData`` when the file opens.
     Splitting a name sheet into pages therefore has to copy this data and
     move / scale its coordinates instead of cropping pixels.
How: ``VectorData`` is an external chunk (big endian). Observed layout:

         u32 0, u32 length of the rest
         object × n:
           header (header_size bytes):
             u32 header_size, u32 ?, u32 point_size, u32 ?, u32 point_count,
             u32 flags, i32 bbox[4] (x0, y0, x1, y1), ...
           point × point_count (point_size bytes each):
             f64 x, f64 y, i32 segment bbox[4], ...

     Coordinates are in canvas pixels before ``LayerOffsetX/Y`` is added.
     Fields shown as ``...`` (colours, brush size, pressure) are not decoded
     and are copied unchanged by :func:`transform_vector_data`.
"""
from __future__ import annotations

from dataclasses import dataclass
import math
import struct

from .errors import CspFormatError

OBJECT_HEADER = struct.Struct(">6I4i")
POINT_HEAD = struct.Struct(">2d4i")
PAYLOAD_HEAD = struct.Struct(">II")
CLOSED_FLAG = 0x1000

BBox = tuple[int, int, int, int]


@dataclass(frozen=True)
class VectorObject:
    """One stroke or shape in a vector layer (layer-local coordinates)."""

    flags: int
    bbox: BBox
    points: tuple[tuple[float, float], ...]

    @property
    def closed(self) -> bool:
        """Whether the shape is closed (observed for rectangles and balloons)."""
        return bool(self.flags & CLOSED_FLAG)


@dataclass(frozen=True)
class _ObjectSpan:
    start: int
    header_size: int
    point_size: int
    point_count: int


def parse_vector_data(payload: bytes) -> list[VectorObject]:
    """Decode all objects of a ``VectorData`` payload."""
    objects: list[VectorObject] = []
    for span in _iter_spans(payload):
        _, _, _, _, _, flags, *bbox = OBJECT_HEADER.unpack_from(payload, span.start)
        points = []
        for index in range(span.point_count):
            x, y, *_ = POINT_HEAD.unpack_from(payload, _point_offset(span, index))
            points.append((x, y))
        objects.append(VectorObject(flags=flags, bbox=_bbox(bbox), points=tuple(points)))
    return objects


def transform_vector_data(payload: bytes, scale: float, dx: float, dy: float) -> bytes:
    """Return a copy of ``payload`` with every coordinate mapped to ``p * scale + d``.

    Why: Moving a page cell of a name sheet onto its own page canvas.
    How: Rewrites point positions, segment bounding boxes and object
         bounding boxes in place. Line widths are not scaled yet.
    """
    if scale <= 0:
        raise ValueError("scale must be positive")
    data = bytearray(payload)
    for span in _iter_spans(payload):
        bbox_offset = span.start + 24
        bbox = struct.unpack_from(">4i", data, bbox_offset)
        struct.pack_into(">4i", data, bbox_offset, *_map_bbox(bbox, scale, dx, dy))
        for index in range(span.point_count):
            offset = _point_offset(span, index)
            x, y, *segment = POINT_HEAD.unpack_from(data, offset)
            mapped = _map_bbox(tuple(segment), scale, dx, dy)
            POINT_HEAD.pack_into(data, offset, x * scale + dx, y * scale + dy, *mapped)
    return bytes(data)


def select_vector_objects(payload: bytes, indexes: tuple[int, ...] | list[int]) -> bytes:
    """Return a payload that keeps only the objects at ``indexes`` (in order)."""
    spans = _iter_spans(payload)
    keep = set(indexes)
    body = b"".join(
        payload[span.start:span.start + span.header_size + span.point_size * span.point_count]
        for index, span in enumerate(spans) if index in keep
    )
    return PAYLOAD_HEAD.pack(0, len(body)) + body


def _iter_spans(payload: bytes) -> list[_ObjectSpan]:
    if len(payload) < PAYLOAD_HEAD.size:
        raise CspFormatError("VectorData is too short")
    _, length = PAYLOAD_HEAD.unpack_from(payload, 0)
    end = PAYLOAD_HEAD.size + length
    if end > len(payload):
        raise CspFormatError("VectorData length exceeds the payload")
    spans: list[_ObjectSpan] = []
    position = PAYLOAD_HEAD.size
    while position < end:
        if position + OBJECT_HEADER.size > end:
            raise CspFormatError(f"Truncated vector object at {position}")
        header_size, _, point_size, _, point_count, _ = struct.unpack_from(">6I", payload, position)
        if header_size < OBJECT_HEADER.size or point_size < POINT_HEAD.size:
            raise CspFormatError(f"Unexpected vector object layout at {position}")
        span = _ObjectSpan(position, header_size, point_size, point_count)
        position += header_size + point_size * point_count
        if position > end:
            raise CspFormatError("Vector object exceeds VectorData length")
        spans.append(span)
    return spans


def _point_offset(span: _ObjectSpan, index: int) -> int:
    return span.start + span.header_size + index * span.point_size


def _bbox(values: list[int]) -> BBox:
    return (values[0], values[1], values[2], values[3])


def _map_bbox(bbox: tuple[int, ...], scale: float, dx: float, dy: float) -> BBox:
    x0, y0, x1, y1 = bbox
    return (
        math.floor(x0 * scale + dx),
        math.floor(y0 * scale + dy),
        math.ceil(x1 * scale + dx),
        math.ceil(y1 * scale + dy),
    )
