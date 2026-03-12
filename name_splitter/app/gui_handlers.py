"""Event handlers for CSP Name Splitter GUI.

Why: gui.py orchestrates the Flet UI but should not contain business logic.
     GuiHandlers isolates all event callbacks and state mutations so that
     gui.py only wires widgets to handlers.
How: GuiHandlers inherits seven mixins — GuiHandlersSizeMixin (size/page
     computations), GuiHandlersConfigMixin (config loading/applying),
     GuiHandlersBatchMixin (batch processing), GuiHandlersPresetMixin
     (preset management), GuiHandlersJobMixin (job execution and preview),
     GuiHandlersTemplateMixin (template generation), and GuiHandlersLogMixin
     (log, config save, and utility handlers). This file retains only the
     shared UI helpers, recent-file handlers, Quick Run, and tab-change.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from name_splitter.app.gui_state import GuiState
from name_splitter.app.gui_types import (
    CommonFields,
    ImageFields,
    TemplateFields,
    UiElements,
    BatchFields,
    PresetFields,
    RecentFields,
    Page,
    Clipboard,
)
from name_splitter.app.gui_handlers_config import GuiHandlersConfigMixin
from name_splitter.app.gui_handlers_size import GuiHandlersSizeMixin
from name_splitter.app.gui_handlers_batch import GuiHandlersBatchMixin
from name_splitter.app.gui_handlers_preset import GuiHandlersPresetMixin
from name_splitter.app.gui_handlers_job import GuiHandlersJobMixin
from name_splitter.app.gui_handlers_template import GuiHandlersTemplateMixin
from name_splitter.app.gui_handlers_log import GuiHandlersLogMixin
from name_splitter.app.gui_utils import (
    PageSizeParams,
    parse_int,
    px_to_mm,
    convert_unit_value,
    compute_page_size_px as compute_page_size_px_impl,
)
from name_splitter.app.error_messages import get_ja_message


@dataclass
class GuiWidgets:
    """References to all GUI widgets organized into logical groups.

    Why: Passing individual widget references between functions becomes
         unwieldy as the UI grows. A single dataclass provides a typed,
         navigable structure that both GuiHandlers and gui.py can use.
    How: Groups widgets into CommonFields, ImageFields, TemplateFields,
         UiElements, and optionally BatchFields matching the named-tuple
         dataclasses in gui_types.
    """

    common: CommonFields
    image: ImageFields
    template: TemplateFields
    ui: UiElements
    batch: "BatchFields | None" = None
    preset: "PresetFields | None" = None


class GuiHandlers(
    GuiHandlersSizeMixin,
    GuiHandlersConfigMixin,
    GuiHandlersBatchMixin,
    GuiHandlersPresetMixin,
    GuiHandlersJobMixin,
    GuiHandlersTemplateMixin,
    GuiHandlersLogMixin,
):
    """Event handlers and UI helper methods for CSP Name Splitter GUI.

    Why: Centralising all Flet event callbacks in one class (with mixin
         support for size, config, batch, preset, job, template, and log
         concerns) prevents gui.py from growing into an untestable monolith.
    How: Inherits GuiHandlersSizeMixin (size/page computations),
         GuiHandlersConfigMixin (config file operations),
         GuiHandlersBatchMixin (batch processing),
         GuiHandlersPresetMixin (preset management),
         GuiHandlersJobMixin (job execution and preview),
         GuiHandlersTemplateMixin (template generation), and
         GuiHandlersLogMixin (log, config save, utility handlers).
         This class retains only shared UI helpers, recent-file handlers,
         Quick Run, and the tab-change handler.
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

    def add_error_log(self, msg: str) -> None:
        """Append an error-prefixed timestamped line to the log.

        Why: Error lines must stand out when users scan the log to find
             what went wrong among many informational entries.
        How: Delegates to add_log with an [ERROR] prefix for grep-ability.
        """
        self.add_log(f"[ERROR] {msg}")

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

    def flush_from_thread(self) -> None:
        """Commit pending changes from a background thread.

        Why: page.update() called from a page.run_thread background thread
             may not trigger an immediate visual refresh in Flet desktop;
             the display only repaints on user interaction (e.g. tab switch).
        How: Calls control-level update() on progress_bar, status_text, and
             log_field individually, which sends targeted WebSocket messages
             and reliably triggers a repaint from non-main threads.
        """
        try:
            self.w.ui.progress_bar.update()
            self.w.ui.status_text.update()
            self.w.ui.log_field.update()
        except Exception:  # noqa: BLE001
            # Why: Flet may raise if controls are not yet mounted or page is
            #      closing; fall back to page.update() which is better than
            #      nothing.
            try:
                self.page.update()
            except Exception:  # noqa: BLE001
                pass

    def update_color_swatches(self) -> None:
        """Sync color swatch containers with their corresponding text fields.

        Why: Users need immediate visual feedback when typing hex color codes;
             a small colored square next to the field makes correctness obvious.
        How: Reads each color text field, validates the hex format, and sets
             the swatch container's bgcolor. Invalid values are silently ignored.
        """
        swatches = [
            (self.w.common.grid_color_field, self.w.common.grid_color_swatch),
            (self.w.template.finish_color_field, self.w.template.finish_color_swatch),
            (self.w.template.basic_color_field, self.w.template.basic_color_swatch),
        ]
        for color_field, swatch in swatches:
            raw = (color_field.value or "").strip()
            if raw and len(raw) in (4, 7) and raw.startswith("#"):
                swatch.bgcolor = raw

    def show_error(self, msg: str) -> None:
        """Display an error message in a transient snackbar.

        Why: Errors from background threads cannot use dialog boxes
             (which require synchronous context); a snackbar is safe.
        How: Translates the English error string to Japanese for GUI display
             using get_ja_message, then opens a red-background SnackBar with
             a 5-second duration. The technical English message is preserved
             in the log via add_error_log — only the snackbar shows Japanese.
             The try/except guard prevents crashes in test environments
             where flet may not be importable.
        """
        try:
            import flet as ft
            self.page.open(ft.SnackBar(  # type: ignore[attr-defined]
                content=ft.Text(get_ja_message(msg)),
                bgcolor="red",
                duration=5000,
            ))
        except Exception:  # noqa: BLE001
            pass

    def show_success(self, msg: str) -> None:
        """Display a success message in a transient snackbar.

        Why: Users need visible feedback when an action completes
             successfully, especially when the result is a file write
             that produces no other visible change in the UI.
        How: Opens a green-background SnackBar with a 3-second duration.
             The try/except guard prevents crashes in test environments.
        """
        try:
            import flet as ft
            self.page.open(ft.SnackBar(  # type: ignore[attr-defined]
                content=ft.Text(str(msg)),
                bgcolor="green",
                duration=3000,
            ))
        except Exception:  # noqa: BLE001
            pass

    # ------------------------------------------------------------------ #
    # A-2: Recent file handlers                                           #
    # ------------------------------------------------------------------ #

    def on_recent_input_select(self, e: Any) -> None:
        """Handle recent input dropdown selection — populate the input field.

        Why: Letting users re-open a recently used image from a dropdown
             is faster than navigating the file picker each time.
        How: Reads the selected path from the recent dropdown value and
             writes it to the input_field, then triggers auto-preview.

        Args:
            e: Flet ControlEvent from the dropdown's on_change callback.
        """
        if self.w.ui.recent is None:
            return
        path = self.w.ui.recent.recent_input_dropdown.value
        if not path:
            return
        self.w.image.input_field.value = path
        self.auto_preview_if_enabled(e)
        self.flush()

    def on_recent_config_select(self, e: Any) -> None:
        """Handle recent config dropdown selection — load and apply the config.

        Why: Re-loading a recently used config file from a dropdown is
             faster and less error-prone than retyping the full path.
        How: Sets config_field to the selected path and delegates to
             on_config_change which reads, parses, and applies the file.

        Args:
            e: Flet ControlEvent from the dropdown's on_change callback.
        """
        if self.w.ui.recent is None:
            return
        path = self.w.ui.recent.recent_config_dropdown.value
        if not path:
            return
        self.w.common.config_field.value = path
        self.on_config_change(e)

    # ------------------------------------------------------------------ #
    # A-3: Quick Run                                                       #
    # ------------------------------------------------------------------ #

    def on_quick_run(self, _: Any) -> None:
        """Handle Quick Run button click — restore last run config and execute.

        Why: Iterative workflows (tweak settings → run → inspect → tweak)
             require re-running the same image with minor config changes.
             Quick Run skips re-entering common fields.
        How: Loads last_run_config from AppSettings, applies it to the UI
             via _apply_preset_dict_to_ui (reusing the preset mixin logic),
             then delegates to on_run to start the background job.
        """
        try:
            from name_splitter.app.app_settings import load_app_settings  # noqa: PLC0415
            settings = load_app_settings()
            cfg_dict = settings.last_run_config
            if not cfg_dict:
                self.add_error_log("No previous run found. Run a job first.")
                self.flush()
                return
            self._apply_preset_dict_to_ui(cfg_dict)
            # Restore input path if saved
            input_d = cfg_dict.get("input", {})
            if isinstance(input_d, dict) and input_d.get("image_path"):
                self.w.image.input_field.value = str(input_d["image_path"])
            output_d = cfg_dict.get("output", {})
            if isinstance(output_d, dict) and output_d.get("out_dir"):
                self.w.image.out_dir_field.value = str(output_d["out_dir"])
        except Exception as exc:  # noqa: BLE001
            self.add_error_log(f"Quick Run restore: {exc}")
            self.flush()
            return
        self.on_run(None)

    def _save_last_run_config(self) -> None:
        """Persist the current UI configuration as last_run_config in AppSettings.

        Why: Quick Run needs to know the exact field values from the most
             recent successful execution, including the input image path and
             output directory.
        How: Builds a config dict from current UI values (reusing the preset
             config builder with additional input/output keys), then saves
             to AppSettings.last_run_config. Also enables the quick_run_btn
             so the user can see it is now usable.
        """
        try:
            from name_splitter.app.app_settings import (  # noqa: PLC0415
                load_app_settings,
                save_app_settings,
            )
            settings = load_app_settings()
            # Build a full run config dict (superset of preset dict)
            cfg_dict = self._build_preset_config_dict()
            cfg_dict["input"] = {
                "image_path": (self.w.image.input_field.value or "").strip(),
            }
            out_dir = (self.w.image.out_dir_field.value or "").strip()
            if isinstance(cfg_dict.get("output"), dict):
                cfg_dict["output"]["out_dir"] = out_dir  # type: ignore[index]
            settings.last_run_config = cfg_dict
            save_app_settings(settings)
            # Enable Quick Run button now that a run config exists
            if self.w.ui.quick_run_btn is not None:
                self.w.ui.quick_run_btn.disabled = False
        except Exception:  # noqa: BLE001
            pass  # Why: Failure to persist last run config must never crash the app

    def on_tab_change(self, e: Any) -> None:
        """Handle tab selection change.

        Why: The active tab determines which preview to show when
             auto_preview_if_enabled is triggered.
        How: Maps UI tab indices to preview-relevant state:
             Tab 0 (Config) and Tab 3 (Log) are not preview-relevant.
             Tab 1 (Image Split) → state index 0.
             Tab 2 (Template) → state index 1.
             Preview-relevant tabs trigger an immediate synchronous refresh.
        """
        tab_index = int(e.data)
        # Why: Only Image Split (1) and Template (2) need preview updates.
        _TAB_TO_STATE = {1: 0, 2: 1}
        if tab_index in _TAB_TO_STATE:
            self.state.set_tab(_TAB_TO_STATE[tab_index])
            self.flush()
            if self.state.auto_preview_enabled:
                try:
                    self.on_preview(None)
                except Exception:  # noqa: BLE001
                    pass
        else:
            self.flush()

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


__all__ = ["GuiWidgets", "GuiHandlers", "BatchFields"]
