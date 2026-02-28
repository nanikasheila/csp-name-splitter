"""Event handlers for CSP Name Splitter GUI.

Why: gui.py orchestrates the Flet UI but should not contain business logic.
     GuiHandlers isolates all event callbacks and state mutations so that
     gui.py only wires widgets to handlers.
How: GuiHandlers inherits GuiHandlersSizeMixin (size computations and UI
     update helpers) and GuiHandlersConfigMixin (config loading / applying).
     This file retains only the UI helpers and event handlers that do not
     belong to either mixin.
"""
from __future__ import annotations

import base64
from dataclasses import dataclass, replace
from datetime import datetime
from typing import Any

from name_splitter.core import (
    ConfigError,
    ImageReadError,
    LimitExceededError,
    run_job,
)
from name_splitter.core.preview import build_preview_png
from name_splitter.core.template import (
    build_template_preview_png,
    generate_template_png,
    parse_hex_color,
)
from name_splitter.app.gui_state import GuiState
from name_splitter.app.gui_types import (
    CommonFields,
    ImageFields,
    TemplateFields,
    UiElements,
    Page,
    Clipboard,
)
from name_splitter.app.gui_utils import (
    PageSizeParams,
    parse_int,
    px_to_mm,
    convert_unit_value,
    compute_page_size_px as compute_page_size_px_impl,
)
from name_splitter.app.gui_handlers_config import GuiHandlersConfigMixin
from name_splitter.app.gui_handlers_size import GuiHandlersSizeMixin


@dataclass
class GuiWidgets:
    """References to all GUI widgets organized into logical groups.

    Why: Passing individual widget references between functions becomes
         unwieldy as the UI grows. A single dataclass provides a typed,
         navigable structure that both GuiHandlers and gui.py can use.
    How: Groups widgets into CommonFields, ImageFields, TemplateFields,
         and UiElements matching the named-tuple dataclasses in gui_types.
    """

    common: CommonFields
    image: ImageFields
    template: TemplateFields
    ui: UiElements


class GuiHandlers(GuiHandlersSizeMixin, GuiHandlersConfigMixin):
    """Event handlers and UI helper methods for CSP Name Splitter GUI.

    Why: Centralising all Flet event callbacks in one class (with mixin
         support for size and config concerns) prevents gui.py from growing
         into an untestable monolith.
    How: Inherits GuiHandlersSizeMixin for size/page computations and
         GuiHandlersConfigMixin for config file operations. This class adds
         low-level UI helpers and all user-interaction event handlers.
    """

    def __init__(
        self,
        widgets: GuiWidgets,
        state: GuiState,
        page: Page,
        clipboard: Clipboard,
    ) -> None:
        """Initialise handlers with all required dependencies.

        Why: All dependencies are injected so the class can be tested with
             mock widgets and a headless GuiState.
        How: Stores references as instance attributes; uses a short alias
             self.w for widgets to keep handler bodies concise.

        Args:
            widgets: GuiWidgets holding references to all UI controls
            state: GuiState for cancel token, tab index, unit conversion state
            page: Flet Page for flush / snackbar / run_thread / run_task
            clipboard: Flet Clipboard service (may be None when unavailable)
        """
        self.w = widgets
        self.state = state
        self.page = page
        self.clipboard = clipboard

    # ------------------------------------------------------------------ #
    # UI helper methods                                                    #
    # ------------------------------------------------------------------ #

    def add_log(self, msg: str) -> None:
        """Append a timestamped line to the log text field.

        Why: All handlers share a single log area; centralising the format
             keeps timestamps consistent across the application.
        How: Prepends current time in HH:MM:SS format to the message and
             appends to the existing field value.
        """
        ts = datetime.now().strftime("%H:%M:%S")
        self.w.ui.log_field.value = f"{self.w.ui.log_field.value or ''}{ts} {msg}\n"

    def set_status(self, msg: str) -> None:
        """Set the status bar text.

        Why: Status updates are frequent; a helper avoids repeating the
             widget path in every handler.
        How: Direct value assignment to the status_text widget.
        """
        self.w.ui.status_text.value = msg

    def set_progress(self, done: int, total: int) -> None:
        """Update the progress bar to reflect job progress.

        Why: Progress bar value must be clamped to [0, 1] for Flet to
             display it correctly; repeating the clamp logic in each
             on_progress callback would be error-prone.
        How: Computes done/total ratio clamped to [0.0, 1.0]; passes
             None when total is 0 to show an indeterminate bar.

        Args:
            done: Number of steps completed
            total: Total number of steps
        """
        self.w.ui.progress_bar.value = max(0.0, min(1.0, done / total)) if total else None

    def flush(self) -> None:
        """Commit all pending widget value changes to the Flet page.

        Why: Flet batches widget updates until page.update() is called;
             without this, changes are not visible to the user.
        How: Delegates to page.update().
        """
        self.page.update()

    def show_error(self, msg: str) -> None:
        """Display an error message in a transient snackbar.

        Why: Errors from background threads cannot use dialog boxes
             (which require synchronous context); a snackbar is safe.
        How: Opens a red-background SnackBar with a 5-second duration.
             The try/except guard prevents crashes in test environments
             where flet may not be importable.
        """
        try:
            import flet as ft
            self.page.open(ft.SnackBar(
                content=ft.Text(str(msg)),
                bgcolor="red",
                duration=5000,
            ))
        except Exception:  # noqa: BLE001
            pass

    # ------------------------------------------------------------------ #
    # Event handlers                                                       #
    # ------------------------------------------------------------------ #

    def on_preview(self, _: Any) -> None:
        """Render a preview image for the Image Split or Template tab.

        Why: Users need immediate visual feedback when adjusting grid and
             margin settings before committing to a full job run.
        How: Detects the active tab; for Template tab generates a synthetic
             template PNG; for Image Split tab loads the input image and
             draws grid lines via build_preview_png. Result is base64-encoded
             and set as the preview_image src.
        """
        try:
            grid_cfg = self.build_grid_config()
            if self.state.is_template_tab():
                w, h = self.compute_canvas_size_px()
                dpi = parse_int(self.w.common.dpi_field.value or "0", "DPI")
                png = build_template_preview_png(
                    w, h, grid_cfg, self.build_template_style(), dpi
                )
                self.w.ui.preview_image.src = (
                    f"data:image/png;base64,{base64.b64encode(png).decode('ascii')}"
                )
                self.set_status("Template preview")
            else:
                path = (self.w.image.input_field.value or "").strip()
                if not path:
                    raise ValueError("Input image is required for preview")
                msg, cfg = self.load_config_for_ui()
                cfg = replace(cfg, grid=grid_cfg)
                grid_alpha = parse_int(self.w.common.grid_alpha_field.value or "170", "Grid alpha")
                grid_line_color = parse_hex_color(
                    self.w.common.grid_color_field.value or "#FF5030", grid_alpha
                )
                grid_line_width = max(
                    1, parse_int(self.w.common.grid_width_field.value or "1", "Grid width")
                )
                png = build_preview_png(
                    path, cfg.grid, line_color=grid_line_color, line_width=grid_line_width
                )
                self.w.ui.preview_image.src = (
                    f"data:image/png;base64,{base64.b64encode(png).decode('ascii')}"
                )
                self.set_status(msg)
            self.flush()
        except (ConfigError, ImageReadError, ValueError, RuntimeError) as exc:
            self.add_log(f"Error: {exc}")
            self.set_status("Error")
            self.show_error(str(exc))
            self.flush()

    def _run_job(self) -> None:
        """Execute the image-split job in a background thread.

        Why: Image splitting can take seconds to minutes; running it on the
             UI thread would freeze the application.
        How: Reads UI fields, builds a job config, and calls run_job with
             an on_progress callback that updates the progress bar and log.
             Always re-enables Run / disables Cancel in the finally block.
        """
        try:
            path = (self.w.image.input_field.value or "").strip()
            if not path:
                raise ValueError("Input image is required")
            msg, cfg = self.load_config_for_ui()
            cfg = replace(cfg, grid=self.build_grid_config())
            out = (self.w.image.out_dir_field.value or "").strip() or None
            tp = self.w.image.test_page_field.value.strip() if self.w.image.test_page_field.value else ""
            tp_val = int(tp) if tp else None
            self.set_status(msg)
            self.flush()

            def on_progress(ev: Any) -> None:
                self.set_progress(ev.done, ev.total)
                self.set_status(f"{ev.phase} {ev.done}/{ev.total}")
                self.add_log(f"[{ev.phase}] {ev.done}/{ev.total} {ev.message}".strip())
                self.flush()

            result = run_job(
                path, cfg,
                out_dir=out,
                test_page=tp_val,
                on_progress=on_progress,
                cancel_token=self.state.cancel_token,
            )
            self.add_log(f"Plan written to {result.plan.manifest_path}")
            self.add_log(f"Pages: {result.page_count}")
            self.set_status("Done")
            self.w.ui.progress_bar.color = "green"
            self.flush()
        except (ConfigError, LimitExceededError, ImageReadError, ValueError, RuntimeError) as exc:
            self.add_log(f"Error: {exc}")
            self.set_status("Error")
            self.w.ui.progress_bar.color = "red"
            self.show_error(str(exc))
            self.flush()
        finally:
            self.w.ui.run_btn.disabled = False
            self.w.ui.cancel_btn.disabled = True
            self.flush()

    def on_run(self, _: Any) -> None:
        """Handle Run button click — start image-split job in a thread.

        Why: The Run button must disable itself and enable Cancel
             atomically before handing off to the background thread.
        How: Resets cancel token, resets progress bar state, toggles
             button states, then calls page.run_thread with _run_job.
        """
        self.state.reset_cancel_token()
        self.w.ui.progress_bar.value = 0
        self.w.ui.progress_bar.color = None
        self.w.ui.run_btn.disabled = True
        self.w.ui.cancel_btn.disabled = False
        self.add_log("Starting job...")
        self.flush()
        self.page.run_thread(self._run_job)

    def on_cancel(self, _: Any) -> None:
        """Handle Cancel button click — request job cancellation.

        Why: The background job checks state.cancel_token periodically;
             setting it here propagates the cancel signal asynchronously.
        How: Delegates to state.request_cancel() and updates status text.
        """
        self.state.request_cancel()
        self.set_status("Cancel requested")
        self.flush()

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
            self.flush()
        except (ConfigError, ValueError, RuntimeError) as exc:
            self.add_log(f"Error: {exc}")
            self.set_status("Error")
            self.show_error(str(exc))
            self.flush()

    def on_generate_template(self, _: Any) -> None:
        """Handle Generate Template button click.

        Why: Template generation must run off-thread to avoid UI freezes.
        How: Shows a status message then delegates to page.run_thread.
        """
        self.add_log("Generating template...")
        self.set_status("Generating template")
        self.flush()
        self.page.run_thread(self._run_template)

    async def _copy_log(self) -> None:
        """Copy the log text to the system clipboard (async).

        Why: Clipboard access is asynchronous in Flet; a coroutine avoids
             blocking the UI thread.
        How: Reads log_field.value and calls clipboard.set(); guards against
             empty log and unavailable clipboard service.
        """
        text = (self.w.ui.log_field.value or "").strip()
        if not text:
            self.add_log("Log is empty")
            self.flush()
            return
        if self.clipboard is None:
            self.add_log("Clipboard not available")
            self.flush()
            return
        try:
            await self.clipboard.set(text)
            self.add_log("Log copied")
            self.set_status("Log copied")
        except Exception as exc:  # noqa: BLE001
            self.add_log(f"Error: {exc}")
        self.flush()

    def on_copy_log(self, _: Any) -> None:
        """Handle Copy Log button click.

        Why: page.run_task is the safe way to schedule a coroutine from a
             synchronous event handler in Flet.
        How: Schedules _copy_log as an async task on the Flet event loop.
        """
        self.page.run_task(self._copy_log)

    def on_tab_change(self, e: Any) -> None:
        """Handle tab selection change.

        Why: The active tab determines which preview to show when
             auto_preview_if_enabled is triggered.
        How: Updates state.tab index then fires auto_preview_if_enabled.
        """
        self.state.set_tab(int(e.data))
        self.flush()
        self.auto_preview_if_enabled(e)

    def on_margin_unit_change(self, e: Any) -> None:
        """Handle margin unit dropdown change — convert existing values.

        Why: When the user switches between px and mm, the displayed margin
             values must be recalculated to represent the same physical size.
        How: Reads old and new units from state and UI, calls convert_unit_value
             for each of the four margin fields, updates state.unit_state,
             then refreshes size info and auto-preview.
        """
        old_unit = self.state.unit_state.margin_unit
        new_unit = self.w.common.margin_unit_field.value or "px"

        if old_unit == new_unit:
            return

        dpi = parse_int(self.w.common.dpi_field.value or "300", "DPI")
        for fld in [
            self.w.common.margin_top_field,
            self.w.common.margin_bottom_field,
            self.w.common.margin_left_field,
            self.w.common.margin_right_field,
        ]:
            if fld.value:
                fld.value = convert_unit_value(fld.value, old_unit, new_unit, dpi)

        self.state.unit_state.margin_unit = new_unit
        self.update_size_info(e)
        self.auto_preview_if_enabled(e)

    def on_custom_size_unit_change(self, e: Any) -> None:
        """Handle page size unit dropdown change — convert custom width/height.

        Why: When the unit switches between px and mm, the custom page size
             fields must show equivalent values in the new unit.
        How: For preset sizes, computes exact px values from PageSizeParams
             and converts to the new unit. For Custom, converts the existing
             field values directly using convert_unit_value.
        """
        old_unit = self.state.unit_state.page_size_unit
        new_unit = self.w.common.custom_size_unit_field.value or "px"

        if old_unit == new_unit:
            return

        dpi = parse_int(self.w.common.dpi_field.value or "300", "DPI")
        size_choice = self.w.common.page_size_field.value or "A4"

        if size_choice == "Custom":
            for fld in [self.w.common.custom_width_field, self.w.common.custom_height_field]:
                if fld.value:
                    fld.value = convert_unit_value(fld.value, old_unit, new_unit, dpi)
        else:
            params = PageSizeParams(
                page_size_name=size_choice,
                orientation=self.w.common.orientation_field.value or "portrait",
                dpi=dpi,
                custom_width=None,
                custom_height=None,
                custom_unit="px",
            )
            w_px, h_px = compute_page_size_px_impl(params, 0, 0)
            if new_unit == "mm":
                self.w.common.custom_width_field.value = f"{px_to_mm(w_px, dpi):.2f}"
                self.w.common.custom_height_field.value = f"{px_to_mm(h_px, dpi):.2f}"
            else:
                self.w.common.custom_width_field.value = str(w_px)
                self.w.common.custom_height_field.value = str(h_px)

        self.state.unit_state.page_size_unit = new_unit
        self.update_size_info(e)
        self.auto_preview_if_enabled(e)

    def on_gutter_unit_change(self, e: Any) -> None:
        """Handle gutter unit dropdown change — convert existing gutter value.

        Why: Switching the gutter unit recalculates the field so the gutter
             represents the same physical gap in the new unit.
        How: Reads old and new units from state and UI, applies
             convert_unit_value if the field is non-empty, then refreshes.
        """
        old_unit = self.state.unit_state.gutter_unit
        new_unit = self.w.common.gutter_unit_field.value or "px"

        if old_unit == new_unit:
            return

        dpi = parse_int(self.w.common.dpi_field.value or "300", "DPI")
        if self.w.common.gutter_field.value:
            self.w.common.gutter_field.value = convert_unit_value(
                self.w.common.gutter_field.value, old_unit, new_unit, dpi
            )

        self.state.unit_state.gutter_unit = new_unit
        self.update_size_info(e)
        self.auto_preview_if_enabled(e)


__all__ = ["GuiWidgets", "GuiHandlers"]
