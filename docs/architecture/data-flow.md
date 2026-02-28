# データフロー

**最終更新**: 2026年3月1日

---

## 主要データフロー

### 1. CLI 分割フロー

ユーザーが CLI から画像を分割する際のデータフロー。

```text
CLI引数 (image_path, config_path)
  │
  ▼
config.py: load_config() → SplitConfig (GridConfig + MergeConfig + OutputConfig)
  │
  ▼
job.py: run_job()
  ├── image_read.py: 入力画像の読み込み → PIL.Image
  ├── grid.py: compute_cells() → セル座標リスト [(x, y, w, h), ...]
  ├── image_ops.py: crop_cell() → ページ画像群
  └── render.py: render_pages() → 出力 PNG ファイル群
```

**Source of Truth**: `SplitConfig`（YAML ファイルから生成）

### 2. GUI プレビューフロー

GUI でパラメータ変更時にプレビューを更新するフロー。

```text
GUI ウィジェット入力
  │
  ▼
gui_handlers.py: イベントハンドラ
  ├── gui_utils.py: build_grid_config() → GridConfig
  ├── gui_handlers_size.py: サイズ計算・UI 更新
  └── preview.py: build_preview_png() → PNG バイト列
        │
        ▼
      GUI プレビュー表示
```

**Source of Truth**: GUI ウィジェットの現在値 → `GridConfig` に変換

### 3. バッチ処理フロー

ディレクトリ内の複数画像を一括処理するフロー。

```text
入力ディレクトリ
  │
  ▼
batch.py: prepare_batch_jobs()
  ├── ディレクトリスキャン → 画像ファイル一覧
  ├── find_config_for_image() → 各画像の設定ファイル特定
  └── ジョブリスト生成
        │
        ▼
      batch.py: run_batch()
        └── job.py: run_job() × N回（各画像を順次処理）
              │
              ▼
            出力ディレクトリ（ページ PNG 群）
```

### 4. テンプレート生成フロー

テンプレート画像（罫線・枠線・背景）を生成するフロー。

```text
GUI テンプレート設定
  │
  ▼
gui_handlers.py: テンプレートハンドラ
  ├── gui_utils.py: build_template_style() → TemplateStyle
  └── template.py: generate_template_png()
        ├── _render_template_image() → テンプレート画像描画
        └── PIL.Image.save() → PNG ファイル出力
```

---

## 変換ポイント

データ形式が変わる主要なポイント。

| 場所 | 入力 | 出力 | 変換 |
| --- | --- | --- | --- |
| `config.py: load_config()` | YAML ファイル | `SplitConfig` | 辞書 → dataclass |
| `grid.py: compute_cells()` | `GridConfig` | セル座標リスト | 設定 → 座標計算 |
| `image_ops.py: crop_cell()` | PIL.Image + 座標 | PIL.Image | 画像クロップ |
| `preview.py: build_preview_png()` | PIL.Image + GridConfig | PNG バイト列 | 画像 → バイト列 |
| `gui_utils.py: build_grid_config()` | GUI ウィジェット値 | `GridConfig` | UI値 → dataclass |
| `template.py: generate_template_png()` | `TemplateStyle` | PNG ファイル | 設定 → 画像描画 |

---

## Source of Truth

| データ | Source of Truth | 備考 |
| --- | --- | --- |
| 分割設定 | YAML ファイル（`plan.yaml`） | CLI/バッチで使用 |
| GUI 表示値 | GUI ウィジェットの現在値 | `gui_state.py` で一部管理 |
| グリッド計算 | `GridConfig` dataclass | config から生成。不変 |
| 出力パス | `OutputConfig.out_dir` | YAML の `output.out_dir` |
| デフォルト設定 | `resources/default_config.yaml` | 未指定項目のフォールバック |
