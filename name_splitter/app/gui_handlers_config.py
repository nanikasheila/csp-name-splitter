"""Config loading and UI application mixin for CSP Name Splitter GUI.

Why: The config-related methods in GuiHandlers (loading config files and
     applying their values to GUI fields) represent a distinct responsibility
     that makes gui_handlers.py exceed the 500-line limit. Extracting them
     as a mixin maintains class-based encapsulation while reducing file size.
How: Pure mixin class — no __init__, relies on GuiHandlers to initialize
     self.w (GuiWidgets), self.state (GuiState), and utility methods.
     GuiHandlers inherits this mixin and gains all config methods.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

from name_splitter.core import load_config, load_default_config

if TYPE_CHECKING:
    from name_splitter.app.gui_state import GuiState


class GuiHandlersConfigMixin:
    """Mixin providing config file loading and application to UI fields.

    Why: Config application involves many branching unit-conversion paths
         across DPI, page size, grid, gutter, and margins. Isolating this
         logic makes both this module and GuiHandlers easier to navigate.
    How: Each _apply_*_to_ui helper handles one logical group of fields.
         apply_config_to_ui orchestrates them while temporarily disabling
         auto-preview to avoid redundant refreshes during bulk updates.
    """

    # Declared here so that the type checker recognises these attributes
    # that are initialised by the concrete GuiHandlers class.
    if TYPE_CHECKING:
        w: Any  # GuiWidgets — set in GuiHandlers.__init__
        state: GuiState  # set in GuiHandlers.__init__

        def update_size_info(self, _: Any = None) -> None: ...
        def add_log(self, msg: str) -> None: ...
        def add_error_log(self, msg: str) -> None: ...
        def set_status(self, msg: str) -> None: ...
        def show_error(self, msg: str) -> None: ...
        def show_success(self, msg: str) -> None: ...
        def flush(self) -> None: ...
        def on_save_config(self, _: Any) -> None: ...

    # ------------------------------------------------------------------
    # Config loading
    # ------------------------------------------------------------------

    def load_config_for_ui(self) -> tuple[str, Any]:
        """Load config file or fall back to built-in defaults.

        Why: GUI needs a unified entry point that handles both the
             "user supplied a config path" and "no config file" cases.
        How: Checks config_field value; delegates to load_config or
             load_default_config from name_splitter.core.

        Returns:
            Tuple of (status message, loaded config object)
        """
        if self.w.common.config_field.value:
            return "Loaded config", load_config(self.w.common.config_field.value)
        return "Loaded default config", load_default_config()

    # ------------------------------------------------------------------
    # Private: apply individual config groups to UI
    # ------------------------------------------------------------------

    def _apply_dpi_to_ui(self, cfg: Any) -> None:
        """Apply DPI setting from config to the DPI field.

        Why: DPI must be applied first so subsequent unit conversions use
             the correct pixel density.
        How: Checks for grid.dpi attribute and updates the text field if
             a valid positive value is present.
        """
        if hasattr(cfg.grid, "dpi") and cfg.grid.dpi > 0:
            self.w.common.dpi_field.value = str(cfg.grid.dpi)

    def _apply_page_size_to_ui(self, cfg: Any) -> None:
        """Apply page size and orientation settings from config to UI.

        Why: Page size selection (preset vs. custom) affects many other
             fields, so it must be applied before margin/gutter values.
        How: Sets page_size_name and orientation first, then fills custom
             width/height fields — converting px→mm when the unit is mm.
        """
        if hasattr(cfg.grid, "page_size_name"):
            self.w.common.page_size_field.value = cfg.grid.page_size_name
        if hasattr(cfg.grid, "orientation"):
            self.w.common.orientation_field.value = cfg.grid.orientation

        if hasattr(cfg.grid, "page_width_px") and hasattr(cfg.grid, "page_height_px"):
            w, h = cfg.grid.page_width_px, cfg.grid.page_height_px
            if w > 0 and h > 0:
                unit = cfg.grid.page_size_unit if hasattr(cfg.grid, "page_size_unit") else "px"
                self.w.common.custom_size_unit_field.value = unit
                if unit == "mm":
                    dpi = cfg.grid.dpi
                    self.w.common.custom_width_field.value = f"{w * 25.4 / dpi:.1f}"
                    self.w.common.custom_height_field.value = f"{h * 25.4 / dpi:.1f}"
                else:
                    self.w.common.custom_width_field.value = str(w)
                    self.w.common.custom_height_field.value = str(h)
                if self.w.common.page_size_field.value != "Custom":
                    self.w.common.page_size_field.value = "Custom"

    def _apply_grid_settings_to_ui(self, cfg: Any) -> None:
        """Apply rows, cols, and order settings from config to UI.

        Why: Grid layout parameters are core settings that users expect
             to be restored exactly as saved in the config file.
        How: Direct string assignment to the matching text/dropdown fields.
        """
        self.w.common.rows_field.value = str(cfg.grid.rows)
        self.w.common.cols_field.value = str(cfg.grid.cols)
        self.w.common.order_field.value = cfg.grid.order

    def _apply_gutter_to_ui(self, cfg: Any) -> None:
        """Apply gutter value from config to UI, converting units as needed.

        Why: Config stores gutter in pixels internally, but the UI allows
             mm display; the conversion must use the already-applied DPI.
        How: Reads gutter_unit from config (falling back to the current UI
             value), then converts from px using px * 25.4 / dpi for mm.
        """
        if hasattr(cfg.grid, "gutter_unit"):
            self.w.common.gutter_unit_field.value = cfg.grid.gutter_unit

        dpi = cfg.grid.dpi
        gutter_unit = self.w.common.gutter_unit_field.value or "px"
        if gutter_unit == "mm":
            self.w.common.gutter_field.value = f"{cfg.grid.gutter_px * 25.4 / dpi:.2f}"
        else:
            self.w.common.gutter_field.value = str(cfg.grid.gutter_px)

    def _apply_margins_to_ui(self, cfg: Any) -> None:
        """Apply margin values from config to UI, supporting legacy uniform format.

        Why: Config files may use either per-direction margins (top/bottom/
             left/right) or a legacy uniform margin field. Both must be
             handled to preserve backward compatibility.
        How: Checks if any per-direction margin is non-zero to distinguish
             new from legacy format, then converts px→mm when unit is mm.
        """
        if hasattr(cfg.grid, "margin_unit"):
            self.w.common.margin_unit_field.value = cfg.grid.margin_unit

        dpi = cfg.grid.dpi
        unit = self.w.common.margin_unit_field.value or "px"

        if (cfg.grid.margin_top_px or cfg.grid.margin_bottom_px
                or cfg.grid.margin_left_px or cfg.grid.margin_right_px):
            # Per-direction margins
            if unit == "mm":
                self.w.common.margin_top_field.value = f"{cfg.grid.margin_top_px * 25.4 / dpi:.2f}"
                self.w.common.margin_bottom_field.value = f"{cfg.grid.margin_bottom_px * 25.4 / dpi:.2f}"
                self.w.common.margin_left_field.value = f"{cfg.grid.margin_left_px * 25.4 / dpi:.2f}"
                self.w.common.margin_right_field.value = f"{cfg.grid.margin_right_px * 25.4 / dpi:.2f}"
            else:
                self.w.common.margin_top_field.value = str(cfg.grid.margin_top_px)
                self.w.common.margin_bottom_field.value = str(cfg.grid.margin_bottom_px)
                self.w.common.margin_left_field.value = str(cfg.grid.margin_left_px)
                self.w.common.margin_right_field.value = str(cfg.grid.margin_right_px)
        else:
            # Legacy uniform margin
            if unit == "mm":
                val_mm = f"{cfg.grid.margin_px * 25.4 / dpi:.2f}"
                self.w.common.margin_top_field.value = val_mm
                self.w.common.margin_bottom_field.value = val_mm
                self.w.common.margin_left_field.value = val_mm
                self.w.common.margin_right_field.value = val_mm
            else:
                val_px = str(cfg.grid.margin_px)
                self.w.common.margin_top_field.value = val_px
                self.w.common.margin_bottom_field.value = val_px
                self.w.common.margin_left_field.value = val_px
                self.w.common.margin_right_field.value = val_px

    # ------------------------------------------------------------------
    # Public: orchestrated config application and event handler
    # ------------------------------------------------------------------

    def apply_config_to_ui(self, cfg: Any) -> None:
        """Apply all fields from a loaded config object to the UI.

        Why: Config load must update many fields atomically without
             triggering intermediate auto-preview refreshes (which would
             cause errors or flicker during partial updates).
        How: Disables auto-preview via state guard, applies each logical
             group in order (DPI first, then page size, grid, gutter,
             margins), updates unit state, then restores auto-preview.
        """
        self.state.disable_auto_preview()
        try:
            self._apply_dpi_to_ui(cfg)
            self._apply_page_size_to_ui(cfg)
            self._apply_grid_settings_to_ui(cfg)
            self._apply_gutter_to_ui(cfg)
            self._apply_margins_to_ui(cfg)

            self.state.unit_state.margin_unit = self.w.common.margin_unit_field.value or "px"
            self.state.unit_state.page_size_unit = self.w.common.custom_size_unit_field.value or "px"
            self.state.unit_state.gutter_unit = self.w.common.gutter_unit_field.value or "px"

            # Apply output format if available
            if hasattr(cfg.output, "container"):
                self.w.image.output_format_field.value = cfg.output.container
            # B-1: Output DPI
            if hasattr(cfg.output, "output_dpi"):
                self.w.image.output_dpi_field.value = str(cfg.output.output_dpi)
            # B-2: Page numbering
            if hasattr(cfg.output, "page_number_start"):
                self.w.image.page_number_start_field.value = str(cfg.output.page_number_start)
            if hasattr(cfg.output, "skip_pages") and cfg.output.skip_pages:
                self.w.image.skip_pages_field.value = ",".join(str(p) for p in cfg.output.skip_pages)
            else:
                self.w.image.skip_pages_field.value = ""
            if hasattr(cfg.output, "odd_even"):
                self.w.image.odd_even_field.value = cfg.output.odd_even

            self.update_size_info()
            self.add_log("Config applied to UI")
            self.flush()
        finally:
            self.state.enable_auto_preview()

    def on_config_change(self, _: Any) -> None:
        """Handle config file field change: load and apply to UI.

        Why: Users can type or paste a config path; the GUI should
             immediately reflect the config values without extra clicks.
        How: Calls load_config_for_ui and apply_config_to_ui; errors are
             caught and shown in the log without crashing the app.
        """
        if not self.w.common.config_field.value:
            return
        try:
            msg, cfg = self.load_config_for_ui()
            self.apply_config_to_ui(cfg)
            self.set_status(msg)
        except Exception as exc:  # noqa: BLE001
            self.add_log(f"Config load error: {exc}")
            self.set_status("Config error")
        self.flush()

    def on_export_config(self, _: Any) -> None:
        """C-2: Export current GUI settings to a new YAML file.

        Why: Users need to share their configuration with others
             (e.g., assistants or collaborators).
        How: Reuses on_save_config but prompts for path via the
             config_field if empty, or saves to the current path.
        """
        self.on_save_config(_)

    def on_import_config(self, _: Any) -> None:
        """C-2: Import settings from a YAML/JSON file.

        Why: Users receive config files from others and need to
             apply them to their GUI.
        How: Reads config_field path, loads via load_config_for_ui,
             and applies to UI. Same as on_config_change but explicit.
        """
        config_path = (self.w.common.config_field.value or "").strip()
        if not config_path:
            self.add_error_log("Config file path is empty. Pick or enter a config file.")
            self.show_error("Config file path is empty.")
            self.flush()
            return
        try:
            msg, cfg = self.load_config_for_ui()
            self.apply_config_to_ui(cfg)
            self.add_log(f"Config imported from {config_path}")
            self.set_status("Config imported")
            self.show_success(f"Config imported from {config_path}")
        except Exception as exc:  # noqa: BLE001
            self.add_error_log(f"Import config: {exc}")
            self.show_error(str(exc))
        self.flush()


__all__ = ["GuiHandlersConfigMixin"]
