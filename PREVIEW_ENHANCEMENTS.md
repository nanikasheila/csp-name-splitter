# プレビュー機能の強化 - 変更概要

## 実装した機能

### 1. ページ番号表示機能

プレビューに各ページのページ番号を表示する機能を追加しました。

**変更ファイル:**
- `name_splitter/core/preview.py`
- `name_splitter/core/template.py`

**機能詳細:**
- 各セル（ページ）の中央にページ番号を表示
- フォントサイズは画像サイズに応じて自動調整（12px〜48px）
- ページ番号は白色テキスト + 半透明黒背景で視認性を確保
- テンプレートプレビューも同様にページ番号を表示

**パラメータ:**
```python
build_preview_png(
    path,
    grid,
    show_page_numbers=True,  # デフォルトでTrue
    page_number_color=(255, 255, 255, 255),  # 白
    page_number_bg_color=(0, 0, 0, 200),  # 半透明黒
)
```

### 2. インタラクティブビューア（ズーム機能）

プレビュー画像をマウスで操作できるようにしました。

**変更ファイル:**
- `name_splitter/app/gui.py`

**機能詳細:**
- `ft.InteractiveViewer`でプレビュー画像をラップ
- マウスホイールでズーム（0.5倍〜5倍）
- ドラッグでパン（移動）操作が可能
- 大きな画像の細部を確認しやすく

**使用方法:**
1. GUIを起動: `python -m name_splitter.app.cli --gui`
2. 入力画像を選択
3. グリッド設定を調整
4. 「Preview」ボタンをクリック
5. プレビュー画像をマウスホイールでズーム
6. ドラッグで画像を移動

## その他の修正

### Python 3.8互換性対応
- `image_ops.py`: 型エイリアス定義を`Tuple`に変更

### FilePicker修正
- `gui.py`: FilePickerコントロールをpage.overlayに追加

## テスト方法

```bash
# プレビュー生成テスト
python test_preview.py

# GUI起動
python -m name_splitter.app.cli --gui
```

## サンプル出力

テストにより生成された `test_preview_output.png` には：
- 4×4グリッド（16ページ）の分割線
- 各ページに1〜16の番号
- 画像プレビューとして保存

## 今後の拡張案

- [ ] ページ番号のフォント・色・位置をGUIで設定可能に
- [ ] ページ番号の表示/非表示トグル追加
- [ ] 読み順のビジュアル表示（矢印など）
- [ ] ズームレベルの表示とリセットボタン
