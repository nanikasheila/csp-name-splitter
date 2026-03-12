"""JSON-RPC bridge for Tauri sidecar communication.

Why: Tauri cannot call Python directly. A JSON-RPC bridge over
     stdin/stdout lets the Rust backend invoke core functions
     without embedding a Python interpreter.
How: Reads newline-delimited JSON-RPC 2.0 requests from stdin,
     dispatches to core API handlers, and writes JSON-RPC responses
     to stdout. Progress events for long-running jobs are sent as
     JSON-RPC notifications (no id).
"""

from __future__ import annotations

import base64
import json
import sys
from dataclasses import asdict
from pathlib import Path
from typing import Any

from .core import (
    CancelToken,
    Config,
    ConfigError,
    ImageReadError,
    LimitExceededError,
    load_config,
    load_default_config,
    read_image,
    run_job,
    validate_config,
)
from .core.config import GridConfig, OutputConfig
from .core.preview import build_preview_png
from .core.template import (
    TemplateStyle,
    build_template_preview_png,
    compute_page_size_px,
    generate_template_png,
    parse_hex_color,
)
from .app.gui_utils import FrameSizeParams, compute_frame_size_mm

# -- Error codes for JSON-RPC responses --
ERROR_PARSE = -32700
ERROR_INVALID_REQUEST = -32600
ERROR_METHOD_NOT_FOUND = -32601
ERROR_INTERNAL = -32603
ERROR_CONFIG = -32001
ERROR_IMAGE_READ = -32002
ERROR_LIMIT_EXCEEDED = -32003
ERROR_CANCELLED = -32004

# -- Global cancel token for the current job --
_cancel_token: CancelToken | None = None


# ----------------------------------------------------------------
# JSON-RPC helpers
# ----------------------------------------------------------------

def _ok_response(request_id: int | str | None, result: Any) -> dict[str, Any]:
    """Build a JSON-RPC 2.0 success response.

    Why: Every RPC reply must conform to the JSON-RPC 2.0 spec.
    How: Wraps the result value with jsonrpc/id fields.
    """
    return {"jsonrpc": "2.0", "id": request_id, "result": result}


def _error_response(
    request_id: int | str | None, code: int, message: str, data: Any = None
) -> dict[str, Any]:
    """Build a JSON-RPC 2.0 error response.

    Why: Errors must be structured per JSON-RPC 2.0 spec so the Rust
         host can parse and relay them to the frontend.
    How: Standard error object with code, message, and optional data.
    """
    error: dict[str, Any] = {"code": code, "message": message}
    if data is not None:
        error["data"] = data
    return {"jsonrpc": "2.0", "id": request_id, "error": error}


def _write(obj: dict[str, Any]) -> None:
    """Write a JSON object as a single line to stdout and flush.

    Why: The Rust host reads stdout line-by-line. Each message must
         be a complete JSON object terminated by a newline.
    How: json.dumps with ensure_ascii=False for Unicode paths,
         followed by flush to prevent buffering delays.
    """
    line = json.dumps(obj, ensure_ascii=False)
    sys.stdout.write(line + "\n")
    sys.stdout.flush()


# ----------------------------------------------------------------
# RPC method handlers
# ----------------------------------------------------------------

def _handle_load_config(params: dict[str, Any]) -> dict[str, Any]:
    """Load a YAML/JSON config file and return it as a dict.

    Why: The frontend needs config values to populate form fields.
    How: Delegates to core.load_config, converts frozen dataclass to dict.
    """
    path = params.get("path", "")
    cfg = load_config(path)
    return asdict(cfg)


def _handle_load_default_config(_params: dict[str, Any]) -> dict[str, Any]:
    """Return the built-in default configuration.

    Why: New sessions start with sensible defaults.
    How: Delegates to core.load_default_config.
    """
    cfg = load_default_config()
    return asdict(cfg)


def _handle_validate_config(params: dict[str, Any]) -> dict[str, Any]:
    """Validate a config dict and return any errors.

    Why: The frontend needs instant validation feedback.
    How: Reconstruct Config from dict, call validate_config which raises
         ConfigError on invalid values. Catch and return errors as a list.
    """
    cfg = _dict_to_config(params.get("config", {}))
    try:
        validate_config(cfg)
    except ConfigError as exc:
        return {"valid": False, "errors": [str(exc)]}
    return {"valid": True, "errors": []}


def _handle_read_image(params: dict[str, Any]) -> dict[str, Any]:
    """Read image dimensions without loading full pixel data.

    Why: The frontend needs image size to compute grid layout.
    How: Delegates to core.read_image which opens the header only.
    """
    path = params.get("path", "")
    info = read_image(path)
    return {"width": info.width, "height": info.height}


def _handle_build_preview(params: dict[str, Any]) -> dict[str, Any]:
    """Build a JPEG preview image with optional grid overlay.

    Why: Users need visual feedback when adjusting grid settings.
         Template tab needs the raw image without grid lines.
    How: Calls core.preview.build_preview_png, returns base64-encoded
         JPEG bytes. When show_grid is False, grid lines and page
         numbers are suppressed.
    """
    image_path = params.get("image_path", "")
    grid_dict = params.get("grid_config", {})
    max_dim = params.get("max_dim", 800)
    show_grid = params.get("show_grid", True)

    grid = _dict_to_grid_config(grid_dict)
    jpeg_bytes = build_preview_png(
        image_path,
        grid,
        max_dim=max_dim,
        line_width=1 if show_grid else 0,
        show_page_numbers=show_grid,
    )
    b64 = base64.b64encode(jpeg_bytes).decode("ascii")
    return {"image_base64": b64, "width": 0, "height": 0}


def _resolve_frame_sizes(
    style_dict: dict[str, Any], grid: GridConfig, dpi: int,
) -> dict[str, Any]:
    """Resolve size_mode fields to width_mm / height_mm values.

    Why: Frontend sends size_mode (e.g. "A4", "Custom mm") plus raw
         width/height values. The bridge must compute mm values that
         TemplateStyle expects.
    How: For each frame prefix (finish, basic), if a *_size_mode key
         exists, delegates to compute_frame_size_mm and injects
         *_width_mm / *_height_mm into the returned dict.
    """
    result = dict(style_dict)
    pw, ph = compute_page_size_px(grid.page_size_name, dpi, grid.orientation)

    for prefix in ("finish", "basic"):
        mode = str(result.get(f"{prefix}_size_mode", ""))
        if not mode:
            continue
        params = FrameSizeParams(
            mode=mode,
            dpi=dpi,
            orientation=grid.orientation,
            width_value=str(result.get(f"{prefix}_width", "")),
            height_value=str(result.get(f"{prefix}_height", "")),
            page_width_px=pw,
            page_height_px=ph,
        )
        w_mm, h_mm = compute_frame_size_mm(params)
        result[f"{prefix}_width_mm"] = w_mm
        result[f"{prefix}_height_mm"] = h_mm

    return result


def _dict_to_template_style(data: dict[str, Any]) -> TemplateStyle:
    """Reconstruct a TemplateStyle from a plain dict.

    Why: JSON-RPC params arrive as dicts; core expects dataclass.
    How: Extracts fields with defaults, converts hex strings to RGBA tuples.
    """
    return TemplateStyle(
        grid_color=parse_hex_color(
            str(data.get("grid_color", "#FF5028")),
            int(data.get("grid_alpha", 170)),
        ),
        grid_width=int(data.get("grid_width", 1)),
        finish_color=parse_hex_color(
            str(data.get("finish_color", "#FFFFFF")),
            int(data.get("finish_alpha", 200)),
        ),
        finish_width=int(data.get("finish_line_width", 2)),
        finish_width_mm=float(data.get("finish_width_mm", 0)),
        finish_height_mm=float(data.get("finish_height_mm", 0)),
        finish_offset_x_mm=float(data.get("finish_offset_x_mm", 0)),
        finish_offset_y_mm=float(data.get("finish_offset_y_mm", 0)),
        draw_finish=bool(data.get("draw_finish", True)),
        basic_color=parse_hex_color(
            str(data.get("basic_color", "#00AAFF")),
            int(data.get("basic_alpha", 200)),
        ),
        basic_width=int(data.get("basic_line_width", 2)),
        basic_width_mm=float(data.get("basic_width_mm", 0)),
        basic_height_mm=float(data.get("basic_height_mm", 0)),
        basic_offset_x_mm=float(data.get("basic_offset_x_mm", 0)),
        basic_offset_y_mm=float(data.get("basic_offset_y_mm", 0)),
        draw_basic=bool(data.get("draw_basic", True)),
    )


def _handle_build_template_preview(params: dict[str, Any]) -> dict[str, Any]:
    """Build a PNG template preview with grid, finish/basic frames, and page numbers.

    Why: Template tab shows a synthetic preview (no source image) with
         grid lines, finish/basic frame overlays, and page numbers.
    How: Computes canvas size from grid config and page size, then calls
         build_template_preview_png. Returns base64-encoded PNG.
    """
    grid_dict = params.get("grid_config", {})
    style_dict = params.get("style", {})
    max_dim = int(params.get("max_dim", 800))

    grid = _dict_to_grid_config(grid_dict)
    dpi = grid.dpi

    # Why: Resolve size_mode before building TemplateStyle
    resolved = _resolve_frame_sizes(style_dict, grid, dpi)
    style = _dict_to_template_style(resolved)

    # Why: Canvas size is grid cells * page size + margins + gutters
    pw, ph = compute_page_size_px(grid.page_size_name, dpi, grid.orientation)
    canvas_w = (
        grid.margin_left_px
        + grid.margin_right_px
        + grid.cols * pw
        + max(0, grid.cols - 1) * grid.gutter_px
    )
    canvas_h = (
        grid.margin_top_px
        + grid.margin_bottom_px
        + grid.rows * ph
        + max(0, grid.rows - 1) * grid.gutter_px
    )

    png_bytes = build_template_preview_png(
        canvas_w, canvas_h, grid, style, dpi, max_dim=max_dim,
    )
    b64 = base64.b64encode(png_bytes).decode("ascii")
    return {"image_base64": b64, "width": canvas_w, "height": canvas_h}


def _handle_generate_template(params: dict[str, Any]) -> dict[str, Any]:
    """Generate a template PNG file to disk.

    Why: Users save templates as PNG files for use in image editors.
    How: Computes canvas size, builds TemplateStyle, and calls
         generate_template_png to write the file.
    """
    grid_dict = params.get("grid_config", {})
    style_dict = params.get("style", {})
    output_path = str(params.get("output_path", ""))

    if not output_path:
        raise ValueError("Template output path is required")
    if not output_path.lower().endswith(".png"):
        output_path = f"{output_path}.png"

    grid = _dict_to_grid_config(grid_dict)
    dpi = grid.dpi

    # Why: Resolve size_mode before building TemplateStyle
    resolved = _resolve_frame_sizes(style_dict, grid, dpi)
    style = _dict_to_template_style(resolved)

    pw, ph = compute_page_size_px(grid.page_size_name, dpi, grid.orientation)
    canvas_w = (
        grid.margin_left_px
        + grid.margin_right_px
        + grid.cols * pw
        + max(0, grid.cols - 1) * grid.gutter_px
    )
    canvas_h = (
        grid.margin_top_px
        + grid.margin_bottom_px
        + grid.rows * ph
        + max(0, grid.rows - 1) * grid.gutter_px
    )

    result_path = generate_template_png(
        output_path, canvas_w, canvas_h, grid, style, dpi,
    )
    return {"path": str(result_path)}


def _handle_run_job(
    params: dict[str, Any], request_id: int | str | None
) -> dict[str, Any]:
    """Execute the image-split job with streaming progress.

    Why: The main processing pipeline. Must stream progress events
         so the frontend can show a live progress bar.
    How: Sets up a CancelToken and progress callback that writes
         JSON-RPC notifications to stdout. The final result is
         returned as the normal RPC response.
    """
    global _cancel_token  # noqa: PLW0603
    _cancel_token = CancelToken()

    image_path = params.get("image_path", "")
    config_dict = params.get("config", {})
    out_dir = params.get("out_dir", "")
    test_page = params.get("test_page")

    cfg = _dict_to_config(config_dict)

    def on_progress(event: Any) -> None:
        """Emit a progress notification to stdout.

        Why: Rust reads stdout and re-emits as Tauri events.
        How: JSON-RPC notification (no id field).
        """
        _write({
            "jsonrpc": "2.0",
            "method": "progress",
            "params": asdict(event),
        })

    result = run_job(
        input_image=image_path,
        cfg=cfg,
        out_dir=out_dir if out_dir else None,
        test_page=test_page,
        on_progress=on_progress,
        cancel_token=_cancel_token,
    )

    _cancel_token = None

    return {
        "out_dir": str(result.out_dir),
        "page_count": result.page_count,
        "pdf_path": str(result.pdf_path) if result.pdf_path else None,
        "elapsed_seconds": result.elapsed_seconds,
    }


def _handle_cancel_job(_params: dict[str, Any]) -> dict[str, Any]:
    """Cancel the currently running job.

    Why: Users need to be able to abort long-running jobs.
    How: Sets the cancel flag on the shared CancelToken.
    """
    if _cancel_token is not None:
        _cancel_token.cancel()
    return {"ok": True}


def _handle_get_page_sizes(_params: dict[str, Any]) -> dict[str, Any]:
    """Return the list of predefined page sizes.

    Why: The frontend needs this for the page size dropdown.
    How: Hardcoded list matching the Config-supported page sizes.
    """
    return {
        "sizes": [
            {"name": "A4", "width_mm": 210, "height_mm": 297},
            {"name": "B4", "width_mm": 257, "height_mm": 364},
            {"name": "A5", "width_mm": 148, "height_mm": 210},
            {"name": "B5", "width_mm": 182, "height_mm": 257},
            {"name": "Custom", "width_mm": 0, "height_mm": 0},
        ]
    }


# ----------------------------------------------------------------
# Config reconstruction helpers
# ----------------------------------------------------------------

def _dict_to_grid_config(data: dict[str, Any]) -> GridConfig:
    """Reconstruct a GridConfig from a plain dict.

    Why: JSON-RPC params arrive as dicts; core expects dataclasses.
    How: Extracts known fields with defaults from GridConfig.__init__.
    """
    return GridConfig(
        rows=int(data.get("rows", 4)),
        cols=int(data.get("cols", 4)),
        order=str(data.get("order", "rtl_ttb")),
        margin_px=int(data.get("margin_px", 0)),
        margin_top_px=int(data.get("margin_top_px", 0)),
        margin_bottom_px=int(data.get("margin_bottom_px", 0)),
        margin_left_px=int(data.get("margin_left_px", 0)),
        margin_right_px=int(data.get("margin_right_px", 0)),
        gutter_px=int(data.get("gutter_px", 0)),
        gutter_unit=str(data.get("gutter_unit", "px")),
        margin_unit=str(data.get("margin_unit", "px")),
        dpi=int(data.get("dpi", 300)),
        page_size_name=str(data.get("page_size_name", "A4")),
        orientation=str(data.get("orientation", "portrait")),
        page_width_px=int(data.get("page_width_px", 0)),
        page_height_px=int(data.get("page_height_px", 0)),
        page_size_unit=str(data.get("page_size_unit", "px")),
    )


def _dict_to_config(data: dict[str, Any]) -> Config:
    """Reconstruct a full Config from a nested dict.

    Why: JSON-RPC params arrive as nested dicts from the frontend.
    How: Builds each sub-config from its corresponding dict section.
    """
    from .core.config import InputConfig, LimitsConfig, MergeConfig

    grid_data = data.get("grid", {})
    output_data = data.get("output", {})
    input_data = data.get("input", {})
    limits_data = data.get("limits", {})

    return Config(
        version=int(data.get("version", 1)),
        input=InputConfig(image_path=str(input_data.get("image_path", ""))),
        grid=_dict_to_grid_config(grid_data),
        merge=MergeConfig(),
        output=OutputConfig(
            out_dir=str(output_data.get("out_dir", "")),
            page_basename=str(output_data.get("page_basename", "page_{page:03d}")),
            raster_ext=str(output_data.get("raster_ext", "png")),
            container=str(output_data.get("container", "png")),
            layout=str(output_data.get("layout", "layers")),
            output_dpi=int(output_data.get("output_dpi", 0)),
            page_number_start=int(output_data.get("page_number_start", 1)),
            skip_pages=tuple(output_data.get("skip_pages", ())),
            odd_even=str(output_data.get("odd_even", "all")),
        ),
        limits=LimitsConfig(
            max_dim_px=int(limits_data.get("max_dim_px", 30000)),
            on_exceed=str(limits_data.get("on_exceed", "error")),
        ),
    )


# ----------------------------------------------------------------
# Method dispatch table
# ----------------------------------------------------------------

_METHODS: dict[str, Any] = {
    "load_config": _handle_load_config,
    "load_default_config": _handle_load_default_config,
    "validate_config": _handle_validate_config,
    "read_image": _handle_read_image,
    "build_preview": _handle_build_preview,
    "build_template_preview": _handle_build_template_preview,
    "generate_template": _handle_generate_template,
    "cancel_job": _handle_cancel_job,
    "get_page_sizes": _handle_get_page_sizes,
}

# run_job has a special signature (needs request_id for streaming)
_STREAMING_METHODS = {"run_job"}


# ----------------------------------------------------------------
# Main loop
# ----------------------------------------------------------------

def _dispatch(request: dict[str, Any]) -> dict[str, Any] | None:
    """Dispatch a single JSON-RPC request and return the response.

    Why: Central dispatcher that maps method names to handlers.
    How: Looks up the method in dispatch tables, calls the handler,
         catches domain exceptions and maps them to error codes.
    """
    request_id = request.get("id")
    method = request.get("method", "")
    params = request.get("params", {})

    if not isinstance(params, dict):
        params = {}

    try:
        if method in _STREAMING_METHODS:
            result = _handle_run_job(params, request_id)
        elif method in _METHODS:
            result = _METHODS[method](params)
        else:
            return _error_response(
                request_id, ERROR_METHOD_NOT_FOUND,
                f"Method not found: {method}",
            )
        return _ok_response(request_id, result)
    except ConfigError as exc:
        return _error_response(request_id, ERROR_CONFIG, str(exc))
    except ImageReadError as exc:
        return _error_response(request_id, ERROR_IMAGE_READ, str(exc))
    except LimitExceededError as exc:
        return _error_response(request_id, ERROR_LIMIT_EXCEEDED, str(exc))
    except RuntimeError as exc:
        if "cancelled" in str(exc).lower():
            return _error_response(request_id, ERROR_CANCELLED, "Job cancelled")
        return _error_response(request_id, ERROR_INTERNAL, str(exc))
    except Exception as exc:
        return _error_response(request_id, ERROR_INTERNAL, str(exc))


def main() -> None:
    """Run the JSON-RPC bridge main loop.

    Why: Entry point for the sidecar process.
    How: Reads stdin line-by-line, parses JSON, dispatches, writes
         response to stdout. Exits cleanly on EOF or empty line.
    """
    # Why: Prevent Python from writing BOM or using a locale-dependent
    #      encoding. The Rust host expects raw UTF-8 JSON lines.
    # How: Cast to io.TextIOWrapper which declares reconfigure().
    import io
    from typing import cast
    cast(io.TextIOWrapper, sys.stdin).reconfigure(encoding="utf-8")
    cast(io.TextIOWrapper, sys.stdout).reconfigure(encoding="utf-8")

    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue

        try:
            request = json.loads(line)
        except json.JSONDecodeError:
            _write(_error_response(None, ERROR_PARSE, "Parse error"))
            continue

        if not isinstance(request, dict):
            _write(_error_response(None, ERROR_INVALID_REQUEST, "Invalid request"))
            continue

        response = _dispatch(request)
        if response is not None:
            _write(response)


if __name__ == "__main__":
    main()
