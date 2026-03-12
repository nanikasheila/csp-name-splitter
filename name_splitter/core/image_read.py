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
    """Read image metadata (width and height) without loading pixel data.

    Why: Grid and limit checks only need dimensions, so avoiding a full pixel
         load keeps memory usage low for large source images.
    How: Opens the file with PIL in a context manager to read the size header,
         then closes without decoding pixel data.
    """
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
    except (OSError, ValueError, SyntaxError) as exc:
        raise ImageReadError(f"Failed to read image: {image_path}") from exc
    return ImageInfo(width=int(width), height=int(height))


def read_image_document(path: str | Path) -> ImageDocument:
    """Fully load an image file and return it as an RGBA ImageDocument.

    Why: Rendering requires actual pixel data, so the full image must be
         decoded and converted to the internal RGBA representation.
    How: Opens with PIL, converts to RGBA via ImageData.from_pil(), and
         bundles the result with its ImageInfo into an ImageDocument.
    """
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
    except (OSError, ValueError, SyntaxError) as exc:
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
