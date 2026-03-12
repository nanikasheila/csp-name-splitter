"""Job execution event handlers mixin for CSP Name Splitter GUI.

Why: gui_handlers.py exceeds 900 lines; the job execution group
     (preview, run_job, auto-open output, taskbar flash, run/cancel)
     forms a cohesive unit that belongs in a dedicated mixin.
How: Pure mixin — no __init__, relies on GuiHandlers to expose self.w,
     self.state, self.page, and shared helpers. GuiHandlers inherits this
     mixin and gains all job-execution event handlers.
"""
from __future__ import annotations

import base64
import os
import subprocess
import sys
from dataclasses import replace
from typing import TYPE_CHECKING, Any

from name_splitter.core import ConfigError, ImageReadError, LimitExceededError, run_job
from name_splitter.core.preview import build_preview_png, load_and_resize_image
from name_splitter.core.template import build_template_preview_png, parse_hex_color
from name_splitter.app.gui_utils import parse_int

if TYPE_CHECKING:
    from name_splitter.app.gui_state import GuiState


class GuiHandlersJobMixin:
    """Mixin providing job execution event handlers for image splitting.

    Why: Job execution (preview, run_job, auto-open output, taskbar flash,
         run/cancel) is logically independent of config, size, and batch
         concerns. Isolating it here keeps gui_handlers.py within a
         manageable size.
    How: Relies on GuiHandlers.__init__ to expose self.w (GuiWidgets),
         self.state (GuiState), self.page, self.add_log, self.add_error_log,
         self.set_status, self.set_progress, self.flush, self.flush_from_thread,
         self.show_error, self.show_success, self.load_config_for_ui,
         self.build_grid_config, self.build_template_style,
         self.compute_canvas_size_px, and self._save_last_run_config via
         the MRO.
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
        def set_progress(self, done: int, total: int) -> None: ...
        def flush(self) -> None: ...
        def flush_from_thread(self) -> None: ...
        def show_error(self, msg: str) -> None: ...
        def show_success(self, msg: str) -> None: ...
        def load_config_for_ui(self) -> tuple[str, Any]: ...
        def build_grid_config(self) -> Any: ...
        def build_template_style(self) -> Any: ...
        def compute_canvas_size_px(self) -> tuple[int, int]: ...
        def _save_last_run_config(self) -> None: ...

    # ------------------------------------------------------------------ #
    # Job event handlers                                                   #
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
            # Why: Read B-1 (output DPI) and B-2 (page numbering) fields from GUI
            # How: Use safe int conversion with fallback defaults for invalid input
            output_dpi_str = (self.w.image.output_dpi_field.value or "0").strip()
            try:
                output_dpi = int(output_dpi_str) if output_dpi_str else 0
            except ValueError:
                output_dpi = 0
            page_start_str = (self.w.image.page_number_start_field.value or "1").strip()
            try:
                page_start = int(page_start_str) if page_start_str else 1
            except ValueError:
                page_start = 1
            skip_str = (self.w.image.skip_pages_field.value or "").strip()
            skip_pages = tuple(
                int(s.strip()) for s in skip_str.split(",") if s.strip().isdigit()
            ) if skip_str else ()
            odd_even = (self.w.image.odd_even_field.value or "all").strip()
            cfg = replace(cfg, output=replace(
                cfg.output,
                container=output_format,
                output_dpi=output_dpi,
                page_number_start=page_start,
                skip_pages=skip_pages,
                odd_even=odd_even,
            ))
            out = (self.w.image.out_dir_field.value or "").strip() or None
            tp = self.w.image.test_page_field.value.strip() if self.w.image.test_page_field.value else ""
            tp_val = int(tp) if tp else None
            self.set_status(msg)
            self.flush()

            def on_progress(ev: Any) -> None:
                # C-1: Enhanced progress with speed/ETA during render_pages
                self.set_progress(ev.done, ev.total)
                pct = int(ev.done / ev.total * 100) if ev.total else 0
                parts = [f"{ev.phase} {ev.done}/{ev.total} ({pct}%)"]
                if ev.pages_per_second > 0:
                    parts.append(f"{ev.pages_per_second:.1f}p/s")
                if ev.eta_seconds is not None and ev.eta_seconds > 0:
                    parts.append(f"残り{ev.eta_seconds:.0f}秒")
                self.set_status(" ".join(parts))
                self.add_log(f"[{ev.phase}] {ev.done}/{ev.total} {ev.message}".strip())
                self.flush_from_thread()

            result = run_job(
                path, cfg,
                out_dir=out,
                test_page=tp_val,
                on_progress=on_progress,
                cancel_token=self.state.cancel_token,
            )
            # D-1: Result report
            self.add_log("--- 処理結果 ---")
            self.add_log(f"Plan written to {result.plan.manifest_path}")
            self.add_log(f"ページ数: {result.page_count}")
            self.add_log(f"処理時間: {result.elapsed_seconds:.1f}秒")
            try:
                total_bytes = sum(
                    p.stat().st_size for p in result.out_dir.rglob("*") if p.is_file()
                )
                if total_bytes >= 1_048_576:
                    self.add_log(f"総ファイルサイズ: {total_bytes / 1_048_576:.1f} MB")
                else:
                    self.add_log(f"総ファイルサイズ: {total_bytes / 1024:.1f} KB")
            except OSError:
                pass
            if result.pdf_path:
                resolved = result.pdf_path.resolve()
                size_kb = resolved.stat().st_size / 1024
                self.add_log(f"PDF exported: {resolved} ({size_kb:.1f} KB)")
                self.show_success(f"PDF exported: {resolved.name} ({size_kb:.1f} KB)")
            self.add_log(f"出力先: {result.out_dir.resolve()}")
            self.add_log("--- ---")
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


__all__ = ["GuiHandlersJobMixin"]
