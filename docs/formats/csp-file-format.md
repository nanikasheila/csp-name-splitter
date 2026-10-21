# CLIP STUDIO PAINT ファイル形式メモ（.clip / .cmc）

**最終更新**: 2026-10-21
**対象**: CLIP STUDIO PAINT EX で保存された実ファイル（2024-10〜2025-06 保存分）を読み取り専用で観察した結果

公式仕様は公開されていません。ここに書いた内容は実ファイルの観察から導いたもので、CSP の更新で変わる可能性があります。
「確認済み」は複数の実ファイルで一致を確かめたもの、「未解明」は今後の調査が必要なものです。

---

## .cmc（複数ページ作品）

**中身は素の SQLite データベース**です（チャンクコンテナに包まれていない）。各ページの `.clip` は `.cmc` と同じフォルダに置かれます。

### Project テーブル（1行）

作品全体の設定です。主な列:

| 列 | 意味 |
|---|---|
| `ProjectInternalVersion` | 内部バージョン（観察値 `1.1.0`） |
| `ProjectRootCanvasNode` | ページ一覧のルートノード（`CanvasNode.MainId`） |
| `ComicStoryStoryName` / `ComicStoryAuthorName` | 作品名・作者名 |
| `ComicBindPosition` / `ComicStartPage` / `ComicCoverExist` | 綴じ位置・開始ページ・表紙の有無 |
| `DefaultPage*` | ページ追加時の既定値（単位・幅・高さ・解像度・見開き・テンプレート・トンボなど） |
| `MaxCanvasFileIndex` | 次に作るページファイルの番号の上限（`pageNNNN.clip` の採番に使われていると推測） |

### CanvasNode テーブル（ページ一覧）

**連結リスト**になっています（確認済み）。

- ルートノード（`Type = 0`）の `FirstChildIndex` が先頭ページの `MainId`
- 各ページ（`Type = 2`）の `NextIndex` が次のページの `MainId`（0 で終端）
- 並び順は `MainId` やファイル名の番号と一致しない。ページを並べ替えると `NextIndex` だけが変わる
- `LinkPath` がページファイルへの参照。例 `.:page0001.clip`（`:` が区切り、`.` が `.cmc` のフォルダ）
- `LinkWidth` / `LinkHeight` / `LinkResolution` / `LinkWrite*` はキャッシュらしく、0 のページもある

未解明: `PageFlag`（0 / 1 の意味）、`SelectedIndex`、`CanvasIndex`。

---

## .clip（1ページ）

### チャンクコンテナ（確認済み）

数値はすべてビッグエンディアンです。

```
"CSFCHUNK"  u64 ファイル全体のサイズ  u64 最初のチャンクの位置(24)
チャンク:   8バイトのタグ  u64 本体の長さ  本体
  CHNKHead  40バイト（内容未解明）
  CHNKExta  外部チャンク（画素ブロックなど）。本体 = u64 40 + 40文字の外部ID + データ
  CHNKSQLi  SQLite データベース本体
  CHNKFoot  終端（長さ 0）
```

SQLite の `ExternalChunk` テーブルが「外部ID → ファイル内の位置（チャンクヘッダの先頭）」を持っています。
表から参照されていても外部チャンクが存在しないことがあり、その場合は「データなし」として扱います（空のレイヤーなど）。

### Canvas テーブル（1行）

`CanvasUnit`（2 = mm, 0 = px と推測）、`CanvasWidth` / `CanvasHeight`、`CanvasResolution`、`CanvasRootFolder`（ルートフォルダのレイヤーID）、
トンボ（`CropFrame*`）、作品情報（`ComicStory*`、`.cmc` の値の写し）、`ComicPageIndex` など。

### Layer テーブル（レイヤーツリー、確認済み）

- `Canvas.CanvasRootFolder` がルートフォルダの `MainId`
- `LayerFirstChildIndex`（最初の子）と `LayerNextIndex`（次の兄弟）で木構造を表す。値は `MainId`、0 で終端
- **兄弟は下から上の順**に並ぶ（用紙レイヤーが先頭）

種類の見分け方:

| 条件 | 種類 |
|---|---|
| `LayerType = 256` | ルートフォルダ |
| `LayerType = 1584` | 用紙 |
| `LayerType = 800` | 作品情報（テキスト） |
| `LayerType = 1` | ラスターレイヤー |
| `LayerFolder` の bit0 が立つ | フォルダー（`ComicFrameLineMipmap` があればコマ枠フォルダー） |
| `TextLayerString` がある | テキストレイヤー（本文は UTF-8） |
| `VectorObjectList.LayerId` にある | ベクターレイヤー |

その他の列: `LayerVisibility`（bit0 = 表示）、`LayerOpacity`（256 = 100%）、`LayerComposite`（合成モード、0 = 通常。他の値の対応は未解明）、
`LayerOffsetX/Y`、`LayerClip`、`LayerLock`、`LayerRenderMipmap`（描画結果）、`LayerLayerMaskMipmap`（マスク）。

### 画素データ（確認済み）

`Layer.LayerRenderMipmap` → `Mipmap.BaseMipmapInfo` → `MipmapInfo.Offscreen`（100% の段）→ `Offscreen` 行。
`MipmapInfo` は 100%, 50%, 25%… と縮小版を `NextIndex` でつないでいます。

`Offscreen.Attribute` の先頭 16 バイトの後に `u32 文字数 + UTF-16 "Parameter"` があり、続く値は:

```
幅, 高さ, 横ブロック数, 縦ブロック数, 画素種別(33=カラー, 17=グレー, 1=マスク),
アルファ面数(1), 色面数(4 / 1 / 0), 総面数(5 / 2 / 1), ...
```

`Offscreen.BlockData` は外部IDです。外部チャンクのデータ部:

```
u64 残りの長さ
ブロックレコード × (横ブロック数 × 縦ブロック数):
  u32 レコード長  u32 19  UTF-16 "BlockDataBeginChunk"
  u32 ブロック番号  u32 展開後サイズ  u32 256  u32 256  u32 データ有無
  [データ有りのとき] u32 長さ(=4+zlib長)  u32 zlib長(リトルエンディアン)  zlib データ
  u32 17  UTF-16 "BlockDataEndChunk"
u32 11  UTF-16 "BlockStatus"    u32 12  u32 ブロック数  u32 4  u32 × ブロック数（観察値はすべて 1）
u32 13  UTF-16 "BlockCheckSum"  u32 12  u32 ブロック数  u32 4  u32 × ブロック数
```

- ブロックは 256×256。番号は左上から行優先
- 展開後のデータは「アルファ面 65536 バイト」＋「色面」。カラーは BGRX（4 面ぶん）、グレーは 1 面
- **チェックサムは「リトルエンディアンの zlib 長 4 バイト＋zlib データ」の Adler-32**（データなしのブロックは 0）。3ファイル・5,473 ブロックで一致を確認

### 画素を持たないレイヤー

ベクターレイヤー・テキストレイヤー・コマ枠は、レンダリング結果の画素を保存していないことが多いです。
CSP はファイルを開いたときに自前のデータから描き直します。
そのため、ページ分割ではこれらを画素として切り出すのではなく、**行ごとコピーして座標をずらす**方針が有力です（未検証）。

### 未解明・要調査

- `LayerOffsetX/Y` と、キャンバスより大きいオフスクリーンの位置関係（`LayerRenderOffscrOffsetX/Y` も関係しそう）
- `LayerComposite` の値と合成モードの対応
- `VectorObjectList.VectorData`（外部チャンク）とテキスト属性（`TextLayerAttributes` など）の中身。座標の移動に必要
- コマ枠フォルダーのマスクとコマ枠線（`ComicFrameLineMipmap`）
- 縮小版ミップマップ・サムネイル・`CanvasPreview` を書き出し時に作り直す必要があるか
- `CHNKHead` の内容、`ParamScheme` / `ElemScheme`（スキーマ定義らしい）の扱い
- 保存した CSP のバージョンによる違い

---

## 調べ方

```bash
# 構造を JSON で確認する（読み取り専用）
python -m name_splitter.app.cli inspect page0001.clip --pixels
python -m name_splitter.app.cli inspect 作品.cmc
```

差分観察: CSP で 1 か所だけ変えて別名保存し、2 つの `inspect` 結果を比べると、どの列が何を表すかを特定しやすくなります。
