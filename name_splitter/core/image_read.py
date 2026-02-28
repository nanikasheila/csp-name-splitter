from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .errors import ImageReadError
from .image_ops import ImageData


@dataclass(frozen=True)
class ImageInfo:
    # 入力画像のサイズ
    width: int
    height: int


@dataclass(frozen=True)
class LayerPixels:
    # レイヤーの配置矩形とピクセル情報
    bbox: tuple[int, int, int, int]
    image: ImageData


@dataclass(frozen=True)
class LayerNode:
    # レイヤー/グループの構造情報（互換維持用）
    name: str
    kind: str
    visible: bool
    children: tuple["LayerNode", ...] = ()
    pixels: LayerPixels | None = None


@dataclass(frozen=True)
class ImageDocument:
    info: ImageInfo
    image: ImageData


def read_image(path: str | Path) -> ImageInfo:
    # 画像のメタ情報だけ読み込む
    image_path = Path(path)
    if not image_path.exists():
        raise ImageReadError(f"Image not found: {image_path}")
    try:
        from PIL import Image
    except ImportError as exc:
        raise ImageReadError("Pillow is required to read image files") from exc
    try:
        with Image.open(image_path) as image:
            width, height = image.size
    except Exception as exc:  # noqa: BLE001
        raise ImageReadError(f"Failed to read image: {image_path}") from exc
    return ImageInfo(width=int(width), height=int(height))


def read_image_document(path: str | Path) -> ImageDocument:
    # 画像全体を読み込む
    image_path = Path(path)
    if not image_path.exists():
        raise ImageReadError(f"Image not found: {image_path}")
    try:
        from PIL import Image
    except ImportError as exc:
        raise ImageReadError("Pillow is required to read image files") from exc
    try:
        with Image.open(image_path) as image:
            image_data = ImageData.from_pil(image)
            width, height = image_data.width, image_data.height
    except Exception as exc:  # noqa: BLE001
        raise ImageReadError(f"Failed to read image: {image_path}") from exc
    info = ImageInfo(width=int(width), height=int(height))
    return ImageDocument(info=info, image=image_data)


__all__ = [
    "ImageDocument",
    "ImageInfo",
    "LayerNode",
    "LayerPixels",
    "read_image",
    "read_image_document",
]
