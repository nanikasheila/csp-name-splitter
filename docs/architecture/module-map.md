# モジュールマップ

**最終更新**: 2026年3月1日（v1.0.0 製品化対応版）

---

## レイヤー構造

```
┌─────────────────────────────────────────┐
│       Application Layer (app/)          │
│  CLI / GUI — ユーザーインターフェース    │
└──────────────┬──────────────────────────┘
               │ 依存方向: app/ → core/（一方向）
               ▼
┌─────────────────────────────────────────┐
│       Core Layer (core/)                │
│  ビジネスロジック・画像処理・設定管理    │
└──────────────┬──────────────────────────┘
               │
               ▼
┌─────────────────────────────────────────┐
│       External Dependencies             │
│  Pillow / Flet / PyYAML / psd-tools    │
└─────────────────────────────────────────┘
```

**依存制約**: core/ は app/ に依存してはならない。

---

## app/ — アプリケーション層

ユーザーとの接点。CLI と GUI の2つのインターフェースを提供する。

| モジュール | 責務 |
|---|---|
| `cli.py` | CLI エントリーポイント。引数解析 → `job.run_job()` 呼び出し |
| `main.py` | パッケージ配布用エントリーポイント（flet pack / PyInstaller 向け） |
| `gui.py` | Flet ベースの GUI メインウィンドウ構築・起動 |
| `gui_handlers.py` | GUI イベントハンドラ統合クラス（Mixin パターン） |
| `gui_handlers_batch.py` | バッチ処理 GUI Mixin（フォルダスキャン・複数ジョブのオーケストレーション） |
| `gui_handlers_config.py` | コンフィグ読み込み・UI 反映 Mixin |
| `gui_handlers_size.py` | ページ/キャンバスサイズ計算・UI 更新 Mixin |
| `gui_state.py` | GUI 状態管理（選択状態・パス等） |
| `gui_types.py` | GUI 型定義（Protocol, dataclass） |
| `gui_utils.py` | ユーティリティ関数（パース・単位変換・サイズ計算） |
| `gui_widgets.py` | ウィジェット生成統合クラス（Mixin パターン） |
| `gui_widgets_layout.py` | レイアウト構築 Mixin |
| `app_settings.py` | アプリ設定永続化（ウィンドウサイズ・テーマ・最近使ったファイル等） |
| `error_messages.py` | GUI 向けエラーメッセージ日本語化辞書 |

### GUI Mixin 構造

```
GuiHandlers(GuiHandlersBatchMixin, GuiHandlersSizeMixin, GuiHandlersConfigMixin)
  ├── GuiHandlersBatchMixin   (gui_handlers_batch.py)
  ├── GuiHandlersSizeMixin    (gui_handlers_size.py)
  └── GuiHandlersConfigMixin  (gui_handlers_config.py)

WidgetBuilder(WidgetLayoutMixin)
  └── WidgetLayoutMixin       (gui_widgets_layout.py)
```

---

## core/ — コア処理層

画像分割のビジネスロジック。GUI/CLI に依存しない純粋な処理。

| モジュール | 責務 |
|---|---|
| `config.py` | YAML 設定読み込み・`GridConfig` データクラス定義 |
| `grid.py` | グリッド計算（セル座標・マージン・ガッター考慮） |
| `image_ops.py` | 画像操作（クロップ・レイヤー合成） |
| `image_read.py` | PNG/JPEG 画像の読み込み |
| `psd_read.py` | PSD ファイルのレイヤー抽出 |
| `im_wrap.py` | 画像ラッパー（統一インターフェース） |
| `merge.py` | マージルール適用（レイヤーのフィルタリング・グループ化） |
| `render.py` | ページレンダリング・ファイル出力 |
| `preview.py` | プレビュー PNG 生成（ページ番号オーバーレイ） |
| `template.py` | テンプレート画像生成（罫線・枠線・背景） |
| `batch.py` | バッチ処理（ディレクトリ内の複数画像を一括処理） |
| `job.py` | ジョブ実行管理（config → grid → image → render のオーケストレーション） |
| `errors.py` | カスタム例外定義（`ConfigError`, `ImageReadError` 等） |
| `logging.py` | ロギング設定 |

### core/ 内の依存関係

```
job.py → config.py, grid.py, image_ops.py, render.py, merge.py
batch.py → job.py, config.py
render.py → image_ops.py, grid.py
template.py → grid.py, image_ops.py
preview.py → grid.py, image_ops.py
```

---

## その他のディレクトリ

| ディレクトリ | 役割 |
|---|---|
| `resources/` | デフォルト設定ファイル（`default_config.yaml`） |
| `template_pages/` | テンプレート素材（bg/frame/lines/notes/text） |
| `tests/` | pytest テストスイート |
| `tools/` | 開発支援ツール（テスト環境構築・検証スクリプト等） |
| `sample/` | サンプル画像（.gitignore 対象） |
| `test_env/` | テスト用データ（.gitignore 対象） |

---

## 外部依存ライブラリ

| ライブラリ | 用途 | 利用層 |
|---|---|---|
| Pillow >= 9.0 | 画像処理（読み込み・クロップ・合成・保存） | core/ |
| PyYAML >= 6.0 | YAML 設定ファイルの読み書き | core/ |
| Flet >= 0.20 | GUI フレームワーク | app/（オプション） |
| pytest >= 7.0 | テストフレームワーク | tests/（開発時のみ） |
