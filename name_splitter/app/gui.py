"""Flet-based GUI for CSP Name Splitter (Refactored Layout).

Layout: Preview (left) | Settings (right with tabs).
Features:
- Config file picker (YAML/JSON)
- Page size & DPI (shared)
- Grid settings with 4-direction margins  (px/mm selectable)
- Two tabs: Image Split | Template Generation
"""
from __future__ import annotations

import base64
from datetime import datetime
from dataclasses import replace
from typing import Any

from name_splitter.core import (
    CancelToken,
    ConfigError,
    ImageReadError,
    LimitExceededError,
    load_config,
    load_default_config,
    run_job,
)
from name_splitter.core.config import GridConfig
from name_splitter.core.preview import build_preview_png
from name_splitter.core.template import (
    TemplateStyle,
    build_template_preview_png,
    generate_template_png,
    parse_hex_color,
)
from name_splitter.app.gui_utils import (
    PageSizeParams,
    GridConfigParams,
    TemplateStyleParams,
    FrameSizeParams,
    parse_int,
    parse_float,
    px_to_mm,
    mm_to_px,
    convert_margin_to_px,
    convert_unit_value,
    compute_page_size_px as compute_page_size_px_impl,
    compute_canvas_size_px as compute_canvas_size_px_impl,
    compute_frame_size_mm as compute_frame_size_mm_impl,
    build_grid_config as build_grid_config_from_params,
    build_template_style as build_template_style_from_params,
)

TRANSPARENT_PNG_BASE64 = (
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR4nGNgYAAAAAMA"
    "ASsJTYQAAAAASUVORK5CYII="
)


def main() -> None:
    try:
        import flet as ft  # type: ignore
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError("flet is required for GUI mode") from exc

    def _app(page: ft.Page) -> None:
        page.title = "CSP Name Splitter"
        page.window.width = 1200
        page.window.height = 850

        # ============================================================== #
        #  共通フィールド                                                  #
        # ============================================================== #
        # -- 設定ファイル --
        config_field = ft.TextField(label="Config (YAML/JSON, optional)", expand=True)
        
        # -- ページサイズ & DPI (共通化) --
        page_size_field = ft.Dropdown(
            label="Page size",
            options=[
                ft.dropdown.Option("A4"),
                ft.dropdown.Option("B4"),
                ft.dropdown.Option("A5"),
                ft.dropdown.Option("B5"),
                ft.dropdown.Option("Custom"),
            ],
            value="A4",
            width=135,
        )
        orientation_field = ft.Dropdown(
            label="Orientation",
            options=[
                ft.dropdown.Option(key="portrait", text="縦 (portrait)"),
                ft.dropdown.Option(key="landscape", text="横 (landscape)"),
            ],
            value="portrait",
            width=155,
        )
        dpi_field = ft.TextField(label="DPI", value="300", width=80, hint_text="例: 600", keyboard_type=ft.KeyboardType.NUMBER)
        custom_size_unit_field = ft.Dropdown(
            label="Size unit",
            options=[
                ft.dropdown.Option("px"),
                ft.dropdown.Option("mm"),
            ],
            value="px",
            width=100,
        )
        custom_width_field = ft.TextField(label="Width", value="", width=100, keyboard_type=ft.KeyboardType.NUMBER)
        custom_height_field = ft.TextField(label="Height", value="", width=100, keyboard_type=ft.KeyboardType.NUMBER)
        size_info_text = ft.Text("", size=11, italic=True)

        # -- Grid 設定 --
        rows_field = ft.TextField(label="Rows", value="4", width=80, keyboard_type=ft.KeyboardType.NUMBER)
        cols_field = ft.TextField(label="Cols", value="4", width=80, keyboard_type=ft.KeyboardType.NUMBER)
        order_field = ft.Dropdown(
            label="Order",
            options=[
                ft.dropdown.Option(key="rtl_ttb", text="右→左 ↓"),
                ft.dropdown.Option(key="ltr_ttb", text="左→右 ↓"),
            ],
            value="rtl_ttb",
            width=145,
        )
        gutter_unit_field = ft.Dropdown(
            label="Gutter unit",
            options=[
                ft.dropdown.Option("px"),
                ft.dropdown.Option("mm"),
            ],
            value="px",
            width=110,
        )
        gutter_field = ft.TextField(label="Gutter", value="0", width=90, keyboard_type=ft.KeyboardType.NUMBER)

        # -- Margin 4方向 + 単位選択 --
        margin_unit_field = ft.Dropdown(
            label="Margin unit",
            options=[
                ft.dropdown.Option("px"),
                ft.dropdown.Option("mm"),
            ],
            value="px",
            width=110,
        )
        margin_top_field = ft.TextField(label="Top", value="0", width=80, keyboard_type=ft.KeyboardType.NUMBER)
        margin_bottom_field = ft.TextField(label="Bottom", value="0", width=80, keyboard_type=ft.KeyboardType.NUMBER)
        margin_left_field = ft.TextField(label="Left", value="0", width=80, keyboard_type=ft.KeyboardType.NUMBER)
        margin_right_field = ft.TextField(label="Right", value="0", width=80, keyboard_type=ft.KeyboardType.NUMBER)

        # ============================================================== #
        #  Image Split タブ用                                             #
        # ============================================================== #
        input_field = ft.TextField(label="Input image (PNG)", expand=True)
        out_dir_field = ft.TextField(label="Output directory (optional)", expand=True)
        test_page_field = ft.TextField(label="Test page (1-based, optional)", width=180)

        # ============================================================== #
        #  Template タブ用                                                #
        # ============================================================== #
        template_out_field = ft.TextField(label="Template output PNG", expand=True)

        # -- Finish frame --
        draw_finish_field = ft.Checkbox(label="Draw finish frame", value=True)
        finish_size_mode_field = ft.Dropdown(
            label="Finish size",
            options=[
                ft.dropdown.Option("Use per-page size"),
                ft.dropdown.Option("A4"),
                ft.dropdown.Option("B4"),
                ft.dropdown.Option("A5"),
                ft.dropdown.Option("B5"),
                ft.dropdown.Option("Custom mm"),
                ft.dropdown.Option("Custom px"),
            ],
            value="Use per-page size",
            width=160,
        )
        finish_width_field = ft.TextField(label="Width", value="", width=110)
        finish_height_field = ft.TextField(label="Height", value="", width=110)
        finish_offset_x_field = ft.TextField(label="Offset X mm", value="0", width=110)
        finish_offset_y_field = ft.TextField(label="Offset Y mm", value="0", width=110)
        finish_color_field = ft.TextField(label="Color", value="#FFFFFF", width=100)
        finish_alpha_field = ft.TextField(label="Alpha", value="200", width=90)
        finish_line_width_field = ft.TextField(label="Line px", value="2", width=90)

        # -- Basic frame --
        draw_basic_field = ft.Checkbox(label="Draw basic frame", value=True)
        basic_size_mode_field = ft.Dropdown(
            label="Basic size",
            options=[
                ft.dropdown.Option("Use per-page size"),
                ft.dropdown.Option("A4"),
                ft.dropdown.Option("B4"),
                ft.dropdown.Option("A5"),
                ft.dropdown.Option("B5"),
                ft.dropdown.Option("Custom mm"),
                ft.dropdown.Option("Custom px"),
            ],
            value="Use per-page size",
            width=160,
        )
        basic_width_field = ft.TextField(label="Width", value="", width=110)
        basic_height_field = ft.TextField(label="Height", value="", width=110)
        basic_offset_x_field = ft.TextField(label="Offset X mm", value="0", width=110)
        basic_offset_y_field = ft.TextField(label="Offset Y mm", value="0", width=110)
        basic_color_field = ft.TextField(label="Color", value="#00AAFF", width=100)
        basic_alpha_field = ft.TextField(label="Alpha", value="200", width=90)
        basic_line_width_field = ft.TextField(label="Line px", value="2", width=90)

        # -- Grid visual --
        grid_color_field = ft.TextField(label="Grid color", value="#FF5030", width=110)
        grid_alpha_field = ft.TextField(label="Alpha", value="170", width=90)
        grid_width_field = ft.TextField(label="Width px", value="1", width=90)

        # ============================================================== #
        #  共通 UI 部品                                                   #
        # ============================================================== #
        log_field = ft.TextField(multiline=True, read_only=True, expand=True, value="")
        progress_bar = ft.ProgressBar(width=350, value=0)
        status_text = ft.Text("Idle")

        preview_image = ft.Image(
            src=f"data:image/png;base64,{TRANSPARENT_PNG_BASE64}",
            width=550,
            height=550,
            fit="contain",
        )
        preview_viewer = ft.InteractiveViewer(
            content=preview_image,
            min_scale=0.1,
            max_scale=5.0,
            boundary_margin=ft.Margin.all(100),
        )

        clipboard = ft.Clipboard() if hasattr(ft, "Clipboard") else None
        cancel_token_holder: dict[str, CancelToken] = {"token": CancelToken()}
        current_margin_unit: dict[str, str] = {"unit": "px"}  # Track current margin unit for conversion
        current_page_size_unit: dict[str, str] = {"unit": "px"}  # Track current page size unit for conversion
        current_gutter_unit: dict[str, str] = {"unit": "px"}  # Track current gutter unit for conversion
        active_tab: dict[str, int] = {"index": 0}  # 0=Image Split, 1=Template
        auto_preview_enabled: dict[str, bool] = {"enabled": False}  # 初期化中は無効

        # ============================================================== #
        #  ヘルパー関数                                                    #
        # ============================================================== #
        def add_log(msg: str) -> None:
            ts = datetime.now().strftime("%H:%M:%S")
            log_field.value = f"{log_field.value or ''}{ts} {msg}\n"

        def set_status(msg: str) -> None:
            status_text.value = msg

        def set_progress(done: int, total: int) -> None:
            progress_bar.value = max(0.0, min(1.0, done / total)) if total else None

        def flush() -> None:
            page.update()

        def show_error(msg: str) -> None:
            """エラーをスナックバーで通知"""
            try:
                page.open(ft.SnackBar(
                    content=ft.Text(str(msg)),
                    bgcolor="red",
                    duration=5000,
                ))
            except Exception:
                pass

        # parse_int, parse_float, convert_margin_to_px は gui_utils からインポート

        def build_grid_config() -> GridConfig:
            """UIフィールドからGridConfigを構築（gui_utilsを使用）。"""
            page_w_px, page_h_px = compute_page_px()
            params = GridConfigParams(
                rows=rows_field.value or "0",
                cols=cols_field.value or "0",
                order=order_field.value or "rtl_ttb",
                margin_top=margin_top_field.value or "0",
                margin_bottom=margin_bottom_field.value or "0",
                margin_left=margin_left_field.value or "0",
                margin_right=margin_right_field.value or "0",
                margin_unit=margin_unit_field.value or "px",
                gutter=gutter_field.value or "0",
                gutter_unit=gutter_unit_field.value or "px",
                dpi=dpi_field.value or "300",
                page_size_name=page_size_field.value or "A4",
                orientation=orientation_field.value or "portrait",
                page_width_px=page_w_px,
                page_height_px=page_h_px,
                page_size_unit=custom_size_unit_field.value or "px",
            )
            return build_grid_config_from_params(params)

        last_size: dict[str, int] = {"w": 0, "h": 0}

        def compute_page_px() -> tuple[int, int]:
            """UIフィールドからページサイズ（ピクセル）を計算（gui_utilsを使用）。"""
            params = PageSizeParams(
                page_size_name=page_size_field.value or "A4",
                orientation=orientation_field.value or "portrait",
                dpi=parse_int(dpi_field.value or "300", "DPI"),
                custom_width=custom_width_field.value,
                custom_height=custom_height_field.value,
                custom_unit=custom_size_unit_field.value or "px",
            )
            w, h = compute_page_size_px_impl(params, last_size["w"], last_size["h"])
            last_size.update(w=w, h=h)
            return w, h

        def compute_canvas_size_px() -> tuple[int, int]:
            """UIフィールドからキャンバスサイズ（ピクセル）を計算（gui_utilsを使用）。"""
            pw, ph = compute_page_px()
            g = build_grid_config()
            return compute_canvas_size_px_impl(g, pw, ph)

        def compute_page_size_mm() -> tuple[float, float]:
            """UIフィールドからページサイズ（ミリメートル）を計算（gui_utilsを使用）。"""
            dpi = parse_int(dpi_field.value or "0", "DPI")
            if dpi <= 0:
                raise ValueError("DPI must be positive")
            wpx, hpx = compute_page_px()
            return px_to_mm(wpx, dpi), px_to_mm(hpx, dpi)

        def compute_frame_size_mm_ui(mode: str, w_val: str, h_val: str) -> tuple[float, float]:
            """UIフィールドからフレームサイズ（ミリメートル）を計算（gui_utilsを使用）。"""
            pw, ph = compute_page_px()
            params = FrameSizeParams(
                mode=mode or "Use per-page size",
                dpi=parse_int(dpi_field.value or "0", "DPI"),
                orientation=orientation_field.value or "portrait",
                width_value=w_val,
                height_value=h_val,
                page_width_px=pw,
                page_height_px=ph,
            )
            return compute_frame_size_mm_impl(params)

        def build_template_style() -> TemplateStyle:
            """UIフィールドからTemplateStyleを構築（gui_utilsを使用）。"""
            pw, ph = compute_page_px()
            params = TemplateStyleParams(
                grid_color=grid_color_field.value or "#FF5030",
                grid_alpha=grid_alpha_field.value or "0",
                grid_width=grid_width_field.value or "0",
                finish_color=finish_color_field.value or "#FFFFFF",
                finish_alpha=finish_alpha_field.value or "0",
                finish_line_width=finish_line_width_field.value or "0",
                finish_size_mode=finish_size_mode_field.value or "Use per-page size",
                finish_width=finish_width_field.value or "",
                finish_height=finish_height_field.value or "",
                finish_offset_x=finish_offset_x_field.value or "0",
                finish_offset_y=finish_offset_y_field.value or "0",
                draw_finish=bool(draw_finish_field.value),
                basic_color=basic_color_field.value or "#00AAFF",
                basic_alpha=basic_alpha_field.value or "0",
                basic_line_width=basic_line_width_field.value or "0",
                basic_size_mode=basic_size_mode_field.value or "Use per-page size",
                basic_width=basic_width_field.value or "",
                basic_height=basic_height_field.value or "",
                basic_offset_x=basic_offset_x_field.value or "0",
                basic_offset_y=basic_offset_y_field.value or "0",
                draw_basic=bool(draw_basic_field.value),
                dpi=parse_int(dpi_field.value or "300", "DPI"),
                orientation=orientation_field.value or "portrait",
                page_width_px=pw,
                page_height_px=ph,
            )
            return build_template_style_from_params(params)

        def update_size_info(_: ft.ControlEvent | None = None) -> None:
            try:
                gc = build_grid_config()
                pw, ph = compute_page_px()
                cw, ch = compute_canvas_size_px()
                wmm, hmm = compute_page_size_mm()
                size_info_text.value = (
                    f"Page: {pw}×{ph} px ({wmm:.1f}×{hmm:.1f} mm)  |  "
                    f"Canvas: {cw}×{ch} px  |  Grid: {gc.rows}×{gc.cols}"
                )
                size_info_text.color = None

                is_custom = page_size_field.value == "Custom"
                custom_width_field.disabled = not is_custom
                custom_height_field.disabled = not is_custom
                
                # Custom以外でもページサイズを表示（現在の単位に応じて）
                page_size_unit = custom_size_unit_field.value or "px"
                if is_custom and (not custom_width_field.value or not custom_height_field.value):
                    if page_size_unit == "mm":
                        custom_width_field.value = f"{wmm:.2f}"
                        custom_height_field.value = f"{hmm:.2f}"
                    else:
                        custom_width_field.value = str(pw)
                        custom_height_field.value = str(ph)
                if not is_custom:
                    # プリセットサイズでも現在の単位で表示
                    if page_size_unit == "mm":
                        custom_width_field.value = f"{wmm:.2f}"
                        custom_height_field.value = f"{hmm:.2f}"
                    else:
                        custom_width_field.value = str(pw)
                        custom_height_field.value = str(ph)

                # Finish frame auto-fill
                fm = finish_size_mode_field.value or "Use per-page size"
                if fm in {"Use per-page size", "A4", "A5", "B4", "B5"}:
                    fw, fh = compute_frame_size_mm_ui(fm, "", "")
                    finish_width_field.value = f"{fw:.2f}"
                    finish_height_field.value = f"{fh:.2f}"
                if fm == "Custom mm" and (not finish_width_field.value or not finish_height_field.value):
                    finish_width_field.value = f"{wmm:.2f}"
                    finish_height_field.value = f"{hmm:.2f}"
                if fm == "Custom px" and (not finish_width_field.value or not finish_height_field.value):
                    finish_width_field.value = str(pw)
                    finish_height_field.value = str(ph)
                finish_width_field.disabled = not fm.startswith("Custom")
                finish_height_field.disabled = not fm.startswith("Custom")

                # Basic frame auto-fill
                bm = basic_size_mode_field.value or "Use per-page size"
                if bm in {"Use per-page size", "A4", "A5", "B4", "B5"}:
                    bw, bh = compute_frame_size_mm_ui(bm, "", "")
                    basic_width_field.value = f"{bw:.2f}"
                    basic_height_field.value = f"{bh:.2f}"
                if bm == "Custom mm" and (not basic_width_field.value or not basic_height_field.value):
                    basic_width_field.value = f"{max(0.0, wmm - 20):.2f}"
                    basic_height_field.value = f"{max(0.0, hmm - 20):.2f}"
                if bm == "Custom px" and (not basic_width_field.value or not basic_height_field.value):
                    basic_width_field.value = str(max(0, pw - 200))
                    basic_height_field.value = str(max(0, ph - 200))
                basic_width_field.disabled = not bm.startswith("Custom")
                basic_height_field.disabled = not bm.startswith("Custom")
            except Exception as exc:  # noqa: BLE001
                size_info_text.value = f"Size error: {exc}"
                size_info_text.color = "red"
            flush()

        # ============================================================== #
        #  FilePicker (Flet ≥ 0.80 Service API)                          #
        # ============================================================== #
        async def pick_config(_: ft.ControlEvent) -> None:
            try:
                files = await ft.FilePicker().pick_files(
                    allow_multiple=False,
                    file_type=ft.FilePickerFileType.CUSTOM,
                    allowed_extensions=["yaml", "yml", "json"],
                )
            except Exception as exc:  # noqa: BLE001
                if "Session closed" not in str(exc):
                    add_log(f"FilePicker error: {exc}")
                    flush()
                return
            if files:
                config_field.value = files[0].path
                on_config_change(None)  # UI反映 + 状態更新
                flush()

        async def pick_input(_: ft.ControlEvent) -> None:
            try:
                files = await ft.FilePicker().pick_files(
                    allow_multiple=False,
                    file_type=ft.FilePickerFileType.CUSTOM,
                    allowed_extensions=["png"],
                )
            except Exception as exc:  # noqa: BLE001
                if "Session closed" not in str(exc):
                    add_log(f"FilePicker error: {exc}")
                    flush()
                return
            if files:
                input_field.value = files[0].path
                auto_preview_if_enabled(None)  # 画像選択時に自動プレビュー
                flush()

        async def pick_out_dir(_: ft.ControlEvent) -> None:
            try:
                path = await ft.FilePicker().get_directory_path()
            except Exception as exc:  # noqa: BLE001
                if "Session closed" not in str(exc):
                    add_log(f"FilePicker error: {exc}")
                    flush()
                return
            if path:
                out_dir_field.value = path
                flush()

        async def pick_template_out(_: ft.ControlEvent) -> None:
            try:
                path = await ft.FilePicker().save_file(
                    file_name="template.png",
                    file_type=ft.FilePickerFileType.CUSTOM,
                    allowed_extensions=["png"],
                )
            except Exception as exc:  # noqa: BLE001
                if "Session closed" not in str(exc):
                    add_log(f"FilePicker error: {exc}")
                    flush()
                return
            if path:
                template_out_field.value = path
                flush()

        # ============================================================== #
        #  コア操作                                                       #
        # ============================================================== #
        def load_config_for_ui() -> tuple[str, Any]:
            if config_field.value:
                return "Loaded config", load_config(config_field.value)
            return "Loaded default config", load_default_config()

        def apply_config_to_ui(cfg: Any) -> None:
            """設定ファイルをUIに反映"""
            auto_preview_enabled["enabled"] = False  # 反映中は自動更新を無効化
            try:
                # DPI
                if hasattr(cfg.grid, "dpi") and cfg.grid.dpi > 0:
                    dpi_field.value = str(cfg.grid.dpi)
                
                # Page size name & orientation
                if hasattr(cfg.grid, "page_size_name"):
                    page_size_field.value = cfg.grid.page_size_name
                if hasattr(cfg.grid, "orientation"):
                    orientation_field.value = cfg.grid.orientation
                
                # Custom page size
                if hasattr(cfg.grid, "page_width_px") and hasattr(cfg.grid, "page_height_px"):
                    w, h = cfg.grid.page_width_px, cfg.grid.page_height_px
                    if w > 0 and h > 0:
                        unit = cfg.grid.page_size_unit if hasattr(cfg.grid, "page_size_unit") else "px"
                        custom_size_unit_field.value = unit
                        if unit == "mm":
                            dpi = cfg.grid.dpi
                            custom_width_field.value = f"{w * 25.4 / dpi:.1f}"
                            custom_height_field.value = f"{h * 25.4 / dpi:.1f}"
                        else:
                            custom_width_field.value = str(w)
                            custom_height_field.value = str(h)
                        if page_size_field.value != "Custom":
                            page_size_field.value = "Custom"
                
                # Grid設定
                rows_field.value = str(cfg.grid.rows)
                cols_field.value = str(cfg.grid.cols)
                order_field.value = cfg.grid.order
                
                # Gutter unit
                if hasattr(cfg.grid, "gutter_unit"):
                    gutter_unit_field.value = cfg.grid.gutter_unit
                
                # Gutter (設定ファイルにはpx値で保存されているので、UIの単位に応じて変換)
                dpi = cfg.grid.dpi
                gutter_unit = gutter_unit_field.value or "px"
                if gutter_unit == "mm":
                    gutter_field.value = f"{cfg.grid.gutter_px * 25.4 / dpi:.2f}"
                else:
                    gutter_field.value = str(cfg.grid.gutter_px)
                
                # Margin unit
                if hasattr(cfg.grid, "margin_unit"):
                    margin_unit_field.value = cfg.grid.margin_unit
                
                # Margin（4方向が指定されていればそれを、なければlegacy margin_pxを使用）
                # 設定ファイルには常にpx値で保存されているので、UIの単位に応じて変換
                dpi = cfg.grid.dpi
                unit = margin_unit_field.value or "px"
                if cfg.grid.margin_top_px or cfg.grid.margin_bottom_px or cfg.grid.margin_left_px or cfg.grid.margin_right_px:
                    if unit == "mm":
                        margin_top_field.value = f"{cfg.grid.margin_top_px * 25.4 / dpi:.2f}"
                        margin_bottom_field.value = f"{cfg.grid.margin_bottom_px * 25.4 / dpi:.2f}"
                        margin_left_field.value = f"{cfg.grid.margin_left_px * 25.4 / dpi:.2f}"
                        margin_right_field.value = f"{cfg.grid.margin_right_px * 25.4 / dpi:.2f}"
                    else:
                        margin_top_field.value = str(cfg.grid.margin_top_px)
                        margin_bottom_field.value = str(cfg.grid.margin_bottom_px)
                        margin_left_field.value = str(cfg.grid.margin_left_px)
                        margin_right_field.value = str(cfg.grid.margin_right_px)
                else:
                    # Legacy margin_pxを全方向に適用
                    if unit == "mm":
                        val_mm = f"{cfg.grid.margin_px * 25.4 / dpi:.2f}"
                        margin_top_field.value = val_mm
                        margin_bottom_field.value = val_mm
                        margin_left_field.value = val_mm
                        margin_right_field.value = val_mm
                    else:
                        margin_top_field.value = str(cfg.grid.margin_px)
                        margin_bottom_field.value = str(cfg.grid.margin_px)
                        margin_left_field.value = str(cfg.grid.margin_px)
                        margin_right_field.value = str(cfg.grid.margin_px)
                
                # 現在の単位を更新
                current_margin_unit["unit"] = margin_unit_field.value or "px"
                current_page_size_unit["unit"] = custom_size_unit_field.value or "px"
                current_gutter_unit["unit"] = gutter_unit_field.value or "px"
                
                update_size_info()
                add_log("Config applied to UI")
                flush()
            finally:
                auto_preview_enabled["enabled"] = True

        def auto_preview_if_enabled(_: ft.ControlEvent | None = None) -> None:
            """自動プレビュー更新（有効な場合のみ）"""
            if not auto_preview_enabled["enabled"]:
                return
            # Image Splitタブでinput_fieldが空の場合はスキップ
            if active_tab["index"] == 0 and not (input_field.value or "").strip():
                return
            try:
                on_preview(None)
            except Exception:  # noqa: BLE001
                pass

        def on_config_change(_: ft.ControlEvent) -> None:
            """設定ファイルが変更されたらUIに反映"""
            if not config_field.value:
                return
            try:
                msg, cfg = load_config_for_ui()
                apply_config_to_ui(cfg)
                set_status(msg)
            except Exception as exc:  # noqa: BLE001
                add_log(f"Config load error: {exc}")
                set_status("Config error")
            flush()

        def on_preview(_: ft.ControlEvent) -> None:
            try:
                grid_cfg = build_grid_config()
                if active_tab["index"] == 1:
                    # Template preview
                    w, h = compute_canvas_size_px()
                    dpi = parse_int(dpi_field.value or "0", "DPI")
                    png = build_template_preview_png(w, h, grid_cfg, build_template_style(), dpi)
                    preview_image.src = f"data:image/png;base64,{base64.b64encode(png).decode('ascii')}"
                    set_status("Template preview")
                else:
                    # Image preview
                    path = (input_field.value or "").strip()
                    if not path:
                        raise ValueError("Input image is required for preview")
                    msg, cfg = load_config_for_ui()
                    cfg = replace(cfg, grid=grid_cfg)
                    # Grid lines 設定を取得
                    grid_alpha = parse_int(grid_alpha_field.value or "170", "Grid alpha")
                    grid_line_color = parse_hex_color(grid_color_field.value or "#FF5030", grid_alpha)
                    grid_line_width = max(1, parse_int(grid_width_field.value or "1", "Grid width"))
                    png = build_preview_png(path, cfg.grid, line_color=grid_line_color, line_width=grid_line_width)
                    preview_image.src = f"data:image/png;base64,{base64.b64encode(png).decode('ascii')}"
                    set_status(msg)
                flush()
            except (ConfigError, ImageReadError, ValueError, RuntimeError) as exc:
                add_log(f"Error: {exc}")
                set_status("Error")
                show_error(str(exc))
                flush()

        def _run_job() -> None:
            try:
                path = (input_field.value or "").strip()
                if not path:
                    raise ValueError("Input image is required")
                msg, cfg = load_config_for_ui()
                cfg = replace(cfg, grid=build_grid_config())
                out = (out_dir_field.value or "").strip() or None
                tp = test_page_field.value.strip() if test_page_field.value else ""
                tp_val = int(tp) if tp else None
                set_status(msg)
                flush()

                def on_progress(ev: Any) -> None:
                    set_progress(ev.done, ev.total)
                    set_status(f"{ev.phase} {ev.done}/{ev.total}")
                    add_log(f"[{ev.phase}] {ev.done}/{ev.total} {ev.message}".strip())
                    flush()

                result = run_job(path, cfg, out_dir=out, test_page=tp_val, on_progress=on_progress, cancel_token=cancel_token_holder["token"])
                add_log(f"Plan written to {result.plan.manifest_path}")
                add_log(f"Pages: {result.page_count}")
                set_status("Done")
                progress_bar.color = "green"
                flush()
            except (ConfigError, LimitExceededError, ImageReadError, ValueError, RuntimeError) as exc:
                add_log(f"Error: {exc}")
                set_status("Error")
                progress_bar.color = "red"
                show_error(str(exc))
                flush()
            finally:
                run_btn.disabled = False
                cancel_btn.disabled = True
                flush()

        def on_run(_: ft.ControlEvent) -> None:
            cancel_token_holder["token"] = CancelToken()
            progress_bar.value = 0
            progress_bar.color = None
            run_btn.disabled = True
            cancel_btn.disabled = False
            add_log("Starting job...")
            flush()
            page.run_thread(_run_job)

        def on_cancel(_: ft.ControlEvent) -> None:
            cancel_token_holder["token"].cancel()
            set_status("Cancel requested")
            flush()

        def _run_template() -> None:
            try:
                w, h = compute_canvas_size_px()
                dpi = parse_int(dpi_field.value or "0", "DPI")
                out = (template_out_field.value or "").strip()
                if not out:
                    raise ValueError("Template output path is required")
                if not out.lower().endswith(".png"):
                    out = f"{out}.png"
                rpath = generate_template_png(out, w, h, build_grid_config(), build_template_style(), dpi)
                add_log(f"Template written: {rpath}")
                set_status("Template written")
                flush()
            except (ConfigError, ValueError, RuntimeError) as exc:
                add_log(f"Error: {exc}")
                set_status("Error")
                show_error(str(exc))
                flush()

        def on_generate_template(_: ft.ControlEvent) -> None:
            add_log("Generating template...")
            set_status("Generating template")
            flush()
            page.run_thread(_run_template)

        async def _copy_log() -> None:
            text = (log_field.value or "").strip()
            if not text:
                add_log("Log is empty"); flush(); return
            if clipboard is None:
                add_log("Clipboard not available"); flush(); return
            try:
                await clipboard.set(text)
                add_log("Log copied")
                set_status("Log copied")
            except Exception as exc:  # noqa: BLE001
                add_log(f"Error: {exc}")
            flush()

        def on_copy_log(_: ft.ControlEvent) -> None:
            page.run_task(_copy_log)

        def on_tab_change(e: ft.ControlEvent) -> None:
            active_tab["index"] = int(e.data)
            flush()
            # タブ切替時に自動プレビュー更新
            auto_preview_if_enabled(e)

        # ============================================================== #
        #  イベント登録                                                   #
        # ============================================================== #
        # 設定ファイル変更時
        config_field.on_change = on_config_change
        config_field.on_blur = on_config_change
        
        # Input画像変更時（Image Splitタブで自動プレビュー）
        input_field.on_blur = auto_preview_if_enabled
        
        # Preview影響フィールド（サイズ情報更新 + 自動プレビュー）
        # -- 即時バリデーション付きハンドラ --
        # 整数フィールド → 空 or 整数のみ許可
        _int_fields = {
            dpi_field, rows_field, cols_field,
            finish_alpha_field, basic_alpha_field, grid_alpha_field,
            finish_line_width_field, basic_line_width_field, grid_width_field,
        }
        # 数値(小数可)フィールド
        _num_fields = {
            margin_top_field, margin_bottom_field, margin_left_field, margin_right_field,
            gutter_field, custom_width_field, custom_height_field,
            finish_width_field, finish_height_field,
            finish_offset_x_field, finish_offset_y_field,
            basic_width_field, basic_height_field,
            basic_offset_x_field, basic_offset_y_field,
        }

        def _validate_field(fld: ft.TextField) -> None:
            """フィールドの値を即時バリデーション → error_text設定"""
            val = (fld.value or "").strip()
            if not val:
                fld.error_text = None
                return
            if fld in _int_fields:
                try:
                    int(val)
                    fld.error_text = None
                except ValueError:
                    fld.error_text = "整数を入力"
            elif fld in _num_fields:
                try:
                    float(val)
                    fld.error_text = None
                except ValueError:
                    fld.error_text = "数値を入力"
            else:
                fld.error_text = None

        def make_preview_handler():
            """on_change用: バリデーション + サイズ情報更新のみ（軽量）"""
            def handler(e):
                if hasattr(e, "control") and isinstance(e.control, ft.TextField):
                    _validate_field(e.control)
                update_size_info(e)
            return handler

        def make_blur_handler():
            """on_blur用: バリデーション + サイズ情報更新 + プレビュー更新"""
            def handler(e):
                if hasattr(e, "control") and isinstance(e.control, ft.TextField):
                    _validate_field(e.control)
                update_size_info(e)
                auto_preview_if_enabled(e)
            return handler
        
        preview_affected_fields = (
            dpi_field, rows_field, cols_field, margin_top_field, margin_bottom_field,
            margin_left_field, margin_right_field, gutter_field,
            custom_width_field, custom_height_field,
            # Template fields
            finish_width_field, finish_height_field, finish_offset_x_field, finish_offset_y_field,
            finish_color_field, finish_alpha_field, finish_line_width_field,
            basic_width_field, basic_height_field, basic_offset_x_field, basic_offset_y_field,
            basic_color_field, basic_alpha_field, basic_line_width_field,
            grid_color_field, grid_alpha_field, grid_width_field,
        )
        for _fld in preview_affected_fields:
            _fld.on_change = make_preview_handler()
            _fld.on_blur = make_blur_handler()
        
        # Margin単位切替時の専用ハンドラ（値の自動換算）
        def on_margin_unit_change(e):
            old_unit = current_margin_unit["unit"]
            new_unit = margin_unit_field.value or "px"
            
            # 同じ単位の場合は何もしない
            if old_unit == new_unit:
                return
            
            dpi = parse_int(dpi_field.value or "300", "DPI")
            
            # 各マージン値を換算 (gui_utilsを使用)
            for fld in [margin_top_field, margin_bottom_field, margin_left_field, margin_right_field]:
                if fld.value:
                    fld.value = convert_unit_value(fld.value, old_unit, new_unit, dpi)
            
            # 現在の単位を更新
            current_margin_unit["unit"] = new_unit
            update_size_info(e)
            auto_preview_if_enabled(e)
        
        margin_unit_field.on_change = on_margin_unit_change
        if hasattr(margin_unit_field, "on_select"):
            margin_unit_field.on_select = on_margin_unit_change
        
        # Page size unit切替時の専用ハンドラ（値の自動換算）
        def on_custom_size_unit_change(e):
            old_unit = current_page_size_unit["unit"]
            new_unit = custom_size_unit_field.value or "px"
            
            # 同じ単位の場合は何もしない
            if old_unit == new_unit:
                return
            
            dpi = parse_int(dpi_field.value or "300", "DPI")
            size_choice = page_size_field.value or "A4"
            
            # 現在のページサイズをpxで取得
            if size_choice == "Custom":
                # Customの場合は既存の値を換算 (gui_utilsを使用)
                for fld in [custom_width_field, custom_height_field]:
                    if fld.value:
                        fld.value = convert_unit_value(fld.value, old_unit, new_unit, dpi)
            else:
                # A4, B5などのプリセットサイズの場合、px値を計算して表示
                # compute_page_px()を呼ぶと現在の値が使われるので、直接計算
                params = PageSizeParams(
                    page_size_name=size_choice,
                    orientation=orientation_field.value or "portrait",
                    dpi=dpi,
                    custom_width=None,
                    custom_height=None,
                    custom_unit="px",
                )
                w_px, h_px = compute_page_size_px_impl(params, 0, 0)
                if new_unit == "mm":
                    custom_width_field.value = f"{px_to_mm(w_px, dpi):.2f}"
                    custom_height_field.value = f"{px_to_mm(h_px, dpi):.2f}"
                else:
                    custom_width_field.value = str(w_px)
                    custom_height_field.value = str(h_px)
            
            # 現在の単位を更新
            current_page_size_unit["unit"] = new_unit
            update_size_info(e)
            auto_preview_if_enabled(e)
        
        custom_size_unit_field.on_change = on_custom_size_unit_change
        if hasattr(custom_size_unit_field, "on_select"):
            custom_size_unit_field.on_select = on_custom_size_unit_change
        
        # Gutter単位切替時の専用ハンドラ（値の自動換算）
        def on_gutter_unit_change(e):
            old_unit = current_gutter_unit["unit"]
            new_unit = gutter_unit_field.value or "px"
            
            # 同じ単位の場合は何もしない
            if old_unit == new_unit:
                return
            
            dpi = parse_int(dpi_field.value or "300", "DPI")
            
            # gutter値を換算 (gui_utilsを使用)
            if gutter_field.value:
                gutter_field.value = convert_unit_value(gutter_field.value, old_unit, new_unit, dpi)
            
            # 現在の単位を更新
            current_gutter_unit["unit"] = new_unit
            update_size_info(e)
            auto_preview_if_enabled(e)
        
        gutter_unit_field.on_change = on_gutter_unit_change
        if hasattr(gutter_unit_field, "on_select"):
            gutter_unit_field.on_select = on_gutter_unit_change
        
        # Preview影響Dropdown（選択＝確定なので即時プレビュー）
        preview_affected_dropdowns = (page_size_field, orientation_field, order_field,
                                       finish_size_mode_field, basic_size_mode_field)
        for _dd in preview_affected_dropdowns:
            handler = make_blur_handler()
            if hasattr(_dd, "on_select"):
                _dd.on_select = handler
            if hasattr(_dd, "on_text_change"):
                _dd.on_text_change = handler
        
        # Template checkboxes（トグル＝確定なので即時プレビュー）
        for _cb in (draw_finish_field, draw_basic_field):
            _cb.on_change = make_blur_handler()

        # ============================================================== #
        #  ボタン                                                         #
        # ============================================================== #
        run_btn = ft.ElevatedButton("Run", on_click=on_run, icon=ft.Icons.PLAY_ARROW)
        cancel_btn = ft.OutlinedButton("Cancel", on_click=on_cancel, icon=ft.Icons.CANCEL, disabled=True)
        tmpl_btn = ft.ElevatedButton("Generate Template", on_click=on_generate_template, icon=ft.Icons.GRID_ON)
        copy_log_btn = ft.OutlinedButton("Copy log", on_click=on_copy_log, icon=ft.Icons.COPY)

        # ============================================================== #
        #  Tab 1: Image Split                                            #
        # ============================================================== #
        tab_image = ft.Container(
            content=ft.Column([
                ft.Row([
                    input_field,
                    ft.IconButton(icon=ft.Icons.FOLDER_OPEN, tooltip="Select image", on_click=pick_input),
                ]),
                ft.Row([
                    out_dir_field,
                    ft.IconButton(icon=ft.Icons.FOLDER, tooltip="Select output dir", on_click=pick_out_dir),
                    test_page_field,
                ]),
                ft.Row([run_btn, cancel_btn]),
            ], spacing=6, scroll=ft.ScrollMode.AUTO),
            padding=ft.Padding(8, 6, 8, 6),
        )

        # ============================================================== #
        #  Tab 2: Template Generation                                    #
        # ============================================================== #
        tab_template = ft.Container(
            content=ft.Column([
                # Finish frame (accordion)
                ft.ExpansionPanelList(
                    controls=[
                        ft.ExpansionPanel(
                            header=ft.Row([draw_finish_field, ft.Text("Finish frame", weight=ft.FontWeight.BOLD, size=12)], spacing=4),
                            content=ft.Column([
                                ft.Row([finish_size_mode_field, finish_width_field, finish_height_field], wrap=True),
                                ft.Row([finish_offset_x_field, finish_offset_y_field, finish_color_field, finish_alpha_field, finish_line_width_field], wrap=True),
                            ], spacing=4),
                            expanded=False,
                            can_tap_header=True,
                        ),
                    ],
                    elevation=0,
                    spacing=0,
                ),
                # Basic frame (accordion)
                ft.ExpansionPanelList(
                    controls=[
                        ft.ExpansionPanel(
                            header=ft.Row([draw_basic_field, ft.Text("Basic frame", weight=ft.FontWeight.BOLD, size=12)], spacing=4),
                            content=ft.Column([
                                ft.Row([basic_size_mode_field, basic_width_field, basic_height_field], wrap=True),
                                ft.Row([basic_offset_x_field, basic_offset_y_field, basic_color_field, basic_alpha_field, basic_line_width_field], wrap=True),
                            ], spacing=4),
                            expanded=False,
                            can_tap_header=True,
                        ),
                    ],
                    elevation=0,
                    spacing=0,
                ),
                ft.Divider(height=4),
                # Template output
                ft.Row([
                    template_out_field,
                    ft.IconButton(icon=ft.Icons.SAVE, tooltip="Save template PNG", on_click=pick_template_out),
                ]),
                ft.Row([tmpl_btn]),
            ], spacing=4, scroll=ft.ScrollMode.AUTO),
            padding=ft.Padding(8, 6, 8, 6),
        )

        # ============================================================== #
        #  共通設定エリア（右側上部）                                        #
        # ============================================================== #
        common_settings = ft.Container(
            content=ft.Column([
                # Config file
                ft.Row([ft.Icon(ft.Icons.DESCRIPTION, size=16), ft.Text("Config file", weight=ft.FontWeight.BOLD, size=12)], spacing=4),
                ft.Row([
                    config_field,
                    ft.IconButton(icon=ft.Icons.SETTINGS, tooltip="Select config YAML/JSON", on_click=pick_config),
                ]),
                ft.Divider(height=2),
                # Page size & DPI
                ft.Row([ft.Icon(ft.Icons.STRAIGHTEN, size=16), ft.Text("Page size & DPI", weight=ft.FontWeight.BOLD, size=12)], spacing=4),
                ft.Row([page_size_field, orientation_field, dpi_field], wrap=True),
                ft.Row([custom_size_unit_field, custom_width_field, custom_height_field], wrap=True),
                ft.Container(
                    content=size_info_text,
                    bgcolor=ft.Colors.SURFACE_CONTAINER,
                    border_radius=6,
                    padding=ft.Padding(8, 4, 8, 4),
                ),
                ft.Divider(height=2),
                # Grid settings
                ft.Row([ft.Icon(ft.Icons.GRID_VIEW, size=16), ft.Text("Grid settings", weight=ft.FontWeight.BOLD, size=12)], spacing=4),
                ft.Row([rows_field, cols_field, order_field], wrap=True),
                ft.Row([gutter_unit_field, gutter_field], wrap=True),
                ft.Row([grid_color_field, grid_alpha_field, grid_width_field], wrap=True),
                ft.Divider(height=2),
                ft.Row([ft.Icon(ft.Icons.CROP_FREE, size=16), ft.Text("Margins", weight=ft.FontWeight.BOLD, size=12)], spacing=4),
                ft.Row([margin_unit_field, margin_top_field, margin_bottom_field, margin_left_field, margin_right_field], wrap=True),
            ], spacing=4, scroll=ft.ScrollMode.AUTO),
            padding=ft.Padding(8, 4, 8, 4),
        )

        # ============================================================== #
        #  レイアウト組み立て: Preview(左) | Settings(右)                  #
        # ============================================================== #
        outline_color = ft.Colors.OUTLINE if hasattr(ft, "Colors") else ft.colors.OUTLINE

        page.add(
            ft.Row([
                # 左側: Preview
                ft.Container(
                    content=ft.Container(
                        content=preview_viewer,
                        border=ft.border.all(1, outline_color),
                        padding=8,
                    ),
                    expand=1,
                    padding=ft.Padding(4, 4, 2, 4),
                ),
                # 右側: Settings + Tabs + Log + Status
                ft.Container(
                    content=ft.Column([
                        # 共通設定
                        common_settings,
                        # タブ
                        ft.Tabs(
                            length=2,
                            selected_index=0,
                            on_change=on_tab_change,
                            content=ft.Column([
                                ft.TabBar(tabs=[
                                    ft.Tab(label="Image Split", icon=ft.Icons.IMAGE),
                                    ft.Tab(label="Template", icon=ft.Icons.GRID_ON),
                                ]),
                                ft.TabBarView(controls=[tab_image, tab_template], height=220),
                            ]),
                        ),
                        ft.Divider(height=2),
                        # Status & Progress
                        ft.Row([progress_bar, status_text]),
                        # Log
                        ft.Row([ft.Text("Log", weight=ft.FontWeight.BOLD, size=12), copy_log_btn], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
                        ft.Container(
                            content=log_field,
                            border=ft.border.all(1, outline_color),
                            padding=8,
                            expand=True,
                        ),
                    ], expand=True),
                    expand=1,
                    padding=ft.Padding(2, 4, 4, 4),
                ),
            ], expand=True)
        )

        update_size_info()
        # 初期化完了後、自動プレビューを有効化
        auto_preview_enabled["enabled"] = True

    ft.app(target=_app)


__all__ = ["main"]
