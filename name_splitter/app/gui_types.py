"""Type definitions and protocols for Flet GUI widgets.

This module provides type-safe definitions for Flet widgets using Protocols.
This allows proper type checking while maintaining compatibility with Flet's
dynamic nature.
"""
from __future__ import annotations

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
    """Protocol for Flet Button widgets."""
    text: str
    icon: Any
    disabled: bool
    on_click: Optional[Callable[[Any], None]]


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
