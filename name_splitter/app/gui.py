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
from name_splitter.app.gui_state import GuiState
from name_splitter.app.gui_handlers import GuiWidgets, GuiHandlers

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
        state = GuiState()  # 状態管理クラス
        
        # Buttons (need to be defined before handlers)
        run_btn = ft.ElevatedButton("Run", icon=ft.Icons.PLAY_ARROW)
        cancel_btn = ft.OutlinedButton("Cancel", icon=ft.Icons.CANCEL, disabled=True)
        
        # Initialize GuiWidgets and GuiHandlers
        widgets = GuiWidgets(
            config_field=config_field,
            page_size_field=page_size_field,
            orientation_field=orientation_field,
            dpi_field=dpi_field,
            custom_size_unit_field=custom_size_unit_field,
            custom_width_field=custom_width_field,
            custom_height_field=custom_height_field,
            size_info_text=size_info_text,
            rows_field=rows_field,
            cols_field=cols_field,
            order_field=order_field,
            gutter_unit_field=gutter_unit_field,
            gutter_field=gutter_field,
            margin_unit_field=margin_unit_field,
            margin_top_field=margin_top_field,
            margin_bottom_field=margin_bottom_field,
            margin_left_field=margin_left_field,
            margin_right_field=margin_right_field,
            input_field=input_field,
            out_dir_field=out_dir_field,
            test_page_field=test_page_field,
            template_out_field=template_out_field,
            draw_finish_field=draw_finish_field,
            finish_size_mode_field=finish_size_mode_field,
            finish_width_field=finish_width_field,
            finish_height_field=finish_height_field,
            finish_offset_x_field=finish_offset_x_field,
            finish_offset_y_field=finish_offset_y_field,
            finish_color_field=finish_color_field,
            finish_alpha_field=finish_alpha_field,
            finish_line_width_field=finish_line_width_field,
            draw_basic_field=draw_basic_field,
            basic_size_mode_field=basic_size_mode_field,
            basic_width_field=basic_width_field,
            basic_height_field=basic_height_field,
            basic_offset_x_field=basic_offset_x_field,
            basic_offset_y_field=basic_offset_y_field,
            basic_color_field=basic_color_field,
            basic_alpha_field=basic_alpha_field,
            basic_line_width_field=basic_line_width_field,
            grid_color_field=grid_color_field,
            grid_alpha_field=grid_alpha_field,
            grid_width_field=grid_width_field,
            log_field=log_field,
            progress_bar=progress_bar,
            status_text=status_text,
            preview_image=preview_image,
            run_btn=run_btn,
            cancel_btn=cancel_btn,
        )
        
        handlers = GuiHandlers(widgets, state, page, clipboard)
        
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
                    handlers.add_log(f"FilePicker error: {exc}")
                    handlers.flush()
                return
            if files:
                config_field.value = files[0].path
                handlers.on_config_change(None)  # UI反映 + 状態更新
                handlers.flush()

        async def pick_input(_: ft.ControlEvent) -> None:
            try:
                files = await ft.FilePicker().pick_files(
                    allow_multiple=False,
                    file_type=ft.FilePickerFileType.CUSTOM,
                    allowed_extensions=["png"],
                )
            except Exception as exc:  # noqa: BLE001
                if "Session closed" not in str(exc):
                    handlers.add_log(f"FilePicker error: {exc}")
                    handlers.flush()
                return
            if files:
                input_field.value = files[0].path
                handlers.auto_preview_if_enabled(None)  # 画像選択時に自動プレビュー
                handlers.flush()

        async def pick_out_dir(_: ft.ControlEvent) -> None:
            try:
                path = await ft.FilePicker().get_directory_path()
            except Exception as exc:  # noqa: BLE001
                if "Session closed" not in str(exc):
                    handlers.add_log(f"FilePicker error: {exc}")
                    handlers.flush()
                return
            if path:
                out_dir_field.value = path
                handlers.flush()

        async def pick_template_out(_: ft.ControlEvent) -> None:
            try:
                path = await ft.FilePicker().save_file(
                    file_name="template.png",
                    file_type=ft.FilePickerFileType.CUSTOM,
                    allowed_extensions=["png"],
                )
            except Exception as exc:  # noqa: BLE001
                if "Session closed" not in str(exc):
                    handlers.add_log(f"FilePicker error: {exc}")
                    handlers.flush()
                return
            if path:
                template_out_field.value = path
                handlers.flush()

        # ============================================================== #
        #  イベント登録                                                   #
        # ============================================================== #
        # 設定ファイル変更時
        config_field.on_change = handlers.on_config_change
        config_field.on_blur = handlers.on_config_change
        
        # Input画像変更時（Image Splitタブで自動プレビュー）
        input_field.on_blur = handlers.auto_preview_if_enabled
        
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
                handlers.update_size_info(e)
            return handler

        def make_blur_handler():
            """on_blur用: バリデーション + サイズ情報更新 + プレビュー更新"""
            def handler(e):
                if hasattr(e, "control") and isinstance(e.control, ft.TextField):
                    _validate_field(e.control)
                handlers.update_size_info(e)
                handlers.auto_preview_if_enabled(e)
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
        margin_unit_field.on_change = handlers.on_margin_unit_change
        if hasattr(margin_unit_field, "on_select"):
            margin_unit_field.on_select = handlers.on_margin_unit_change
        
        # Page size unit切替時の専用ハンドラ（値の自動換算）
        custom_size_unit_field.on_change = handlers.on_custom_size_unit_change
        if hasattr(custom_size_unit_field, "on_select"):
            custom_size_unit_field.on_select = handlers.on_custom_size_unit_change
        
        # Gutter単位切替時の専用ハンドラ（値の自動換算）
        gutter_unit_field.on_change = handlers.on_gutter_unit_change
        if hasattr(gutter_unit_field, "on_select"):
            gutter_unit_field.on_select = handlers.on_gutter_unit_change
        
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
        run_btn.on_click = handlers.on_run
        cancel_btn.on_click = handlers.on_cancel
        tmpl_btn = ft.ElevatedButton("Generate Template", on_click=handlers.on_generate_template, icon=ft.Icons.GRID_ON)
        copy_log_btn = ft.OutlinedButton("Copy log", on_click=handlers.on_copy_log, icon=ft.Icons.COPY)

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
                            on_change=handlers.on_tab_change,
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

        handlers.update_size_info()
        # 初期化完了後、自動プレビューを有効化
        state.enable_auto_preview()

    ft.app(target=_app)


__all__ = ["main"]
