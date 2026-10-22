"""Tests for the read-only .clip parser (container, layer tree, pixels).

Why: The .clip reader is the foundation of the layered page split. These
     tests pin the structure observed in real CSP files using small
     synthetic files built by ``csp_fixtures``.
"""
from __future__ import annotations

from pathlib import Path
import struct

from PIL import Image
import pytest

from csp_fixtures import FixtureLayer, build_block_payload, build_clip
from name_splitter.csp import CspFormatError, read_clip
from name_splitter.csp.container import parse_csf_container
from name_splitter.csp.offscreen import iter_pixel_blocks


def _sample_image(width: int, height: int) -> Image.Image:
    image = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    image.paste((255, 0, 0, 255), (10, 10, 40, 40))
    image.paste((0, 0, 255, 128), (300, 260, 310, 270))
    return image


@pytest.fixture()
def clip_path(tmp_path: Path) -> Path:
    layers = [
        FixtureLayer(main_id=2, name="用紙", layer_type=1584),
        FixtureLayer(main_id=3, name="下描き", image=_sample_image(320, 280), opacity=128),
        FixtureLayer(
            main_id=4, name="コマ 1", layer_type=0, folder=1, is_frame=True,
            children=[
                FixtureLayer(main_id=5, name="線画", image=_sample_image(320, 280), gray=True),
                FixtureLayer(main_id=6, name="セリフ", layer_type=0, text="こんにちは", offset=(-5, 7)),
                FixtureLayer(main_id=7, name="ベクター", layer_type=0, is_vector=True, visibility=0),
            ],
        ),
        FixtureLayer(main_id=8, name="フォルダー", layer_type=0, folder=17),
    ]
    return build_clip(tmp_path / "page.clip", 320, 280, layers)


def test_canvas_settings(clip_path: Path) -> None:
    document = read_clip(clip_path)
    assert (document.canvas.width_px, document.canvas.height_px) == (320, 280)
    assert document.canvas.unit == "px"
    assert document.preview_png is not None


def test_layer_tree_order_and_kinds(clip_path: Path) -> None:
    document = read_clip(clip_path)
    top = document.root.children
    assert [layer.name for layer in top] == ["用紙", "下描き", "コマ 1", "フォルダー"]
    assert [layer.kind for layer in top] == ["paper", "raster", "frame_folder", "folder"]
    frame = top[2]
    assert [child.kind for child in frame.children] == ["raster", "text", "vector"]
    assert frame.children[1].text == "こんにちは"
    assert (frame.children[1].offset_x, frame.children[1].offset_y) == (-5, 7)
    assert frame.children[2].visible is False
    assert top[1].opacity == pytest.approx(0.5)
    assert [layer.main_id for layer in document.iter_layers()] == [2, 3, 4, 5, 6, 7, 8]


def test_color_layer_pixels_round_trip(clip_path: Path) -> None:
    document = read_clip(clip_path)
    image = document.render_layer_pixels(document.find_layer(3))
    assert image is not None and image.size == (320, 280)
    assert image.getpixel((20, 20)) == (255, 0, 0, 255)
    assert image.getpixel((305, 265)) == (0, 0, 255, 128)
    assert image.getpixel((200, 100)) == (0, 0, 0, 0)


def test_gray_layer_pixels_round_trip(clip_path: Path) -> None:
    document = read_clip(clip_path)
    image = document.render_layer_pixels(document.find_layer(5))
    assert image is not None
    red_as_gray = Image.new("RGB", (1, 1), (255, 0, 0)).convert("L").getpixel((0, 0))
    assert image.getpixel((20, 20)) == (red_as_gray, red_as_gray, red_as_gray, 255)


def test_layers_without_pixels_return_none(clip_path: Path) -> None:
    document = read_clip(clip_path)
    assert document.render_layer_pixels(document.find_layer(6)) is None


def test_only_blocks_with_data_are_yielded() -> None:
    image = Image.new("RGBA", (600, 300), (0, 0, 0, 0))
    image.paste((1, 2, 3, 255), (520, 280, 530, 290))
    payload = build_block_payload(image, gray=False)
    assert [block.index for block in iter_pixel_blocks(payload)] == [5]


def test_rejects_non_clip_file(tmp_path: Path) -> None:
    path = tmp_path / "bad.clip"
    path.write_bytes(b"not a clip file at all.....")
    with pytest.raises(CspFormatError):
        read_clip(path)


def test_rejects_size_mismatch(clip_path: Path) -> None:
    data = bytearray(clip_path.read_bytes())
    data[8:16] = struct.pack(">Q", len(data) + 1)
    with pytest.raises(CspFormatError):
        parse_csf_container(bytes(data))


def test_reader_does_not_modify_file(clip_path: Path) -> None:
    before = clip_path.read_bytes()
    document = read_clip(clip_path)
    document.render_layer_pixels(document.find_layer(3))
    assert clip_path.read_bytes() == before


def test_database_fallback_without_deserialize(clip_path: Path) -> None:
    # Python 3.10 has no Connection.deserialize; the backup path must work too.
    import sqlite3

    from name_splitter.csp.container import _load_database_via_backup, read_csf_container

    target = sqlite3.connect(":memory:")
    _load_database_via_backup(read_csf_container(clip_path).sqlite_bytes, target)
    assert target.execute("SELECT count(*) FROM Layer").fetchone()[0] == 8
