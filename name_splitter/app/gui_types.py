"""Type definitions and protocols for Flet GUI widgets.

This module provides type-safe definitions for Flet widgets using Protocols.
This allows proper type checking while maintaining compatibility with Flet's
dynamic nature.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, Any, Callable, Optional


# ============================================================== #
#  Flet Widget Protocols                                         #
# ============================================================== #

class FletTextField(Protocol):
    """Protocol for Flet TextField widget."""
    value: str
    label: str
    expand: bool
    width: int
    hint_text: str
    keyboard_type: Any
    read_only: bool
    multiline: bool
    error_text: Optional[str]
    on_change: Optional[Callable[[Any], None]]


class FletDropdown(Protocol):
    """Protocol for Flet Dropdown widget."""
    value: str
    label: str
    width: int
    options: list[Any]
    on_change: Optional[Callable[[Any], None]]


class FletCheckbox(Protocol):
    """Protocol for Flet Checkbox widget."""
    value: bool
    label: str
    on_change: Optional[Callable[[Any], None]]


class FletText(Protocol):
    """Protocol for Flet Text widget."""
    value: str
    size: int
    italic: bool
    weight: Any


class FletProgressBar(Protocol):
    """Protocol for Flet ProgressBar widget."""
    value: Optional[float]
    width: int


class FletImage(Protocol):
    """Protocol for Flet Image widget."""
    src: str
    width: int
    height: int
    fit: str


class FletButton(Protocol):
    """Protocol for Flet Button widgets (ElevatedButton, OutlinedButton, etc)."""
    icon: Any
    disabled: bool
    on_click: Any


class FletInteractiveViewer(Protocol):
    """Protocol for Flet InteractiveViewer widget."""
    content: Any
    min_scale: float
    max_scale: float
    boundary_margin: Any


# ============================================================== #
#  Type Aliases for Common Widget Types                         #
# ============================================================== #

# Field widgets
TextField = FletTextField
Dropdown = FletDropdown
Checkbox = FletCheckbox

# Display widgets
Text = FletText
ProgressBar = FletProgressBar
Image = FletImage

# Interactive widgets
Button = FletButton
InteractiveViewer = FletInteractiveViewer

# Generic widget type
Widget = Any  # For widgets not yet typed

# Page and event types
Page = Any
ControlEvent = Any
FilePicker = Any
Clipboard = Any


# ============================================================== #
#  Widget Field Groups (Phase 6: Data Structure Improvement)    #
# ============================================================== #

@dataclass
class CommonFields:
    """Common settings fields: config, page size, DPI, grid, margins."""
    
    # Configuration
    config_field: TextField
    
    # Page size and DPI
    page_size_field: Dropdown
    orientation_field: Dropdown
    dpi_field: TextField
    custom_size_unit_field: Dropdown
    custom_width_field: TextField
    custom_height_field: TextField
    size_info_text: Text
    
    # Grid settings
    rows_field: TextField
    cols_field: TextField
    order_field: Dropdown
    gutter_unit_field: Dropdown
    gutter_field: TextField
    grid_color_field: TextField
    grid_alpha_field: TextField
    grid_width_field: TextField
    grid_color_swatch: Any  # Color preview container for grid line color
    
    # Margin settings
    margin_unit_field: Dropdown
    margin_top_field: TextField
    margin_bottom_field: TextField
    margin_left_field: TextField
    margin_right_field: TextField


@dataclass
class ImageFields:
    """Image split tab fields."""
    
    input_field: TextField
    out_dir_field: TextField
    test_page_field: TextField
    output_format_field: Dropdown


@dataclass
class TemplateFields:
    """Template generation tab fields."""
    
    template_out_field: TextField
    
    # Finish frame
    draw_finish_field: Checkbox
    finish_size_mode_field: Dropdown
    finish_width_field: TextField
    finish_height_field: TextField
    finish_offset_x_field: TextField
    finish_offset_y_field: TextField
    finish_color_field: TextField
    finish_alpha_field: TextField
    finish_line_width_field: TextField
    finish_color_swatch: Any  # Color preview container for finish frame color
    
    # Basic frame
    draw_basic_field: Checkbox
    basic_size_mode_field: Dropdown
    basic_width_field: TextField
    basic_height_field: TextField
    basic_offset_x_field: TextField
    basic_offset_y_field: TextField
    basic_color_field: TextField
    basic_alpha_field: TextField
    basic_line_width_field: TextField
    basic_color_swatch: Any  # Color preview container for basic frame color


@dataclass
class UiElements:
    """Common UI elements: log, progress, status, preview."""
    
    log_field: TextField
    progress_bar: ProgressBar
    status_text: Text
    preview_image: Image
    preview_viewer: InteractiveViewer
    preview_loading_ring: Any  # ProgressRing shown during preview generation
    run_btn: Button
    cancel_btn: Button


@dataclass
class BatchFields:
    """Batch processing tab fields.

    Why: Batch processing has its own set of UI controls (directory pickers,
         recursive flag, dedicated run/cancel, status) that are logically
         separate from single-image ImageFields.
    How: Plain dataclass grouping all batch-specific widget references so
         GuiHandlersBatchMixin can access them via self.w.batch.
    """

    batch_dir_field: TextField
    batch_out_dir_field: TextField
    batch_recursive_field: Checkbox
    batch_run_btn: Button
    batch_cancel_btn: Button
    batch_status_text: Text


__all__ = ["CommonFields", "ImageFields", "TemplateFields", "UiElements", "BatchFields"]
