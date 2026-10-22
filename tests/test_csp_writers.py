"""Tests for the low-level .clip writers (container and pixel blocks).

Why: Written files must read back exactly; CSP rejects a file whose chunk
     offsets or block checksums are wrong.
"""
from __future__ import annotations

from pathlib import Path
import struct
import zlib

from PIL import Image
import pytest

from csp_fixtures import FixtureLayer, build_attribute, build_clip
from name_splitter.csp import read_clip
from name_splitter.csp.container import open_sqlite_bytes, parse_csf_container, read_csf_container
from name_splitter.csp.container_writer import assemble_container, head_file_id
from name_splitter.csp.offscreen import (
    decode_offscreen_image,
    decode_offscreen_region,
    iter_block_records,
    parse_offscreen_attribute,
)
from name_splitter.csp.offscreen_writer import encode_offscreen_image


def _pattern(width: int, height: int) -> Image.Image:
    image = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    image.paste((10, 20, 30, 255), (5, 5, 60, 60))
    image.paste((200, 100, 50, 128), (280, 270, 300, 290))
    return image


def test_container_rebuild_is_byte_identical(tmp_path: Path) -> None:
    path = build_clip(tmp_path / "page.clip", 320, 300,
                      [FixtureLayer(main_id=2, name="下描き", image=_pattern(320, 300))])
    container = read_csf_container(path)
    database = open_sqlite_bytes(container.sqlite_bytes)
    ordered = sorted(container.external_chunks.items(), key=lambda item: item[1].header_offset)
    externals = [(key, container.external_payload(key) or b"") for key, _ in ordered]
    rebuilt = assemble_container(database, externals, head_file_id(container))
    # The fixture writes a zero head; real files carry the SQLite offset there.
    head = struct.unpack(">QQQ", rebuilt[40:64])
    assert head[0] == 256 and rebuilt[head[1]:head[1] + 8] == b"CHNKSQLi"
    assert assemble_container(open_sqlite_bytes(parse_csf_container(rebuilt).sqlite_bytes), externals,
                              head_file_id(container)) == rebuilt


def test_container_adds_and_drops_externals(tmp_path: Path) -> None:
    path = build_clip(tmp_path / "page.clip", 320, 300,
                      [FixtureLayer(main_id=2, name="下描き", image=_pattern(320, 300))])
    container = read_csf_container(path)
    database = open_sqlite_bytes(container.sqlite_bytes)
    new_id = "extrnlid" + "A" * 32
    data = assemble_container(database, [(new_id, b"payload")], bytes(16))
    parsed = parse_csf_container(data)
    assert parsed.external_payload(new_id) == b"payload"
    index = dict(open_sqlite_bytes(parsed.sqlite_bytes).execute("SELECT ExternalID, Offset FROM ExternalChunk"))
    assert index == {new_id: parsed.external_chunks[new_id].header_offset}
    with pytest.raises(ValueError):
        assemble_container(database, [("short", b"")], bytes(16))


@pytest.mark.parametrize("gray", [False, True])
def test_offscreen_encode_round_trip(gray: bool) -> None:
    attribute = build_attribute(320, 300, gray)
    parameters = parse_offscreen_attribute(attribute)
    image = _pattern(320, 300)
    payload = encode_offscreen_image(image, parameters)
    decoded = decode_offscreen_image(attribute, payload)
    assert decoded is not None
    if not gray:
        assert decoded.tobytes() == image.tobytes()
    assert decoded.getpixel((10, 10))[3] == 255
    records = list(iter_block_records(payload))
    assert [index for index, _, data in records if data is not None] == [0, 3]
    assert records[0][2] is not None and records[0][2][:2] == b"\x78\x01"


def test_offscreen_checksums_match_block_data() -> None:
    attribute = build_attribute(320, 300, False)
    payload = encode_offscreen_image(_pattern(320, 300), parse_offscreen_attribute(attribute))
    name = "BlockCheckSum".encode("utf-16-be")
    tail = payload.index(name) + len(name)
    count = struct.unpack(">I", payload[tail + 4:tail + 8])[0]
    sums = struct.unpack(f">{count}I", payload[tail + 12:tail + 12 + 4 * count])
    for index, _, data in iter_block_records(payload):
        expected = 0 if data is None else zlib.adler32(struct.pack("<I", len(data)) + data)
        assert sums[index] == expected


def test_region_decoding_matches_full_image(tmp_path: Path) -> None:
    path = build_clip(tmp_path / "page.clip", 320, 300,
                      [FixtureLayer(main_id=2, name="下描き", image=_pattern(320, 300))])
    document = read_clip(path)
    layer = document.find_layer(2)
    full = document.render_layer_pixels(layer)
    assert full is not None
    box = (250, 240, 310, 295)
    assert document.layer_pixels_in_box(layer, box).tobytes() == full.crop(box).tobytes()
    attribute = build_attribute(320, 300, False)
    assert decode_offscreen_region(attribute, None, (0, 0, 4, 4)).getbbox() is None
