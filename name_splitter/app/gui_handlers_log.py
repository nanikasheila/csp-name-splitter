"""Log management, config save, and utility event handlers mixin for CSP Name Splitter GUI.

Why: gui_handlers.py exceeds 900 lines; log/clipboard operations, config
     persistence, defaults reset, and folder opening form a cohesive group
     of utility handlers that belongs in a dedicated mixin.
How: Pure mixin — no __init__, relies on GuiHandlers to expose self.w,
     self.state, self.page, self.clipboard, and shared helpers. GuiHandlers
     inherits this mixin and gains all log/config/utility event handlers.
"""
from __future__ import annotations

import os
import subprocess
import sys
from typing import TYPE_CHECKING, Any

from name_splitter.core import ConfigError, load_default_config

if TYPE_CHECKING:
    from name_splitter.app.gui_state import GuiState


class GuiHandlersLogMixin:
    """Mixin providing log, config-save, and utility event handlers.

    Why: Log copy/clear, config save, defaults reset, and folder-open are
         utility actions that share no logic with job execution or template
         generation. Isolating them here keeps gui_handlers.py focused.
    How: Relies on GuiHandlers.__init__ to expose self.w (GuiWidgets),
         self.state (GuiState), self.page, self.clipboard, self.add_log,
         self.add_error_log, self.set_status, self.flush, self.show_error,
         self.show_success, self.build_grid_config, and
         self.apply_config_to_ui via the MRO.
    """

    # Declared here so that the type checker recognises attributes that are
    # set by the concrete GuiHandlers class.
    if TYPE_CHECKING:
        w: Any        # GuiWidgets — set in GuiHandlers.__init__
        state: GuiState
        page: Any
        clipboard: Any

        def add_log(self, msg: str) -> None: ...
        def add_error_log(self, msg: str) -> None: ...
        def set_status(self, msg: str) -> None: ...
        def flush(self) -> None: ...
        def show_error(self, msg: str) -> None: ...
        def show_success(self, msg: str) -> None: ...
        def build_grid_config(self) -> Any: ...
        def apply_config_to_ui(self, cfg: Any) -> None: ...

    # ------------------------------------------------------------------ #
    # Log handlers                                                         #
    # ------------------------------------------------------------------ #

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
            self.add_error_log(str(exc))
        self.flush()

    def on_copy_log(self, _: Any) -> None:
        """Handle Copy Log button click.

        Why: page.run_task is the safe way to schedule a coroutine from a
             synchronous event handler in Flet.
        How: Schedules _copy_log as an async task on the Flet event loop.
        """
        self.page.run_task(self._copy_log)

    def on_clear_log(self, _: Any) -> None:
        """Clear all log entries and reset status text.

        Why: Users accumulate logs during iterative adjustments; a clear
             button prevents scrolling through outdated entries.
        How: Empties the log_field value and resets status to Idle.
        """
        self.w.ui.log_field.value = ""
        self.set_status("Idle")
        self.flush()

    # ------------------------------------------------------------------ #
    # Config save / reset handlers                                         #
    # ------------------------------------------------------------------ #

    def on_save_config(self, _: Any) -> None:
        """Handle Save Config button click — export current settings to YAML.

        Why: Users tweaking settings in the GUI need a way to persist their
             configuration so it can be reloaded later or shared.
        How: Builds a config dict from current UI field values, serializes
             to YAML, and writes to the path in config_field (or prompts
             via snackbar if no path is set).
        """
        try:
            import yaml  # type: ignore[import-untyped]
        except ImportError:
            self.add_error_log("PyYAML is required to save config files")
            self.flush()
            return

        config_path = (self.w.common.config_field.value or "").strip()
        if not config_path:
            self.add_error_log("Set a config file path first (Config tab)")
            self.show_error("Config file path is empty. Enter a path or pick a file.")
            self.flush()
            return

        try:
            grid_cfg = self.build_grid_config()
            output_format = (self.w.image.output_format_field.value or "png").strip()

            config_dict = {
                "version": 1,
                "input": {"image_path": ""},
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
                "merge": {
                    "group_rules": [],
                    "layer_rules": [],
                    "include_hidden_layers": False,
                },
                "output": {
                    "out_dir": "",
                    "page_basename": "page_{page:03d}",
                    "layer_stack": ["flat"],
                    "raster_ext": "png",
                    "container": output_format,
                    "layout": "layers",
                    "output_dpi": int(self.w.image.output_dpi_field.value or "0") if hasattr(self.w.image, "output_dpi_field") else 0,
                    "page_number_start": int(self.w.image.page_number_start_field.value or "1") if hasattr(self.w.image, "page_number_start_field") else 1,
                    "skip_pages": [int(s.strip()) for s in (self.w.image.skip_pages_field.value or "").split(",") if s.strip().isdigit()] if hasattr(self.w.image, "skip_pages_field") else [],
                    "odd_even": (self.w.image.odd_even_field.value or "all").strip() if hasattr(self.w.image, "odd_even_field") else "all",
                },
                "limits": {
                    "max_dim_px": 30000,
                    "on_exceed": "error",
                },
            }

            from pathlib import Path
            path = Path(config_path)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(
                yaml.dump(config_dict, allow_unicode=True, sort_keys=False),
                encoding="utf-8",
            )
            self.add_log(f"Config saved to {config_path}")
            self.set_status("Config saved")
            self.show_success(f"Config saved to {config_path}")
        except Exception as exc:  # noqa: BLE001
            self.add_error_log(f"Save config: {exc}")
            self.show_error(str(exc))
        self.flush()

    def on_reset_defaults(self, _: Any) -> None:
        """Reset all settings to built-in default values.

        Why: Users experimenting with settings need a quick way to revert
             to a known-good state without manually clearing each field.
        How: Loads the built-in default config via load_default_config,
             clears the config file path, and applies defaults to all UI
             fields through apply_config_to_ui.
        """
        try:
            cfg = load_default_config()
            self.w.common.config_field.value = ""
            self.apply_config_to_ui(cfg)
            self.add_log("Settings reset to defaults")
            self.set_status("Reset to defaults")
        except Exception as exc:  # noqa: BLE001
            self.add_error_log(f"Reset: {exc}")
        self.flush()

    # ------------------------------------------------------------------ #
    # Folder open handler                                                  #
    # ------------------------------------------------------------------ #

    def on_open_output_folder(self, _: Any) -> None:
        """Open the output directory in the system file manager.

        Why: After a job completes users want to inspect the output files;
             navigating manually to the directory is tedious.
        How: Reads the output dir field value and opens it with the
             platform-specific file manager command. Falls back gracefully
             on missing or invalid paths.
        """
        out_dir = (self.w.image.out_dir_field.value or "").strip()
        if not out_dir:
            self.add_error_log("No output directory specified")
            self.flush()
            return
        if not os.path.isdir(out_dir):
            self.add_error_log(f"Directory not found: {out_dir}")
            self.flush()
            return
        try:
            if sys.platform == "win32":
                os.startfile(out_dir)  # noqa: S606
            elif sys.platform == "darwin":
                subprocess.Popen(["open", out_dir])  # noqa: S603, S607
            else:
                subprocess.Popen(["xdg-open", out_dir])  # noqa: S603, S607
            self.add_log(f"Opened folder: {out_dir}")
        except Exception as exc:  # noqa: BLE001
            self.add_error_log(f"Failed to open folder: {exc}")
        self.flush()


__all__ = ["GuiHandlersLogMixin"]
