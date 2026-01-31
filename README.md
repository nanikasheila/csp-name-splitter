# csp-name-splitter
CSPネーム分割ツール

## 目的

* CSPで作成した「16ページ俯瞰ネーム（1枚）」を自動でページ分割
* CSP EXの複数ページ作品として一括取り込み可能なPNG群を生成

制約・方針:

* Photoshop依存なし
* `.clip` の直接生成・編集はしない
* テキストはラスタ化OK（編集可能性は維持しない）
* レイヤー構造は実務的に再現（意味は順序で担保）
* 配布可能なツールとして成立させる

## 全体アーキテクチャ

```
CSP (.clip)
  ↓ 書き出し
PNG（1枚画像）
  ↓ 読み取り（Pillow）
RGBA処理
  ↓ 均等セル分割
ページ別PNG群
  ↓ CSP EX
バッチインポート（1回）
```

* 画像の読み取り: Pillow
* 正規化の最終責任: CSP EX

## セットアップ（開発・実行）

### 依存関係

* Python 3.10+
* Pillow（PNG読み取り/書き出し）
* GUIを使う場合: Flet

### GUI 起動メモ

* GUIはFletを使います。未導入の場合はFletを導入してください。
* `--gui` を付けるとGUIが起動します（CLIと同じCoreを使用）。

### Pillow

* PNGの読み取り/保存にPillowを使用します。

## トラブルシュート（代表例）

* `LimitExceededError`: 画像サイズが上限（30000px）を超過。CSP側で縮小して再出力。
* `ImageReadError`: 入力画像の破損、Pillow未導入、または書き出し不整合。
* GUI起動失敗: Flet未導入、または環境依存の表示系エラー。

## 重要な設計判断

### 単一画像前提

* PSD生成は行わず、PNGの分割のみを行う
* レイヤー情報は扱わない（単一画像を分割）

### サイズ制限

* 想定最大サイズ: B3見開き600dpi ≒ 17k × 12k px
* ツール制限: 30000 × 30000 pxまで
* 超過時はエラーで拒否（リサイズはユーザー責任）

## Core / CLI / GUI 分離方針

### 方針

* Coreを明確に分離
* CLI / GUI は Core を直接呼ぶ薄い層
* GUIがCLIを叩く方式は採用しない

### ディレクトリ構成

```
name_splitter/
  app/
    cli.py        # argparse → core.run_job()
    gui.py        # Flet GUI → core.run_job()
  core/
    job.py        # run_job(), ProgressEvent, CancelToken
    config.py     # Config dataclass + YAML load/save/validate
    image_read.py # 画像読み取り（Pillow）
    merge.py      # フォルダ統合・レイヤ抽出
    grid.py       # 均等セル座標・ページ順生成
    render.py     # 合成 → セル切り出し → PNG
    im_wrap.py    # 互換用スタブ（現在は未使用）
    preview.py    # 低解像度プレビュー生成（GUI用）
  resources/
    default_config.yaml
```

## Core API（単一入口）

```python
def run_job(
    input_image: str,
    cfg: Config,
    *,
    out_dir: str | None = None,
    test_page: int | None = None,
    on_progress: Callable[[ProgressEvent], None] | None = None,
    cancel_token: CancelToken | None = None,
) -> JobResult:
    ...
```

* CLI/GUI 共通
* `test_page` で1ページだけ生成可能
* 進捗はコールバックで通知

## 進捗イベント設計

```python
@dataclass
class ProgressEvent:
    phase: str   # load_image / grid / render_pages
    done: int
    total: int
    message: str = ""
```

## 例外設計（構造化）

* `ConfigError`
* `LimitExceededError`
* `ImageReadError`
* ルール未一致は warning 扱い

## 設定ファイル（config.yaml）

```yaml
version: 1

input:
  image_path: ""

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
  out_dir: ""
  page_basename: "page_{page:03d}"
  layer_stack: ["flat"]
  raster_ext: "png"
  container: "png"
  layout: "layers"

limits:
  max_dim_px: 30000
  on_exceed: "error"
```

## 均等セル分割仕様

* 有効領域:
  * `W_eff = W - 2*margin - (cols-1)*gutter`
  * `H_eff = H - 2*margin - (rows-1)*gutter`
* セルサイズ:
  * `cell_w = W_eff / cols`
  * `cell_h = H_eff / rows`
* 読み順:
  * `rtl_ttb`: 右→左、上→下
  * `ltr_ttb`: 左→右、上→下
* 端数は最後の列/行に吸収

## GUI方針（Flet）

### 採用理由

* 画像プレビュー＋グリッドオーバーレイが容易
* 設定変更の即時反映
* 配布可能

### 最低限の機能

* 画像選択
* 設定編集（rows/cols/order/margin/gutter/mergeルール）
* プレビュー表示（縮小画像＋グリッド＋ページ番号）
* Test page / Run / Cancel
* 進捗バー＋ログ

## CLI方針

```bash
# 既定設定で実行
tool.exe input.png

# 設定指定
tool.exe input.png --config config.yaml

# テスト（1ページのみ）
tool.exe input.png --page 1

# GUI起動
tool.exe --gui
```

## 実装優先順

1. grid.py
2. config.py
3. image_read.py / merge.py
4. render.py
5. im_wrap.py
6. cli.py
7. preview.py / gui.py

## 初期仕様（決め打ち）

* 単一画像を分割してPNG出力
* 出力レイヤー: flat（1枚）
* max_dim 超過はエラー

## テスト用環境

`tools/create_test_env.py` を実行すると `test_env/` にテスト用データが生成されます。
生成された `test_env/README.md` にCLI実行手順がまとまっています。

```bash
python tools/create_test_env.py
```

Pillow が未導入の環境では、`tools/run_smoke_test.py` は実行できません。
`tools/run_smoke_test.py` によりグリッド計算と `plan.json` 生成までのスモークテストを実行できます。

```bash
python tools/run_smoke_test.py
```
