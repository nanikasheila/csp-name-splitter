import unittest

from name_splitter.core.image_ops import ImageData


class ImageOpsTests(unittest.TestCase):
    def test_composite_overlays_pixels(self) -> None:
        # 1ピクセルのオーバーレイ合成を確認
        base = ImageData.blank(2, 1)
        overlay = ImageData(width=1, height=1, pixels=[[(255, 0, 0, 255)]])
        base.composite_over(overlay, 1, 0)
        self.assertEqual(base.pixels[0][0], (0, 0, 0, 0))
        self.assertEqual(base.pixels[0][1], (255, 0, 0, 255))

    def test_crop_bounds(self) -> None:
        # 切り出し範囲の結果を確認
        image = ImageData(
            width=2,
            height=2,
            pixels=[
                [(1, 1, 1, 255), (2, 2, 2, 255)],
                [(3, 3, 3, 255), (4, 4, 4, 255)],
            ],
        )
        cropped = image.crop(1, 0, 2, 1)
        self.assertEqual(cropped.width, 1)
        self.assertEqual(cropped.height, 1)
        self.assertEqual(cropped.pixels[0][0], (2, 2, 2, 255))


if __name__ == "__main__":
    unittest.main()
