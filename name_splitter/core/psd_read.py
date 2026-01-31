from __future__ import annotations

from .image_read import ImageDocument, ImageInfo, LayerNode, LayerPixels, read_image, read_image_document

# 互換性維持のためのPSD向け名前（PNG入力に置換済み）
PsdInfo = ImageInfo
PsdDocument = ImageDocument
read_psd = read_image
read_psd_document = read_image_document

__all__ = [
    "PsdInfo",
    "PsdDocument",
    "LayerNode",
    "LayerPixels",
    "read_psd",
    "read_psd_document",
]
