from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from .errors import ImageReadError

RGBA = tuple[int, int, int, int]


@dataclass
class ImageData:
    # RGBAピクセルを保持する最小画像表現
    width: int
    height: int
    pixels: list[list[RGBA]]

    @classmethod
    def blank(cls, width: int, height: int, color: RGBA = (0, 0, 0, 0)) -> "ImageData":
        # 指定色で塗りつぶした空画像を作成
        pixels = [[color for _ in range(width)] for _ in range(height)]
        return cls(width=width, height=height, pixels=pixels)

    @classmethod
    def from_pil(cls, image) -> "ImageData":
        # PIL画像をRGBAのImageDataに変換
        try:
            converted = image.convert("RGBA")
        except Exception as exc:  # noqa: BLE001
            raise ImageReadError("Failed to convert image to RGBA") from exc
        width, height = converted.size
        data = list(converted.getdata())
        pixels = [data[row * width : (row + 1) * width] for row in range(height)]
        return cls(width=width, height=height, pixels=pixels)

    def crop(self, x0: int, y0: int, x1: int, y1: int) -> "ImageData":
        # 指定矩形で切り出す
        x0 = max(0, min(self.width, x0))
        x1 = max(0, min(self.width, x1))
        y0 = max(0, min(self.height, y0))
        y1 = max(0, min(self.height, y1))
        width = max(0, x1 - x0)
        height = max(0, y1 - y0)
        pixels = [row[x0:x1] for row in self.pixels[y0:y1]]
        if width == 0 or height == 0:
            pixels = [[(0, 0, 0, 0)] * width for _ in range(height)]
        return ImageData(width=width, height=height, pixels=pixels)

    def composite_over(self, overlay: "ImageData", offset_x: int, offset_y: int) -> None:
        # オーバーレイ画像をアルファ合成して重ねる
        for y in range(overlay.height):
            dest_y = offset_y + y
            if dest_y < 0 or dest_y >= self.height:
                continue
            row = self.pixels[dest_y]
            overlay_row = overlay.pixels[y]
            for x in range(overlay.width):
                dest_x = offset_x + x
                if dest_x < 0 or dest_x >= self.width:
                    continue
                src_r, src_g, src_b, src_a = overlay_row[x]
                if src_a == 0:
                    continue
                dst_r, dst_g, dst_b, dst_a = row[dest_x]
                inv_a = 255 - src_a
                out_a = src_a + (dst_a * inv_a + 127) // 255
                if out_a == 0:
                    row[dest_x] = (0, 0, 0, 0)
                    continue
                out_r = (src_r * src_a * 255 + dst_r * dst_a * inv_a + out_a * 127) // (
                    out_a * 255
                )
                out_g = (src_g * src_a * 255 + dst_g * dst_a * inv_a + out_a * 127) // (
                    out_a * 255
                )
                out_b = (src_b * src_a * 255 + dst_b * dst_a * inv_a + out_a * 127) // (
                    out_a * 255
                )
                row[dest_x] = (out_r, out_g, out_b, out_a)

    def save(self, path: Path) -> None:
        # 画像を保存（PPMは内蔵、PNGはPillow）
        ext = path.suffix.lower().lstrip(".")
        if ext == "ppm":
            _save_ppm(self, path)
            return
        try:
            from PIL import Image  # type: ignore
        except ImportError as exc:
            raise RuntimeError("Pillow is required to save PNG files") from exc
        image = Image.new("RGBA", (self.width, self.height))
        image.putdata([pixel for row in self.pixels for pixel in row])
        image.save(path)


def composite_layers(
    canvas_size: tuple[int, int],
    layers: Iterable[tuple[ImageData, tuple[int, int]]],
) -> ImageData:
    # 複数レイヤーを順に合成して1枚にする
    canvas = ImageData.blank(canvas_size[0], canvas_size[1])
    for image, (x0, y0) in layers:
        canvas.composite_over(image, x0, y0)
    return canvas


def _save_ppm(image: ImageData, path: Path) -> None:
    # 簡易PPM(P3)として保存
    with path.open("w", encoding="utf-8") as handle:
        handle.write("P3\n")
        handle.write(f"{image.width} {image.height}\n")
        handle.write("255\n")
        for row in image.pixels:
            line_parts = []
            for r, g, b, _a in row:
                line_parts.append(f"{r} {g} {b}")
            handle.write(" ".join(line_parts))
            handle.write("\n")
