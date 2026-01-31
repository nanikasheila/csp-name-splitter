from __future__ import annotations

from pathlib import Path


def ensure_magick_available() -> None:
    # PNG運用のためImageMagickは不要
    raise RuntimeError("ImageMagick support has been removed")


def build_psd(layer_paths: list[Path], output_path: Path) -> None:
    # PSD生成は廃止
    raise RuntimeError("PSD wrapping is no longer supported")
