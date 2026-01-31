from __future__ import annotations

from pathlib import Path

from name_splitter.core.image_ops import ImageData

TEST_ENV_DIR = Path(__file__).resolve().parents[1] / "test_env"


def write_sample_png(path: Path, width: int = 16, height: int = 16) -> None:
  pixels = []
  for y in range(height):
    row = []
    for x in range(width):
      if (x + y) % 2 == 0:
        row.append((255, 255, 255, 255))
      else:
        row.append((30, 30, 30, 255))
    pixels.append(row)
  image = ImageData(width=width, height=height, pixels=pixels)
  image.save(path)


def write_config(path: Path) -> None:
    path.write_text(
        """version: 1

input:
  image_path: ""

grid:
  rows: 4
  cols: 4
  order: rtl_ttb
  margin_px: 0
  gutter_px: 0

merge:
  group_rules:
    - group_name: "Lines"
      output_layer: "lines"
    - group_name: "BG"
      output_layer: "bg"
    - group_name: "Notes"
      output_layer: "notes"
  layer_rules:
    - layer_name: "template"
      output_layer: "frame"
    - layer_name: "Frame"
      output_layer: "frame"
  include_hidden_layers: false

output:
  out_dir: "output"
  page_basename: "page_{page:03d}"
  layer_stack: ["flat"]
  raster_ext: "png"
  container: "png"
  layout: "layers"

limits:
  max_dim_px: 30000
  on_exceed: "error"
""",
        encoding="utf-8",
    )


def write_readme(path: Path) -> None:
    path.write_text(
        """# テスト用環境

このディレクトリには、CLIの動作確認に使う最小構成のデータが入っています。

## 構成

- `sample.ppm`: 16x16のチェッカーボード画像（テスト用画像）
- `test_config.yaml`: テスト用設定

## 使い方

1. CLIで実行

```bash
python -m name_splitter.app.cli sample.png --config test_config.yaml --out-dir output
```

3. 生成される `output/plan.json` を確認
""",
        encoding="utf-8",
    )


def main() -> None:
    TEST_ENV_DIR.mkdir(parents=True, exist_ok=True)
    write_sample_png(TEST_ENV_DIR / "sample.png")
    write_config(TEST_ENV_DIR / "test_config.yaml")
    write_readme(TEST_ENV_DIR / "README.md")
    print(f"Test environment written to {TEST_ENV_DIR}")


if __name__ == "__main__":
    main()
