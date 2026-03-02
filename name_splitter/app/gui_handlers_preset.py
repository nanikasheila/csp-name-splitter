"""Preset management event handlers mixin for CSP Name Splitter GUI.

Why: gui_handlers.py already inherits multiple mixins for size, config, and
     batch concerns. Preset management (save / load / delete named configs)
     is a distinct responsibility that would push gui_handlers.py over the
     700-line limit if added inline.
How: Pure mixin — no __init__, relies on GuiHandlers to expose self.w,
     self.state, self.page, and shared helpers. GuiHandlers inherits this
     mixin and gains all preset event handlers.
"""
from __future__ import annotations

from types import SimpleNamespace
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from name_splitter.core.config import GridConfig
    from name_splitter.app.gui_state import GuiState


class GuiHandlersPresetMixin:
    """Mixin providing preset management event handlers for the Config tab.

    Why: Preset operations (save, load, delete) share access patterns with
         the config mixin (apply_config_to_ui, build_grid_config) but are
         logically independent — they persist named snapshots in AppSettings
         rather than reading YAML files from disk.
    How: Relies on GuiHandlers.__init__ to expose self.w (GuiWidgets),
         self.state (GuiState), self.page, self.add_log, self.add_error_log,
         self.set_status, self.flush, and self.build_grid_config via MRO.
    """

    # Declared here so that the type checker recognises attributes set by
    # the concrete GuiHandlers class.
    if TYPE_CHECKING:
        w: Any        # GuiWidgets — set in GuiHandlers.__init__
        state: GuiState
        page: Any

        def add_log(self, msg: str) -> None: ...
        def add_error_log(self, msg: str) -> None: ...
        def set_status(self, msg: str) -> None: ...
        def flush(self) -> None: ...
        def build_grid_config(self) -> GridConfig: ...
        def apply_config_to_ui(self, cfg: Any) -> None: ...

    # ------------------------------------------------------------------ #
    # Preset event handlers                                               #
    # ------------------------------------------------------------------ #

    def on_save_preset(self, e: Any) -> None:  # noqa: ARG002
        """Handle Save Preset button click — prompt for a name and persist settings.

        Why: Presets let users snapshot the current configuration (grid, DPI,
             margins, output format) for instant recall without re-entering
             all fields on every session start.
        How: Opens an AlertDialog with a text input for the preset name.
             On confirmation, builds a serialisable config dict from the
             current UI state and delegates to AppSettings.save_preset,
             then refreshes the preset dropdown.
        """
        try:
            import flet as ft  # noqa: PLC0415
        except ImportError:
            return

        name_field = ft.TextField(label="Preset name", autofocus=True, width=280)
        dlg: Any = None  # forward reference for the inner callbacks

        def _do_save(_: Any) -> None:
            name = (name_field.value or "").strip()
            if not name:
                return
            if dlg is not None:
                dlg.open = False
                self.page.update()
            try:
                from name_splitter.app.app_settings import (  # noqa: PLC0415
                    load_app_settings,
                    save_app_settings,
                )
                settings = load_app_settings()
                config_dict = self._build_preset_config_dict()
                settings.save_preset(name, config_dict)
                save_app_settings(settings)
                self._refresh_preset_dropdown(settings)
                self.add_log(f"Preset saved: {name}")
                self.set_status(f"Preset '{name}' saved")
            except Exception as exc:  # noqa: BLE001
                self.add_error_log(f"Save preset: {exc}")
            self.flush()

        def _on_cancel(_: Any) -> None:
            if dlg is not None:
                dlg.open = False
            self.flush()

        dlg = ft.AlertDialog(
            title=ft.Text("Save Preset"),
            content=name_field,
            actions=[
                ft.ElevatedButton("Save", on_click=_do_save),
                ft.TextButton("Cancel", on_click=_on_cancel),
            ],
            actions_alignment=ft.MainAxisAlignment.END,
        )
        self.page.open(dlg)

    def on_load_preset(self, e: Any) -> None:  # noqa: ARG002
        """Handle preset dropdown selection — apply saved config to UI fields.

        Why: One-click preset loading eliminates manual re-entry of every
             setting when switching between common print configurations.
        How: Reads the selected name from the preset dropdown, retrieves
             the stored config dict from AppSettings, constructs a minimal
             SimpleNamespace config object compatible with apply_config_to_ui,
             and delegates to that method to apply all field values atomically.
        """
        if self.w.preset is None:
            return
        name = self.w.preset.dropdown.value
        if not name:
            return
        try:
            from name_splitter.app.app_settings import load_app_settings  # noqa: PLC0415
            settings = load_app_settings()
            cfg_dict = settings.get_preset(name)
            if cfg_dict is None:
                self.add_error_log(f"Preset not found: {name}")
                self.flush()
                return
            self._apply_preset_dict_to_ui(cfg_dict)
            self.add_log(f"Preset loaded: {name}")
            self.set_status(f"Preset '{name}' loaded")
        except Exception as exc:  # noqa: BLE001
            self.add_error_log(f"Load preset: {exc}")
        self.flush()

    def on_delete_preset(self, e: Any) -> None:  # noqa: ARG002
        """Handle Delete Preset button click — remove the currently selected preset.

        Why: Accumulated presets clutter the dropdown; deletion keeps the
             list manageable without requiring an app restart.
        How: Reads the selected name, calls AppSettings.delete_preset,
             persists the change, refreshes the dropdown, and clears the
             selection to avoid referencing the now-deleted name.
        """
        if self.w.preset is None:
            return
        name = self.w.preset.dropdown.value
        if not name:
            return
        try:
            from name_splitter.app.app_settings import (  # noqa: PLC0415
                load_app_settings,
                save_app_settings,
            )
            settings = load_app_settings()
            settings.delete_preset(name)
            save_app_settings(settings)
            self._refresh_preset_dropdown(settings)
            self.w.preset.dropdown.value = None
            self.add_log(f"Preset deleted: {name}")
            self.set_status(f"Preset '{name}' deleted")
        except Exception as exc:  # noqa: BLE001
            self.add_error_log(f"Delete preset: {exc}")
        self.flush()

    # ------------------------------------------------------------------ #
    # Private helpers                                                      #
    # ------------------------------------------------------------------ #

    def _build_preset_config_dict(self) -> dict[str, object]:
        """Build a serialisable config dict from current UI field values.

        Why: Presets must capture all grid/page/output settings so they can
             be reapplied exactly. Storing a plain dict (rather than a Config
             dataclass) keeps AppSettings JSON-serialisable.
        How: Calls build_grid_config to obtain typed pixel values, then
             assembles a plain dict mirroring the YAML config schema.

        Returns:
            Dict containing "version", "grid", and "output" sections.
        """
        grid_cfg = self.build_grid_config()
        output_format = (self.w.image.output_format_field.value or "png").strip()
        return {
            "version": 1,
            "grid": {
                "rows": grid_cfg.rows,
                "cols": grid_cfg.cols,
                "order": grid_cfg.order,
                "margin_top_px": grid_cfg.margin_top_px,
                "margin_bottom_px": grid_cfg.margin_bottom_px,
                "margin_left_px": grid_cfg.margin_left_px,
                "margin_right_px": grid_cfg.margin_right_px,
                "gutter_px": grid_cfg.gutter_px,
                "gutter_unit": grid_cfg.gutter_unit,
                "margin_unit": grid_cfg.margin_unit,
                "dpi": grid_cfg.dpi,
                "page_size_name": grid_cfg.page_size_name,
                "orientation": grid_cfg.orientation,
                "page_width_px": grid_cfg.page_width_px,
                "page_height_px": grid_cfg.page_height_px,
                "page_size_unit": grid_cfg.page_size_unit,
            },
            "output": {
                "container": output_format,
            },
        }

    def _apply_preset_dict_to_ui(self, cfg_dict: dict) -> None:
        """Apply a preset config dict to UI fields via apply_config_to_ui.

        Why: apply_config_to_ui accepts a config object with attribute access
             patterns. Building a lightweight SimpleNamespace avoids writing
             a temporary YAML file or instantiating a full Config dataclass.
        How: Constructs SimpleNamespace objects for the "grid" and "output"
             sub-sections, fills in sensible defaults for missing keys, and
             passes the resulting namespace to apply_config_to_ui.

        Args:
            cfg_dict: Config dict as stored by AppSettings.save_preset.
        """
        grid_d = cfg_dict.get("grid", {})
        output_d = cfg_dict.get("output", {})

        grid = SimpleNamespace(
            rows=grid_d.get("rows", 4),
            cols=grid_d.get("cols", 4),
            order=grid_d.get("order", "rtl_ttb"),
            margin_px=0,
            margin_top_px=grid_d.get("margin_top_px", 0),
            margin_bottom_px=grid_d.get("margin_bottom_px", 0),
            margin_left_px=grid_d.get("margin_left_px", 0),
            margin_right_px=grid_d.get("margin_right_px", 0),
            gutter_px=grid_d.get("gutter_px", 0),
            gutter_unit=grid_d.get("gutter_unit", "px"),
            margin_unit=grid_d.get("margin_unit", "px"),
            dpi=grid_d.get("dpi", 300),
            page_size_name=grid_d.get("page_size_name", "A4"),
            orientation=grid_d.get("orientation", "portrait"),
            page_width_px=grid_d.get("page_width_px", 0),
            page_height_px=grid_d.get("page_height_px", 0),
            page_size_unit=grid_d.get("page_size_unit", "px"),
        )
        output = SimpleNamespace(
            container=output_d.get("container", "png"),
        )
        cfg = SimpleNamespace(grid=grid, output=output)
        self.apply_config_to_ui(cfg)

    def _refresh_preset_dropdown(self, settings: Any) -> None:
        """Rebuild the preset dropdown options from the current settings.

        Why: After every save/delete the dropdown must show the updated list
             immediately so the user can see the change without restarting.
        How: Calls settings.get_preset_names(), creates dropdown.Option
             objects, and triggers a control-level update for a live refresh.

        Args:
            settings: AppSettings instance with the updated preset list.
        """
        if self.w.preset is None:
            return
        try:
            import flet as ft  # noqa: PLC0415
            names = settings.get_preset_names()
            self.w.preset.dropdown.options = [ft.dropdown.Option(n) for n in names]
            try:
                self.w.preset.dropdown.update()
            except Exception:  # noqa: BLE001
                self.flush()
        except ImportError:
            pass


__all__ = ["GuiHandlersPresetMixin"]
