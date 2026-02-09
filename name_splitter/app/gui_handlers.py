"""Event handlers and helper methods for CSP Name Splitter GUI.

This module extracts the event handlers and business logic from gui.py
into a clean, testable GuiHandlers class.
"""
from __future__ import annotations

import base64
from dataclasses import dataclass, replace
from datetime import datetime
from typing import Any

from name_splitter.core import (
    CancelToken,
    ConfigError,
    ImageReadError,
    LimitExceededError,
    load_config,
    load_default_config,
    run_job,
)
from name_splitter.core.config import GridConfig
from name_splitter.core.preview import build_preview_png
from name_splitter.core.template import (
    TemplateStyle,
    build_template_preview_png,
    generate_template_png,
    parse_hex_color,
)
from name_splitter.app.gui_state import GuiState
from name_splitter.app.gui_utils import (
    PageSizeParams,
    GridConfigParams,
    TemplateStyleParams,
    FrameSizeParams,
    parse_int,
    parse_float,
    px_to_mm,
    mm_to_px,
    convert_margin_to_px,
    convert_unit_value,
    compute_page_size_px as compute_page_size_px_impl,
    compute_canvas_size_px as compute_canvas_size_px_impl,
    compute_frame_size_mm as compute_frame_size_mm_impl,
    build_grid_config as build_grid_config_from_params,
    build_template_style as build_template_style_from_params,
)


@dataclass
class GuiWidgets:
    """References to all GUI widgets."""
    
    # Configuration
    config_field: Any
    
    # Page size and DPI
    page_size_field: Any
    orientation_field: Any
    dpi_field: Any
    custom_size_unit_field: Any
    custom_width_field: Any
    custom_height_field: Any
    size_info_text: Any
    
    # Grid settings
    rows_field: Any
    cols_field: Any
    order_field: Any
    gutter_unit_field: Any
    gutter_field: Any
    
    # Margin settings
    margin_unit_field: Any
    margin_top_field: Any
    margin_bottom_field: Any
    margin_left_field: Any
    margin_right_field: Any
    
    # Image split tab
    input_field: Any
    out_dir_field: Any
    test_page_field: Any
    
    # Template tab
    template_out_field: Any
    draw_finish_field: Any
    finish_size_mode_field: Any
    finish_width_field: Any
    finish_height_field: Any
    finish_offset_x_field: Any
    finish_offset_y_field: Any
    finish_color_field: Any
    finish_alpha_field: Any
    finish_line_width_field: Any
    draw_basic_field: Any
    basic_size_mode_field: Any
    basic_width_field: Any
    basic_height_field: Any
    basic_offset_x_field: Any
    basic_offset_y_field: Any
    basic_color_field: Any
    basic_alpha_field: Any
    basic_line_width_field: Any
    grid_color_field: Any
    grid_alpha_field: Any
    grid_width_field: Any
    
    # UI elements
    log_field: Any
    progress_bar: Any
    status_text: Any
    preview_image: Any
    run_btn: Any
    cancel_btn: Any


class GuiHandlers:
    """Event handlers and helper methods for CSP Name Splitter GUI."""
    
    def __init__(self, widgets: GuiWidgets, state: GuiState, page: Any, clipboard: Any):
        """Initialize handlers with dependencies.
        
        Args:
            widgets: GuiWidgets containing all UI element references
            state: GuiState for state management
            page: Flet Page object
            clipboard: Flet clipboard service (may be None)
        """
        self.w = widgets  # Short alias for widgets
        self.state = state
        self.page = page
        self.clipboard = clipboard
    
    # ============================================================== #
    #  Helper methods                                                #
    # ============================================================== #
    
    def add_log(self, msg: str) -> None:
        """Add a timestamped log message."""
        ts = datetime.now().strftime("%H:%M:%S")
        self.w.log_field.value = f"{self.w.log_field.value or ''}{ts} {msg}\n"
    
    def set_status(self, msg: str) -> None:
        """Set status text."""
        self.w.status_text.value = msg
    
    def set_progress(self, done: int, total: int) -> None:
        """Set progress bar value."""
        self.w.progress_bar.value = max(0.0, min(1.0, done / total)) if total else None
    
    def flush(self) -> None:
        """Update the page to reflect changes."""
        self.page.update()
    
    def show_error(self, msg: str) -> None:
        """Show error in snackbar."""
        try:
            import flet as ft
            self.page.open(ft.SnackBar(
                content=ft.Text(str(msg)),
                bgcolor="red",
                duration=5000,
            ))
        except Exception:
            pass
    
    def build_grid_config(self) -> GridConfig:
        """Build GridConfig from UI fields (using gui_utils)."""
        page_w_px, page_h_px = self.compute_page_px()
        params = GridConfigParams(
            rows=self.w.rows_field.value or "0",
            cols=self.w.cols_field.value or "0",
            order=self.w.order_field.value or "rtl_ttb",
            margin_top=self.w.margin_top_field.value or "0",
            margin_bottom=self.w.margin_bottom_field.value or "0",
            margin_left=self.w.margin_left_field.value or "0",
            margin_right=self.w.margin_right_field.value or "0",
            margin_unit=self.w.margin_unit_field.value or "px",
            gutter=self.w.gutter_field.value or "0",
            gutter_unit=self.w.gutter_unit_field.value or "px",
            dpi=self.w.dpi_field.value or "300",
            page_size_name=self.w.page_size_field.value or "A4",
            orientation=self.w.orientation_field.value or "portrait",
            page_width_px=page_w_px,
            page_height_px=page_h_px,
            page_size_unit=self.w.custom_size_unit_field.value or "px",
        )
        return build_grid_config_from_params(params)
    
    def compute_page_px(self) -> tuple[int, int]:
        """Compute page size in pixels from UI fields (using gui_utils)."""
        params = PageSizeParams(
            page_size_name=self.w.page_size_field.value or "A4",
            orientation=self.w.orientation_field.value or "portrait",
            dpi=parse_int(self.w.dpi_field.value or "300", "DPI"),
            custom_width=self.w.custom_width_field.value,
            custom_height=self.w.custom_height_field.value,
            custom_unit=self.w.custom_size_unit_field.value or "px",
        )
        w, h = compute_page_size_px_impl(params, *self.state.page_size_cache.get())
        self.state.page_size_cache.update(w, h)
        return w, h
    
    def compute_canvas_size_px(self) -> tuple[int, int]:
        """Compute canvas size in pixels from UI fields (using gui_utils)."""
        pw, ph = self.compute_page_px()
        g = self.build_grid_config()
        return compute_canvas_size_px_impl(g, pw, ph)
    
    def compute_page_size_mm(self) -> tuple[float, float]:
        """Compute page size in millimeters from UI fields (using gui_utils)."""
        dpi = parse_int(self.w.dpi_field.value or "0", "DPI")
        if dpi <= 0:
            raise ValueError("DPI must be positive")
        wpx, hpx = self.compute_page_px()
        return px_to_mm(wpx, dpi), px_to_mm(hpx, dpi)
    
    def compute_frame_size_mm_ui(self, mode: str, w_val: str, h_val: str) -> tuple[float, float]:
        """Compute frame size in millimeters from UI fields (using gui_utils)."""
        pw, ph = self.compute_page_px()
        params = FrameSizeParams(
            mode=mode or "Use per-page size",
            dpi=parse_int(self.w.dpi_field.value or "0", "DPI"),
            orientation=self.w.orientation_field.value or "portrait",
            width_value=w_val,
            height_value=h_val,
            page_width_px=pw,
            page_height_px=ph,
        )
        return compute_frame_size_mm_impl(params)
    
    def build_template_style(self) -> TemplateStyle:
        """Build TemplateStyle from UI fields (using gui_utils)."""
        pw, ph = self.compute_page_px()
        params = TemplateStyleParams(
            grid_color=self.w.grid_color_field.value or "#FF5030",
            grid_alpha=self.w.grid_alpha_field.value or "0",
            grid_width=self.w.grid_width_field.value or "0",
            finish_color=self.w.finish_color_field.value or "#FFFFFF",
            finish_alpha=self.w.finish_alpha_field.value or "0",
            finish_line_width=self.w.finish_line_width_field.value or "0",
            finish_size_mode=self.w.finish_size_mode_field.value or "Use per-page size",
            finish_width=self.w.finish_width_field.value or "",
            finish_height=self.w.finish_height_field.value or "",
            finish_offset_x=self.w.finish_offset_x_field.value or "0",
            finish_offset_y=self.w.finish_offset_y_field.value or "0",
            draw_finish=bool(self.w.draw_finish_field.value),
            basic_color=self.w.basic_color_field.value or "#00AAFF",
            basic_alpha=self.w.basic_alpha_field.value or "0",
            basic_line_width=self.w.basic_line_width_field.value or "0",
            basic_size_mode=self.w.basic_size_mode_field.value or "Use per-page size",
            basic_width=self.w.basic_width_field.value or "",
            basic_height=self.w.basic_height_field.value or "",
            basic_offset_x=self.w.basic_offset_x_field.value or "0",
            basic_offset_y=self.w.basic_offset_y_field.value or "0",
            draw_basic=bool(self.w.draw_basic_field.value),
            dpi=parse_int(self.w.dpi_field.value or "300", "DPI"),
            orientation=self.w.orientation_field.value or "portrait",
            page_width_px=pw,
            page_height_px=ph,
        )
        return build_template_style_from_params(params)
    
    def update_size_info(self, _: Any = None) -> None:
        """Update size information text and related UI elements."""
        try:
            gc = self.build_grid_config()
            pw, ph = self.compute_page_px()
            cw, ch = self.compute_canvas_size_px()
            wmm, hmm = self.compute_page_size_mm()
            self.w.size_info_text.value = (
                f"Page: {pw}×{ph} px ({wmm:.1f}×{hmm:.1f} mm)  |  "
                f"Canvas: {cw}×{ch} px  |  Grid: {gc.rows}×{gc.cols}"
            )
            self.w.size_info_text.color = None

            is_custom = self.w.page_size_field.value == "Custom"
            self.w.custom_width_field.disabled = not is_custom
            self.w.custom_height_field.disabled = not is_custom
            
            # Custom以外でもページサイズを表示（現在の単位に応じて）
            page_size_unit = self.w.custom_size_unit_field.value or "px"
            if is_custom and (not self.w.custom_width_field.value or not self.w.custom_height_field.value):
                if page_size_unit == "mm":
                    self.w.custom_width_field.value = f"{wmm:.2f}"
                    self.w.custom_height_field.value = f"{hmm:.2f}"
                else:
                    self.w.custom_width_field.value = str(pw)
                    self.w.custom_height_field.value = str(ph)
            if not is_custom:
                # プリセットサイズでも現在の単位で表示
                if page_size_unit == "mm":
                    self.w.custom_width_field.value = f"{wmm:.2f}"
                    self.w.custom_height_field.value = f"{hmm:.2f}"
                else:
                    self.w.custom_width_field.value = str(pw)
                    self.w.custom_height_field.value = str(ph)

            # Finish frame auto-fill
            fm = self.w.finish_size_mode_field.value or "Use per-page size"
            if fm in {"Use per-page size", "A4", "A5", "B4", "B5"}:
                fw, fh = self.compute_frame_size_mm_ui(fm, "", "")
                self.w.finish_width_field.value = f"{fw:.2f}"
                self.w.finish_height_field.value = f"{fh:.2f}"
            if fm == "Custom mm" and (not self.w.finish_width_field.value or not self.w.finish_height_field.value):
                self.w.finish_width_field.value = f"{wmm:.2f}"
                self.w.finish_height_field.value = f"{hmm:.2f}"
            if fm == "Custom px" and (not self.w.finish_width_field.value or not self.w.finish_height_field.value):
                self.w.finish_width_field.value = str(pw)
                self.w.finish_height_field.value = str(ph)
            self.w.finish_width_field.disabled = not fm.startswith("Custom")
            self.w.finish_height_field.disabled = not fm.startswith("Custom")

            # Basic frame auto-fill
            bm = self.w.basic_size_mode_field.value or "Use per-page size"
            if bm in {"Use per-page size", "A4", "A5", "B4", "B5"}:
                bw, bh = self.compute_frame_size_mm_ui(bm, "", "")
                self.w.basic_width_field.value = f"{bw:.2f}"
                self.w.basic_height_field.value = f"{bh:.2f}"
            if bm == "Custom mm" and (not self.w.basic_width_field.value or not self.w.basic_height_field.value):
                self.w.basic_width_field.value = f"{max(0.0, wmm - 20):.2f}"
                self.w.basic_height_field.value = f"{max(0.0, hmm - 20):.2f}"
            if bm == "Custom px" and (not self.w.basic_width_field.value or not self.w.basic_height_field.value):
                self.w.basic_width_field.value = str(max(0, pw - 200))
                self.w.basic_height_field.value = str(max(0, ph - 200))
            self.w.basic_width_field.disabled = not bm.startswith("Custom")
            self.w.basic_height_field.disabled = not bm.startswith("Custom")
        except Exception as exc:  # noqa: BLE001
            self.w.size_info_text.value = f"Size error: {exc}"
            self.w.size_info_text.color = "red"
        self.flush()
    
    def load_config_for_ui(self) -> tuple[str, Any]:
        """Load config file or default config."""
        if self.w.config_field.value:
            return "Loaded config", load_config(self.w.config_field.value)
        return "Loaded default config", load_default_config()
    
    def apply_config_to_ui(self, cfg: Any) -> None:
        """Apply loaded config to UI fields."""
        self.state.disable_auto_preview()  # Disable auto-update during config application
        try:
            # DPI
            if hasattr(cfg.grid, "dpi") and cfg.grid.dpi > 0:
                self.w.dpi_field.value = str(cfg.grid.dpi)
            
            # Page size name & orientation
            if hasattr(cfg.grid, "page_size_name"):
                self.w.page_size_field.value = cfg.grid.page_size_name
            if hasattr(cfg.grid, "orientation"):
                self.w.orientation_field.value = cfg.grid.orientation
            
            # Custom page size
            if hasattr(cfg.grid, "page_width_px") and hasattr(cfg.grid, "page_height_px"):
                w, h = cfg.grid.page_width_px, cfg.grid.page_height_px
                if w > 0 and h > 0:
                    unit = cfg.grid.page_size_unit if hasattr(cfg.grid, "page_size_unit") else "px"
                    self.w.custom_size_unit_field.value = unit
                    if unit == "mm":
                        dpi = cfg.grid.dpi
                        self.w.custom_width_field.value = f"{w * 25.4 / dpi:.1f}"
                        self.w.custom_height_field.value = f"{h * 25.4 / dpi:.1f}"
                    else:
                        self.w.custom_width_field.value = str(w)
                        self.w.custom_height_field.value = str(h)
                    if self.w.page_size_field.value != "Custom":
                        self.w.page_size_field.value = "Custom"
            
            # Grid settings
            self.w.rows_field.value = str(cfg.grid.rows)
            self.w.cols_field.value = str(cfg.grid.cols)
            self.w.order_field.value = cfg.grid.order
            
            # Gutter unit
            if hasattr(cfg.grid, "gutter_unit"):
                self.w.gutter_unit_field.value = cfg.grid.gutter_unit
            
            # Gutter (stored as px in config, convert to UI unit)
            dpi = cfg.grid.dpi
            gutter_unit = self.w.gutter_unit_field.value or "px"
            if gutter_unit == "mm":
                self.w.gutter_field.value = f"{cfg.grid.gutter_px * 25.4 / dpi:.2f}"
            else:
                self.w.gutter_field.value = str(cfg.grid.gutter_px)
            
            # Margin unit
            if hasattr(cfg.grid, "margin_unit"):
                self.w.margin_unit_field.value = cfg.grid.margin_unit
            
            # Margin (stored as px in config, convert to UI unit)
            unit = self.w.margin_unit_field.value or "px"
            if cfg.grid.margin_top_px or cfg.grid.margin_bottom_px or cfg.grid.margin_left_px or cfg.grid.margin_right_px:
                if unit == "mm":
                    self.w.margin_top_field.value = f"{cfg.grid.margin_top_px * 25.4 / dpi:.2f}"
                    self.w.margin_bottom_field.value = f"{cfg.grid.margin_bottom_px * 25.4 / dpi:.2f}"
                    self.w.margin_left_field.value = f"{cfg.grid.margin_left_px * 25.4 / dpi:.2f}"
                    self.w.margin_right_field.value = f"{cfg.grid.margin_right_px * 25.4 / dpi:.2f}"
                else:
                    self.w.margin_top_field.value = str(cfg.grid.margin_top_px)
                    self.w.margin_bottom_field.value = str(cfg.grid.margin_bottom_px)
                    self.w.margin_left_field.value = str(cfg.grid.margin_left_px)
                    self.w.margin_right_field.value = str(cfg.grid.margin_right_px)
            else:
                # Legacy margin_px to all directions
                if unit == "mm":
                    val_mm = f"{cfg.grid.margin_px * 25.4 / dpi:.2f}"
                    self.w.margin_top_field.value = val_mm
                    self.w.margin_bottom_field.value = val_mm
                    self.w.margin_left_field.value = val_mm
                    self.w.margin_right_field.value = val_mm
                else:
                    self.w.margin_top_field.value = str(cfg.grid.margin_px)
                    self.w.margin_bottom_field.value = str(cfg.grid.margin_px)
                    self.w.margin_left_field.value = str(cfg.grid.margin_px)
                    self.w.margin_right_field.value = str(cfg.grid.margin_px)
            
            # Update current units
            self.state.unit_state.margin_unit = self.w.margin_unit_field.value or "px"
            self.state.unit_state.page_size_unit = self.w.custom_size_unit_field.value or "px"
            self.state.unit_state.gutter_unit = self.w.gutter_unit_field.value or "px"
            
            self.update_size_info()
            self.add_log("Config applied to UI")
            self.flush()
        finally:
            self.state.enable_auto_preview()
    
    def auto_preview_if_enabled(self, _: Any = None) -> None:
        """Auto-update preview if enabled."""
        if not self.state.auto_preview_enabled:
            return
        # Skip if Image Split tab and input_field is empty
        if self.state.is_image_split_tab() and not (self.w.input_field.value or "").strip():
            return
        try:
            self.on_preview(None)
        except Exception:  # noqa: BLE001
            pass
    
    # ============================================================== #
    #  Event handlers                                                #
    # ============================================================== #
    
    def on_config_change(self, _: Any) -> None:
        """Handle config file change."""
        if not self.w.config_field.value:
            return
        try:
            msg, cfg = self.load_config_for_ui()
            self.apply_config_to_ui(cfg)
            self.set_status(msg)
        except Exception as exc:  # noqa: BLE001
            self.add_log(f"Config load error: {exc}")
            self.set_status("Config error")
        self.flush()
    
    def on_preview(self, _: Any) -> None:
        """Handle preview button click."""
        try:
            grid_cfg = self.build_grid_config()
            if self.state.is_template_tab():
                # Template preview
                w, h = self.compute_canvas_size_px()
                dpi = parse_int(self.w.dpi_field.value or "0", "DPI")
                png = build_template_preview_png(w, h, grid_cfg, self.build_template_style(), dpi)
                self.w.preview_image.src = f"data:image/png;base64,{base64.b64encode(png).decode('ascii')}"
                self.set_status("Template preview")
            else:
                # Image preview
                path = (self.w.input_field.value or "").strip()
                if not path:
                    raise ValueError("Input image is required for preview")
                msg, cfg = self.load_config_for_ui()
                cfg = replace(cfg, grid=grid_cfg)
                # Grid lines settings
                grid_alpha = parse_int(self.w.grid_alpha_field.value or "170", "Grid alpha")
                grid_line_color = parse_hex_color(self.w.grid_color_field.value or "#FF5030", grid_alpha)
                grid_line_width = max(1, parse_int(self.w.grid_width_field.value or "1", "Grid width"))
                png = build_preview_png(path, cfg.grid, line_color=grid_line_color, line_width=grid_line_width)
                self.w.preview_image.src = f"data:image/png;base64,{base64.b64encode(png).decode('ascii')}"
                self.set_status(msg)
            self.flush()
        except (ConfigError, ImageReadError, ValueError, RuntimeError) as exc:
            self.add_log(f"Error: {exc}")
            self.set_status("Error")
            self.show_error(str(exc))
            self.flush()
    
    def _run_job(self) -> None:
        """Run image split job (background thread)."""
        try:
            path = (self.w.input_field.value or "").strip()
            if not path:
                raise ValueError("Input image is required")
            msg, cfg = self.load_config_for_ui()
            cfg = replace(cfg, grid=self.build_grid_config())
            out = (self.w.out_dir_field.value or "").strip() or None
            tp = self.w.test_page_field.value.strip() if self.w.test_page_field.value else ""
            tp_val = int(tp) if tp else None
            self.set_status(msg)
            self.flush()

            def on_progress(ev: Any) -> None:
                self.set_progress(ev.done, ev.total)
                self.set_status(f"{ev.phase} {ev.done}/{ev.total}")
                self.add_log(f"[{ev.phase}] {ev.done}/{ev.total} {ev.message}".strip())
                self.flush()

            result = run_job(path, cfg, out_dir=out, test_page=tp_val, on_progress=on_progress, cancel_token=self.state.cancel_token)
            self.add_log(f"Plan written to {result.plan.manifest_path}")
            self.add_log(f"Pages: {result.page_count}")
            self.set_status("Done")
            self.w.progress_bar.color = "green"
            self.flush()
        except (ConfigError, LimitExceededError, ImageReadError, ValueError, RuntimeError) as exc:
            self.add_log(f"Error: {exc}")
            self.set_status("Error")
            self.w.progress_bar.color = "red"
            self.show_error(str(exc))
            self.flush()
        finally:
            self.w.run_btn.disabled = False
            self.w.cancel_btn.disabled = True
            self.flush()
    
    def on_run(self, _: Any) -> None:
        """Handle run button click."""
        self.state.reset_cancel_token()
        self.w.progress_bar.value = 0
        self.w.progress_bar.color = None
        self.w.run_btn.disabled = True
        self.w.cancel_btn.disabled = False
        self.add_log("Starting job...")
        self.flush()
        self.page.run_thread(self._run_job)
    
    def on_cancel(self, _: Any) -> None:
        """Handle cancel button click."""
        self.state.request_cancel()
        self.set_status("Cancel requested")
        self.flush()
    
    def _run_template(self) -> None:
        """Generate template PNG (background thread)."""
        try:
            w, h = self.compute_canvas_size_px()
            dpi = parse_int(self.w.dpi_field.value or "0", "DPI")
            out = (self.w.template_out_field.value or "").strip()
            if not out:
                raise ValueError("Template output path is required")
            if not out.lower().endswith(".png"):
                out = f"{out}.png"
            rpath = generate_template_png(out, w, h, self.build_grid_config(), self.build_template_style(), dpi)
            self.add_log(f"Template written: {rpath}")
            self.set_status("Template written")
            self.flush()
        except (ConfigError, ValueError, RuntimeError) as exc:
            self.add_log(f"Error: {exc}")
            self.set_status("Error")
            self.show_error(str(exc))
            self.flush()
    
    def on_generate_template(self, _: Any) -> None:
        """Handle generate template button click."""
        self.add_log("Generating template...")
        self.set_status("Generating template")
        self.flush()
        self.page.run_thread(self._run_template)
    
    async def _copy_log(self) -> None:
        """Copy log to clipboard (async)."""
        text = (self.w.log_field.value or "").strip()
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
        """Handle copy log button click."""
        self.page.run_task(self._copy_log)
    
    def on_tab_change(self, e: Any) -> None:
        """Handle tab change."""
        self.state.set_tab(int(e.data))
        self.flush()
        # Auto-update preview on tab change
        self.auto_preview_if_enabled(e)
    
    def on_margin_unit_change(self, e: Any) -> None:
        """Handle margin unit change (convert values)."""
        old_unit = self.state.unit_state.margin_unit
        new_unit = self.w.margin_unit_field.value or "px"
        
        # Skip if same unit
        if old_unit == new_unit:
            return
        
        dpi = parse_int(self.w.dpi_field.value or "300", "DPI")
        
        # Convert margin values (using gui_utils)
        for fld in [self.w.margin_top_field, self.w.margin_bottom_field, self.w.margin_left_field, self.w.margin_right_field]:
            if fld.value:
                fld.value = convert_unit_value(fld.value, old_unit, new_unit, dpi)
        
        # Update current unit
        self.state.unit_state.margin_unit = new_unit
        self.update_size_info(e)
        self.auto_preview_if_enabled(e)
    
    def on_custom_size_unit_change(self, e: Any) -> None:
        """Handle page size unit change (convert values)."""
        old_unit = self.state.unit_state.page_size_unit
        new_unit = self.w.custom_size_unit_field.value or "px"
        
        # Skip if same unit
        if old_unit == new_unit:
            return
        
        dpi = parse_int(self.w.dpi_field.value or "300", "DPI")
        size_choice = self.w.page_size_field.value or "A4"
        
        # Get current page size in px
        if size_choice == "Custom":
            # Convert existing values for Custom (using gui_utils)
            for fld in [self.w.custom_width_field, self.w.custom_height_field]:
                if fld.value:
                    fld.value = convert_unit_value(fld.value, old_unit, new_unit, dpi)
        else:
            # For preset sizes (A4, B5, etc.), calculate px values and display
            params = PageSizeParams(
                page_size_name=size_choice,
                orientation=self.w.orientation_field.value or "portrait",
                dpi=dpi,
                custom_width=None,
                custom_height=None,
                custom_unit="px",
            )
            w_px, h_px = compute_page_size_px_impl(params, 0, 0)
            if new_unit == "mm":
                self.w.custom_width_field.value = f"{px_to_mm(w_px, dpi):.2f}"
                self.w.custom_height_field.value = f"{px_to_mm(h_px, dpi):.2f}"
            else:
                self.w.custom_width_field.value = str(w_px)
                self.w.custom_height_field.value = str(h_px)
        
        # Update current unit
        self.state.unit_state.page_size_unit = new_unit
        self.update_size_info(e)
        self.auto_preview_if_enabled(e)
    
    def on_gutter_unit_change(self, e: Any) -> None:
        """Handle gutter unit change (convert values)."""
        old_unit = self.state.unit_state.gutter_unit
        new_unit = self.w.gutter_unit_field.value or "px"
        
        # Skip if same unit
        if old_unit == new_unit:
            return
        
        dpi = parse_int(self.w.dpi_field.value or "300", "DPI")
        
        # Convert gutter value (using gui_utils)
        if self.w.gutter_field.value:
            self.w.gutter_field.value = convert_unit_value(self.w.gutter_field.value, old_unit, new_unit, dpi)
        
        # Update current unit
        self.state.unit_state.gutter_unit = new_unit
        self.update_size_info(e)
        self.auto_preview_if_enabled(e)


__all__ = ["GuiWidgets", "GuiHandlers"]
