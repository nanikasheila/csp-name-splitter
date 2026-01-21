from __future__ import annotations

import subprocess
from pathlib import Path
from shutil import which

from .errors import ImageMagickNotFoundError


def build_psd(layer_paths: list[Path], output_path: Path) -> None:
    # ImageMagickでレイヤー画像をPSDにまとめる
    command = _find_magick()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    args = [command, *[str(path) for path in layer_paths], str(output_path)]
    result = subprocess.run(args, check=False, capture_output=True, text=True)
    if result.returncode != 0:
        stderr = result.stderr.strip()
        raise RuntimeError(f"ImageMagick failed ({result.returncode}): {stderr}")


def _find_magick() -> str:
    # ImageMagick実行コマンドを検出
    for candidate in ("magick", "convert"):
        if which(candidate):
            return candidate
    raise ImageMagickNotFoundError("ImageMagick is not available in PATH")
