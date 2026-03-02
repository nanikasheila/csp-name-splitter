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
import os
import subprocess
import sys
from dataclasses import dataclass, replace
from datetime import datetime
from typing import Any

from name_splitter.core import (
    ConfigError,
    ImageReadError,
    LimitExceededError,
    load_default_config,
    run_job,
)
from name_splitter.core.preview import build_preview_png, load_and_resize_image
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
    BatchFields,
    PresetFields,
    RecentFields,
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
from name_splitter.app.gui_handlers_batch import GuiHandlersBatchMixin
from name_splitter.app.gui_handlers_preset import GuiHandlersPresetMixin
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
):
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
    # Event handlers                                                       #
    # ------------------------------------------------------------------ #

    # P5: Reduced default preview dimension — UI widget further down-scales
    _preview_max_dim: int = 800

    def on_preview(self, _: Any) -> None:
        """Render a preview image for the Image Split or Template tab.

        Why: Users need immediate visual feedback when adjusting grid and
             margin settings before committing to a full job run.
        How: Shows a loading spinner before computation, then hides it.
             For Image Split tab, uses PreviewImageCache to skip disk I/O
             and resize when only grid settings changed. Outputs JPEG for
             faster encoding and smaller data-URI payloads. Template tab
             generates a synthetic preview via build_template_preview_png.
        """
        self.w.ui.preview_loading_ring.visible = True
        self.flush()
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
                # P1: Try image cache to skip I/O + resize
                cache = self.state.preview_image_cache
                cached = cache.get(path, self._preview_max_dim)
                if cached is not None:
                    cached_image, cached_scale = cached
                else:
                    cached_image, cached_scale = load_and_resize_image(
                        path, self._preview_max_dim
                    )
                    cache.store(path, self._preview_max_dim, cached_image, cached_scale)
                # P3: JPEG output from build_preview_png
                jpeg_bytes = build_preview_png(
                    path,
                    cfg.grid,
                    max_dim=self._preview_max_dim,
                    line_color=grid_line_color,
                    line_width=grid_line_width,
                    cached_image=cached_image,
                    cached_scale=cached_scale,
                )
                self.w.ui.preview_image.src = (
                    f"data:image/jpeg;base64,{base64.b64encode(jpeg_bytes).decode('ascii')}"
                )
                self.set_status(msg)
            self.w.ui.preview_loading_ring.visible = False
            self.flush()
        except (ConfigError, ImageReadError, ValueError, RuntimeError) as exc:
            self.w.ui.preview_loading_ring.visible = False
            self.add_error_log(str(exc))
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
            # Why: GUI output format dropdown overrides config container setting
            # How: Replace output config with user-selected container format
            output_format = (self.w.image.output_format_field.value or "png").strip()
            cfg = replace(cfg, output=replace(cfg.output, container=output_format))
            out = (self.w.image.out_dir_field.value or "").strip() or None
            tp = self.w.image.test_page_field.value.strip() if self.w.image.test_page_field.value else ""
            tp_val = int(tp) if tp else None
            self.set_status(msg)
            self.flush()

            def on_progress(ev: Any) -> None:
                self.set_progress(ev.done, ev.total)
                pct = int(ev.done / ev.total * 100) if ev.total else 0
                self.set_status(f"{ev.phase} {ev.done}/{ev.total} ({pct}%)")
                self.add_log(f"[{ev.phase}] {ev.done}/{ev.total} {ev.message}".strip())
                self.flush_from_thread()

            result = run_job(
                path, cfg,
                out_dir=out,
                test_page=tp_val,
                on_progress=on_progress,
                cancel_token=self.state.cancel_token,
            )
            self.add_log(f"Plan written to {result.plan.manifest_path}")
            self.add_log(f"Pages: {result.page_count}")
            if result.pdf_path:
                resolved = result.pdf_path.resolve()
                size_kb = resolved.stat().st_size / 1024
                self.add_log(f"PDF exported: {resolved} ({size_kb:.1f} KB)")
                self.show_success(f"PDF exported: {resolved.name} ({size_kb:.1f} KB)")
            self.set_status("Done")
            self.w.ui.progress_bar.color = "green"
            self._auto_open_output(out)
            # A-3: persist last run config so Quick Run can repeat it
            self._save_last_run_config()
            self.flush_from_thread()
        except (ConfigError, LimitExceededError, ImageReadError, ValueError, RuntimeError) as exc:
            self.add_error_log(str(exc))
            self.set_status("Error")
            self.w.ui.progress_bar.color = "red"
            self.show_error(str(exc))
            self.flush_from_thread()
        finally:
            self._flash_taskbar()
            self.w.ui.run_btn.disabled = False
            self.w.ui.cancel_btn.disabled = True
            self.flush_from_thread()
            # Why: control-level update in flush_from_thread does not cover
            #      run_btn / cancel_btn; a final page.update ensures button
            #      states propagate.
            try:
                self.page.update()
            except Exception:  # noqa: BLE001
                pass

    def _auto_open_output(self, out_dir: str | None) -> None:
        """Auto-open output folder after successful job completion.

        Why: ユーザーの「完了→ファイル確認」ワークフローを短縮する。
             出力先フォルダを手動で探す手間をなくす。
        How: AppSettings.auto_open_output をチェックし、有効なら
             os.startfile（Windows）/ subprocess（macOS/Linux）で出力フォルダを開く。
             ベストエフォート — OSError は無視して処理を続ける。

        Args:
            out_dir: 出力ディレクトリのパス文字列。None または存在しない場合は no-op。
        """
        if not out_dir or not os.path.isdir(out_dir):
            return
        # Why: ユーザーが設定で自動オープンを無効にしている場合は何もしない
        from name_splitter.app.app_settings import load_app_settings
        settings = load_app_settings()
        if not settings.auto_open_output:
            return
        try:
            if sys.platform == "win32":
                os.startfile(out_dir)  # noqa: S606
            elif sys.platform == "darwin":
                subprocess.Popen(["open", out_dir])  # noqa: S603, S607
            else:
                subprocess.Popen(["xdg-open", out_dir])  # noqa: S603, S607
        except OSError:
            pass  # ベストエフォート

    def _flash_taskbar(self) -> None:
        """Flash taskbar button to notify user of job completion.

        Why: ユーザーがバックグラウンドで作業中でも完了を知らせる。
             SnackBar は別ウィンドウにいるユーザーには見えない。
        How: Windows ctypes で FlashWindowEx を直接呼び出す。
             非Windows 環境は no-op（OSError/AttributeError を無視）。
        """
        if sys.platform != "win32":
            return
        try:
            import ctypes
            import ctypes.wintypes

            class FLASHWINFO(ctypes.Structure):
                _fields_ = [
                    ("cbSize", ctypes.c_uint),
                    ("hwnd", ctypes.wintypes.HWND),
                    ("dwFlags", ctypes.c_uint),
                    ("uCount", ctypes.c_uint),
                    ("dwTimeout", ctypes.c_uint),
                ]

            FLASHW_ALL = 3
            FLASHW_TIMERNOFG = 12

            hwnd = ctypes.windll.user32.FindWindowW(None, "CSP Name Splitter")
            if not hwnd:
                return

            info = FLASHWINFO(
                cbSize=ctypes.sizeof(FLASHWINFO),
                hwnd=hwnd,
                dwFlags=FLASHW_ALL | FLASHW_TIMERNOFG,
                uCount=3,
                dwTimeout=0,
            )
            ctypes.windll.user32.FlashWindowEx(ctypes.byref(info))
        except (OSError, AttributeError):
            pass  # 非Windows環境またはAPI不在時は静かにスキップ

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
