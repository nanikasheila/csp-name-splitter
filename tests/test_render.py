import tempfile
import unittest
from pathlib import Path

from name_splitter.core.config import Config, GridConfig, MergeConfig, MergeRule, OutputConfig
from name_splitter.core.grid import compute_cells
from name_splitter.core.image_ops import ImageData
from name_splitter.core.merge import apply_merge_rules
from name_splitter.core.image_read import ImageInfo, LayerNode, LayerPixels
from name_splitter.core.render import render_pages


class RenderTests(unittest.TestCase):
    def test_merge_builds_output_images(self) -> None:
        # マージ結果が合成画像を生成することを確認
        red_pixel = ImageData(width=1, height=1, pixels=[[(255, 0, 0, 255)]])
        blue_pixel = ImageData(width=1, height=1, pixels=[[(0, 0, 255, 255)]])
        layers = (
            LayerNode(
                name="Red",
                kind="layer",
                visible=True,
                pixels=LayerPixels(bbox=(0, 0, 1, 1), image=red_pixel),
            ),
            LayerNode(
                name="Blue",
                kind="layer",
                visible=True,
                pixels=LayerPixels(bbox=(1, 0, 2, 1), image=blue_pixel),
            ),
        )
        cfg = MergeConfig(
            layer_rules=(
                MergeRule(layer_name="Red", output_layer="lines"),
                MergeRule(layer_name="Blue", output_layer="lines"),
            ),
            include_hidden_layers=True,
        )
        result = apply_merge_rules(layers, cfg, canvas_size=(2, 1))
        self.assertIn("lines", result.output_images)
        merged = result.output_images["lines"]
        self.assertEqual(merged.pixels[0][0], (255, 0, 0, 255))
        self.assertEqual(merged.pixels[0][1], (0, 0, 255, 255))

    def test_render_pages_writes_ppm(self) -> None:
        # PPM出力でページ分割が行えることを確認
        image = ImageData(
            width=2,
            height=2,
            pixels=[
                [(10, 10, 10, 255), (20, 20, 20, 255)],
                [(30, 30, 30, 255), (40, 40, 40, 255)],
            ],
        )
        layers = (
            LayerNode(
                name="BG",
                kind="layer",
                visible=True,
                pixels=LayerPixels(bbox=(0, 0, 2, 2), image=image),
            ),
        )
        cfg = Config(
            grid=GridConfig(rows=1, cols=2, order="ltr_ttb", margin_px=0, gutter_px=0),
            merge=MergeConfig(layer_rules=(MergeRule(layer_name="BG", output_layer="bg"),)),
            output=OutputConfig(raster_ext="ppm", layer_stack=("bg",)),
        )
        image_info = ImageInfo(width=2, height=2)
        cells = compute_cells(image_info.width, image_info.height, cfg.grid)
        merge_result = apply_merge_rules(layers, cfg.merge, canvas_size=(2, 2))
        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir)
            pages = render_pages(output_dir, image_info, cells, cfg, [0, 1], merge_result)
            self.assertEqual(len(pages), 2)
            for page in pages:
                path = page.layer_paths["bg"]
                self.assertTrue(path.exists())
                width, height = _read_ppm_size(path)
                self.assertEqual((width, height), (1, 2))


def _read_ppm_size(path: Path) -> tuple[int, int]:
    # PPMヘッダからサイズを読み取る簡易関数
    with path.open("r", encoding="utf-8") as handle:
        if handle.readline().strip() != "P3":
            raise AssertionError("Unexpected PPM format")
        line = handle.readline().strip()
        while line.startswith("#") or not line:
            line = handle.readline().strip()
        width_str, height_str = line.split()
        return int(width_str), int(height_str)


if __name__ == "__main__":
    unittest.main()
