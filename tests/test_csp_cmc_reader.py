"""Tests for the .cmc (multi-page work) reader and the inspect command."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from csp_fixtures import FixtureLayer, build_clip, build_cmc
from name_splitter.app.cli import main
from name_splitter.csp import CspFormatError, inspect_file, read_cmc
from name_splitter.csp.cmc_reader import link_path_to_file_name


def test_pages_follow_linked_list_order(tmp_path: Path) -> None:
    files = ["page0001.clip", "page0002.clip", "page0003.clip"]
    path = build_cmc(tmp_path / "work.cmc", files, order=[0, 2, 1])
    project = read_cmc(path)
    assert [page.file_name for page in project.pages] == ["page0001.clip", "page0003.clip", "page0002.clip"]
    assert [page.order for page in project.pages] == [1, 2, 3]
    assert project.page_file_paths()[1] == tmp_path / "page0003.clip"
    assert project.story_name == "Story"
    assert project.default_page.resolution == 600.0


def test_link_path_conversion() -> None:
    assert link_path_to_file_name(".:page0001.clip") == "page0001.clip"
    assert link_path_to_file_name(".:sub:page0002.clip") == str(Path("sub", "page0002.clip"))
    with pytest.raises(CspFormatError):
        link_path_to_file_name(".:")


def test_rejects_non_sqlite(tmp_path: Path) -> None:
    path = tmp_path / "bad.cmc"
    path.write_bytes(b"CSFCHUNK not sqlite")
    with pytest.raises(CspFormatError):
        read_cmc(path)


def test_inspect_cmc_summary(tmp_path: Path) -> None:
    path = build_cmc(tmp_path / "work.cmc", ["a.clip", "b.clip"])
    summary = inspect_file(path)
    assert summary["format"] == "cmc"
    assert summary["page_count"] == 2


def test_inspect_cli_writes_json(tmp_path: Path) -> None:
    clip = build_clip(
        tmp_path / "page.clip", 64, 64,
        [FixtureLayer(main_id=2, name="用紙", layer_type=1584), FixtureLayer(main_id=3, name="テキスト", layer_type=0, text="あ")],
    )
    output = tmp_path / "out.json"
    assert main(["inspect", str(clip), "--pixels", "--output", str(output)]) == 0
    summary = json.loads(output.read_text(encoding="utf-8"))
    assert [layer["kind"] for layer in summary["layers"]] == ["paper", "text"]
    assert summary["layers"][1]["text"] == "あ"


def test_inspect_cli_missing_file(tmp_path: Path) -> None:
    assert main(["inspect", str(tmp_path / "missing.clip")]) == 2
