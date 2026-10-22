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

- `PageFlag = 1` は見開きページ（幅が倍のページで観察）と推測

未解明: `SelectedIndex`、`CanvasIndex`。

- `LinkWrite*`（年月日時分秒）はページファイルの更新日時、`LinkUnit` / `LinkWidth` / `LinkHeight` / `LinkResolution` はページの大きさのキャッシュらしい。
  CSP が書いた実ファイルでも 0 や不自然な値の行があり、厳密には使われていないと推測
- `MainId` の最大値は `ElemScheme`（`TableName = 'CanvasNode'`）の `MaxIndex` にも記録される

### .cmc の書き出し（`split --cmc`）

CSP で作った同じ作品の .cmc をテンプレートにして、`Project` 行（作品の設定）はそのまま残し、`CanvasNode` のページ行だけを作り直す。
ページ行はテンプレートの最初のページ行を写してから、`LinkPath`・`NextIndex`・`PageFlag`（見開き）・`LinkWrite*`（ファイルの更新日時）・ページの大きさを書き換える。
`MaxCanvasFileIndex` はページファイル名の番号の最大値にする。
各ページの `Canvas` の作品情報（`ComicStory*`、`ComicBindPosition`）は、テンプレートのページではなく .cmc の `Project` の値で上書きする。

### ページ一覧のサムネイル（`CanvasPreview`）

`CanvasPreview` は 1 行で、`ImageData` が PNG（RGBA、A3 600dpi のページで 877×1240）。CSP EX は作品のページ一覧にこれを表示するらしく、
テンプレートの白紙のプレビューのままだと全ページが白紙に見えた（CSP EX 5.1.4 で確認）。
書き出しでは、ネーム用紙のプレビューからページ枠の部分を切り抜き、ページと同じ変換で貼り付ける。

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

- 基本枠は `CropFrameInnerWidth` / `CropFrameInnerHeight`（観察値 212×300mm）。`CropFrameInnerOffsetX/Y` は中央からのずれと推測（観察値はすべて 0、
  `CropFrameInnerOffsetBasePosition` の意味は未解明）。分割では既定でネームの内枠をこの基本枠に合わせる
- `ComicPageIndex` は作品内のページ位置（0 始まり、見開きは 2 ページ分）、`ComicIsLeftPage` は左ページかどうか。
  6 ファイルで「位置が 1 つ進むごとに左右が入れ替わる」ことと矛盾しない。右綴じ・`ComicStartPage = 0` の作品では位置 0 が左ページ。
  ページを書き出すときは、テンプレートのページの組を基準に左右を決める（綴じ方向の推測が要らない）

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

作品情報レイヤー（`LayerType = 800`）は `ComicStoryInfoType` が 1 = 作品名・話数・作者名、2 = ノンブル。レイヤーパレットには出ない。
1 の `TextLayerString` に「作品名 N話」、`TextLayerStringArray` に作者名を持つ。

未解明（2026-10-22、CSP EX 5.1.4）: 第3話のページをテンプレートにすると、`TextLayerString`・`Canvas.ComicStory*`・書式（文字数・外接矩形）を
変えても、ファイル内に「ユメノストラ」が一つも無い状態（VACUUM 後）でも、CSP は「ユメノストラ 3話」と表示した。
作品情報レイヤーを外すと何も表示されず、別作品のページは自分の作品名を表示する。CSP はファイルの外（開いている作品か内部の記憶）から
この表示を引いているとみられる。確認用ファイルは `tools/csp_story_info_check.py` で作れる。

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

### 画素データの位置（推測、5ファイルで矛盾なし）

保存された画素の左上は、キャンバス上の `LayerOffsetX + LayerRenderOffscrOffsetX`（Y も同様）にあります。
多くのレイヤーでは `LayerRenderOffscrOffset = -LayerOffset` なので、画素はキャンバス座標のまま保存されています。
オフスクリーンはキャンバスを 256px 単位に切り上げた大きさが基本で、それより大きいレイヤーは 1 ブロックぶん左上にずれていました。

### テーブルと列は必要になってから作られる（確認済み）

空に近いページには `VectorObjectList` テーブルが無い、`VectorNormalBalloonIndex` 列が無い、といった違いがあります。
読み取り側は「テーブルや列が無い＝データ無し」として扱う必要があり、書き出しではテンプレートの表定義に合わせる必要があります。

### 画素を持たないレイヤー

ベクターレイヤー・テキストレイヤー・コマ枠は、レンダリング結果の画素を保存していないことが多いです。
CSP はファイルを開いたときに自前のデータから描き直します。
そのため、ページ分割ではこれらを画素として切り出すのではなく、**行ごとコピーして座標をずらす**方針です。

### ベクターデータ（`VectorObjectList.VectorData`、確認済み）

外部チャンクで、ビッグエンディアンです。座標はレイヤー内の座標で、キャンバス上の位置は `LayerOffsetX/Y` を足したものです
（同じ枠を複製して `LayerOffset` だけ変えたレイヤー 2 枚で一致を確認）。

```
u32 0  u32 残りの長さ
オブジェクト × n:
  ヘッダー（header_size バイト、観察値 92 / 96）:
    u32 header_size  u32 ?  u32 point_size(88)  u32 ?  u32 点の数  u32 フラグ
    i32 外接矩形 x0 y0 x1 y1  u32 × 3  色 u32 × 3  f64 不透明度
    u32 ブラシスタイル ID など（1〜3 個、ヘッダーの長さの差はここ）  f64 ブラシサイズ（px）  u32 ?
  点 × 点の数（point_size バイトずつ）:
    f64 x  f64 y  i32 区間の外接矩形 x0 y0 x1 y1  … 筆圧・角の情報らしき値（未解読）
```

- フラグ: 四角形とフキダシは `0x1111` / `0x3188`、開いた線は `0x11`。`0x1000` が「閉じた図形」と推測
- 実ファイル 237 オブジェクトで、読み取り → 座標変換（等倍）→ 書き戻しが元のバイト列と一致
- ブラシサイズはヘッダー末尾から 12 バイト目の f64（ヘッダー 88 / 92 / 96 バイトの 3 種で確認。ネーム枠 3.6px、ペン 25px など）。
  点ごとの値（点の 36・40 バイト目の f32、観察値 0〜1）は筆圧による倍率らしく、分割ではブラシサイズだけを拡大率倍にする

### テキスト（`TextLayerAttributes` ほか、確認済み）

`TextLayerString` が本文（UTF-8）、`TextLayerAttributes` がリトルエンディアンの TLV（`u32 ID, u32 長さ, データ`）です。
フキダシが複数あるレイヤーは、`TextLayerStringArray` / `TextLayerAttributesArray` に「`u32 長さ` + 本文 / TLV」を並べて持ちます。

| ID | 中身 |
|---|---|
| `0x20` | フォントサイズ × 100（pt）。ネーム用紙で 4pt、原稿で 16pt など |
| `0x2a` | 外接矩形 i32 × 4（レイヤー内の座標） |
| `0x39` | フォント名（`u16 ?, u16 長さ, UTF-8, u16 長さ, PostScript 名`） |
| `0x3f` | 文字ブロックの幅・高さ（px） |
| `0x40` | 四隅の座標 i32 × 8（1/100 px、文字の基準点からの相対）。縦書きでは基準点が右上 |

- フキダシの無いテキスト（ネームのセリフ、作品情報、ノンブル）は、外接矩形 + `LayerOffset` がキャンバス上の位置と一致
- フキダシ付きのテキストは、フキダシの形が同じレイヤーの `VectorObjectList` にあり（`+ LayerOffset` で位置が一致）、
  文字の外接矩形はフキダシの中心付近を原点にした相対座標になっていた。**どの文字ブロックがどのフキダシに属するかの対応は未解明**
  （並び順は一致しない）。分割では、フキダシが 1 ページに収まるならレイヤーごと、複数ページにまたがるならレイヤーを丸ごと各ページに複製する

### 未解明・要調査

- 文字ブロックとフキダシの対応（CSP でフキダシ 2 つのテキストを作り、片方だけ動かして保存した差分で特定できる見込み）
- ベクターの色の並び（RGB の順か）、`0x1000` 以外のフラグ
- `LayerComposite` の値と合成モードの対応
- コマ枠フォルダーのマスクとコマ枠線（`ComicFrameLineMipmap`）
- 縮小版ミップマップ・サムネイル・`CanvasPreview` を書き出し時に作り直す必要があるか
- `CHNKHead` の内容、`ParamScheme` / `ElemScheme`（スキーマ定義らしい）の扱い
- 保存した CSP のバージョンによる違い

---

## ネーム用紙の構成（観察例）

実際のネーム作品（.cmc）では、ネーム用紙が見開きページ（594×420mm、600dpi、`PageFlag = 1`）として入っていました。

- 用紙の左右それぞれに、4 行 × 2 見開き = 16 ページ分の枠（計 32 ページ）
- 枠はベクターレイヤーの四角形。見開きの外枠（灰色）1 つと、その中のページ内枠 2 つで 1 組
- 左半分の枠は、右半分の枠レイヤーを複製して `LayerOffsetX` だけ変えたもの
- セリフはフキダシ無しのテキストレイヤー（4pt）、線はベクターレイヤー
- 1 ページ分の外枠の縦横比は A3（ページのキャンバス）とほぼ同じ。内枠は仕上がり枠・基本枠のどちらとも正確には一致しない

`plan` サブコマンドはこの構成を前提に、繰り返し現れる四角形からページ枠を求めます。

---

## 調べ方

```bash
# 構造を JSON で確認する（読み取り専用）
python -m name_splitter.app.cli inspect page0001.clip --pixels
python -m name_splitter.app.cli inspect 作品.cmc
```

差分観察: CSP で 1 か所だけ変えて別名保存し、2 つの `inspect` 結果を比べると、どの列が何を表すかを特定しやすくなります。
