from __future__ import annotations

import base64
from datetime import datetime
from dataclasses import replace
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
    compute_page_size_px as template_compute_page_size_px,
    generate_template_png,
    parse_hex_color,
)

TRANSPARENT_PNG_BASE64 = (
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR4nGNgYAAAAAMA"
    "ASsJTYQAAAAASUVORK5CYII="
)


def main() -> None:
    try:
        import flet as ft  # type: ignore
    except ImportError as exc:  # pragma: no cover - import guard
        raise RuntimeError("flet is required for GUI mode") from exc

    def _app(page: ft.Page) -> None:
        page.title = "CSP Name Splitter"
        page.window_width = 1100
        page.window_height = 760
        page.scroll = ft.ScrollMode.AUTO

        input_field = ft.TextField(label="Input image (PNG)", expand=True)
        config_field = ft.TextField(label="Config YAML (optional)", expand=True)
        out_dir_field = ft.TextField(label="Output directory (optional)", expand=True)
        test_page_field = ft.TextField(label="Test page (1-based, optional)")

        page_size_field = ft.Dropdown(
            label="Page size (per page)",
            options=[
                ft.dropdown.Option("A4"),
                ft.dropdown.Option("B4"),
                ft.dropdown.Option("A5"),
                ft.dropdown.Option("B5"),
                ft.dropdown.Option("Custom"),
            ],
            value="A4",
            width=140,
        )
        orientation_field = ft.Dropdown(
            label="Orientation",
            options=[
                ft.dropdown.Option("portrait"),
                ft.dropdown.Option("landscape"),
            ],
            value="portrait",
            width=150,
        )
        dpi_field = ft.TextField(label="DPI", value="300", width=100)
        custom_width_field = ft.TextField(label="Page width px", value="", width=150)
        custom_height_field = ft.TextField(label="Page height px", value="", width=150)
        size_info_text = ft.Text("")
        template_out_field = ft.TextField(label="Template output PNG (canvas)", expand=True)

        rows_field = ft.TextField(label="Rows", value="4", width=120)
        cols_field = ft.TextField(label="Cols", value="4", width=120)
        order_field = ft.Dropdown(
            label="Order",
            options=[
                ft.dropdown.Option("rtl_ttb"),
                ft.dropdown.Option("ltr_ttb"),
            ],
            value="rtl_ttb",
            width=160,
        )
        margin_field = ft.TextField(label="Margin px", value="0", width=140)
        gutter_field = ft.TextField(label="Gutter px", value="0", width=140)

        draw_finish_field = ft.Checkbox(label="Draw finish frame", value=True)
        finish_size_mode_field = ft.Dropdown(
            label="Finish size (per page)",
            options=[
                ft.dropdown.Option("Use per-page size"),
                ft.dropdown.Option("A4"),
                ft.dropdown.Option("B4"),
                ft.dropdown.Option("A5"),
                ft.dropdown.Option("B5"),
                ft.dropdown.Option("Custom mm"),
                ft.dropdown.Option("Custom px"),
            ],
            value="Use per-page size",
            width=170,
        )
        finish_width_field = ft.TextField(label="Finish width", value="", width=150)
        finish_height_field = ft.TextField(label="Finish height", value="", width=150)
        finish_offset_x_field = ft.TextField(label="Finish offset X (mm)", value="0", width=160)
        finish_offset_y_field = ft.TextField(label="Finish offset Y (mm)", value="0", width=160)
        finish_color_field = ft.TextField(label="Finish color (hex)", value="#FFFFFF", width=160)
        finish_alpha_field = ft.TextField(label="Finish alpha (0-255)", value="200", width=160)
        finish_line_width_field = ft.TextField(label="Finish line width px", value="2", width=180)

        draw_basic_field = ft.Checkbox(label="Draw basic frame", value=True)
        basic_size_mode_field = ft.Dropdown(
            label="Basic size (per page)",
            options=[
                ft.dropdown.Option("Use per-page size"),
                ft.dropdown.Option("A4"),
                ft.dropdown.Option("B4"),
                ft.dropdown.Option("A5"),
                ft.dropdown.Option("B5"),
                ft.dropdown.Option("Custom mm"),
                ft.dropdown.Option("Custom px"),
            ],
            value="Use per-page size",
            width=170,
        )
        basic_width_field = ft.TextField(label="Basic width", value="", width=150)
        basic_height_field = ft.TextField(label="Basic height", value="", width=150)
        basic_offset_x_field = ft.TextField(label="Basic offset X (mm)", value="0", width=160)
        basic_offset_y_field = ft.TextField(label="Basic offset Y (mm)", value="0", width=160)
        basic_color_field = ft.TextField(label="Basic color (hex)", value="#00AAFF", width=160)
        basic_alpha_field = ft.TextField(label="Basic alpha (0-255)", value="200", width=160)
        basic_line_width_field = ft.TextField(label="Basic line width px", value="2", width=180)
        grid_color_field = ft.TextField(label="Grid color (hex)", value="#FF5030", width=160)
        grid_alpha_field = ft.TextField(label="Grid alpha (0-255)", value="170", width=160)
        grid_width_field = ft.TextField(label="Grid width px", value="1", width=160)

        log_field = ft.TextField(multiline=True, read_only=True, expand=True, value="")
        progress_bar = ft.ProgressBar(width=420, value=0)
        status_text = ft.Text("Idle")
        image_fit = ft.ImageFit.CONTAIN if hasattr(ft, "ImageFit") else "contain"
        preview_image = ft.Image(
            src=f"data:image/png;base64,{TRANSPARENT_PNG_BASE64}",
            width=520,
            height=520,
            fit=image_fit,
        )
        clipboard = ft.Clipboard() if hasattr(ft, "Clipboard") else None

        cancel_token_holder = {"token": CancelToken()}

        def add_log(message: str) -> None:
            timestamp = datetime.now().strftime("%H:%M:%S")
            current = log_field.value or ""
            log_field.value = f"{current}{timestamp} {message}\n"

        def set_status(message: str) -> None:
            status_text.value = message

        def set_progress(done: int, total: int) -> None:
            if total:
                progress = done / total
                progress_bar.value = max(0.0, min(1.0, progress))
            else:
                progress_bar.value = None

        def flush() -> None:
            page.update()

        def parse_int(value: str, label: str) -> int:
            try:
                return int(value)
            except ValueError as exc:
                raise ValueError(f"{label} must be an integer") from exc

        def parse_float(value: str, label: str) -> float:
            try:
                return float(value)
            except ValueError as exc:
                raise ValueError(f"{label} must be a number") from exc

        def build_grid_config() -> GridConfig:
            rows = parse_int(rows_field.value or "0", "Rows")
            cols = parse_int(cols_field.value or "0", "Cols")
            margin = parse_int(margin_field.value or "0", "Margin")
            gutter = parse_int(gutter_field.value or "0", "Gutter")
            order = order_field.value or "rtl_ttb"
            return GridConfig(rows=rows, cols=cols, order=order, margin_px=margin, gutter_px=gutter)

        last_size = {"w": 0, "h": 0}

        def compute_page_px() -> tuple[int, int]:
            size_choice = page_size_field.value or "A4"
            if size_choice == "Custom":
                if custom_width_field.value and custom_height_field.value:
                    width_px = parse_int(custom_width_field.value or "0", "Width px")
                    height_px = parse_int(custom_height_field.value or "0", "Height px")
                    last_size["w"] = width_px
                    last_size["h"] = height_px
                    return width_px, height_px
                if last_size["w"] > 0 and last_size["h"] > 0:
                    return last_size["w"], last_size["h"]
                dpi = parse_int(dpi_field.value or "0", "DPI")
                orientation = orientation_field.value or "portrait"
                width_px, height_px = template_compute_page_size_px("A4", dpi, orientation)
                last_size["w"] = width_px
                last_size["h"] = height_px
                return width_px, height_px
            dpi = parse_int(dpi_field.value or "0", "DPI")
            orientation = orientation_field.value or "portrait"
            width_px, height_px = template_compute_page_size_px(size_choice, dpi, orientation)
            last_size["w"] = width_px
            last_size["h"] = height_px
            return width_px, height_px

        def compute_canvas_size_px() -> tuple[int, int]:
            page_w, page_h = compute_page_px()
            grid_cfg = build_grid_config()
            width_px = (
                2 * grid_cfg.margin_px + grid_cfg.cols * page_w + (grid_cfg.cols - 1) * grid_cfg.gutter_px
            )
            height_px = (
                2 * grid_cfg.margin_px + grid_cfg.rows * page_h + (grid_cfg.rows - 1) * grid_cfg.gutter_px
            )
            return width_px, height_px

        def build_template_style() -> TemplateStyle:
            grid_alpha = parse_int(grid_alpha_field.value or "0", "Grid alpha")
            finish_alpha = parse_int(finish_alpha_field.value or "0", "Finish alpha")
            basic_alpha = parse_int(basic_alpha_field.value or "0", "Basic alpha")
            grid_color = parse_hex_color(grid_color_field.value or "#FF5030", grid_alpha)
            finish_color = parse_hex_color(finish_color_field.value or "#FFFFFF", finish_alpha)
            basic_color = parse_hex_color(basic_color_field.value or "#00AAFF", basic_alpha)
            grid_width = parse_int(grid_width_field.value or "0", "Grid width px")
            finish_line_width = parse_int(finish_line_width_field.value or "0", "Finish line width px")
            basic_line_width = parse_int(basic_line_width_field.value or "0", "Basic line width px")
            finish_width_mm, finish_height_mm = compute_frame_size_mm(
                finish_size_mode_field.value or "Use per-page size",
                finish_width_field.value,
                finish_height_field.value,
            )
            basic_width_mm, basic_height_mm = compute_frame_size_mm(
                basic_size_mode_field.value or "Use per-page size",
                basic_width_field.value,
                basic_height_field.value,
            )
            finish_offset_x_mm = parse_float(finish_offset_x_field.value or "0", "Finish offset X mm")
            finish_offset_y_mm = parse_float(finish_offset_y_field.value or "0", "Finish offset Y mm")
            basic_offset_x_mm = parse_float(basic_offset_x_field.value or "0", "Basic offset X mm")
            basic_offset_y_mm = parse_float(basic_offset_y_field.value or "0", "Basic offset Y mm")
            draw_finish = bool(draw_finish_field.value)
            draw_basic = bool(draw_basic_field.value)
            return TemplateStyle(
                grid_color=grid_color,
                grid_width=grid_width,
                finish_color=finish_color,
                finish_width=finish_line_width,
                finish_width_mm=finish_width_mm,
                finish_height_mm=finish_height_mm,
                finish_offset_x_mm=finish_offset_x_mm,
                finish_offset_y_mm=finish_offset_y_mm,
                draw_finish=draw_finish,
                basic_color=basic_color,
                basic_width=basic_line_width,
                basic_width_mm=basic_width_mm,
                basic_height_mm=basic_height_mm,
                basic_offset_x_mm=basic_offset_x_mm,
                basic_offset_y_mm=basic_offset_y_mm,
                draw_basic=draw_basic,
            )

        def compute_page_size_mm() -> tuple[float, float]:
            dpi = parse_int(dpi_field.value or "0", "DPI")
            width_px, height_px = compute_page_px()
            if dpi <= 0:
                raise ValueError("DPI must be positive")
            width_mm = width_px * 25.4 / dpi
            height_mm = height_px * 25.4 / dpi
            return width_mm, height_mm

        def compute_frame_size_mm(mode: str, width_value: str, height_value: str) -> tuple[float, float]:
            mode = mode or "Use per-page size"
            dpi = parse_int(dpi_field.value or "0", "DPI")
            if mode == "Use per-page size":
                return compute_page_size_mm()
            if mode in {"A4", "A5", "B4", "B5"}:
                orientation = orientation_field.value or "portrait"
                width_px, height_px = template_compute_page_size_px(mode, dpi, orientation)
                return (width_px * 25.4 / dpi, height_px * 25.4 / dpi)
            if mode == "Custom px":
                width_px = parse_int(width_value or "0", "Width px")
                height_px = parse_int(height_value or "0", "Height px")
                return (width_px * 25.4 / dpi, height_px * 25.4 / dpi)
            width_mm = parse_float(width_value or "0", "Width mm")
            height_mm = parse_float(height_value or "0", "Height mm")
            return (width_mm, height_mm)

        def update_size_info(_: ft.ControlEvent | None = None) -> None:
            try:
                grid_cfg = build_grid_config()
                page_w_px, page_h_px = compute_page_px()
                canvas_w_px, canvas_h_px = compute_canvas_size_px()
                width_mm, height_mm = compute_page_size_mm()
                size_info_text.value = (
                    f"Per-page: {page_w_px} x {page_h_px} px / {width_mm:.2f} x {height_mm:.2f} mm"
                    f" | Canvas: {canvas_w_px} x {canvas_h_px} px"
                    f" | Grid: {grid_cfg.rows} x {grid_cfg.cols}"
                )
                size_info_text.color = None
                is_custom = (page_size_field.value or "") == "Custom"
                custom_width_field.disabled = not is_custom
                custom_height_field.disabled = not is_custom
                if is_custom and (not custom_width_field.value or not custom_height_field.value):
                    custom_width_field.value = str(page_w_px)
                    custom_height_field.value = str(page_h_px)
                if not is_custom:
                    custom_width_field.value = str(page_w_px)
                    custom_height_field.value = str(page_h_px)
                finish_mode = finish_size_mode_field.value or "Use per-page size"
                if finish_mode in {"Use per-page size", "A4", "A5", "B4", "B5"}:
                    f_w_mm, f_h_mm = compute_frame_size_mm(finish_mode, "", "")
                    finish_width_field.value = f"{f_w_mm:.2f}"
                    finish_height_field.value = f"{f_h_mm:.2f}"
                if finish_mode == "Custom mm":
                    if not finish_width_field.value or not finish_height_field.value:
                        finish_width_field.value = f"{width_mm:.2f}"
                        finish_height_field.value = f"{height_mm:.2f}"
                if finish_mode == "Custom px":
                    if not finish_width_field.value or not finish_height_field.value:
                        finish_width_field.value = str(page_w_px)
                        finish_height_field.value = str(page_h_px)
                basic_mode = basic_size_mode_field.value or "Use per-page size"
                if basic_mode in {"Use per-page size", "A4", "A5", "B4", "B5"}:
                    b_w_mm, b_h_mm = compute_frame_size_mm(basic_mode, "", "")
                    basic_width_field.value = f"{b_w_mm:.2f}"
                    basic_height_field.value = f"{b_h_mm:.2f}"
                if basic_mode == "Custom mm":
                    if not basic_width_field.value or not basic_height_field.value:
                        basic_width_field.value = f"{max(0.0, width_mm - 20.0):.2f}"
                        basic_height_field.value = f"{max(0.0, height_mm - 20.0):.2f}"
                if basic_mode == "Custom px":
                    if not basic_width_field.value or not basic_height_field.value:
                        basic_width_field.value = str(max(0, page_w_px - 200))
                        basic_height_field.value = str(max(0, page_h_px - 200))
                finish_custom = finish_mode.startswith("Custom")
                finish_width_field.disabled = not finish_custom
                finish_height_field.disabled = not finish_custom
                basic_custom = basic_mode.startswith("Custom")
                basic_width_field.disabled = not basic_custom
                basic_height_field.disabled = not basic_custom
            except Exception as exc:  # noqa: BLE001
                size_info_text.value = f"Size error: {exc}"
                size_info_text.color = "red"
            flush()

        if hasattr(page_size_field, "on_select"):
            page_size_field.on_select = update_size_info
        if hasattr(page_size_field, "on_text_change"):
            page_size_field.on_text_change = update_size_info
        if hasattr(orientation_field, "on_select"):
            orientation_field.on_select = update_size_info
        if hasattr(orientation_field, "on_text_change"):
            orientation_field.on_text_change = update_size_info
        if hasattr(finish_size_mode_field, "on_select"):
            finish_size_mode_field.on_select = update_size_info
        if hasattr(finish_size_mode_field, "on_text_change"):
            finish_size_mode_field.on_text_change = update_size_info
        if hasattr(basic_size_mode_field, "on_select"):
            basic_size_mode_field.on_select = update_size_info
        if hasattr(basic_size_mode_field, "on_text_change"):
            basic_size_mode_field.on_text_change = update_size_info
        dpi_field.on_change = update_size_info
        dpi_field.on_blur = update_size_info
        rows_field.on_change = update_size_info
        rows_field.on_blur = update_size_info
        cols_field.on_change = update_size_info
        cols_field.on_blur = update_size_info
        margin_field.on_change = update_size_info
        margin_field.on_blur = update_size_info
        gutter_field.on_change = update_size_info
        gutter_field.on_blur = update_size_info
        custom_width_field.on_change = update_size_info
        custom_width_field.on_blur = update_size_info
        custom_height_field.on_change = update_size_info
        custom_height_field.on_blur = update_size_info
        finish_width_field.on_change = update_size_info
        finish_width_field.on_blur = update_size_info
        finish_height_field.on_change = update_size_info
        finish_height_field.on_blur = update_size_info
        basic_width_field.on_change = update_size_info
        basic_width_field.on_blur = update_size_info
        basic_height_field.on_change = update_size_info
        basic_height_field.on_blur = update_size_info

        input_picker = ft.FilePicker()
        config_picker = ft.FilePicker()
        out_dir_picker = ft.FilePicker()
        template_save_picker = ft.FilePicker()



        async def pick_input_file() -> None:
            try:
                files = await input_picker.pick_files(
                    allow_multiple=False,
                    file_type=ft.FilePickerFileType.CUSTOM,
                    allowed_extensions=["png"],
                )
            except RuntimeError as exc:
                if "Session closed" not in str(exc):
                    add_log(f"Error: {exc}")
                    set_status("Error")
                    flush()
                return
            if files:
                input_field.value = files[0].path
                flush()

        async def pick_config_file() -> None:
            try:
                files = await config_picker.pick_files(
                    allow_multiple=False,
                    file_type=ft.FilePickerFileType.CUSTOM,
                    allowed_extensions=["yaml", "yml"],
                )
            except RuntimeError as exc:
                if "Session closed" not in str(exc):
                    add_log(f"Error: {exc}")
                    set_status("Error")
                    flush()
                return
            if files:
                config_field.value = files[0].path
                flush()

        async def pick_output_dir() -> None:
            try:
                path = await out_dir_picker.get_directory_path()
            except RuntimeError as exc:
                if "Session closed" not in str(exc):
                    add_log(f"Error: {exc}")
                    set_status("Error")
                    flush()
                return
            if path:
                out_dir_field.value = path
                flush()

        async def pick_template_output() -> None:
            try:
                path = await template_save_picker.save_file(
                    file_name="template.png",
                    file_type=ft.FilePickerFileType.CUSTOM,
                    allowed_extensions=["png"],
                )
            except RuntimeError as exc:
                if "Session closed" not in str(exc):
                    add_log(f"Error: {exc}")
                    set_status("Error")
                    flush()
                return
            if path:
                template_out_field.value = path
                flush()

        def load_config_for_ui() -> tuple[str, Any]:
            if config_field.value:
                cfg = load_config(config_field.value)
                return "Loaded config", cfg
            cfg = load_default_config()
            return "Loaded default config", cfg

        def on_preview(_: ft.ControlEvent) -> None:
            try:
                grid_cfg = build_grid_config()
                preview_source = preview_mode_field.value or "Image"
                if preview_source == "Template":
                    width_px, height_px = compute_canvas_size_px()
                    style = build_template_style()
                    dpi = parse_int(dpi_field.value or "0", "DPI")
                    preview_png = build_template_preview_png(
                        width_px,
                        height_px,
                        grid_cfg,
                        style,
                        dpi,
                    )
                    encoded = base64.b64encode(preview_png).decode("ascii")
                    preview_image.src = f"data:image/png;base64,{encoded}"
                    set_status("Template preview")
                else:
                    input_path = (input_field.value or "").strip()
                    if not input_path:
                        raise ValueError("Input image is required for preview")
                    cfg_status, cfg = load_config_for_ui()
                    cfg = replace(cfg, grid=grid_cfg)
                    preview_png = build_preview_png(input_path, cfg.grid)
                    encoded = base64.b64encode(preview_png).decode("ascii")
                    set_status(cfg_status)
                    preview_image.src = f"data:image/png;base64,{encoded}"
                flush()
            except (ConfigError, ImageReadError, ValueError, RuntimeError) as exc:
                add_log(f"Error: {exc}")
                set_status("Error")
                flush()

        def _run_job() -> None:
            try:
                input_path = (input_field.value or "").strip()
                if not input_path:
                    raise ValueError("Input image is required")
                status, cfg = load_config_for_ui()
                grid_cfg = build_grid_config()
                cfg = replace(cfg, grid=grid_cfg)
                out_dir = (out_dir_field.value or "").strip() or None
                test_page = test_page_field.value.strip() if test_page_field.value else ""
                test_page_value = int(test_page) if test_page else None
                set_status(status)
                flush()

                def on_progress(event: Any) -> None:
                    set_progress(event.done, event.total)
                    set_status(f"{event.phase} {event.done}/{event.total}")
                    add_log(f"[{event.phase}] {event.done}/{event.total} {event.message}".strip())
                    flush()

                result = run_job(
                    input_path,
                    cfg,
                    out_dir=out_dir,
                    test_page=test_page_value,
                    on_progress=on_progress,
                    cancel_token=cancel_token_holder["token"],
                )
                add_log(f"Plan written to {result.plan.manifest_path}")
                add_log(f"Pages: {result.page_count}")
                set_status("Done")
                flush()
            except (ConfigError, LimitExceededError, ImageReadError, ValueError, RuntimeError) as exc:
                add_log(f"Error: {exc}")
                set_status("Error")
                flush()

        def on_run(_: ft.ControlEvent) -> None:
            cancel_token_holder["token"] = CancelToken()
            progress_bar.value = 0
            add_log("Starting job...")
            flush()
            page.run_thread(_run_job)

        def on_cancel(_: ft.ControlEvent) -> None:
            cancel_token_holder["token"].cancel()
            set_status("Cancel requested")
            flush()

        async def copy_log() -> None:
            text = (log_field.value or "").strip()
            if not text:
                add_log("Log is empty")
                set_status("Log empty")
                flush()
                return
            if clipboard is None:
                add_log("Clipboard service not available. Select text to copy.")
                set_status("Clipboard unavailable")
                flush()
                return
            try:
                await clipboard.set(text)
                add_log("Log copied to clipboard")
                set_status("Log copied")
            except Exception as exc:  # noqa: BLE001
                add_log(f"Error: {exc}")
                set_status("Error")
            flush()

        def on_copy_log(_: ft.ControlEvent) -> None:
            page.run_task(copy_log)

        def _run_template() -> None:
            try:
                width_px, height_px = compute_canvas_size_px()
                grid_cfg = build_grid_config()
                style = build_template_style()
                dpi = parse_int(dpi_field.value or "0", "DPI")
                output_path = (template_out_field.value or "").strip()
                if not output_path:
                    raise ValueError("Template output path is required")
                if not output_path.lower().endswith(".png"):
                    output_path = f"{output_path}.png"
                result_path = generate_template_png(
                    output_path,
                    width_px,
                    height_px,
                    grid_cfg,
                    style,
                    dpi,
                )
                add_log(f"Template written: {result_path}")
                set_status("Template written")
                flush()
            except (ConfigError, ValueError, RuntimeError) as exc:
                add_log(f"Error: {exc}")
                set_status("Error")
                flush()

        def on_generate_template(_: ft.ControlEvent) -> None:
            add_log("Generating template...")
            set_status("Generating template")
            flush()
            page.run_thread(_run_template)

        run_button = ft.ElevatedButton("Run", on_click=on_run)
        template_button = ft.ElevatedButton("Generate Template", on_click=on_generate_template)
        cancel_button = ft.OutlinedButton("Cancel", on_click=on_cancel)
        preview_button = ft.OutlinedButton("Preview", on_click=on_preview)
        copy_log_button = ft.OutlinedButton("Copy log", on_click=on_copy_log)
        preview_mode_field = ft.Dropdown(
            label="Preview source",
            options=[
                ft.dropdown.Option("Image"),
                ft.dropdown.Option("Template"),
            ],
            value="Image",
            width=170,
        )

        outline_color = ft.Colors.OUTLINE if hasattr(ft, "Colors") else ft.colors.OUTLINE
        page.add(
            ft.Column(
                [
                    ft.Row(
                        [
                            input_field,
                            ft.IconButton(
                                icon=ft.Icons.FOLDER_OPEN,
                                tooltip="Select image",
                                on_click=lambda _: page.run_task(pick_input_file),
                            ),
                        ],
                        alignment=ft.MainAxisAlignment.START,
                    ),
                    ft.Row(
                        [
                            config_field,
                            ft.IconButton(
                                icon=ft.Icons.SETTINGS,
                                tooltip="Select config",
                                on_click=lambda _: page.run_task(pick_config_file),
                            ),
                        ]
                    ),
                    ft.Row(
                        [
                            out_dir_field,
                            ft.IconButton(
                                icon=ft.Icons.FOLDER,
                                tooltip="Select output directory",
                                on_click=lambda _: page.run_task(pick_output_dir),
                            ),
                            test_page_field,
                        ]
                    ),
                    ft.Row(
                        [
                            template_out_field,
                            ft.IconButton(
                                icon=ft.Icons.SAVE,
                                tooltip="Save template PNG",
                                on_click=lambda _: page.run_task(pick_template_output),
                            ),
                        ]
                    ),
                    ft.Row(
                        [
                            page_size_field,
                            orientation_field,
                            dpi_field,
                            custom_width_field,
                            custom_height_field,
                        ],
                        alignment=ft.MainAxisAlignment.START,
                    ),
                    ft.Row([size_info_text]),
                    ft.Text("Finish frame settings"),
                    ft.Row(
                        [
                            draw_finish_field,
                            finish_size_mode_field,
                            finish_width_field,
                            finish_height_field,
                            finish_offset_x_field,
                            finish_offset_y_field,
                        ],
                        alignment=ft.MainAxisAlignment.START,
                    ),
                    ft.Row(
                        [
                            finish_color_field,
                            finish_alpha_field,
                            finish_line_width_field,
                        ],
                        alignment=ft.MainAxisAlignment.START,
                    ),
                    ft.Text("Basic frame settings"),
                    ft.Row(
                        [
                            draw_basic_field,
                            basic_size_mode_field,
                            basic_width_field,
                            basic_height_field,
                            basic_offset_x_field,
                            basic_offset_y_field,
                        ],
                        alignment=ft.MainAxisAlignment.START,
                    ),
                    ft.Row(
                        [
                            basic_color_field,
                            basic_alpha_field,
                            basic_line_width_field,
                        ],
                        alignment=ft.MainAxisAlignment.START,
                    ),
                    ft.Text("Grid settings"),
                    ft.Row(
                        [
                            grid_color_field,
                            grid_alpha_field,
                            grid_width_field,
                        ],
                        alignment=ft.MainAxisAlignment.START,
                    ),
                    ft.Row(
                        [rows_field, cols_field, order_field, margin_field, gutter_field],
                        alignment=ft.MainAxisAlignment.START,
                    ),
                    ft.Row(
                        [
                            run_button,
                            template_button,
                            preview_mode_field,
                            preview_button,
                            cancel_button,
                            copy_log_button,
                            progress_bar,
                            status_text,
                        ]
                    ),
                    ft.Divider(),
                    ft.Row(
                        [
                            ft.Container(
                                content=preview_image,
                                padding=10,
                                expand=True,
                                border=ft.border.all(1, outline_color),
                            ),
                            ft.Container(
                                content=log_field,
                                padding=10,
                                expand=True,
                                border=ft.border.all(1, outline_color),
                            ),
                        ],
                        expand=True,
                    ),
                ],
                expand=True,
            )
        )

        update_size_info()

    ft.app(target=_app)


__all__ = ["main"]
