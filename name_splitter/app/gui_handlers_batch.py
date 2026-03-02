"""Batch processing event handlers mixin for CSP Name Splitter GUI.

Why: gui_handlers.py is already 750+ lines. Batch processing adds another
     distinct responsibility (directory scanning, multi-job orchestration,
     per-job progress) that belongs in a dedicated mixin.
How: Pure mixin — no __init__, relies on GuiHandlers to expose self.w,
     self.state, self.page, and shared helpers. GuiHandlers inherits this
     mixin and gains all batch-processing event handlers.
"""
from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

from name_splitter.core.errors import ConfigError, ImageReadError, LimitExceededError

if TYPE_CHECKING:
    from name_splitter.app.gui_state import GuiState


class GuiHandlersBatchMixin:
    """Mixin providing batch-processing event handlers for the Batch tab.

    Why: Batch processing (scan directory → build job specs → run_batch)
         is logically independent of single-image splitting. Isolating it
         here keeps gui_handlers.py within a manageable size limit.
    How: Relies on GuiHandlers.__init__ to expose self.w (GuiWidgets),
         self.state (GuiState), self.page, self.add_log, self.add_error_log,
         self.flush_from_thread, and self.load_config_for_ui via the MRO.
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
        def load_config_for_ui(self) -> tuple[str, Any]: ...

    # ------------------------------------------------------------------ #
    # Batch event handlers                                                #
    # ------------------------------------------------------------------ #

    def on_run_batch(self, _: Any) -> None:
        """Handle Batch Run button click — start batch job in a background thread.

        Why: Batch processing can take minutes; running on the UI thread
             would freeze the application completely.
        How: Resets cancel token, toggles button states, then delegates to
             page.run_thread with _run_batch.
        """
        if self.w.batch is None:
            return
        self.state.reset_cancel_token()
        self.w.batch.batch_run_btn.disabled = True
        self.w.batch.batch_cancel_btn.disabled = False
        self.w.batch.batch_status_text.value = "Starting..."
        self.add_log("Starting batch job...")
        self.flush()
        self.page.run_thread(self._run_batch)

    def on_cancel_batch(self, _: Any) -> None:
        """Handle Batch Cancel button click — request batch cancellation.

        Why: Batch jobs may process dozens of images; the user must be able
             to abort mid-way without killing the application.
        How: Delegates to state.request_cancel() which sets the shared
             CancelToken that run_batch checks between images.
        """
        if self.w.batch is None:
            return
        self.state.request_cancel()
        self.w.batch.batch_status_text.value = "Cancelling..."
        self.set_status("Cancel requested")
        self.flush()

    def _run_batch(self) -> None:
        """Execute the batch image-split job in a background thread.

        Why: Scanning a directory and splitting multiple images is a long-
             running operation that must not block the UI event loop.
        How: Reads the batch input directory and output directory from the
             Batch tab widgets. Uses find_images_in_directory to collect PNG
             paths. Builds BatchJobSpec list using the current UI config.
             Calls run_batch with a progress callback that updates the
             batch status text after each image.
        """
        from name_splitter.core.batch import (
            BatchJobSpec,
            find_images_in_directory,
            run_batch,
        )

        if self.w.batch is None:
            return

        batch = self.w.batch
        try:
            batch_dir_str = (batch.batch_dir_field.value or "").strip()
            if not batch_dir_str:
                raise ValueError("Input directory is required")
            batch_dir = Path(batch_dir_str)
            if not batch_dir.is_dir():
                raise ValueError(f"Directory not found: {batch_dir}")

            batch_out_str = (batch.batch_out_dir_field.value or "").strip()
            batch_out_dir: Path | None = Path(batch_out_str) if batch_out_str else None

            recursive: bool = bool(batch.batch_recursive_field.value)

            images = find_images_in_directory(batch_dir, recursive=recursive)
            if not images:
                raise ValueError(f"No PNG files found in: {batch_dir}")

            _, cfg = self.load_config_for_ui()

            job_specs: list[BatchJobSpec] = [
                BatchJobSpec(
                    input_image=img,
                    config=cfg,
                    out_dir=batch_out_dir,
                )
                for img in images
            ]

            total = len(job_specs)
            self.add_log(f"Batch: {total} files found in {batch_dir}")
            batch.batch_status_text.value = f"0 / {total}"
            self.flush_from_thread()

            def on_batch_progress(ev: Any) -> None:
                """Update batch status text and log after each job step."""
                pct = int(ev.current_job / ev.total_jobs * 100) if ev.total_jobs else 0
                batch.batch_status_text.value = (
                    f"{ev.current_job} / {ev.total_jobs} ({pct}%) — {ev.job_name}"
                )
                self.add_log(
                    f"[batch] {ev.current_job}/{ev.total_jobs}: {ev.job_name}"
                )
                self.flush_from_thread()

            result = run_batch(
                job_specs,
                on_progress=on_batch_progress,
                cancel_token=self.state.cancel_token,
            )

            summary = (
                f"Done: {result.successful_jobs} OK, "
                f"{result.failed_jobs} failed / {result.total_jobs} total"
            )
            self.add_log(f"Batch complete — {summary}")
            batch.batch_status_text.value = summary
            self.flush_from_thread()

        except (ConfigError, LimitExceededError, ImageReadError, ValueError) as exc:
            self.add_error_log(str(exc))
            batch.batch_status_text.value = f"Error: {exc}"
            self.flush_from_thread()
        finally:
            if self.w.batch is not None:
                self.w.batch.batch_run_btn.disabled = False
                self.w.batch.batch_cancel_btn.disabled = True
                self.flush_from_thread()
            try:
                self.page.update()
            except Exception:  # noqa: BLE001
                pass

    def _pick_batch_dir(self, e: Any) -> None:
        """Open a directory picker for the batch input directory.

        Why: Typing a full directory path is error-prone; a native picker
             is faster and avoids typos.
        How: Schedules an async task on the Flet event loop to open a
             directory picker and write the chosen path to batch_dir_field.
        """
        self.page.run_task(self._async_pick_batch_dir)

    async def _async_pick_batch_dir(self) -> None:
        """Async coroutine for batch input directory picker.

        Why: FilePicker in Flet is asynchronous; must run as a coroutine.
        How: Awaits FilePicker().get_directory_path() and writes result.
        """
        if self.w.batch is None:
            return
        try:
            import flet as ft  # noqa: PLC0415
            path = await ft.FilePicker().get_directory_path()
        except Exception:  # noqa: BLE001
            return
        if path:
            self.w.batch.batch_dir_field.value = path
            self.flush()

    def _pick_batch_out_dir(self, e: Any) -> None:
        """Open a directory picker for the batch output directory.

        Why: Same rationale as _pick_batch_dir — avoids path typing errors.
        How: Schedules an async task to open a directory picker.
        """
        self.page.run_task(self._async_pick_batch_out_dir)

    async def _async_pick_batch_out_dir(self) -> None:
        """Async coroutine for batch output directory picker.

        Why: FilePicker in Flet is asynchronous; must run as a coroutine.
        How: Awaits FilePicker().get_directory_path() and writes result.
        """
        if self.w.batch is None:
            return
        try:
            import flet as ft  # noqa: PLC0415
            path = await ft.FilePicker().get_directory_path()
        except Exception:  # noqa: BLE001
            return
        if path:
            self.w.batch.batch_out_dir_field.value = path
            self.flush()


__all__ = ["GuiHandlersBatchMixin"]
