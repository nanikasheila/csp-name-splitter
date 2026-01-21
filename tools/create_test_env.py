from __future__ import annotations

from pathlib import Path

TEST_ENV_DIR = Path(__file__).resolve().parents[1] / "test_env"


def write_sample_ppm(path: Path, width: int = 16, height: int = 16) -> None:
    header = f"P3\n{width} {height}\n255\n"
    lines = [header]
    for y in range(height):
        row = []
        for x in range(width):
            if (x + y) % 2 == 0:
                row.append("255 255 255")
            else:
                row.append("30 30 30")
        lines.append(" ".join(row) + "\n")
    path.write_text("".join(lines), encoding="utf-8")


def write_config(path: Path) -> None:
    path.write_text(
        """version: 1

input:
  psd_path: ""

grid:
  rows: 4
  cols: 4
  order: rtl_ttb
  margin_px: 0
  gutter_px: 0

merge:
  group_rules: []
  layer_rules: []
  include_hidden_layers: false

output:
  out_dir: "output"
  page_basename: "page_{page:03d}"
  layer_stack: ["bg", "lines", "text", "notes"]
  raster_ext: "png"
  container: "psd"

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

1. 画像をPSDに変換（ImageMagickが必要）

```bash
convert sample.ppm sample.psd
```

2. CLIで実行

```bash
python -m name_splitter.app.cli sample.psd --config test_config.yaml --out-dir output
```

3. 生成される `output/plan.json` を確認
""",
        encoding="utf-8",
    )


def main() -> None:
    TEST_ENV_DIR.mkdir(parents=True, exist_ok=True)
    write_sample_ppm(TEST_ENV_DIR / "sample.ppm")
    write_config(TEST_ENV_DIR / "test_config.yaml")
    write_readme(TEST_ENV_DIR / "README.md")
    print(f"Test environment written to {TEST_ENV_DIR}")


if __name__ == "__main__":
    main()
