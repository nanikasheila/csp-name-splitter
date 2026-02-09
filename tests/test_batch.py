from __future__ import annotations

from pathlib import Path

import pytest

from name_splitter.core.batch import (
    find_config_for_image,
    find_images_in_directory,
    prepare_batch_jobs,
)
from name_splitter.core.config import Config, GridConfig, load_default_config


def test_find_images_in_directory(tmp_path: Path) -> None:
    """ディレクトリ内の画像検索テスト"""
    # テスト用のPNGファイルを作成
    (tmp_path / "image1.png").write_text("dummy")
    (tmp_path / "image2.png").write_text("dummy")
    (tmp_path / "other.txt").write_text("dummy")
    
    # 非再帰的検索
    images = find_images_in_directory(tmp_path, recursive=False)
    assert len(images) == 2
    assert all(img.suffix == ".png" for img in images)
    
    # サブディレクトリを作成
    sub_dir = tmp_path / "sub"
    sub_dir.mkdir()
    (sub_dir / "image3.png").write_text("dummy")
    
    # 非再帰的検索（サブディレクトリは含まれない）
    images = find_images_in_directory(tmp_path, recursive=False)
    assert len(images) == 2
    
    # 再帰的検索
    images = find_images_in_directory(tmp_path, recursive=True)
    assert len(images) == 3


def test_find_config_for_image(tmp_path: Path) -> None:
    """画像に対応する設定ファイル検索テスト"""
    default_cfg = load_default_config()
    
    # 画像ファイルを作成
    image_path = tmp_path / "test.png"
    image_path.write_text("dummy")
    
    # デフォルト設定が返されることを確認
    cfg = find_config_for_image(image_path, default_cfg)
    assert cfg == default_cfg
    
    # _config.yaml形式の設定ファイルを作成
    config_path = tmp_path / "test_config.yaml"
    config_path.write_text("""version: 1
grid:
  rows: 2
  cols: 2
""")
    
    cfg = find_config_for_image(image_path, default_cfg)
    assert cfg.grid.rows == 2
    assert cfg.grid.cols == 2


def test_prepare_batch_jobs(tmp_path: Path) -> None:
    """バッチジョブ準備テスト"""
    default_cfg = load_default_config()
    
    # 複数の画像ファイルを作成
    image1 = tmp_path / "image1.png"
    image2 = tmp_path / "image2.png"
    image1.write_text("dummy")
    image2.write_text("dummy")
    
    # 個別ファイル指定
    job_specs = prepare_batch_jobs([image1, image2], default_cfg)
    assert len(job_specs) == 2
    assert job_specs[0].input_image == image1
    assert job_specs[1].input_image == image2
    
    # ディレクトリ指定
    job_specs = prepare_batch_jobs([tmp_path], default_cfg, recursive=False)
    assert len(job_specs) == 2
    
    # サブディレクトリ作成
    sub_dir = tmp_path / "sub"
    sub_dir.mkdir()
    (sub_dir / "image3.png").write_text("dummy")
    
    # 非再帰的
    job_specs = prepare_batch_jobs([tmp_path], default_cfg, recursive=False)
    assert len(job_specs) == 2
    
    # 再帰的
    job_specs = prepare_batch_jobs([tmp_path], default_cfg, recursive=True)
    assert len(job_specs) == 3


def test_prepare_batch_jobs_with_auto_config(tmp_path: Path) -> None:
    """自動設定検索テスト"""
    default_cfg = load_default_config()
    
    # 画像と設定ファイルを作成
    image1 = tmp_path / "image1.png"
    image1.write_text("dummy")
    
    config1 = tmp_path / "image1_config.yaml"
    config1.write_text("""version: 1
grid:
  rows: 3
  cols: 3
""")
    
    # auto_config有効
    job_specs = prepare_batch_jobs([tmp_path], default_cfg, auto_config=True)
    assert len(job_specs) == 1
    assert job_specs[0].config.grid.rows == 3
    
    # auto_config無効
    job_specs = prepare_batch_jobs([tmp_path], default_cfg, auto_config=False)
    assert len(job_specs) == 1
    assert job_specs[0].config.grid.rows == 4  # デフォルト値
