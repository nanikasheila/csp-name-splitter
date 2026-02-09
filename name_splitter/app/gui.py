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
    compute_page_size_px as template_compute_page_size_px,
    generate_template_png,
    parse_hex_color,
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
                ft.dropdown.Option("portrait"),
                ft.dropdown.Option("landscape"),
            ],
            value="portrait",
            width=130,
        )
        dpi_field = ft.TextField(label="DPI", value="300", width=80)
        custom_size_unit_field = ft.Dropdown(
            label="Size unit",
            options=[
                ft.dropdown.Option("px"),
                ft.dropdown.Option("mm"),
            ],
            value="px",
            width=100,
        )
        custom_width_field = ft.TextField(label="Width", value="", width=100)
        custom_height_field = ft.TextField(label="Height", value="", width=100)
        size_info_text = ft.Text("")

        # -- Grid 設定 --
        rows_field = ft.TextField(label="Rows", value="4", width=80)
        cols_field = ft.TextField(label="Cols", value="4", width=80)
        order_field = ft.Dropdown(
            label="Order",
            options=[
                ft.dropdown.Option("rtl_ttb"),
                ft.dropdown.Option("ltr_ttb"),
            ],
            value="rtl_ttb",
            width=130,
        )
        gutter_field = ft.TextField(label="Gutter", value="0", width=90)

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
        margin_top_field = ft.TextField(label="Top", value="0", width=80)
        margin_bottom_field = ft.TextField(label="Bottom", value="0", width=80)
        margin_left_field = ft.TextField(label="Left", value="0", width=80)
        margin_right_field = ft.TextField(label="Right", value="0", width=80)

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

        def parse_int(val: str, label: str) -> int:
            try:
                return int(val)
            except ValueError as exc:
                raise ValueError(f"{label} must be an integer") from exc

        def parse_float(val: str, label: str) -> float:
            try:
                return float(val)
            except ValueError as exc:
                raise ValueError(f"{label} must be a number") from exc

        # -- Margin換算（mm→px） --
        def convert_margin_to_px(val_str: str, unit: str, dpi_val: int) -> int:
            """Marginをpxに換算。unitが'mm'の場合はDPIから計算、'px'ならそのまま"""
            val = parse_float(val_str or "0", "Margin")
            if unit == "mm":
                return max(0, int(round(val * dpi_val / 25.4)))
            return max(0, int(val))

        def build_grid_config() -> GridConfig:
            rows = parse_int(rows_field.value or "0", "Rows")
            cols = parse_int(cols_field.value or "0", "Cols")
            gutter = parse_int(gutter_field.value or "0", "Gutter")
            order = order_field.value or "rtl_ttb"
            unit = margin_unit_field.value or "px"
            dpi = parse_int(dpi_field.value or "300", "DPI")

            m_top = convert_margin_to_px(margin_top_field.value, unit, dpi)
            m_bottom = convert_margin_to_px(margin_bottom_field.value, unit, dpi)
            m_left = convert_margin_to_px(margin_left_field.value, unit, dpi)
            m_right = convert_margin_to_px(margin_right_field.value, unit, dpi)

            page_w_px, page_h_px = compute_page_px()
            page_size_name = page_size_field.value or "A4"
            orientation = orientation_field.value or "portrait"
            page_size_unit = custom_size_unit_field.value or "px"

            return GridConfig(
                rows=rows,
                cols=cols,
                order=order,
                margin_px=max(m_top, m_bottom, m_left, m_right),  # Legacy compat
                margin_top_px=m_top,
                margin_bottom_px=m_bottom,
                margin_left_px=m_left,
                margin_right_px=m_right,
                gutter_px=gutter,
                margin_unit=unit,
                dpi=dpi,
                page_size_name=page_size_name,
                orientation=orientation,
                page_width_px=page_w_px,
                page_height_px=page_h_px,
                page_size_unit=page_size_unit,
            )

        last_size: dict[str, int] = {"w": 0, "h": 0}

        def compute_page_px() -> tuple[int, int]:
            size_choice = page_size_field.value or "A4"
            if size_choice == "Custom":
                if custom_width_field.value and custom_height_field.value:
                    unit = custom_size_unit_field.value or "px"
                    dpi = parse_int(dpi_field.value or "300", "DPI")
                    if unit == "mm":
                        w_mm = float(custom_width_field.value)
                        h_mm = float(custom_height_field.value)
                        w = int(w_mm * dpi / 25.4)
                        h = int(h_mm * dpi / 25.4)
                    else:
                        w = parse_int(custom_width_field.value, "Width")
                        h = parse_int(custom_height_field.value, "Height")
                    last_size.update(w=w, h=h)
                    return w, h
                if last_size["w"] > 0 and last_size["h"] > 0:
                    return last_size["w"], last_size["h"]
                dpi = parse_int(dpi_field.value or "0", "DPI")
                ori = orientation_field.value or "portrait"
                w, h = template_compute_page_size_px("A4", dpi, ori)
                last_size.update(w=w, h=h)
                return w, h
            dpi = parse_int(dpi_field.value or "0", "DPI")
            ori = orientation_field.value or "portrait"
            w, h = template_compute_page_size_px(size_choice, dpi, ori)
            last_size.update(w=w, h=h)
            return w, h

        def compute_canvas_size_px() -> tuple[int, int]:
            pw, ph = compute_page_px()
            g = build_grid_config()
            cw = g.margin_left_px + g.margin_right_px + g.cols * pw + (g.cols - 1) * g.gutter_px
            ch = g.margin_top_px + g.margin_bottom_px + g.rows * ph + (g.rows - 1) * g.gutter_px
            return cw, ch

        def compute_page_size_mm() -> tuple[float, float]:
            dpi = parse_int(dpi_field.value or "0", "DPI")
            if dpi <= 0:
                raise ValueError("DPI must be positive")
            wpx, hpx = compute_page_px()
            return wpx * 25.4 / dpi, hpx * 25.4 / dpi

        def compute_frame_size_mm(mode: str, w_val: str, h_val: str) -> tuple[float, float]:
            mode = mode or "Use per-page size"
            dpi = parse_int(dpi_field.value or "0", "DPI")
            if mode == "Use per-page size":
                return compute_page_size_mm()
            if mode in {"A4", "A5", "B4", "B5"}:
                ori = orientation_field.value or "portrait"
                wpx, hpx = template_compute_page_size_px(mode, dpi, ori)
                return wpx * 25.4 / dpi, hpx * 25.4 / dpi
            if mode == "Custom px":
                wpx = parse_int(w_val or "0", "Width px")
                hpx = parse_int(h_val or "0", "Height px")
                return wpx * 25.4 / dpi, hpx * 25.4 / dpi
            return parse_float(w_val or "0", "Width mm"), parse_float(h_val or "0", "Height mm")

        def build_template_style() -> TemplateStyle:
            ga = parse_int(grid_alpha_field.value or "0", "Grid alpha")
            fa = parse_int(finish_alpha_field.value or "0", "Finish alpha")
            ba = parse_int(basic_alpha_field.value or "0", "Basic alpha")
            g_col = parse_hex_color(grid_color_field.value or "#FF5030", ga)
            f_col = parse_hex_color(finish_color_field.value or "#FFFFFF", fa)
            b_col = parse_hex_color(basic_color_field.value or "#00AAFF", ba)
            fwmm, fhmm = compute_frame_size_mm(
                finish_size_mode_field.value or "Use per-page size",
                finish_width_field.value,
                finish_height_field.value,
            )
            bwmm, bhmm = compute_frame_size_mm(
                basic_size_mode_field.value or "Use per-page size",
                basic_width_field.value,
                basic_height_field.value,
            )
            return TemplateStyle(
                grid_color=g_col,
                grid_width=parse_int(grid_width_field.value or "0", "Grid width"),
                finish_color=f_col,
                finish_width=parse_int(finish_line_width_field.value or "0", "Finish line width"),
                finish_width_mm=fwmm,
                finish_height_mm=fhmm,
                finish_offset_x_mm=parse_float(finish_offset_x_field.value or "0", "Finish offset X"),
                finish_offset_y_mm=parse_float(finish_offset_y_field.value or "0", "Finish offset Y"),
                draw_finish=bool(draw_finish_field.value),
                basic_color=b_col,
                basic_width=parse_int(basic_line_width_field.value or "0", "Basic line width"),
                basic_width_mm=bwmm,
                basic_height_mm=bhmm,
                basic_offset_x_mm=parse_float(basic_offset_x_field.value or "0", "Basic offset X"),
                basic_offset_y_mm=parse_float(basic_offset_y_field.value or "0", "Basic offset Y"),
                draw_basic=bool(draw_basic_field.value),
            )

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
                if is_custom and (not custom_width_field.value or not custom_height_field.value):
                    custom_width_field.value = str(pw)
                    custom_height_field.value = str(ph)
                if not is_custom:
                    custom_width_field.value = str(pw)
                    custom_height_field.value = str(ph)

                # Finish frame auto-fill
                fm = finish_size_mode_field.value or "Use per-page size"
                if fm in {"Use per-page size", "A4", "A5", "B4", "B5"}:
                    fw, fh = compute_frame_size_mm(fm, "", "")
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
                    bw, bh = compute_frame_size_mm(bm, "", "")
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
            except Exception as exc:  # noqa: BLE001
                # エラーは無視（まだ設定が不完全な場合があるため）
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
                    png = build_preview_png(path, cfg.grid)
                    preview_image.src = f"data:image/png;base64,{base64.b64encode(png).decode('ascii')}"
                    set_status(msg)
                flush()
            except (ConfigError, ImageReadError, ValueError, RuntimeError) as exc:
                add_log(f"Error: {exc}")
                set_status("Error")
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
                flush()
            except (ConfigError, LimitExceededError, ImageReadError, ValueError, RuntimeError) as exc:
                add_log(f"Error: {exc}")
                set_status("Error")
                flush()

        def on_run(_: ft.ControlEvent) -> None:
            cancel_token_holder["token"] = CancelToken()
            progress_bar.value = 0
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
        def make_preview_handler():
            def handler(e):
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
            _fld.on_blur = make_preview_handler()
        
        # Margin単位切替時の専用ハンドラ（値の自動換算）
        def on_margin_unit_change(e):
            old_unit = current_margin_unit["unit"]
            new_unit = margin_unit_field.value or "px"
            
            # 同じ単位の場合は何もしない
            if old_unit == new_unit:
                return
            
            dpi = parse_int(dpi_field.value or "300", "DPI")
            
            # 各マージン値を換算
            for fld in [margin_top_field, margin_bottom_field, margin_left_field, margin_right_field]:
                if fld.value:
                    try:
                        val = float(fld.value)
                        if old_unit == "px" and new_unit == "mm":
                            # px → mm
                            fld.value = f"{val * 25.4 / dpi:.2f}"
                        elif old_unit == "mm" and new_unit == "px":
                            # mm → px
                            fld.value = str(int(val * dpi / 25.4))
                    except ValueError:
                        pass
            
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
            
            # width/heightを換算
            for fld in [custom_width_field, custom_height_field]:
                if fld.value:
                    try:
                        val = float(fld.value)
                        if old_unit == "px" and new_unit == "mm":
                            # px → mm
                            fld.value = f"{val * 25.4 / dpi:.2f}"
                        elif old_unit == "mm" and new_unit == "px":
                            # mm → px
                            fld.value = str(int(val * dpi / 25.4))
                    except ValueError:
                        pass
            
            # 現在の単位を更新
            current_page_size_unit["unit"] = new_unit
            update_size_info(e)
            auto_preview_if_enabled(e)
        
        custom_size_unit_field.on_change = on_custom_size_unit_change
        if hasattr(custom_size_unit_field, "on_select"):
            custom_size_unit_field.on_select = on_custom_size_unit_change
        
        # Preview影響Dropdown
        preview_affected_dropdowns = (page_size_field, orientation_field, order_field,
                                       finish_size_mode_field, basic_size_mode_field)
        for _dd in preview_affected_dropdowns:
            handler = make_preview_handler()
            if hasattr(_dd, "on_select"):
                _dd.on_select = handler
            if hasattr(_dd, "on_text_change"):
                _dd.on_text_change = handler
        
        # Template checkboxes
        for _cb in (draw_finish_field, draw_basic_field):
            _cb.on_change = make_preview_handler()

        # ============================================================== #
        #  ボタン                                                         #
        # ============================================================== #
        run_btn = ft.ElevatedButton("Run", on_click=on_run, icon=ft.Icons.PLAY_ARROW)
        cancel_btn = ft.OutlinedButton("Cancel", on_click=on_cancel, icon=ft.Icons.CANCEL)
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
                # Finish frame
                ft.Text("Finish frame", weight=ft.FontWeight.BOLD, size=12),
                ft.Row([draw_finish_field, finish_size_mode_field, finish_width_field, finish_height_field], wrap=True),
                ft.Row([finish_offset_x_field, finish_offset_y_field, finish_color_field, finish_alpha_field, finish_line_width_field], wrap=True),
                # Basic frame
                ft.Text("Basic frame", weight=ft.FontWeight.BOLD, size=12),
                ft.Row([draw_basic_field, basic_size_mode_field, basic_width_field, basic_height_field], wrap=True),
                ft.Row([basic_offset_x_field, basic_offset_y_field, basic_color_field, basic_alpha_field, basic_line_width_field], wrap=True),
                # Grid visual
                ft.Text("Grid lines", weight=ft.FontWeight.BOLD, size=12),
                ft.Row([grid_color_field, grid_alpha_field, grid_width_field]),
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
                ft.Text("Config file", weight=ft.FontWeight.BOLD, size=12),
                ft.Row([
                    config_field,
                    ft.IconButton(icon=ft.Icons.SETTINGS, tooltip="Select config YAML/JSON", on_click=pick_config),
                ]),
                ft.Divider(height=2),
                # Page size & DPI
                ft.Text("Page size & DPI", weight=ft.FontWeight.BOLD, size=12),
                ft.Row([page_size_field, orientation_field, dpi_field], wrap=True),
                ft.Row([custom_size_unit_field, custom_width_field, custom_height_field], wrap=True),
                size_info_text,
                ft.Divider(height=2),
                # Grid settings
                ft.Text("Grid settings", weight=ft.FontWeight.BOLD, size=12),
                ft.Row([rows_field, cols_field, order_field, gutter_field], wrap=True),
                ft.Text("Margins", weight=ft.FontWeight.BOLD, size=12),
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
