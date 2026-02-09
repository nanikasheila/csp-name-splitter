"""Widget builders for CSP Name Splitter GUI.

This module provides the WidgetBuilder class which creates and organizes
all GUI widgets (TextFields, Dropdowns, Buttons, etc.) and layout structures.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Callable

if TYPE_CHECKING:
    from name_splitter.app.gui_types import (
        TextField,
        Dropdown,
        Checkbox,
        Text,
        ProgressBar,
        Image,
        InteractiveViewer,
        Widget,
    )

# TRANSPARENT_PNG_BASE64 for preview image
TRANSPARENT_PNG_BASE64 = (
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR4nGNgYAAAAAMA"
    "ASsJTYQAAAAASUVORK5CYII="
)


class WidgetBuilder:
    """Builds all GUI widgets and layout structures for CSP Name Splitter."""
    
    def __init__(self, ft: any):  # type: ignore
        """Initialize WidgetBuilder with Flet module.
        
        Args:
            ft: The Flet module (imported as 'import flet as ft')
        """
        self.ft = ft
    
    def create_common_fields(self) -> dict[str, TextField | Dropdown | Text]:
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
    
    def create_image_split_fields(self) -> dict[str, TextField]:
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
    
    def create_template_fields(self) -> dict[str, TextField | Dropdown | Checkbox]:
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
    
    def create_ui_elements(self) -> dict[str, TextField | ProgressBar | Text | Image | InteractiveViewer]:
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
    
    def build_common_settings_area(
        self, fields: dict[str, TextField | Dropdown | Text], pick_config: Callable[[any], None]  # type: ignore
    ) -> Widget:
        """Build common settings area (config, page size, grid, margin).
        
        Args:
            fields: Dictionary containing all field widgets
            pick_config: FilePicker function for config selection
            
        Returns:
            ft.Container with common settings layout
        """
        ft = self.ft
        
        return ft.Container(
            content=ft.Column([
                # Config file
                ft.Row([
                    ft.Icon(ft.Icons.DESCRIPTION, size=16),
                    ft.Text("Config file", weight=ft.FontWeight.BOLD, size=12)
                ], spacing=4),
                ft.Row([
                    fields["config_field"],
                    ft.IconButton(
                        icon=ft.Icons.SETTINGS,
                        tooltip="Select config YAML/JSON",
                        on_click=pick_config,
                    ),
                ]),
                ft.Divider(height=2),
                # Page size & DPI
                ft.Row([
                    ft.Icon(ft.Icons.STRAIGHTEN, size=16),
                    ft.Text("Page size & DPI", weight=ft.FontWeight.BOLD, size=12)
                ], spacing=4),
                ft.Row([
                    fields["page_size_field"],
                    fields["orientation_field"],
                    fields["dpi_field"]
                ], wrap=True),
                ft.Row([
                    fields["custom_size_unit_field"],
                    fields["custom_width_field"],
                    fields["custom_height_field"]
                ], wrap=True),
                ft.Container(
                    content=fields["size_info_text"],
                    bgcolor=ft.Colors.SURFACE_CONTAINER,
                    border_radius=6,
                    padding=ft.Padding(8, 4, 8, 4),
                ),
                ft.Divider(height=2),
                # Grid settings
                ft.Row([
                    ft.Icon(ft.Icons.GRID_VIEW, size=16),
                    ft.Text("Grid settings", weight=ft.FontWeight.BOLD, size=12)
                ], spacing=4),
                ft.Row([
                    fields["rows_field"],
                    fields["cols_field"],
                    fields["order_field"]
                ], wrap=True),
                ft.Row([
                    fields["gutter_unit_field"],
                    fields["gutter_field"]
                ], wrap=True),
                ft.Row([
                    fields["grid_color_field"],
                    fields["grid_alpha_field"],
                    fields["grid_width_field"]
                ], wrap=True),
                ft.Divider(height=2),
                ft.Row([
                    ft.Icon(ft.Icons.CROP_FREE, size=16),
                    ft.Text("Margins", weight=ft.FontWeight.BOLD, size=12)
                ], spacing=4),
                ft.Row([
                    fields["margin_unit_field"],
                    fields["margin_top_field"],
                    fields["margin_bottom_field"],
                    fields["margin_left_field"],
                    fields["margin_right_field"]
                ], wrap=True),
            ], spacing=4, scroll=ft.ScrollMode.AUTO),
            padding=ft.Padding(8, 4, 8, 4),
        )
    
    def build_tab_image(
        self,
        fields: dict[str, TextField],
        run_btn: Widget,
        cancel_btn: Widget,
        pick_input: Callable[[any], None],  # type: ignore
        pick_out_dir: Callable[[any], None],  # type: ignore
    ) -> Widget:
        """Build Image Split tab content.
        
        Args:
            fields: Dictionary containing image split field widgets
            run_btn: Run button widget
            cancel_btn: Cancel button widget
            pick_input: FilePicker function for input selection
            pick_out_dir: FilePicker function for output dir selection
            
        Returns:
            ft.Container with Image Split tab layout
        """
        ft = self.ft
        
        return ft.Container(
            content=ft.Column([
                ft.Row([
                    fields["input_field"],
                    ft.IconButton(
                        icon=ft.Icons.FOLDER_OPEN,
                        tooltip="Select image",
                        on_click=pick_input,
                    ),
                ]),
                ft.Row([
                    fields["out_dir_field"],
                    ft.IconButton(
                        icon=ft.Icons.FOLDER,
                        tooltip="Select output dir",
                        on_click=pick_out_dir,
                    ),
                    fields["test_page_field"],
                ]),
                ft.Row([run_btn, cancel_btn]),
            ], spacing=6, scroll=ft.ScrollMode.AUTO),
            padding=ft.Padding(8, 6, 8, 6),
        )
    
    def build_tab_template(
        self,
        fields: dict[str, TextField | Dropdown | Checkbox],
        tmpl_btn: Widget,
        pick_template_out: Callable[[any], None],  # type: ignore
    ) -> Widget:
        """Build Template tab content.
        
        Args:
            fields: Dictionary containing template field widgets
            tmpl_btn: Generate template button widget
            pick_template_out: FilePicker function for template output selection
            
        Returns:
            ft.Container with Template tab layout
        """
        ft = self.ft
        
        return ft.Container(
            content=ft.Column([
                # Finish frame (accordion)
                ft.ExpansionPanelList(
                    controls=[
                        ft.ExpansionPanel(
                            header=ft.Row([
                                fields["draw_finish_field"],
                                ft.Text("Finish frame", weight=ft.FontWeight.BOLD, size=12)
                            ], spacing=4),
                            content=ft.Column([
                                ft.Row([
                                    fields["finish_size_mode_field"],
                                    fields["finish_width_field"],
                                    fields["finish_height_field"]
                                ], wrap=True),
                                ft.Row([
                                    fields["finish_offset_x_field"],
                                    fields["finish_offset_y_field"],
                                    fields["finish_color_field"],
                                    fields["finish_alpha_field"],
                                    fields["finish_line_width_field"]
                                ], wrap=True),
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
                            header=ft.Row([
                                fields["draw_basic_field"],
                                ft.Text("Basic frame", weight=ft.FontWeight.BOLD, size=12)
                            ], spacing=4),
                            content=ft.Column([
                                ft.Row([
                                    fields["basic_size_mode_field"],
                                    fields["basic_width_field"],
                                    fields["basic_height_field"]
                                ], wrap=True),
                                ft.Row([
                                    fields["basic_offset_x_field"],
                                    fields["basic_offset_y_field"],
                                    fields["basic_color_field"],
                                    fields["basic_alpha_field"],
                                    fields["basic_line_width_field"]
                                ], wrap=True),
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
                    fields["template_out_field"],
                    ft.IconButton(
                        icon=ft.Icons.SAVE,
                        tooltip="Save template PNG",
                        on_click=pick_template_out,
                    ),
                ]),
                ft.Row([tmpl_btn]),
            ], spacing=4, scroll=ft.ScrollMode.AUTO),
            padding=ft.Padding(8, 6, 8, 6),
        )


__all__ = ["WidgetBuilder", "TRANSPARENT_PNG_BASE64"]
