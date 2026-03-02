"""Generate application icon for CSP Name Splitter.

Why: アプリアイコンが未設定だと OS のタスクバーや Alt+Tab に
     デフォルトアイコンが表示され、製品らしさが失われる。
How: Pillow で 256x256 PNG を生成する。
     漫画コマ分割をモチーフにした 3x2 グリッドを描画し、
     中央セルにアクセントカラー（薄い青緑）を使う。

Usage:
    python tools/create_icon.py
"""
from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw


# ------------------------------------------------------------------ #
# Constants                                                           #
# ------------------------------------------------------------------ #

_SIZE: int = 256
_BG_COLOR = (255, 255, 255, 255)       # 白背景 (RGBA)
_LINE_COLOR = (20, 20, 20, 255)        # 黒の格子線
_ACCENT_COLOR = (100, 200, 210, 200)   # 薄い青緑のアクセント
_LINE_WIDTH: int = 3
_PADDING: int = 16                     # キャンバス外縁の余白

_GRID_COLS: int = 3
_GRID_ROWS: int = 2

_OUTPUT_PATH = Path(__file__).parent.parent / "resources" / "icon.png"


# ------------------------------------------------------------------ #
# Helper functions                                                    #
# ------------------------------------------------------------------ #

def _build_cell_rects(
    x0: int, y0: int, x1: int, y1: int,
    cols: int, rows: int,
) -> list[tuple[int, int, int, int]]:
    """Compute cell bounding boxes for a grid.

    Why: セルの座標を一か所で計算することで描画ループをシンプルにする。
    How: グリッド領域を等分割してセル矩形リストを生成。

    Args:
        x0, y0: グリッド左上座標
        x1, y1: グリッド右下座標
        cols: 列数
        rows: 行数

    Returns:
        (left, top, right, bottom) タプルのリスト（行優先順）
    """
    rects: list[tuple[int, int, int, int]] = []
    cell_w = (x1 - x0) / cols
    cell_h = (y1 - y0) / rows
    for r in range(rows):
        for c in range(cols):
            left = int(x0 + c * cell_w)
            top = int(y0 + r * cell_h)
            right = int(x0 + (c + 1) * cell_w)
            bottom = int(y0 + (r + 1) * cell_h)
            rects.append((left, top, right, bottom))
    return rects


# ------------------------------------------------------------------ #
# Main generation function                                            #
# ------------------------------------------------------------------ #

def create_icon(output_path: Path = _OUTPUT_PATH) -> Path:
    """Generate the application icon PNG and save it.

    Why: アプリアイコンが未設定だとデフォルトアイコンになる。
         漫画コマ分割ツールのアイコンとして 3x2 グリッドが適切。
    How: RGBA モードで 256x256 キャンバスを作成し、
         外縁パディング付きの 3x2 グリッドを描画する。
         中央セルにアクセントカラーを塗り、黒線で格子を描く。

    Args:
        output_path: 保存先 PNG ファイルパス

    Returns:
        保存した PNG ファイルの絶対パス
    """
    img = Image.new("RGBA", (_SIZE, _SIZE), _BG_COLOR)
    draw = ImageDraw.Draw(img)

    # グリッド領域（外縁パディングを除いた範囲）
    gx0, gy0 = _PADDING, _PADDING
    gx1, gy1 = _SIZE - _PADDING, _SIZE - _PADDING

    cells = _build_cell_rects(gx0, gy0, gx1, gy1, _GRID_COLS, _GRID_ROWS)

    # 中央セルにアクセントカラーを塗る
    # 3x2 グリッドの中央はインデックス 1（上段中央）と 4（下段中央）
    # 視覚的に目立つよう上下どちらか一方（インデックス 1）を使用
    _accent_indices = {1, 4}
    for idx, (left, top, right, bottom) in enumerate(cells):
        if idx in _accent_indices:
            draw.rectangle([left, top, right, bottom], fill=_ACCENT_COLOR)

    # 外枠を描画
    draw.rectangle(
        [gx0, gy0, gx1 - 1, gy1 - 1],
        outline=_LINE_COLOR,
        width=_LINE_WIDTH,
    )

    # 内部格子線を描画
    cell_w = (gx1 - gx0) / _GRID_COLS
    cell_h = (gy1 - gy0) / _GRID_ROWS

    # 縦線
    for c in range(1, _GRID_COLS):
        x = int(gx0 + c * cell_w)
        draw.line([(x, gy0), (x, gy1)], fill=_LINE_COLOR, width=_LINE_WIDTH)

    # 横線
    for r in range(1, _GRID_ROWS):
        y = int(gy0 + r * cell_h)
        draw.line([(gx0, y), (gx1, y)], fill=_LINE_COLOR, width=_LINE_WIDTH)

    # PNG として保存（RGB に変換してファイルサイズを小さくする）
    output_path.parent.mkdir(parents=True, exist_ok=True)
    img.convert("RGB").save(str(output_path), "PNG")
    return output_path.resolve()


if __name__ == "__main__":
    saved = create_icon()
    print(f"Icon saved: {saved}")
