# Tauri GUI 開発ガイド

> CSP Name Splitter — Flet GUI → Tauri v2 移行後の開発手順書

**最終更新**: 2026年3月12日

---

## 📑 目次

- [前提条件](#前提条件)
- [プロジェクト構造](#プロジェクト構造)
- [起動手順](#起動手順)
- [Python コード更新手順](#python-コード更新手順)
- [Tauri フロントエンド更新手順](#tauri-フロントエンド更新手順)
- [新しい RPC メソッドの追加手順](#新しい-rpc-メソッドの追加手順)
- [ビルド・検証手順](#ビルド検証手順)
- [リリースビルド手順](#リリースビルド手順)
- [トラブルシューティング](#トラブルシューティング)

---

## 前提条件

| ツール  | バージョン | 用途                        |
| ------- | ---------- | --------------------------- |
| Python  | 3.10+      | コア処理・JSON-RPC ブリッジ |
| Node.js | 18+        | Vite/Svelte フロントエンド  |
| Rust    | 1.70+      | Tauri バックエンド          |
| npm     | 9+         | パッケージ管理              |

### 初回セットアップ

```powershell
# 1. Python 仮想環境
cd C:\Users\<USER>\source\repos\csp-name-splitter
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"

# 2. Node.js 依存関係
cd tauri-app
npm install

# 3. Rust ツールチェーン（未インストールの場合）
# https://rustup.rs/ から rustup をインストール
rustup default stable
```

---

## プロジェクト構造

```
csp-name-splitter/
├── name_splitter/          ← Python パッケージ
│   ├── core/               ← コア処理（GUI に依存しない）
│   │   ├── config.py       ← GridConfig 定義・YAML 読み込み
│   │   ├── grid.py         ← グリッド座標計算
│   │   ├── preview.py      ← プレビュー画像生成
│   │   ├── template.py     ← テンプレート画像生成
│   │   ├── job.py          ← 分割ジョブ実行
│   │   └── ...
│   ├── app/                ← Flet GUI（レガシー）
│   │   └── gui_utils.py    ← ユーティリティ（bridge からも参照）
│   └── bridge.py           ← JSON-RPC ブリッジ（★ Tauri 連携の要）
│
├── tauri-app/              ← Tauri アプリケーション
│   ├── src/                ← Svelte フロントエンド
│   │   └── lib/
│   │       ├── tauri-bridge.ts   ← TypeScript RPC ラッパー
│   │       ├── stores/index.ts   ← Svelte ストア（状態管理）
│   │       ├── App.svelte        ← メインレイアウト
│   │       ├── Preview.svelte    ← プレビュー表示
│   │       ├── ConfigPanel.svelte
│   │       ├── SplitPanel.svelte
│   │       ├── TemplatePanel.svelte
│   │       ├── BatchPanel.svelte
│   │       └── LogPanel.svelte
│   ├── src-tauri/          ← Rust バックエンド
│   │   └── src/
│   │       ├── main.rs     ← エントリーポイント
│   │       └── bridge.rs   ← Python サイドカー管理・RPC 中継
│   └── package.json
│
├── tests/                  ← Python テスト
├── pyproject.toml          ← Python プロジェクト設定
└── .venv/                  ← Python 仮想環境
```

---

## 起動手順

### 開発モード（推奨）

```powershell
# 1. Python 仮想環境をアクティベート
cd C:\Users\<USER>\source\repos\csp-name-splitter
.\.venv\Scripts\Activate.ps1

# 2. Tauri dev サーバー起動
cd tauri-app
npm run tauri -- dev
```

これにより以下が自動的に行われる:

1. Vite dev サーバーが `http://localhost:1420` で起動
2. Rust バックエンドがコンパイル・起動
3. アプリウィンドウが開く
4. ウィンドウ内で「Start Bridge」により Python ブリッジが起動

> **ポート1420が使用中の場合**:
>
> ```powershell
> Get-NetTCPConnection -LocalPort 1420 -ErrorAction SilentlyContinue |
>   ForEach-Object { Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue }
> ```

### 開発モードの仕組み

```
[Vite Dev Server :1420]  ←→  [Tauri/Rust Window]  ←→  [Python Bridge (stdin/stdout)]
     Svelte UI                   bridge.rs               name_splitter.bridge
```

- **Dev モード**: Rust が `python -m name_splitter.bridge` を直接起動（`.venv` の Python を自動検出）
- **Release モード**: PyInstaller でビルドした `csp-bridge` バイナリをサイドカーとして起動

---

## Python コード更新手順

Python コア処理（`name_splitter/core/`）の変更は **即座に反映** される。

### 手順

1. **Python ファイルを編集**（`name_splitter/core/` や `name_splitter/bridge.py`）
2. **Tauri ウィンドウを再起動**（Ctrl+C → `npm run tauri -- dev`）
   - Dev モードでは Python が直接起動されるため、Python の変更は再起動で反映
   - フロントエンド（Svelte）の変更のみの場合は HMR で自動反映

### 変更がフロントエンドに影響しない場合

Python の内部ロジック変更（例: 画像処理アルゴリズムの改良）で、RPC のインターフェースが変わらない場合:

```
1. name_splitter/core/*.py を編集
2. Tauri アプリを再起動（または UI 上で Bridge を再接続）
   → 新しい Python コードで動作する
```

### 変更がフロントエンドに影響する場合

新しい RPC パラメータの追加や戻り値の変更がある場合は、[新しい RPC メソッドの追加手順](#新しい-rpc-メソッドの追加手順) を参照。

---

## Tauri フロントエンド更新手順

Svelte ファイルの変更は **Vite HMR** で即座に反映される（再起動不要）。

### 各ファイルの役割と変更時の影響

| ファイル          | 変更内容            | 反映方法                 |
| ----------------- | ------------------- | ------------------------ |
| `*.svelte`        | UI コンポーネント   | HMR で自動反映           |
| `tauri-bridge.ts` | RPC 型・関数        | HMR で自動反映           |
| `stores/index.ts` | 状態管理            | HMR で自動反映           |
| `bridge.rs`       | Rust サイドカー管理 | Tauri が自動リコンパイル |
| `tauri.conf.json` | Tauri 設定          | 再起動が必要             |

### Svelte コンポーネントの編集ガイド

```
src/lib/
├── App.svelte            ← タブレイアウト・ブリッジ初期化
├── Preview.svelte        ← プレビュー描画・ズーム/パン
├── ConfigPanel.svelte    ← グリッド設定（行列・マージン・DPI）
├── SplitPanel.svelte     ← 画像分割実行
├── TemplatePanel.svelte  ← テンプレート生成（Finish/Basic frame）
├── BatchPanel.svelte     ← バッチ処理
└── LogPanel.svelte       ← ログ表示
```

---

## 新しい RPC メソッドの追加手順

Python コアの新機能を Tauri UI から呼び出すには、3層すべてに変更が必要。

### Step 1: Python ハンドラ追加（`name_splitter/bridge.py`）

```python
def _handle_my_new_method(params: dict[str, Any]) -> dict[str, Any]:
    """新機能のハンドラ。

    Why: <なぜこのメソッドが必要か>
    How: <どう実現しているか>
    """
    value = params.get("input_value", "")
    # コア処理を呼び出し
    result = some_core_function(value)
    return {"output": result}
```

`_METHODS` ディスパッチテーブルに登録:

```python
_METHODS: dict[str, Callable[..., Any]] = {
    # ... 既存メソッド ...
    "my_new_method": _handle_my_new_method,
}
```

### Step 2: TypeScript 型・関数追加（`tauri-app/src/lib/tauri-bridge.ts`）

```typescript
// 型定義（必要な場合）
export interface MyNewResult {
  output: string;
}

// RPC 関数
export async function myNewMethod(inputValue: string): Promise<MyNewResult> {
  return rpc<MyNewResult>("my_new_method", {
    input_value: inputValue,
  });
}
```

### Step 3: Svelte コンポーネントから呼び出し

```svelte
<script lang="ts">
  import { myNewMethod } from "./tauri-bridge";

  async function handleClick(): Promise<void> {
    const result = await myNewMethod("test");
    console.log(result.output);
  }
</script>
```

### Step 4: ビルド検証

```powershell
# Python インポート確認
.\.venv\Scripts\python.exe -c "from name_splitter.bridge import main; print('OK')"

# Vite ビルド確認
cd tauri-app
npx vite build

# Rust コンパイル確認
cd src-tauri
cargo check
```

---

## ビルド・検証手順

### 個別ビルド確認

```powershell
# Python — インポートエラーがないか
cd C:\Users\<USER>\source\repos\csp-name-splitter
.\.venv\Scripts\python.exe -c "from name_splitter.bridge import main; print('OK')"

# Python — テスト実行
.\.venv\Scripts\python.exe -m pytest tests/ -v

# Vite — フロントエンドビルド
cd tauri-app
npx vite build

# Rust — コンパイルチェック
cd src-tauri
cargo check
```

### 統合ビルド確認

```powershell
cd tauri-app
npm run tauri -- build
```

---

## リリースビルド手順

### 1. Python サイドカーのビルド

```powershell
cd C:\Users\<USER>\source\repos\csp-name-splitter
.\.venv\Scripts\python.exe -m PyInstaller ^
    --name csp-bridge ^
    --onefile ^
    --hidden-import name_splitter.core ^
    --hidden-import name_splitter.app.gui_utils ^
    -m name_splitter.bridge
```

ビルドされたバイナリを配置:

```powershell
Copy-Item dist\csp-bridge.exe tauri-app\src-tauri\binaries\csp-bridge-x86_64-pc-windows-msvc.exe
```

> Tauri のサイドカーは `<name>-<target-triple>` の命名規則でバイナリを検索する。
> `tauri.conf.json` の `bundle.externalBin` に `"binaries/csp-bridge"` を指定。

### 2. Tauri アプリのビルド

```powershell
cd tauri-app
npm run tauri -- build
```

成果物: `tauri-app/src-tauri/target/release/bundle/`

---

## トラブルシューティング

### ポート1420が占有されている

```powershell
Get-NetTCPConnection -LocalPort 1420 -ErrorAction SilentlyContinue |
  ForEach-Object { Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue }
```

### Python ブリッジが起動しない

1. 仮想環境がアクティベートされているか確認
2. `python -m name_splitter.bridge` を単体で実行してエラーを確認:

   ```powershell
   .\.venv\Scripts\python.exe -m name_splitter.bridge
   ```

   正常なら JSON-RPC 入力を待機する（何も出力されない）

3. Rust 側のログを確認: Tauri dev モードではコンソールに `[bridge]` プレフィックスでログが出力される

### プレビューが表示されない

1. ブラウザの DevTools（F12）でコンソールエラーを確認
2. `[Preview]` プレフィックスのログメッセージを確認
3. Python 側のエラー: Tauri コンソールに `stderr` として出力される

### Vite HMR が効かない

```powershell
# node_modules を再インストール
cd tauri-app
Remove-Item -Recurse node_modules
npm install
```

### `cargo check` でエラー

```powershell
# Rust ツールチェーンを更新
rustup update stable
```

---

## アーキテクチャ概要

### 通信フロー

```
┌──────────────────┐     JSON-RPC      ┌──────────────────┐
│  Svelte Frontend │  ←── invoke ──→   │   Rust Backend   │
│  (TypeScript)    │                    │   (bridge.rs)    │
│                  │                    │                  │
│  tauri-bridge.ts │                    │  stdin/stdout    │
│  stores/index.ts │                    │  JSON-RPC relay  │
│  *.svelte        │                    │                  │
└──────────────────┘                    └────────┬─────────┘
                                                 │
                                        spawn / stdin / stdout
                                                 │
                                        ┌────────▼─────────┐
                                        │  Python Bridge   │
                                        │  (bridge.py)     │
                                        │                  │
                                        │  name_splitter/  │
                                        │  core/*          │
                                        └──────────────────┘
```

### JSON-RPC プロトコル

リクエスト（Rust → Python）:

```json
{"jsonrpc": "2.0", "id": 1, "method": "build_preview", "params": {...}}
```

レスポンス（Python → Rust）:

```json
{"jsonrpc": "2.0", "id": 1, "result": {...}}
```

プログレス通知（Python → Rust、`id` なし）:

```json
{
  "jsonrpc": "2.0",
  "method": "progress",
  "params": { "phase": "rendering", "done": 5, "total": 16 }
}
```

### 利用可能な RPC メソッド

| メソッド                 | 用途                       | パラメータ                                          |
| ------------------------ | -------------------------- | --------------------------------------------------- |
| `load_config`            | YAML 設定読み込み          | `path`                                              |
| `load_default_config`    | デフォルト設定取得         | —                                                   |
| `read_image`             | 画像情報取得               | `path`                                              |
| `build_preview`          | 画像プレビュー生成         | `image_path`, `grid_config`, `max_dim`, `show_grid` |
| `build_template_preview` | テンプレートプレビュー生成 | `grid_config`, `style`, `max_dim`                   |
| `generate_template`      | テンプレート PNG 生成      | `grid_config`, `style`, `output_path`               |
| `run_job`                | 画像分割ジョブ実行         | `image_path`, `config`, `out_dir`, `test_page`      |
| `cancel_job`             | 実行中ジョブのキャンセル   | —                                                   |
| `get_page_sizes`         | 用紙サイズ一覧取得         | —                                                   |
