"""Widget builders for CSP Name Splitter GUI.

Why: gui.py requires a clean way to create all Flet widget instances
     (TextFields, Dropdowns, Buttons, etc.) without embedding widget
     construction directly in the application entry-point.
How: WidgetBuilder inherits WidgetLayoutMixin (gui_widgets_layout.py)
     which provides the layout-assembly methods. This file focuses on
     widget instantiation (create_* methods).
"""
from __future__ import annotations

from typing import Any

from name_splitter.app.gui_widgets_layout import WidgetLayoutMixin


# TRANSPARENT_PNG_BASE64 for preview image
TRANSPARENT_PNG_BASE64 = (
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR4nGNgYAAAAAMA"
    "ASsJTYQAAAAASUVORK5CYII="
)


class WidgetBuilder(WidgetLayoutMixin):
    """Builds all GUI widgets and layout structures for CSP Name Splitter.

    Why: Separating widget construction from gui.py keeps the entry-point
         concise and makes each widget's default values easy to locate.
    How: Inherits WidgetLayoutMixin for layout-assembly methods. create_*
         methods return plain dicts so gui.py can unpack them into typed
         dataclasses (CommonFields, ImageFields, etc.).
    """

    def __init__(self, ft: Any) -> None:
        """Initialize WidgetBuilder with the Flet module.

        Why: Flet is imported lazily inside main() to avoid a hard import
             dependency at module level (allows tests without flet installed).
        How: Stores the module reference in self.ft so all create_* and
             build_* methods (from WidgetLayoutMixin) can access it.

        Args:
            ft: The flet module (imported as 'import flet as ft')
        """
        self.ft = ft
    
    def create_common_fields(self) -> dict[str, Any]:
        """Create common fields: config, page size, DPI, grid, margin.
        
        Returns:
            Dictionary with all common field widgets
        """
        ft = self.ft
        
        fields = {}
        
        # -- Config file --
        fields["config_field"] = ft.TextField(
            label="Config (YAML/JSON, optional)", expand=True
        )
        
        # -- Page size & DPI --
        fields["page_size_field"] = ft.Dropdown(
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
        fields["orientation_field"] = ft.Dropdown(
            label="Orientation",
            options=[
                ft.dropdown.Option(key="portrait", text="縦 (portrait)"),
                ft.dropdown.Option(key="landscape", text="横 (landscape)"),
            ],
            value="portrait",
            width=155,
        )
        fields["dpi_field"] = ft.TextField(
            label="DPI",
            value="300",
            width=80,
            hint_text="例: 600",
            keyboard_type=ft.KeyboardType.NUMBER,
        )
        fields["custom_size_unit_field"] = ft.Dropdown(
            label="Size unit",
            options=[
                ft.dropdown.Option("px"),
                ft.dropdown.Option("mm"),
            ],
            value="px",
            width=100,
        )
        fields["custom_width_field"] = ft.TextField(
            label="Width", value="", width=100, keyboard_type=ft.KeyboardType.NUMBER
        )
        fields["custom_height_field"] = ft.TextField(
            label="Height", value="", width=100, keyboard_type=ft.KeyboardType.NUMBER
        )
        fields["size_info_text"] = ft.Text("", size=11, italic=True)
        
        # -- Grid settings --
        fields["rows_field"] = ft.TextField(
            label="Rows", value="4", width=80, keyboard_type=ft.KeyboardType.NUMBER
        )
        fields["cols_field"] = ft.TextField(
            label="Cols", value="4", width=80, keyboard_type=ft.KeyboardType.NUMBER
        )
        fields["order_field"] = ft.Dropdown(
            label="Order",
            options=[
                ft.dropdown.Option(key="rtl_ttb", text="右→左 ↓"),
                ft.dropdown.Option(key="ltr_ttb", text="左→右 ↓"),
            ],
            value="rtl_ttb",
            width=145,
            tooltip="右→左: 日本の漫画形式\n左→右: 海外コミック形式",
        )
        fields["gutter_unit_field"] = ft.Dropdown(
            label="Gutter unit",
            options=[
                ft.dropdown.Option("px"),
                ft.dropdown.Option("mm"),
            ],
            value="px",
            width=110,
            tooltip="コマとコマの間の隙間（間隔）",
        )
        fields["gutter_field"] = ft.TextField(
            label="Gutter", value="0", width=90, keyboard_type=ft.KeyboardType.NUMBER
        )
        fields["grid_color_field"] = ft.TextField(
            label="Grid color", value="#FF5030", width=110
        )
        fields["grid_alpha_field"] = ft.TextField(
            label="Alpha", value="170", width=90,
            tooltip="不透明度（0=透明、255=不透明）",
        )
        fields["grid_width_field"] = ft.TextField(label="Width px", value="1", width=90)
        outline = ft.Colors.OUTLINE if hasattr(ft, "Colors") else ft.colors.OUTLINE
        fields["grid_color_swatch"] = ft.Container(
            width=24, height=24, border_radius=4,
            bgcolor="#FF5030",
            border=ft.border.all(1, outline),
        )
        
        # -- Margin (4 directions + unit) --
        fields["margin_unit_field"] = ft.Dropdown(
            label="Margin unit",
            options=[
                ft.dropdown.Option("px"),
                ft.dropdown.Option("mm"),
            ],
            value="px",
            width=110,
        )
        fields["margin_top_field"] = ft.TextField(
            label="Top", value="0", width=80, keyboard_type=ft.KeyboardType.NUMBER
        )
        fields["margin_bottom_field"] = ft.TextField(
            label="Bottom", value="0", width=80, keyboard_type=ft.KeyboardType.NUMBER
        )
        fields["margin_left_field"] = ft.TextField(
            label="Left", value="0", width=80, keyboard_type=ft.KeyboardType.NUMBER
        )
        fields["margin_right_field"] = ft.TextField(
            label="Right", value="0", width=80, keyboard_type=ft.KeyboardType.NUMBER
        )
        
        return fields
    
    def create_image_split_fields(self) -> dict[str, Any]:
        """Create Image Split tab fields.
        
        Returns:
            Dictionary with Image Split field widgets
        """
        ft = self.ft
        
        fields = {}
        fields["input_field"] = ft.TextField(
            label="入力画像を選択 (PNG)",
            expand=True,
            hint_text="画像ファイルをここにパス入力 または「選択」ボタンをクリック",
        )
        fields["out_dir_field"] = ft.TextField(
            label="Output directory (optional)", expand=True
        )
        fields["test_page_field"] = ft.TextField(
            label="Test page (1-based, optional)", width=180
        )
        fields["output_format_field"] = ft.Dropdown(
            label="Output format",
            options=[
                ft.dropdown.Option(key="png", text="PNG (images)"),
                ft.dropdown.Option(key="pdf", text="PDF (single file)"),
            ],
            value="png",
            width=180,
            tooltip="PNG: 個別画像ファイル\nPDF: 1つのPDFにまとめて出力",
        )
        fields["output_dpi_field"] = ft.TextField(
            label="出力DPI (0=リサイズなし)",
            value="0",
            width=180,
            tooltip="分割後のページを指定DPIにリサイズ（例: 350）。0で無効。",
        )
        fields["page_number_start_field"] = ft.TextField(
            label="開始ページ番号",
            value="1",
            width=140,
            tooltip="出力ファイル名の開始番号（例: 3で page_003 から開始）",
        )
        fields["skip_pages_field"] = ft.TextField(
            label="スキップページ (カンマ区切り)",
            value="",
            width=200,
            tooltip="出力しないページ番号（例: 1,2 で表紙と裏表紙をスキップ）",
        )
        fields["odd_even_field"] = ft.Dropdown(
            label="出力ページ",
            options=[
                ft.dropdown.Option(key="all", text="全ページ"),
                ft.dropdown.Option(key="odd", text="奇数ページのみ"),
                ft.dropdown.Option(key="even", text="偶数ページのみ"),
            ],
            value="all",
            width=160,
        )
        
        return fields

    def create_template_fields(self) -> dict[str, Any]:
        """Create Template tab fields (Finish, Basic, Grid visual).
        
        Returns:
            Dictionary with Template field widgets
        """
        ft = self.ft
        
        fields = {}
        
        # Template output
        fields["template_out_field"] = ft.TextField(
            label="Template output PNG", expand=True
        )
        
        # -- Finish frame --
        fields["draw_finish_field"] = ft.Checkbox(
            label="Draw finish frame", value=True
        )
        fields["finish_size_mode_field"] = ft.Dropdown(
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
        fields["finish_width_field"] = ft.TextField(label="Width", value="", width=110)
        fields["finish_height_field"] = ft.TextField(label="Height", value="", width=110)
        fields["finish_offset_x_field"] = ft.TextField(
            label="Offset X mm", value="0", width=110
        )
        fields["finish_offset_y_field"] = ft.TextField(
            label="Offset Y mm", value="0", width=110
        )
        fields["finish_color_field"] = ft.TextField(
            label="Color", value="#FFFFFF", width=100
        )
        fields["finish_alpha_field"] = ft.TextField(label="Alpha", value="200", width=90)
        fields["finish_line_width_field"] = ft.TextField(
            label="Line px", value="2", width=90
        )
        outline = ft.Colors.OUTLINE if hasattr(ft, "Colors") else ft.colors.OUTLINE
        fields["finish_color_swatch"] = ft.Container(
            width=24, height=24, border_radius=4,
            bgcolor="#FFFFFF",
            border=ft.border.all(1, outline),
        )
        
        # -- Basic frame --
        fields["draw_basic_field"] = ft.Checkbox(
            label="Draw basic frame", value=True
        )
        fields["basic_size_mode_field"] = ft.Dropdown(
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
        fields["basic_width_field"] = ft.TextField(label="Width", value="", width=110)
        fields["basic_height_field"] = ft.TextField(label="Height", value="", width=110)
        fields["basic_offset_x_field"] = ft.TextField(
            label="Offset X mm", value="0", width=110
        )
        fields["basic_offset_y_field"] = ft.TextField(
            label="Offset Y mm", value="0", width=110
        )
        fields["basic_color_field"] = ft.TextField(
            label="Color", value="#00AAFF", width=100
        )
        fields["basic_alpha_field"] = ft.TextField(label="Alpha", value="200", width=90)
        fields["basic_line_width_field"] = ft.TextField(
            label="Line px", value="2", width=90
        )
        outline = ft.Colors.OUTLINE if hasattr(ft, "Colors") else ft.colors.OUTLINE
        fields["basic_color_swatch"] = ft.Container(
            width=24, height=24, border_radius=4,
            bgcolor="#00AAFF",
            border=ft.border.all(1, outline),
        )
        
        return fields
    
    def create_ui_elements(self) -> dict[str, Any]:
        """Create common UI elements: log, progress, status, preview.
        
        Returns:
            Dictionary with UI element widgets
        """
        ft = self.ft
        
        elements = {}
        elements["log_field"] = ft.TextField(
            multiline=True, read_only=True, expand=True, value=""
        )
        elements["progress_bar"] = ft.ProgressBar(width=350, value=0)
        elements["status_text"] = ft.Text("Idle")
        
        elements["preview_image"] = ft.Image(
            src=f"data:image/png;base64,{TRANSPARENT_PNG_BASE64}",
            width=550,
            height=550,
            fit="contain",
        )
        elements["preview_viewer"] = ft.InteractiveViewer(
            content=elements["preview_image"],
            min_scale=0.1,
            max_scale=5.0,
            boundary_margin=ft.Margin.all(100),
        )
        elements["preview_loading_ring"] = ft.ProgressRing(
            width=48, height=48, visible=False,
        )
        
        return elements

    def create_batch_fields(self) -> dict[str, Any]:
        """Create Batch tab fields: input/output dir, recursive flag, run/cancel, status.

        Why: Batch processing requires a dedicated set of controls distinct from
             single-image ImageFields. Centralising widget creation here keeps
             gui.py and the layout mixin free of instantiation details.
        How: Creates TextFields for directory paths, a Checkbox for recursive
             scan, ElevatedButton/OutlinedButton for run/cancel, and a Text
             widget for per-job progress display.

        Returns:
            Dictionary with all batch field widgets keyed by field name.
        """
        ft = self.ft

        fields: dict[str, Any] = {}
        fields["batch_dir_field"] = ft.TextField(
            label="入力ディレクトリ",
            expand=True,
            hint_text="PNG ファイルが入っているフォルダを指定",
        )
        fields["batch_out_dir_field"] = ft.TextField(
            label="出力ディレクトリ（省略可）",
            expand=True,
            hint_text="省略時は各画像の隣に出力",
        )
        fields["batch_recursive_field"] = ft.Checkbox(
            label="サブフォルダを再帰検索",
            value=False,
            tooltip="ON: サブフォルダ内の PNG も対象にする",
        )
        fields["batch_run_btn"] = ft.ElevatedButton(
            "Batch Run",
            icon=ft.Icons.PLAY_ARROW,
        )
        fields["batch_cancel_btn"] = ft.OutlinedButton(
            "Cancel",
            icon=ft.Icons.CANCEL,
            disabled=True,
        )
        fields["batch_status_text"] = ft.Text("Idle", size=12, italic=True)

        return fields

    def create_preset_fields(self) -> dict[str, Any]:
        """Create preset management widgets: dropdown, save button, delete button.

        Why: Presets require three co-located controls. Centralising their
             creation here keeps gui.py and the layout mixin free of widget
             instantiation details.
        How: Returns a dict with 'dropdown', 'save_btn', and 'delete_btn'
             keyed by the PresetFields field names.

        Returns:
            Dictionary with preset widget references keyed by field name.
        """
        ft = self.ft

        fields: dict[str, Any] = {}
        fields["dropdown"] = ft.Dropdown(
            label="プリセット",
            options=[],
            width=220,
            hint_text="保存済みプリセットを選択",
        )
        fields["save_btn"] = ft.ElevatedButton(
            "Save",
            icon=ft.Icons.BOOKMARK_ADD,
            tooltip="現在の設定をプリセットとして保存",
        )
        fields["delete_btn"] = ft.OutlinedButton(
            "Delete",
            icon=ft.Icons.DELETE_OUTLINE,
            tooltip="選択中のプリセットを削除",
        )
        return fields

    def create_recent_dropdown(self, label: str, options: list[str]) -> Any:
        """Create a dropdown widget pre-populated with recently used file paths.

        Why: Letting users re-open a recently used file from a dropdown is
             faster than navigating the file picker again.
        How: Creates a Dropdown with ft.dropdown.Option entries for each
             path string; the dropdown has a fixed width to stay compact.

        Args:
            label: Human-readable label shown above the dropdown.
            options: List of recent file path strings, most-recent first.

        Returns:
            ft.Dropdown widget ready to be placed in a layout.
        """
        ft = self.ft
        return ft.Dropdown(
            label=label,
            options=[ft.dropdown.Option(p) for p in options],
            width=300,
            hint_text="最近使ったファイル",
        )

    def create_quick_run_button(self) -> Any:
        """Create the Quick Run button that repeats the last successful run.

        Why: Users processing the same image repeatedly (iterative tuning)
             should be able to re-run with a single click rather than
             re-entering paths and settings.
        How: Returns an ElevatedButton styled with a REPLAY icon; the
             on_click handler is wired in gui.py.

        Returns:
            ft.ElevatedButton widget for Quick Run.
        """
        ft = self.ft
        return ft.ElevatedButton(
            "Quick Run",
            icon=ft.Icons.REPLAY,
            tooltip="前回の設定で再実行",
            disabled=True,
        )


__all__ = ["WidgetBuilder", "TRANSPARENT_PNG_BASE64"]
