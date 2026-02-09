"""GUI utility functions for CSP Name Splitter.

疎結合な設計：すべての関数は純粋関数またはデータクラスのみに依存し、
Fletのウィジェットや外部状態に直接依存しません。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from name_splitter.core.config import GridConfig
from name_splitter.core.template import (
    TemplateStyle,
    compute_page_size_px as template_compute_page_size_px,
    parse_hex_color,
)


# ============================================================== #
#  基本的なパーサー（純粋関数）                                      #
# ============================================================== #

def parse_int(val: str, label: str) -> int:
    """文字列を整数に変換。失敗時は説明的なエラー。
    
    Args:
        val: 変換する文字列
        label: エラーメッセージに使用するフィールド名
        
    Returns:
        変換された整数値
        
    Raises:
        ValueError: 変換に失敗した場合
    """
    try:
        return int(val)
    except ValueError as exc:
        raise ValueError(f"{label} must be an integer") from exc


def parse_float(val: str, label: str) -> float:
    """文字列を浮動小数点数に変換。失敗時は説明的なエラー。
    
    Args:
        val: 変換する文字列
        label: エラーメッセージに使用するフィールド名
        
    Returns:
        変換された浮動小数点数値
        
    Raises:
        ValueError: 変換に失敗した場合
    """
    try:
        return float(val)
    except ValueError as exc:
        raise ValueError(f"{label} must be a number") from exc


# ============================================================== #
#  単位変換（純粋関数）                                             #
# ============================================================== #

def mm_to_px(mm: float, dpi: int) -> int:
    """ミリメートルをピクセルに変換。
    
    Args:
        mm: ミリメートル値
        dpi: 解像度（dots per inch）
        
    Returns:
        ピクセル値（整数、0以上）
    """
    return max(0, int(round(mm * dpi / 25.4)))


def px_to_mm(px: int, dpi: int) -> float:
    """ピクセルをミリメートルに変換。
    
    Args:
        px: ピクセル値
        dpi: 解像度（dots per inch）
        
    Returns:
        ミリメートル値（浮動小数点）
    """
    if dpi <= 0:
        raise ValueError("DPI must be positive")
    return px * 25.4 / dpi


def convert_margin_to_px(val_str: str, unit: str, dpi: int) -> int:
    """マージン値をピクセルに変換（単位を考慮）。
    
    Args:
        val_str: 値の文字列
        unit: 単位 ("px" または "mm")
        dpi: 解像度（単位がmmの場合に使用）
        
    Returns:
        ピクセル値（整数、0以上）
    """
    val = parse_float(val_str or "0", "Margin")
    if unit == "mm":
        return mm_to_px(val, dpi)
    return max(0, int(val))


# ============================================================== #
#  ページサイズ計算                                                #
# ============================================================== #

@dataclass
class PageSizeParams:
    """ページサイズ計算に必要なパラメータ。
    
    疎結合のため、UIフィールドではなくデータクラスを使用。
    """
    page_size_name: str  # "A4", "B5", "Custom" など
    orientation: str  # "portrait" または "landscape"
    dpi: int
    custom_width: Optional[str] = None  # Custom時の幅
    custom_height: Optional[str] = None  # Custom時の高さ
    custom_unit: str = "px"  # "px" または "mm"


def compute_page_size_px(params: PageSizeParams, last_w: int = 0, last_h: int = 0) -> tuple[int, int]:
    """ページサイズをピクセルで計算。
    
    Args:
        params: ページサイズパラメータ
        last_w: 前回の幅（Customで値が未入力の場合のフォールバック）
        last_h: 前回の高さ（Customで値が未入力の場合のフォールバック）
        
    Returns:
        (幅px, 高さpx) のタプル
    """
    if params.page_size_name == "Custom":
        if params.custom_width and params.custom_height:
            if params.custom_unit == "mm":
                w_mm = float(params.custom_width)
                h_mm = float(params.custom_height)
                w = mm_to_px(w_mm, params.dpi)
                h = mm_to_px(h_mm, params.dpi)
            else:
                w = parse_int(params.custom_width, "Width")
                h = parse_int(params.custom_height, "Height")
            return w, h
        # Customだが値が未入力の場合
        if last_w > 0 and last_h > 0:
            return last_w, last_h
        # フォールバック: A4
        return template_compute_page_size_px("A4", params.dpi, params.orientation)
    
    # プリセットサイズ
    return template_compute_page_size_px(params.page_size_name, params.dpi, params.orientation)


def compute_canvas_size_px(grid: GridConfig, page_w_px: int, page_h_px: int) -> tuple[int, int]:
    """キャンバスサイズ（全体サイズ）をピクセルで計算。
    
    Args:
        grid: グリッド設定
        page_w_px: 1ページの幅（ピクセル）
        page_h_px: 1ページの高さ（ピクセル）
        
    Returns:
        (キャンバス幅px, キャンバス高さpx) のタプル
    """
    canvas_w = (
        grid.margin_left_px 
        + grid.margin_right_px 
        + grid.cols * page_w_px 
        + (grid.cols - 1) * grid.gutter_px
    )
    canvas_h = (
        grid.margin_top_px 
        + grid.margin_bottom_px 
        + grid.rows * page_h_px 
        + (grid.rows - 1) * grid.gutter_px
    )
    return canvas_w, canvas_h


# ============================================================== #
#  フレームサイズ計算（Template用）                                 #
# ============================================================== #

@dataclass
class FrameSizeParams:
    """フレームサイズ計算に必要なパラメータ。"""
    mode: str  # "Use per-page size", "A4", "Custom mm", "Custom px" など
    dpi: int
    orientation: str
    width_value: str  # Custom時の幅
    height_value: str  # Custom時の高さ
    page_width_px: int  # Use per-page size時の参照値
    page_height_px: int  # Use per-page size時の参照値


def compute_frame_size_mm(params: FrameSizeParams) -> tuple[float, float]:
    """フレームサイズをミリメートルで計算。
    
    Args:
        params: フレームサイズパラメータ
        
    Returns:
        (幅mm, 高さmm) のタプル
    """
    mode = params.mode or "Use per-page size"
    
    if mode == "Use per-page size":
        return px_to_mm(params.page_width_px, params.dpi), px_to_mm(params.page_height_px, params.dpi)
    
    if mode in {"A4", "A5", "B4", "B5"}:
        wpx, hpx = template_compute_page_size_px(mode, params.dpi, params.orientation)
        return px_to_mm(wpx, params.dpi), px_to_mm(hpx, params.dpi)
    
    if mode == "Custom px":
        wpx = parse_int(params.width_value or "0", "Width px")
        hpx = parse_int(params.height_value or "0", "Height px")
        return px_to_mm(wpx, params.dpi), px_to_mm(hpx, params.dpi)
    
    # "Custom mm"
    return parse_float(params.width_value or "0", "Width mm"), parse_float(params.height_value or "0", "Height mm")


# ============================================================== #
#  GridConfig & TemplateStyle ビルダー                           #
# ============================================================== #

@dataclass
class GridConfigParams:
    """GridConfig構築に必要なパラメータ。"""
    rows: str
    cols: str
    order: str
    margin_top: str
    margin_bottom: str
    margin_left: str
    margin_right: str
    margin_unit: str
    gutter: str
    gutter_unit: str
    dpi: str
    page_size_name: str
    orientation: str
    page_width_px: int
    page_height_px: int
    page_size_unit: str


def build_grid_config(params: GridConfigParams) -> GridConfig:
    """GridConfigを構築。
    
    Args:
        params: グリッド設定パラメータ
        
    Returns:
        構築されたGridConfig
    """
    rows = parse_int(params.rows or "0", "Rows")
    cols = parse_int(params.cols or "0", "Cols")
    dpi = parse_int(params.dpi or "300", "DPI")
    
    m_top = convert_margin_to_px(params.margin_top, params.margin_unit, dpi)
    m_bottom = convert_margin_to_px(params.margin_bottom, params.margin_unit, dpi)
    m_left = convert_margin_to_px(params.margin_left, params.margin_unit, dpi)
    m_right = convert_margin_to_px(params.margin_right, params.margin_unit, dpi)
    gutter = convert_margin_to_px(params.gutter, params.gutter_unit, dpi)
    
    return GridConfig(
        rows=rows,
        cols=cols,
        order=params.order or "rtl_ttb",
        margin_px=max(m_top, m_bottom, m_left, m_right),  # Legacy compatibility
        margin_top_px=m_top,
        margin_bottom_px=m_bottom,
        margin_left_px=m_left,
        margin_right_px=m_right,
        gutter_px=gutter,
        gutter_unit=params.gutter_unit,
        margin_unit=params.margin_unit,
        dpi=dpi,
        page_size_name=params.page_size_name,
        orientation=params.orientation,
        page_width_px=params.page_width_px,
        page_height_px=params.page_height_px,
        page_size_unit=params.page_size_unit,
    )


@dataclass
class TemplateStyleParams:
    """TemplateStyle構築に必要なパラメータ。"""
    grid_color: str
    grid_alpha: str
    grid_width: str
    finish_color: str
    finish_alpha: str
    finish_line_width: str
    finish_size_mode: str
    finish_width: str
    finish_height: str
    finish_offset_x: str
    finish_offset_y: str
    draw_finish: bool
    basic_color: str
    basic_alpha: str
    basic_line_width: str
    basic_size_mode: str
    basic_width: str
    basic_height: str
    basic_offset_x: str
    basic_offset_y: str
    draw_basic: bool
    dpi: int
    orientation: str
    page_width_px: int
    page_height_px: int


def build_template_style(params: TemplateStyleParams) -> TemplateStyle:
    """TemplateStyleを構築。
    
    Args:
        params: テンプレートスタイルパラメータ
        
    Returns:
        構築されたTemplateStyle
    """
    ga = parse_int(params.grid_alpha or "0", "Grid alpha")
    fa = parse_int(params.finish_alpha or "0", "Finish alpha")
    ba = parse_int(params.basic_alpha or "0", "Basic alpha")
    
    g_col = parse_hex_color(params.grid_color or "#FF5030", ga)
    f_col = parse_hex_color(params.finish_color or "#FFFFFF", fa)
    b_col = parse_hex_color(params.basic_color or "#00AAFF", ba)
    
    # Finish frame size
    finish_params = FrameSizeParams(
        mode=params.finish_size_mode or "Use per-page size",
        dpi=params.dpi,
        orientation=params.orientation,
        width_value=params.finish_width,
        height_value=params.finish_height,
        page_width_px=params.page_width_px,
        page_height_px=params.page_height_px,
    )
    fwmm, fhmm = compute_frame_size_mm(finish_params)
    
    # Basic frame size
    basic_params = FrameSizeParams(
        mode=params.basic_size_mode or "Use per-page size",
        dpi=params.dpi,
        orientation=params.orientation,
        width_value=params.basic_width,
        height_value=params.basic_height,
        page_width_px=params.page_width_px,
        page_height_px=params.page_height_px,
    )
    bwmm, bhmm = compute_frame_size_mm(basic_params)
    
    return TemplateStyle(
        grid_color=g_col,
        grid_width=parse_int(params.grid_width or "0", "Grid width"),
        finish_color=f_col,
        finish_width=parse_int(params.finish_line_width or "0", "Finish line width"),
        finish_width_mm=fwmm,
        finish_height_mm=fhmm,
        finish_offset_x_mm=parse_float(params.finish_offset_x or "0", "Finish offset X"),
        finish_offset_y_mm=parse_float(params.finish_offset_y or "0", "Finish offset Y"),
        draw_finish=params.draw_finish,
        basic_color=b_col,
        basic_width=parse_int(params.basic_line_width or "0", "Basic line width"),
        basic_width_mm=bwmm,
        basic_height_mm=bhmm,
        basic_offset_x_mm=parse_float(params.basic_offset_x or "0", "Basic offset X"),
        basic_offset_y_mm=parse_float(params.basic_offset_y or "0", "Basic offset Y"),
        draw_basic=params.draw_basic,
    )


# ============================================================== #
#  フィールド値変換ヘルパー                                         #
# ============================================================== #

def convert_unit_value(value: str, from_unit: str, to_unit: str, dpi: int) -> str:
    """値を単位変換（px ↔ mm）。
    
    Args:
        value: 変換する値（文字列）
        from_unit: 変換元の単位 ("px" または "mm")
        to_unit: 変換先の単位 ("px" または "mm")
        dpi: 解像度
        
    Returns:
        変換後の値（文字列、適切にフォーマット）
    """
    if from_unit == to_unit:
        return value
    
    try:
        val = float(value)
        if from_unit == "px" and to_unit == "mm":
            return f"{px_to_mm(int(val), dpi):.2f}"
        elif from_unit == "mm" and to_unit == "px":
            return str(mm_to_px(val, dpi))
    except (ValueError, ZeroDivisionError):
        pass
    
    return value


__all__ = [
    "parse_int",
    "parse_float",
    "mm_to_px",
    "px_to_mm",
    "convert_margin_to_px",
    "PageSizeParams",
    "compute_page_size_px",
    "compute_canvas_size_px",
    "FrameSizeParams",
    "compute_frame_size_mm",
    "GridConfigParams",
    "build_grid_config",
    "TemplateStyleParams",
    "build_template_style",
    "convert_unit_value",
]
