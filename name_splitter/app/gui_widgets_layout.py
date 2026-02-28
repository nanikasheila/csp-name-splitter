"""Layout building mixin for CSP Name Splitter GUI.

Why: WidgetBuilder has two distinct responsibilities — creating widget
     instances (field values, options) and assembling them into layout
     trees (Row/Column/Container hierarchies). Separating layout code
     into this mixin keeps gui_widgets.py within the 500-line limit.
How: Pure mixin — no __init__, relies on WidgetBuilder to expose self.ft
     (the Flet module). WidgetBuilder inherits this mixin and gains all
     layout-building methods.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Any, Callable

if TYPE_CHECKING:
    from name_splitter.app.gui_types import (
        TextField,
        Dropdown,
        Checkbox,
        Widget,
    )


class WidgetLayoutMixin:
    """Mixin providing layout-building methods for CSP Name Splitter GUI.

    Why: Layout construction code (Row/Column nesting, Container padding,
         icon labels) is lengthy but conceptually separate from widget
         instantiation. Grouping it here makes both files easier to skim.
    How: Each build_* method receives pre-built widget dicts/objects and
         assembles a Container tree. The mixin only calls self.ft (Flet
         module) for layout primitives — no widget instantiation.
    """

    if TYPE_CHECKING:
        ft: Any  # Flet module — set in WidgetBuilder.__init__

    def build_tab_config(
        self,
        fields: dict,
        pick_config: Callable,
        reset_config: Callable | None = None,
        save_config: Callable | None = None,
    ) -> object:
        """Build the Config tab content (config file, page size, grid, margins).

        Why: All common settings were previously shown above tabs, making
             them always visible but consuming vertical space. Moving them
             into a dedicated Config tab gives each panel full height.
        How: Wraps all field groups in labelled Rows with icon prefixes
             inside a scrollable Column in a padded Container.

        Args:
            fields: Dict of all common field widgets keyed by field name
            pick_config: Async FilePicker callback for config file selection
            reset_config: Optional callback to reset all settings to defaults

        Returns:
            ft.Container with the assembled common settings layout
        """
        ft = self.ft

        config_buttons = [
            ft.IconButton(
                icon=ft.Icons.FOLDER_OPEN,
                tooltip="Select config file",
                on_click=pick_config,
            ),
        ]
        if reset_config is not None:
            config_buttons.append(
                ft.IconButton(
                    icon=ft.Icons.RESTART_ALT,
                    tooltip="Reset to defaults",
                    on_click=reset_config,
                ),
            )
        if save_config is not None:
            config_buttons.append(
                ft.IconButton(
                    icon=ft.Icons.SAVE,
                    tooltip="Save current settings to config file",
                    on_click=save_config,
                ),
            )

        return ft.Container(
            content=ft.Column([
                # Config file row
                ft.Row([
                    ft.Icon(ft.Icons.DESCRIPTION, size=16),
                    ft.Text("Config file", weight=ft.FontWeight.BOLD, size=12)
                ], spacing=4),
                ft.Row([
                    fields["config_field"],
                    *config_buttons,
                ]),
                ft.Divider(height=2),
                # Page size & DPI
                ft.Row([
                    ft.Icon(ft.Icons.STRAIGHTEN, size=16),
                    ft.Text("Page size & DPI", weight=ft.FontWeight.BOLD, size=12),
                    ft.Icon(
                        ft.Icons.INFO_OUTLINE, size=14,
                        color=ft.Colors.OUTLINE,
                        tooltip="DPI: 1インチあたりのドット数。印刷解像度に合わせてください",
                    ),
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
                    ft.Text("Grid settings", weight=ft.FontWeight.BOLD, size=12),
                ], spacing=4),
                ft.Row([
                    fields["rows_field"],
                    fields["cols_field"],
                    fields["order_field"],
                ], wrap=True),
                ft.Row([
                    fields["gutter_unit_field"],
                    fields["gutter_field"]
                ], wrap=True),
                ft.Row([
                    fields["grid_color_field"],
                    fields["grid_color_swatch"],
                    fields["grid_alpha_field"],
                    fields["grid_width_field"]
                ], wrap=True),
                ft.Divider(height=2),
                ft.Row([
                    ft.Icon(ft.Icons.CROP_FREE, size=16),
                    ft.Text("Margins", weight=ft.FontWeight.BOLD, size=12),
                    ft.Icon(
                        ft.Icons.INFO_OUTLINE, size=14,
                        color=ft.Colors.OUTLINE,
                        tooltip="ページ端から有効領域までの余白",
                    ),
                ], spacing=4),
                ft.Row([
                    fields["margin_unit_field"],
                    fields["margin_top_field"],
                    fields["margin_bottom_field"],
                    fields["margin_left_field"],
                    fields["margin_right_field"],
                ], wrap=True),
            ], spacing=8, scroll=ft.ScrollMode.AUTO),
            padding=ft.Padding(8, 4, 8, 4),
            expand=True,
        )

    def build_tab_image(
        self,
        fields: dict,
        run_btn: object,
        cancel_btn: object,
        pick_input: Callable,
        pick_out_dir: Callable,
        open_output_folder: Callable | None = None,
    ) -> object:
        """Build the Image Split tab layout.

        Why: Tab content construction involves nested Row/Column/Container
             trees that obscure intent when mixed with widget creation code.
        How: Accepts pre-built button and field widgets; assembles them in
             a scrollable Column with icon-button rows for file pickers.

        Args:
            fields: Dict of image-split field widgets keyed by field name
            run_btn: ElevatedButton widget for job execution
            cancel_btn: OutlinedButton widget for job cancellation
            pick_input: Async FilePicker callback for input image selection
            pick_out_dir: Async FilePicker callback for output dir selection
            open_output_folder: Optional callback to open output dir in file manager

        Returns:
            ft.Container with the Image Split tab layout
        """
        ft = self.ft

        out_dir_buttons = [
            ft.IconButton(
                icon=ft.Icons.FOLDER,
                tooltip="Select output dir",
                on_click=pick_out_dir,
            ),
        ]
        if open_output_folder is not None:
            out_dir_buttons.append(
                ft.IconButton(
                    icon=ft.Icons.OPEN_IN_NEW,
                    tooltip="Open output folder",
                    on_click=open_output_folder,
                ),
            )

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
                    *out_dir_buttons,
                    fields["test_page_field"],
                ]),
                ft.Divider(height=2),
                # Output format selection
                ft.Row([
                    ft.Icon(ft.Icons.OUTPUT, size=16),
                    ft.Text("Output", weight=ft.FontWeight.BOLD, size=12),
                ], spacing=4),
                ft.Row([fields["output_format_field"]]),
                ft.Divider(height=2),
                ft.Row([run_btn, cancel_btn]),
            ], spacing=6, scroll=ft.ScrollMode.AUTO),
            padding=ft.Padding(8, 6, 8, 6),
        )

    def build_tab_template(
        self,
        fields: dict,
        tmpl_btn: object,
        pick_template_out: Callable,
    ) -> object:
        """Build the Template Generation tab layout.

        Why: The Template tab uses ExpansionPanelList accordions for the
             finish and basic frame sections; the setup code is verbose
             enough to warrant isolation in this mixin.
        How: Wraps finish and basic frame fields in separate
             ExpansionPanelList controls, then adds the output path row and
             generate button. All controls are placed in a scrollable Column.

        Args:
            fields: Dict of template field widgets keyed by field name
            tmpl_btn: ElevatedButton widget for template generation
            pick_template_out: Async FilePicker callback for output path

        Returns:
            ft.Container with the Template tab layout
        """
        ft = self.ft

        return ft.Container(
            content=ft.Column([
                # Finish frame accordion
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
                                    fields["finish_color_swatch"],
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
                # Basic frame accordion
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
                                    fields["basic_color_swatch"],
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
                # Template output path
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


__all__ = ["WidgetLayoutMixin"]
