"""Template generation event handlers mixin for CSP Name Splitter GUI.

Why: gui_handlers.py exceeds 900 lines; template generation (_run_template,
     on_generate_template) is a distinct responsibility that belongs in a
     dedicated mixin alongside other template-specific logic.
How: Pure mixin — no __init__, relies on GuiHandlers to expose self.w,
     self.state, self.page, and shared helpers. GuiHandlers inherits this
     mixin and gains all template-generation event handlers.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

from name_splitter.core import ConfigError
from name_splitter.core.template import generate_template_png
from name_splitter.app.gui_utils import parse_int

if TYPE_CHECKING:
    from name_splitter.app.gui_state import GuiState


class GuiHandlersTemplateMixin:
    """Mixin providing template generation event handlers.

    Why: Template generation (writing a blank template PNG to disk) is
         logically independent of job execution and log management.
         Isolating it here keeps gui_handlers.py within a manageable size.
    How: Relies on GuiHandlers.__init__ to expose self.w (GuiWidgets),
         self.state (GuiState), self.page, self.add_log, self.add_error_log,
         self.set_status, self.flush, self.flush_from_thread, self.show_error,
         self.build_grid_config, self.build_template_style, and
         self.compute_canvas_size_px via the MRO.
    """

    # Declared here so that the type checker recognises attributes that are
    # set by the concrete GuiHandlers class.
    if TYPE_CHECKING:
        w: Any        # GuiWidgets — set in GuiHandlers.__init__
        state: GuiState
        page: Any

        def add_log(self, msg: str) -> None: ...
        def add_error_log(self, msg: str) -> None: ...
        def set_status(self, msg: str) -> None: ...
        def flush(self) -> None: ...
        def flush_from_thread(self) -> None: ...
        def show_error(self, msg: str) -> None: ...
        def build_grid_config(self) -> Any: ...
        def build_template_style(self) -> Any: ...
        def compute_canvas_size_px(self) -> tuple[int, int]: ...

    # ------------------------------------------------------------------ #
    # Template event handlers                                              #
    # ------------------------------------------------------------------ #

    def _run_template(self) -> None:
        """Generate a template PNG in a background thread.

        Why: Template generation can be slow for large page sizes; running
             it off-thread keeps the UI responsive.
        How: Reads the output path from the template_out field, appends
             .png if missing, then calls generate_template_png and logs
             the result path.
        """
        try:
            w, h = self.compute_canvas_size_px()
            dpi = parse_int(self.w.common.dpi_field.value or "0", "DPI")
            out = (self.w.template.template_out_field.value or "").strip()
            if not out:
                raise ValueError("Template output path is required")
            if not out.lower().endswith(".png"):
                out = f"{out}.png"
            rpath = generate_template_png(
                out, w, h, self.build_grid_config(), self.build_template_style(), dpi
            )
            self.add_log(f"Template written: {rpath}")
            self.set_status("Template written")
            self.flush_from_thread()
        except (ConfigError, ValueError, RuntimeError) as exc:
            self.add_error_log(str(exc))
            self.set_status("Error")
            self.show_error(str(exc))
            self.flush_from_thread()

    def on_generate_template(self, _: Any) -> None:
        """Handle Generate Template button click.

        Why: Template generation must run off-thread to avoid UI freezes.
        How: Shows a status message then delegates to page.run_thread.
        """
        self.add_log("Generating template...")
        self.set_status("Generating template")
        self.flush()
        self.page.run_thread(self._run_template)


__all__ = ["GuiHandlersTemplateMixin"]
