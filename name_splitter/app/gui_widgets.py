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
        )
        fields["gutter_unit_field"] = ft.Dropdown(
            label="Gutter unit",
            options=[
                ft.dropdown.Option("px"),
                ft.dropdown.Option("mm"),
            ],
            value="px",
            width=110,
        )
        fields["gutter_field"] = ft.TextField(
            label="Gutter", value="0", width=90, keyboard_type=ft.KeyboardType.NUMBER
        )
        fields["grid_color_field"] = ft.TextField(
            label="Grid color", value="#FF5030", width=110
        )
        fields["grid_alpha_field"] = ft.TextField(label="Alpha", value="170", width=90)
        fields["grid_width_field"] = ft.TextField(label="Width px", value="1", width=90)
        
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
        fields["input_field"] = ft.TextField(label="Input image (PNG)", expand=True)
        fields["out_dir_field"] = ft.TextField(
            label="Output directory (optional)", expand=True
        )
        fields["test_page_field"] = ft.TextField(
            label="Test page (1-based, optional)", width=180
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
        
        return elements


__all__ = ["WidgetBuilder", "TRANSPARENT_PNG_BASE64"]
