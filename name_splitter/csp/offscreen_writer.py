"""Encode raster pixels into the block payload of a .clip offscreen.

Why: Stage 3 writes raster layers (cropped and scaled parts of the name
     sheet) into page files. CSP checks each block with a checksum, so the
     payload must match the layout CSP writes byte for byte where possible.
How: Inverse of :mod:`offscreen`. Each 256x256 block holds an alpha plane
     followed by BGRX colour planes (or one gray plane). Blocks with no
     visible pixel are stored without data. CSP compresses with zlib at the
     fastest level (stream header ``78 01``), so the same level is used.
     The ``BlockCheckSum`` tail is the Adler-32 of ``u32le zlib length +
     zlib data`` (0 for empty blocks).
"""
from __future__ import annotations

import struct
import zlib

from PIL import Image

from .offscreen import BLOCK_PLANE_BYTES, BLOCK_RECORD_NAME, BLOCK_SIZE, OffscreenParameters

BLOCK_END_NAME = "BlockDataEndChunk"
STATUS_NAME = "BlockStatus"
CHECKSUM_NAME = "BlockCheckSum"
ZLIB_LEVEL = 1
TAIL_ENTRY_SIZE = 4
TAIL_HEADER = 12


def _name(text: str) -> bytes:
    return struct.pack(">I", len(text)) + text.encode("utf-16-be")


def encode_block_records(raw_blocks: list[bytes | None], raw_size: int) -> bytes:
    """Encode already-planar blocks (None = empty) into a full payload."""
    records: list[bytes] = []
    checksums: list[int] = []
    begin, end = _name(BLOCK_RECORD_NAME), _name(BLOCK_END_NAME)
    for index, raw in enumerate(raw_blocks):
        body = struct.pack(">IIIII", index, raw_size, BLOCK_SIZE, BLOCK_SIZE, int(raw is not None))
        checksum = 0
        if raw is not None:
            if len(raw) != raw_size:
                raise ValueError(f"Block {index} has {len(raw)} bytes, expected {raw_size}")
            compressed = zlib.compress(raw, ZLIB_LEVEL)
            data = struct.pack("<I", len(compressed)) + compressed
            checksum = zlib.adler32(data)
            body += struct.pack(">I", len(data)) + data
        record = begin + body + end
        records.append(struct.pack(">I", 4 + len(record)) + record)
        checksums.append(checksum)
    count = len(raw_blocks)
    status = _name(STATUS_NAME) + struct.pack(">III", TAIL_HEADER, count, TAIL_ENTRY_SIZE) + struct.pack(
        f">{count}I", *([1] * count))
    sums = _name(CHECKSUM_NAME) + struct.pack(">III", TAIL_HEADER, count, TAIL_ENTRY_SIZE) + struct.pack(
        f">{count}I", *checksums)
    content = b"".join(records) + status + sums
    return struct.pack(">Q", len(content)) + content


def image_to_blocks(image: Image.Image, parameters: OffscreenParameters) -> list[bytes | None]:
    """Split an RGBA image into planar blocks for an offscreen of ``parameters``.

    The image is placed at the offscreen's top-left; parts outside the
    offscreen are dropped. Fully transparent blocks become None.
    """
    if parameters.is_mask:
        raise ValueError("Mask offscreens are not supported yet")
    rgba = image.convert("RGBA")
    blocks: list[bytes | None] = []
    for index in range(parameters.blocks_x * parameters.blocks_y):
        row, column = divmod(index, parameters.blocks_x)
        left, top = column * BLOCK_SIZE, row * BLOCK_SIZE
        tile = rgba.crop((left, top, left + BLOCK_SIZE, top + BLOCK_SIZE))
        alpha = tile.getchannel("A")
        if alpha.getbbox() is None:
            blocks.append(None)
            continue
        if parameters.is_gray:
            color = tile.convert("RGB").convert("L").tobytes()
        else:
            color = tile.convert("RGB").tobytes("raw", "BGRX")
        blocks.append(alpha.tobytes() + color)
    return blocks


def encode_offscreen_image(image: Image.Image, parameters: OffscreenParameters) -> bytes:
    """Encode an RGBA image as the external payload of an offscreen."""
    raw_size = BLOCK_PLANE_BYTES * parameters.total_planes
    return encode_block_records(image_to_blocks(image, parameters), raw_size)
