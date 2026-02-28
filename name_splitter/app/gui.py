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
from name_splitter.app.gui_widgets import WidgetBuilder
from name_splitter.app.gui_types import CommonFields, ImageFields, TemplateFields, UiElements


def main() -> None:
    try:
        import flet as ft
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError("flet is required for GUI mode") from exc

    def _app(page: ft.Page) -> None:
        page.title = "CSP Name Splitter"
        page.window.width = 1200
        page.window.height = 850

        # ============================================================== #
        #  Build widgets using WidgetBuilder                             #
        # ============================================================== #
        builder = WidgetBuilder(ft)
        
        # Create all field widgets
        common_fields = builder.create_common_fields()
        image_fields = builder.create_image_split_fields()
        template_fields = builder.create_template_fields()
        ui_elements = builder.create_ui_elements()
        
        # Extract frequently used widgets for convenience
        config_field = common_fields["config_field"]
        page_size_field = common_fields["page_size_field"]
        orientation_field = common_fields["orientation_field"]
        dpi_field = common_fields["dpi_field"]
        custom_size_unit_field = common_fields["custom_size_unit_field"]
        custom_width_field = common_fields["custom_width_field"]
        custom_height_field = common_fields["custom_height_field"]
        size_info_text = common_fields["size_info_text"]
        rows_field = common_fields["rows_field"]
        cols_field = common_fields["cols_field"]
        order_field = common_fields["order_field"]
        gutter_unit_field = common_fields["gutter_unit_field"]
        gutter_field = common_fields["gutter_field"]
        margin_unit_field = common_fields["margin_unit_field"]
        margin_top_field = common_fields["margin_top_field"]
        margin_bottom_field = common_fields["margin_bottom_field"]
        margin_left_field = common_fields["margin_left_field"]
        margin_right_field = common_fields["margin_right_field"]
        
        input_field = image_fields["input_field"]
        out_dir_field = image_fields["out_dir_field"]
        test_page_field = image_fields["test_page_field"]
        
        template_out_field = template_fields["template_out_field"]
        draw_finish_field = template_fields["draw_finish_field"]
        finish_size_mode_field = template_fields["finish_size_mode_field"]
        finish_width_field = template_fields["finish_width_field"]
        finish_height_field = template_fields["finish_height_field"]
        finish_offset_x_field = template_fields["finish_offset_x_field"]
        finish_offset_y_field = template_fields["finish_offset_y_field"]
        finish_color_field = template_fields["finish_color_field"]
        finish_alpha_field = template_fields["finish_alpha_field"]
        finish_line_width_field = template_fields["finish_line_width_field"]
        draw_basic_field = template_fields["draw_basic_field"]
        basic_size_mode_field = template_fields["basic_size_mode_field"]
        basic_width_field = template_fields["basic_width_field"]
        basic_height_field = template_fields["basic_height_field"]
        basic_offset_x_field = template_fields["basic_offset_x_field"]
        basic_offset_y_field = template_fields["basic_offset_y_field"]
        basic_color_field = template_fields["basic_color_field"]
        basic_alpha_field = template_fields["basic_alpha_field"]
        basic_line_width_field = template_fields["basic_line_width_field"]
        grid_color_field = common_fields["grid_color_field"]
        grid_alpha_field = common_fields["grid_alpha_field"]
        grid_width_field = common_fields["grid_width_field"]
        
        log_field = ui_elements["log_field"]
        progress_bar = ui_elements["progress_bar"]
        status_text = ui_elements["status_text"]
        preview_image = ui_elements["preview_image"]
        preview_viewer = ui_elements["preview_viewer"]
        preview_loading_ring = ui_elements["preview_loading_ring"]

        clipboard = ft.Clipboard() if hasattr(ft, "Clipboard") else None
        state = GuiState()  # 状態管理クラス
        
        # Buttons (need to be defined before handlers)
        run_btn = ft.ElevatedButton("Run", icon=ft.Icons.PLAY_ARROW)
        cancel_btn = ft.OutlinedButton("Cancel", icon=ft.Icons.CANCEL, disabled=True)
        
        # Initialize GuiWidgets using grouped field dataclasses
        widgets = GuiWidgets(
            common=CommonFields(**common_fields),
            image=ImageFields(**image_fields),
            template=TemplateFields(**template_fields),
            ui=UiElements(**ui_elements, run_btn=run_btn, cancel_btn=cancel_btn),
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
        clear_log_btn = ft.OutlinedButton("Clear", on_click=handlers.on_clear_log, icon=ft.Icons.DELETE_OUTLINE)

        # ============================================================== #
        #  Build tab content using WidgetBuilder                         #
        # ============================================================== #
        tab_image = builder.build_tab_image(
            image_fields, run_btn, cancel_btn, pick_input, pick_out_dir,
            open_output_folder=handlers.on_open_output_folder,
        )
        tab_template = builder.build_tab_template(
            template_fields, tmpl_btn, pick_template_out
        )
        common_settings = builder.build_common_settings_area(
            common_fields, pick_config,
            reset_config=handlers.on_reset_defaults,
        )

        # ============================================================== #
        #  レイアウト組み立て: Preview(左) | Settings(右)                  #
        # ============================================================== #
        outline_color = ft.Colors.OUTLINE if hasattr(ft, "Colors") else ft.colors.OUTLINE

        page.add(
            ft.Row([
                # Left: Preview with loading overlay
                ft.Container(
                    content=ft.Stack([
                        ft.Container(
                            content=preview_viewer,
                            border=ft.border.all(1, outline_color),
                            padding=8,
                        ),
                        ft.Container(
                            content=preview_loading_ring,
                            alignment=ft.alignment.center,
                        ),
                    ]),
                    expand=1,
                    padding=ft.Padding(4, 4, 2, 4),
                ),
                # Right: Settings + Tabs + Log + Status
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
                        ft.Row(
                            [ft.Text("Log", weight=ft.FontWeight.BOLD, size=12), clear_log_btn, copy_log_btn],
                            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                        ),
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

        # Keyboard shortcuts: Ctrl+R → Run, Ctrl+. → Cancel
        def on_keyboard(e: ft.KeyboardEvent) -> None:
            """Handle global keyboard shortcuts."""
            if e.ctrl and e.key == "R":
                if not run_btn.disabled:
                    handlers.on_run(None)
            elif e.ctrl and e.key == ".":
                if not cancel_btn.disabled:
                    handlers.on_cancel(None)

        page.on_keyboard_event = on_keyboard

    ft.app(target=_app)


__all__ = ["main"]
