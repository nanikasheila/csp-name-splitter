"""Size computation and UI update mixin for CSP Name Splitter GUI.

Why: Size-related computations (page size, canvas, frame, grid config,
     template style) and their corresponding UI update routines form a
     cohesive group that also makes gui_handlers.py exceed 500 lines.
     Extracting them as a mixin keeps GuiHandlers focused on event wiring.
How: Pure mixin — no __init__, relies on GuiHandlers to set self.w,
     self.state, self.page, and utility methods. GuiHandlers inherits this
     mixin and gains all size-related methods.
"""
from __future__ import annotations

import threading
from typing import TYPE_CHECKING, Any

from name_splitter.core.config import GridConfig
from name_splitter.core.template import TemplateStyle
from name_splitter.app.gui_utils import (
    PageSizeParams,
    GridConfigParams,
    TemplateStyleParams,
    FrameSizeParams,
    parse_int,
    px_to_mm,
    compute_page_size_px as compute_page_size_px_impl,
    compute_canvas_size_px as compute_canvas_size_px_impl,
    compute_frame_size_mm as compute_frame_size_mm_impl,
    build_grid_config as build_grid_config_from_params,
    build_template_style as build_template_style_from_params,
)

if TYPE_CHECKING:
    from name_splitter.app.gui_state import GuiState


class GuiHandlersSizeMixin:
    """Mixin providing size computation and UI update methods.

    Why: Page/canvas size computation, frame size calculation, and the
         corresponding UI refresh routines share the same inputs (DPI,
         page size selection, grid, margin fields) and are called together.
         Grouping them avoids scattering related logic across files.
    How: Each compute_* method builds a typed *Params dataclass from UI
         fields and delegates to the pure functions in gui_utils. The
         update_size_info method calls all compute methods once and
         distributes results to the display helpers.
    """

    if TYPE_CHECKING:
        w: Any        # GuiWidgets — set in GuiHandlers.__init__
        state: GuiState

        def flush(self) -> None: ...

    # ------------------------------------------------------------------
    # Grid / template style builders
    # ------------------------------------------------------------------

    def build_grid_config(self) -> GridConfig:
        """Build GridConfig from current UI field values.

        Why: GridConfig is needed for both preview and job execution.
             Centralising the field-reading logic avoids duplication.
        How: Reads all relevant common fields, packages them into
             GridConfigParams, and delegates to build_grid_config_from_params.

        Returns:
            GridConfig populated from the current UI state
        """
        page_w_px, page_h_px = self.compute_page_px()
        params = GridConfigParams(
            rows=self.w.common.rows_field.value or "0",
            cols=self.w.common.cols_field.value or "0",
            order=self.w.common.order_field.value or "rtl_ttb",
            margin_top=self.w.common.margin_top_field.value or "0",
            margin_bottom=self.w.common.margin_bottom_field.value or "0",
            margin_left=self.w.common.margin_left_field.value or "0",
            margin_right=self.w.common.margin_right_field.value or "0",
            margin_unit=self.w.common.margin_unit_field.value or "px",
            gutter=self.w.common.gutter_field.value or "0",
            gutter_unit=self.w.common.gutter_unit_field.value or "px",
            dpi=self.w.common.dpi_field.value or "300",
            page_size_name=self.w.common.page_size_field.value or "A4",
            orientation=self.w.common.orientation_field.value or "portrait",
            page_width_px=page_w_px,
            page_height_px=page_h_px,
            page_size_unit=self.w.common.custom_size_unit_field.value or "px",
        )
        return build_grid_config_from_params(params)

    def build_template_style(self) -> TemplateStyle:
        """Build TemplateStyle from current UI field values.

        Why: TemplateStyle requires >15 parameters spread across finish,
             basic, and color fields. Centralising this avoids repeated
             field reads in preview and template-generation handlers.
        How: Reads finish/basic frame fields plus shared page/DPI fields,
             packages them into TemplateStyleParams, and delegates to
             build_template_style_from_params in gui_utils.

        Returns:
            TemplateStyle populated from the current UI state
        """
        pw, ph = self.compute_page_px()
        params = TemplateStyleParams(
            grid_color=self.w.common.grid_color_field.value or "#FF5030",
            grid_alpha=self.w.common.grid_alpha_field.value or "0",
            grid_width=self.w.common.grid_width_field.value or "0",
            finish_color=self.w.template.finish_color_field.value or "#FFFFFF",
            finish_alpha=self.w.template.finish_alpha_field.value or "0",
            finish_line_width=self.w.template.finish_line_width_field.value or "0",
            finish_size_mode=self.w.template.finish_size_mode_field.value or "Use per-page size",
            finish_width=self.w.template.finish_width_field.value or "",
            finish_height=self.w.template.finish_height_field.value or "",
            finish_offset_x=self.w.template.finish_offset_x_field.value or "0",
            finish_offset_y=self.w.template.finish_offset_y_field.value or "0",
            draw_finish=bool(self.w.template.draw_finish_field.value),
            basic_color=self.w.template.basic_color_field.value or "#00AAFF",
            basic_alpha=self.w.template.basic_alpha_field.value or "0",
            basic_line_width=self.w.template.basic_line_width_field.value or "0",
            basic_size_mode=self.w.template.basic_size_mode_field.value or "Use per-page size",
            basic_width=self.w.template.basic_width_field.value or "",
            basic_height=self.w.template.basic_height_field.value or "",
            basic_offset_x=self.w.template.basic_offset_x_field.value or "0",
            basic_offset_y=self.w.template.basic_offset_y_field.value or "0",
            draw_basic=bool(self.w.template.draw_basic_field.value),
            dpi=parse_int(self.w.common.dpi_field.value or "300", "DPI"),
            orientation=self.w.common.orientation_field.value or "portrait",
            page_width_px=pw,
            page_height_px=ph,
        )
        return build_template_style_from_params(params)

    # ------------------------------------------------------------------
    # Size computation helpers
    # ------------------------------------------------------------------

    def compute_page_px(self) -> tuple[int, int]:
        """Compute page dimensions in pixels from UI fields.

        Why: Page size is computed repeatedly (grid config, canvas size,
             mm display). Caching the result in state avoids redundant work.
        How: Builds PageSizeParams from UI, delegates to
             compute_page_size_px_impl, and updates state.page_size_cache.

        Returns:
            (width_px, height_px) tuple
        """
        params = PageSizeParams(
            page_size_name=self.w.common.page_size_field.value or "A4",
            orientation=self.w.common.orientation_field.value or "portrait",
            dpi=parse_int(self.w.common.dpi_field.value or "300", "DPI"),
            custom_width=self.w.common.custom_width_field.value,
            custom_height=self.w.common.custom_height_field.value,
            custom_unit=self.w.common.custom_size_unit_field.value or "px",
        )
        w, h = compute_page_size_px_impl(params, *self.state.page_size_cache.get())
        self.state.page_size_cache.update(w, h)
        return w, h

    def compute_canvas_size_px(self) -> tuple[int, int]:
        """Compute canvas dimensions in pixels (page minus margins).

        Why: Canvas size is the drawable area after subtracting margins,
             needed for preview and template generation.
        How: Calls compute_page_px and build_grid_config to obtain the
             margin-aware canvas via compute_canvas_size_px_impl.

        Returns:
            (canvas_width_px, canvas_height_px) tuple
        """
        pw, ph = self.compute_page_px()
        g = self.build_grid_config()
        return compute_canvas_size_px_impl(g, pw, ph)

    def compute_page_size_mm(self) -> tuple[float, float]:
        """Compute page dimensions in millimetres from UI fields.

        Why: The size info text and frame auto-fill need dimensions in mm
             for human-readable display and mm-unit frame fields.
        How: Obtains page_px then converts using px_to_mm with DPI value.

        Returns:
            (width_mm, height_mm) tuple
        Raises:
            ValueError: if DPI is zero or negative
        """
        dpi = parse_int(self.w.common.dpi_field.value or "0", "DPI")
        if dpi <= 0:
            raise ValueError("DPI must be positive")
        wpx, hpx = self.compute_page_px()
        return px_to_mm(wpx, dpi), px_to_mm(hpx, dpi)

    def compute_frame_size_mm_ui(self, mode: str, w_val: str, h_val: str) -> tuple[float, float]:
        """Compute finish/basic frame dimensions in mm for a given size mode.

        Why: Frame size can follow the page, a standard paper size, or a
             custom value; the calculation differs per mode. Centralising it
             prevents duplicate mode-switch logic across finish and basic code.
        How: Builds FrameSizeParams from mode, current UI page/DPI values,
             and delegates to compute_frame_size_mm_impl in gui_utils.

        Returns:
            (frame_width_mm, frame_height_mm) tuple
        """
        pw, ph = self.compute_page_px()
        params = FrameSizeParams(
            mode=mode or "Use per-page size",
            dpi=parse_int(self.w.common.dpi_field.value or "0", "DPI"),
            orientation=self.w.common.orientation_field.value or "portrait",
            width_value=w_val,
            height_value=h_val,
            page_width_px=pw,
            page_height_px=ph,
        )
        return compute_frame_size_mm_impl(params)

    # ------------------------------------------------------------------
    # UI update helpers called by update_size_info
    # ------------------------------------------------------------------

    def _update_size_display(
        self, gc: GridConfig, pw: int, ph: int, cw: int, ch: int, wmm: float, hmm: float
    ) -> None:
        """Render page/canvas/grid dimensions into the size_info_text widget.

        Why: Showing computed dimensions helps users verify their settings
             are producing the expected pixel/mm values.
        How: Formats a single info string and clears any previous error colour.
        """
        self.w.common.size_info_text.value = (
            f"Page: {pw}×{ph} px ({wmm:.1f}×{hmm:.1f} mm)  |  "
            f"Canvas: {cw}×{ch} px  |  Grid: {gc.rows}×{gc.cols}"
        )
        self.w.common.size_info_text.color = None

    def _update_custom_fields(self, pw: int, ph: int, wmm: float, hmm: float) -> None:
        """Enable/disable and auto-fill custom page size fields.

        Why: When a preset size is selected the custom fields should be
             read-only and filled with the preset values; when "Custom" is
             selected they become editable and retain the user's values.
        How: Sets disabled state first, then fills values based on the
             current page size unit (px vs mm) only when fields are empty.
        """
        is_custom = self.w.common.page_size_field.value == "Custom"
        self.w.common.custom_width_field.disabled = not is_custom
        self.w.common.custom_height_field.disabled = not is_custom

        page_size_unit = self.w.common.custom_size_unit_field.value or "px"
        if is_custom and (
            not self.w.common.custom_width_field.value
            or not self.w.common.custom_height_field.value
        ):
            if page_size_unit == "mm":
                self.w.common.custom_width_field.value = f"{wmm:.2f}"
                self.w.common.custom_height_field.value = f"{hmm:.2f}"
            else:
                self.w.common.custom_width_field.value = str(pw)
                self.w.common.custom_height_field.value = str(ph)
        if not is_custom:
            if page_size_unit == "mm":
                self.w.common.custom_width_field.value = f"{wmm:.2f}"
                self.w.common.custom_height_field.value = f"{hmm:.2f}"
            else:
                self.w.common.custom_width_field.value = str(pw)
                self.w.common.custom_height_field.value = str(ph)

    def _update_finish_frame_fields(self, pw: int, ph: int, wmm: float, hmm: float) -> None:
        """Auto-fill finish frame width/height fields and set disabled state.

        Why: Preset finish size modes (A4, B4, etc.) should fill the fields
             automatically so the user sees exact millimetre values.
        How: For preset modes calls compute_frame_size_mm_ui; for custom
             modes fills only when fields are empty (preserving user input).
        """
        fm = self.w.template.finish_size_mode_field.value or "Use per-page size"
        if fm in {"Use per-page size", "A4", "A5", "B4", "B5"}:
            fw, fh = self.compute_frame_size_mm_ui(fm, "", "")
            self.w.template.finish_width_field.value = f"{fw:.2f}"
            self.w.template.finish_height_field.value = f"{fh:.2f}"
        if fm == "Custom mm" and (
            not self.w.template.finish_width_field.value
            or not self.w.template.finish_height_field.value
        ):
            self.w.template.finish_width_field.value = f"{wmm:.2f}"
            self.w.template.finish_height_field.value = f"{hmm:.2f}"
        if fm == "Custom px" and (
            not self.w.template.finish_width_field.value
            or not self.w.template.finish_height_field.value
        ):
            self.w.template.finish_width_field.value = str(pw)
            self.w.template.finish_height_field.value = str(ph)
        self.w.template.finish_width_field.disabled = not fm.startswith("Custom")
        self.w.template.finish_height_field.disabled = not fm.startswith("Custom")

    def _update_basic_frame_fields(self, pw: int, ph: int, wmm: float, hmm: float) -> None:
        """Auto-fill basic frame width/height fields and set disabled state.

        Why: Same rationale as _update_finish_frame_fields — preset modes
             should reflect standard paper dimensions automatically.
        How: Identical pattern to finish frame; custom mm defaults include
             a 20 mm inset and custom px defaults include a 200 px inset.
        """
        bm = self.w.template.basic_size_mode_field.value or "Use per-page size"
        if bm in {"Use per-page size", "A4", "A5", "B4", "B5"}:
            bw, bh = self.compute_frame_size_mm_ui(bm, "", "")
            self.w.template.basic_width_field.value = f"{bw:.2f}"
            self.w.template.basic_height_field.value = f"{bh:.2f}"
        if bm == "Custom mm" and (
            not self.w.template.basic_width_field.value
            or not self.w.template.basic_height_field.value
        ):
            self.w.template.basic_width_field.value = f"{max(0.0, wmm - 20):.2f}"
            self.w.template.basic_height_field.value = f"{max(0.0, hmm - 20):.2f}"
        if bm == "Custom px" and (
            not self.w.template.basic_width_field.value
            or not self.w.template.basic_height_field.value
        ):
            self.w.template.basic_width_field.value = str(max(0, pw - 200))
            self.w.template.basic_height_field.value = str(max(0, ph - 200))
        self.w.template.basic_width_field.disabled = not bm.startswith("Custom")
        self.w.template.basic_height_field.disabled = not bm.startswith("Custom")

    # ------------------------------------------------------------------
    # Public orchestrator
    # ------------------------------------------------------------------

    def update_size_info(self, _: Any = None) -> None:
        """Refresh size display and all dependent auto-fill fields.

        Why: Multiple UI events (DPI change, page size selection, margin
             edits) must all trigger a consistent refresh of the info text
             and the auto-filled frame/custom-size fields.
        How: Computes page and canvas dimensions once, then calls each
             _update_* helper. Errors are caught and shown in red.
        """
        try:
            gc = self.build_grid_config()
            pw, ph = self.compute_page_px()
            cw, ch = self.compute_canvas_size_px()
            wmm, hmm = self.compute_page_size_mm()

            self._update_size_display(gc, pw, ph, cw, ch, wmm, hmm)
            self._update_custom_fields(pw, ph, wmm, hmm)
            self._update_finish_frame_fields(pw, ph, wmm, hmm)
            self._update_basic_frame_fields(pw, ph, wmm, hmm)
        except Exception as exc:  # noqa: BLE001
            self.w.common.size_info_text.value = f"Size error: {exc}"
            self.w.common.size_info_text.color = "red"
        self.flush()

    # Debounce state for auto-preview
    _preview_timer: threading.Timer | None = None
    _preview_debounce_seconds: float = 0.3

    def auto_preview_if_enabled(self, _: Any = None) -> None:
        """Trigger a debounced preview refresh if auto-preview is enabled.

        Why: Many field-change events fire in rapid succession (tab switches,
             slider drags, unit conversions). Rebuilding the full preview on
             every event wastes CPU. Only the last request matters.
        How: Resets a 300 ms one-shot timer on each call. When the timer
             fires without being cancelled, _execute_preview runs once.
             Guards for auto_preview_enabled and empty-input are checked
             both at schedule time (early exit) and at execution time
             (state may have changed during the delay).
        """
        if not self.state.auto_preview_enabled:
            return
        if self.state.is_image_split_tab() and not (self.w.image.input_field.value or "").strip():
            return
        if self._preview_timer is not None:
            self._preview_timer.cancel()
        self._preview_timer = threading.Timer(
            self._preview_debounce_seconds,
            self._execute_preview,
        )
        self._preview_timer.daemon = True
        self._preview_timer.start()

    def _execute_preview(self) -> None:
        """Run the actual preview generation after debounce delay.

        Why: Separated from the timer scheduling so the guard checks can
             be re-evaluated at execution time — the user may have switched
             tabs or cleared the input field during the debounce window.
        How: Re-checks auto_preview_enabled and input state, then delegates
             to on_preview. All exceptions are suppressed to avoid crashing
             the Flet event loop.
        """
        if not self.state.auto_preview_enabled:
            return
        if self.state.is_image_split_tab() and not (self.w.image.input_field.value or "").strip():
            return
        try:
            self.on_preview(None)  # type: ignore[attr-defined]
        except Exception:  # noqa: BLE001
            pass


__all__ = ["GuiHandlersSizeMixin"]
