"""Decode raster pixel data stored in .clip offscreens.

Why: Raster layer pixels in a .clip are split into 256x256 blocks, each
     zlib-compressed and stored in an external chunk. The offscreen's
     ``Attribute`` blob describes the canvas size, block grid and channel
     layout needed to put the blocks back together.
How: ``parse_offscreen_attribute`` reads the "Parameter" section of the
     attribute blob, ``iter_pixel_blocks`` walks the block records of the
     external chunk, and ``decode_offscreen_image`` assembles an RGBA image.

Format notes (observed on CSP files, big-endian unless noted):
    Attribute: u32 x4 header, then u32 name length + UTF-16 "Parameter",
        then width, height, blocks_x, blocks_y, pixel_kind,
        alpha_planes, color_planes, total_planes, ...
    External payload: u64 size, then records of
        u32 record_length, u32 name_length, UTF-16 name,
        and for "BlockDataBeginChunk": u32 block_index, u32 raw_size,
        u32 block_width, u32 block_height, u32 has_data,
        [u32 data_length, u32 zlib_length (little-endian), zlib bytes].
    A decompressed block holds ``total_planes`` planes of 256x256 bytes:
        plane 0 is alpha, then either BGRX (4 planes) or gray (1 plane).
"""
from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
import struct
import zlib

from PIL import Image

from .errors import CspFormatError

BLOCK_SIZE = 256
BLOCK_PLANE_BYTES = BLOCK_SIZE * BLOCK_SIZE
BLOCK_RECORD_NAME = "BlockDataBeginChunk"
PARAMETER_SECTION_NAME = "Parameter"
ATTRIBUTE_HEADER_SIZE = 16
PAYLOAD_HEADER_SIZE = 8


@dataclass(frozen=True)
class OffscreenParameters:
    """Geometry and channel layout of one offscreen."""

    width: int
    height: int
    blocks_x: int
    blocks_y: int
    pixel_kind: int
    alpha_planes: int
    color_planes: int
    total_planes: int

    @property
    def is_color(self) -> bool:
        return self.color_planes == 4

    @property
    def is_gray(self) -> bool:
        return self.color_planes == 1

    @property
    def is_mask(self) -> bool:
        return self.color_planes == 0


@dataclass(frozen=True)
class PixelBlock:
    """One decompressed 256x256 block."""

    index: int
    raw: bytes


def _read_u32(buffer: bytes, offset: int) -> int:
    if offset + 4 > len(buffer):
        raise CspFormatError(f"Unexpected end of data at offset {offset}")
    return int(struct.unpack(">I", buffer[offset:offset + 4])[0])


def _read_utf16_name(buffer: bytes, offset: int) -> tuple[str, int]:
    """Read a u32 length-prefixed UTF-16BE string; return (text, next offset)."""
    length = _read_u32(buffer, offset)
    start = offset + 4
    end = start + length * 2
    if end > len(buffer):
        raise CspFormatError(f"String at offset {offset} overruns the data")
    return buffer[start:end].decode("utf-16-be"), end


def parse_offscreen_attribute(attribute: bytes) -> OffscreenParameters:
    """Parse the "Parameter" section of an offscreen Attribute blob."""
    name, offset = _read_utf16_name(attribute, ATTRIBUTE_HEADER_SIZE)
    if name != PARAMETER_SECTION_NAME:
        raise CspFormatError(f"Unknown offscreen attribute section: {name!r}")
    values = [_read_u32(attribute, offset + 4 * index) for index in range(8)]
    parameters = OffscreenParameters(*values)
    expected_blocks_x = -(-parameters.width // BLOCK_SIZE)
    expected_blocks_y = -(-parameters.height // BLOCK_SIZE)
    if (parameters.blocks_x, parameters.blocks_y) != (expected_blocks_x, expected_blocks_y):
        raise CspFormatError(
            "Block grid does not match image size: "
            f"{parameters.blocks_x}x{parameters.blocks_y} for {parameters.width}x{parameters.height}"
        )
    return parameters


def iter_block_records(payload: bytes) -> Iterator[tuple[int, int, bytes | None]]:
    """Yield ``(block_index, raw_size, zlib data or None)`` for every block record.

    Nothing is decompressed, so this is cheap enough to find which blocks of
    a large name sheet hold pixels.
    """
    position = PAYLOAD_HEADER_SIZE
    while position + 8 <= len(payload):
        record_length = _read_u32(payload, position)
        # Trailing sections (BlockStatus, BlockCheckSum) use another layout,
        # so stop as soon as the record is not a block record.
        if _read_u32(payload, position + 4) != len(BLOCK_RECORD_NAME):
            break
        name, body = _read_utf16_name(payload, position + 4)
        if name != BLOCK_RECORD_NAME:
            break
        block_index = _read_u32(payload, body)
        raw_size = _read_u32(payload, body + 4)
        compressed = None
        if _read_u32(payload, body + 16):
            data_length = _read_u32(payload, body + 20)
            compressed = payload[body + 28:body + 24 + data_length]
        yield block_index, raw_size, compressed
        position += record_length


def iter_pixel_blocks(payload: bytes) -> Iterator[PixelBlock]:
    """Yield the blocks that carry data from an external chunk payload."""
    for block_index, raw_size, compressed in iter_block_records(payload):
        if compressed is None:
            continue
        try:
            raw = zlib.decompress(compressed)
        except zlib.error as exc:
            raise CspFormatError(f"Block {block_index} is not valid zlib data") from exc
        if len(raw) != raw_size:
            raise CspFormatError(f"Block {block_index} size mismatch: {len(raw)} != {raw_size}")
        yield PixelBlock(index=block_index, raw=raw)


def _block_to_image(raw: bytes, parameters: OffscreenParameters) -> Image.Image:
    size = (BLOCK_SIZE, BLOCK_SIZE)
    alpha = Image.frombytes("L", size, raw[:BLOCK_PLANE_BYTES])
    color_bytes = raw[BLOCK_PLANE_BYTES:]
    if parameters.is_color:
        color = Image.frombytes("RGB", size, color_bytes, "raw", "BGRX")
    elif parameters.is_gray:
        color = Image.frombytes("L", size, color_bytes[:BLOCK_PLANE_BYTES]).convert("RGB")
    else:
        # Mask offscreen: the single plane is the mask value itself.
        color = Image.new("RGB", size, (0, 0, 0))
    color.putalpha(alpha)
    return color


def decode_offscreen_image(attribute: bytes, payload: bytes | None) -> Image.Image | None:
    """Assemble the full RGBA image of an offscreen.

    Returns None when the offscreen stores no pixel data at all.
    """
    if payload is None:
        return None
    parameters = parse_offscreen_attribute(attribute)
    expected_raw = BLOCK_PLANE_BYTES * parameters.total_planes
    canvas = Image.new("RGBA", (parameters.width, parameters.height), (0, 0, 0, 0))
    block_count = parameters.blocks_x * parameters.blocks_y
    for block in iter_pixel_blocks(payload):
        if block.index >= block_count:
            raise CspFormatError(f"Block index {block.index} outside grid of {block_count}")
        if len(block.raw) != expected_raw:
            raise CspFormatError(
                f"Block {block.index} has {len(block.raw)} bytes, expected {expected_raw}"
            )
        row, column = divmod(block.index, parameters.blocks_x)
        canvas.paste(_block_to_image(block.raw, parameters), (column * BLOCK_SIZE, row * BLOCK_SIZE))
    return canvas
