"""Tests for vector data and text attribute readers.

Why: Splitting a name sheet moves vector objects and text blocks instead of
     cropping pixels, so their coordinates must be read and rewritten
     exactly. The layouts are pinned with synthetic payloads built the way
     real CSP files store them.
"""
from __future__ import annotations

from pathlib import Path
import struct

import pytest

from csp_fixtures import (
    OPEN,
    VECTOR_BRUSH_SIZE,
    FixtureLayer,
    build_clip,
    build_text_attributes,
    build_vector_payload,
    rectangle,
)
from name_splitter.csp import CspFormatError, inspect_file, read_clip
from name_splitter.csp.text_attributes import (
    build_tlv,
    parse_text_attributes,
    parse_tlv,
    split_attribute_array,
    transform_text_attributes,
)
from name_splitter.csp.vector import parse_vector_data, transform_vector_data


def test_vector_objects_round_trip() -> None:
    payload = build_vector_payload([rectangle(10, 20, 110, 220), (OPEN, [(0.5, 1.5), (30.25, 40.0)])])
    first, second = parse_vector_data(payload)
    assert first.closed and not second.closed
    assert first.points == ((10, 20), (110, 20), (110, 220), (10, 220))
    assert first.bbox == (8, 18, 112, 222)
    assert second.points == ((0.5, 1.5), (30.25, 40.0))


def test_vector_transform_moves_points_and_boxes() -> None:
    payload = build_vector_payload([rectangle(10, 20, 110, 220)])
    assert transform_vector_data(payload, 1.0, 0, 0) == payload
    moved = parse_vector_data(transform_vector_data(payload, 2.0, 5, -10))[0]
    assert moved.points[0] == (25, 30)
    assert moved.points[2] == (225, 430)
    assert moved.bbox == (21, 26, 229, 434)
    assert moved.brush_size == 2 * VECTOR_BRUSH_SIZE
    # Undecoded bytes (colours, pressure) stay as they were.
    assert len(transform_vector_data(payload, 2.0, 5, -10)) == len(payload)


def test_vector_rejects_truncated_payload() -> None:
    payload = build_vector_payload([rectangle(0, 0, 10, 10)])
    with pytest.raises(CspFormatError):
        parse_vector_data(payload[:-10])
    with pytest.raises(ValueError):
        transform_vector_data(payload, 0, 0, 0)


def test_text_attributes_parse_and_rebuild() -> None:
    blob = build_text_attributes((100, 200, 160, 500), font_size_pt=4.5, font_name="游明朝")
    assert build_tlv(parse_tlv(blob)) == blob
    attributes = parse_text_attributes(blob)
    assert attributes.bbox == (100, 200, 160, 500)
    assert attributes.font_size_pt == 4.5
    assert attributes.font_name == "游明朝"


def test_text_transform_scales_font_and_moves_bbox() -> None:
    blob = build_text_attributes((100, 200, 160, 500), font_size_pt=4.0)
    assert transform_text_attributes(blob, 1.0, 0, 0) == blob
    moved = parse_text_attributes(transform_text_attributes(blob, 4.0, -300, 10))
    assert moved.bbox == (100, 810, 340, 2010)
    assert moved.font_size_pt == 16.0
    unknown_before = dict(parse_tlv(blob))[0x0B]
    assert dict(parse_tlv(transform_text_attributes(blob, 4.0, 0, 0)))[0x0B] == unknown_before


def test_text_attribute_array_split() -> None:
    blocks = [build_text_attributes((0, 0, 10, 10)), build_text_attributes((5, 5, 20, 20))]
    array = b"".join(struct.pack("<I", len(block)) + block for block in blocks)
    assert split_attribute_array(array) == blocks
    with pytest.raises(CspFormatError):
        split_attribute_array(array[:-1])
    with pytest.raises(CspFormatError):
        parse_tlv(blocks[0][:-1])


def test_document_exposes_vectors_and_text(tmp_path: Path) -> None:
    layers = [
        FixtureLayer(main_id=2, name="用紙", layer_type=1584),
        FixtureLayer(main_id=3, name="枠", layer_type=0, offset=(10, -5),
                     vector_objects=[rectangle(20, 30, 120, 230)]),
        FixtureLayer(main_id=4, name="セリフ", layer_type=0, text="こんにちは", offset=(7, 3),
                     text_attributes=build_text_attributes((40, 50, 60, 150), 8.0),
                     text_attribute_array=[build_text_attributes((70, 80, 90, 180), 9.0)]),
    ]
    path = build_clip(tmp_path / "sheet.clip", 300, 300, layers)
    document = read_clip(path)
    vector_layer, text_layer = document.find_layer(3), document.find_layer(4)
    assert vector_layer.kind == "vector" and text_layer.kind == "text"
    assert len(document.vector_objects(vector_layer)) == 1
    assert [block.font_size_pt for block in document.text_blocks(text_layer)] == [8.0, 9.0]
    assert document.text_blocks(vector_layer) == []

    summary = inspect_file(path)
    by_id = {layer["id"]: layer for layer in summary["layers"]}
    assert by_id[3]["vector"] == {"objects": 1, "closed": 1, "bbox": [28, 23, 132, 227]}
    assert by_id[4]["text_blocks"][0]["bbox"] == [47, 53, 67, 153]
