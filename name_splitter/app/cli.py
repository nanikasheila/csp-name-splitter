"""Command-line interface for CSP Name Splitter.

Why: The CLI provides a scriptable, headless way to use all core
     functionality (image split, template generation, batch processing)
     without launching the GUI.
How: The default mode (no subcommand) retains the original positional
     image-split interface for full backward compatibility. The optional
     ``template`` and ``batch`` subcommands expose additional workflows.
"""
from __future__ import annotations

import argparse
from datetime import datetime
import sys
from pathlib import Path

from dataclasses import replace

from name_splitter.core import (
    ConfigError,
    ImageReadError,
    LimitExceededError,
    load_config,
    load_default_config,
    run_job,
)
from name_splitter.core.config import OutputConfig

# Subcommand names that trigger the extended parser path
_SUBCOMMANDS: frozenset[str] = frozenset({"template", "batch"})


def build_parser() -> argparse.ArgumentParser:
    """Build the backward-compatible image-split argument parser.

    Why: Existing scripts and tests rely on the positional ``input_image``
         interface. This function is kept stable so callers that import
         ``build_parser`` continue to work without changes.
    How: Returns the same flat argparse.ArgumentParser that has been in use
         since the initial release. For the extended subcommand interface
         see ``_build_subcommand_parser``.

    Returns:
        ArgumentParser for the default image-split workflow.
    """
    parser = argparse.ArgumentParser(description="CSP name splitter")
    parser.add_argument("input_image", nargs="?", help="Input image (PNG) exported from CSP")
    parser.add_argument("--config", dest="config_path", help="Path to config.yaml")
    parser.add_argument("--out-dir", dest="out_dir", help="Output directory")
    parser.add_argument("--page", dest="test_page", type=int, help="Render a single page (1-based)")
    parser.add_argument("--pdf", action="store_true", help="Export pages as a single PDF file")
    parser.add_argument("--gui", action="store_true", help="Launch GUI (not implemented yet)")
    return parser


def _build_subcommand_parser() -> argparse.ArgumentParser:
    """Build the extended argument parser with template and batch subcommands.

    Why: The subcommand interface cannot coexist cleanly with the legacy
         positional ``input_image`` argument in a single parser, so it is
         kept in a separate function. ``main`` dispatches to this parser
         when the first CLI argument matches a known subcommand name.
    How: Creates subparsers for ``template`` (generate a template PNG) and
         ``batch`` (process a directory of images), each with their own
         options.

    Returns:
        ArgumentParser with ``template`` and ``batch`` subparsers.
    """
    parser = argparse.ArgumentParser(description="CSP name splitter (extended)")
    subparsers = parser.add_subparsers(dest="subcommand")

    # --- template subcommand ---
    sp_template = subparsers.add_parser(
        "template",
        help="Generate a template PNG with grid and frame overlays",
    )
    sp_template.add_argument(
        "--output", dest="output_path", default="template.png",
        help="Output PNG file path (default: template.png)",
    )
    sp_template.add_argument(
        "--page-size", dest="page_size", default="A4",
        help="Page size name: A4, B4, A5, B5 (default: A4)",
    )
    sp_template.add_argument(
        "--orientation", dest="orientation", default="portrait",
        choices=["portrait", "landscape"],
        help="Page orientation (default: portrait)",
    )
    sp_template.add_argument(
        "--rows", dest="rows", type=int, default=4,
        help="Grid rows (default: 4)",
    )
    sp_template.add_argument(
        "--cols", dest="cols", type=int, default=4,
        help="Grid columns (default: 4)",
    )
    sp_template.add_argument(
        "--dpi", dest="dpi", type=int, default=300,
        help="Resolution in DPI (default: 300)",
    )

    # --- batch subcommand ---
    sp_batch = subparsers.add_parser(
        "batch",
        help="Batch-process all PNG images in a directory",
    )
    sp_batch.add_argument(
        "input_dir",
        help="Directory containing PNG files to process",
    )
    sp_batch.add_argument(
        "--config", dest="config_path",
        help="Path to config.yaml applied to every image",
    )
    sp_batch.add_argument(
        "--out-dir", dest="out_dir",
        help="Output directory (default: same directory as each image)",
    )
    sp_batch.add_argument(
        "--recursive", action="store_true",
        help="Recursively scan sub-directories for PNG files",
    )

    return parser


def _run_template_subcommand(args: argparse.Namespace) -> int:
    """Execute the ``template`` subcommand — generate a template PNG.

    Why: Separating the subcommand logic into a dedicated function keeps
         ``main`` readable and makes each workflow independently testable.
    How: Builds a GridConfig from the subcommand arguments, calls
         generate_template_png from the core template module, and reports
         the output path.

    Args:
        args: Parsed arguments from the template subparser.

    Returns:
        Exit code: 0 on success, 1 on error.
    """
    # Why: Zero or negative rows/cols cause ZeroDivisionError in grid math.
    if args.rows <= 0 or args.cols <= 0:
        print("Error: rows and cols must be positive integers", file=sys.stderr)
        return 2
    if args.dpi <= 0:
        print("Error: dpi must be a positive integer", file=sys.stderr)
        return 2

    try:
        from name_splitter.core.config import GridConfig  # noqa: PLC0415
        from name_splitter.core.template import (  # noqa: PLC0415
            TemplateStyle,
            generate_template_png,
        )
        from name_splitter.app.gui_utils import compute_page_size_px, PageSizeParams  # noqa: PLC0415

        params = PageSizeParams(
            page_size_name=args.page_size,
            orientation=args.orientation,
            dpi=args.dpi,
            custom_width=None,
            custom_height=None,
            custom_unit="px",
        )
        w_px, h_px = compute_page_size_px(params, 0, 0)

        grid_cfg = GridConfig(
            rows=args.rows,
            cols=args.cols,
            dpi=args.dpi,
            page_size_name=args.page_size,
            orientation=args.orientation,
            page_width_px=w_px,
            page_height_px=h_px,
        )
        style = TemplateStyle()
        out = generate_template_png(args.output_path, w_px, h_px, grid_cfg, style, args.dpi)
        print(f"Template written to {out}")
        return 0
    except Exception as exc:  # noqa: BLE001
        print(f"Error: {exc}", file=sys.stderr)
        return 1


def _run_batch_subcommand(args: argparse.Namespace) -> int:
    """Execute the ``batch`` subcommand — process all PNGs in a directory.

    Why: Same rationale as _run_template_subcommand — dedicated function
         keeps main() concise and the logic independently testable.
    How: Resolves the input directory, loads config, finds PNG files via
         find_images_in_directory, and calls run_batch with a progress
         callback that prints to stdout.

    Args:
        args: Parsed arguments from the batch subparser.

    Returns:
        Exit code: 0 on success, 1 on error, 2 on usage error.
    """
    from name_splitter.core.batch import (  # noqa: PLC0415
        BatchJobSpec,
        find_images_in_directory,
        run_batch,
    )

    input_dir = Path(args.input_dir)
    if not input_dir.is_dir():
        print(f"Directory not found: {input_dir}", file=sys.stderr)
        return 2

    if args.config_path:
        try:
            cfg = load_config(args.config_path)
        except ConfigError as exc:
            print(f"Config error: {exc}", file=sys.stderr)
            return 2
    else:
        try:
            cfg = load_default_config()
        except ConfigError as exc:
            print(f"Config error: {exc}", file=sys.stderr)
            return 2

    images = find_images_in_directory(input_dir, recursive=args.recursive)
    if not images:
        print(f"No PNG files found in: {input_dir}", file=sys.stderr)
        return 2

    out_dir: Path | None = Path(args.out_dir) if args.out_dir else None
    job_specs = [
        BatchJobSpec(input_image=img, config=cfg, out_dir=out_dir)
        for img in images
    ]

    def on_batch_progress(ev: object) -> None:
        """Print batch progress to stdout after each completed image."""
        ts = datetime.now().strftime("%H:%M:%S")
        print(f"{ts} [{getattr(ev, 'current_job', '?')}/{getattr(ev, 'total_jobs', '?')}] "
              f"{getattr(ev, 'job_name', '')}")

    try:
        result = run_batch(job_specs, on_progress=on_batch_progress)
        print(
            f"Batch complete: {result.successful_jobs} OK, "
            f"{result.failed_jobs} failed / {result.total_jobs} total"
        )
        return 0 if result.failed_jobs == 0 else 1
    except (ConfigError, LimitExceededError, ImageReadError, ValueError, RuntimeError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


def main(argv: list[str] | None = None) -> int:
    """Entry point for the CSP Name Splitter CLI.

    Why: A single entry point with subcommand dispatch keeps the public
         interface simple while supporting multiple workflows.
    How: Inspects the first argument; if it matches a known subcommand
         name ("template" or "batch"), routes to the extended parser and
         the corresponding runner function. Otherwise falls back to the
         original image-split parser for full backward compatibility.

    Args:
        argv: Argument list (defaults to sys.argv[1:] when None).

    Returns:
        Exit code: 0 success, 1 error, 2 usage error.
    """
    args_list: list[str] = argv if argv is not None else sys.argv[1:]

    # Route to extended subcommand parser when first token is a known subcommand
    if args_list and args_list[0] in _SUBCOMMANDS:
        sub_args = _build_subcommand_parser().parse_args(args_list)
        if sub_args.subcommand == "template":
            return _run_template_subcommand(sub_args)
        if sub_args.subcommand == "batch":
            return _run_batch_subcommand(sub_args)

    # Default path: original image-split workflow (backward compatible)
    args = build_parser().parse_args(args_list)

    if args.gui:
        try:
            from name_splitter.app.gui import main as gui_main  # noqa: PLC0415
        except Exception as exc:  # noqa: BLE001
            print(f"Failed to launch GUI: {exc}", file=sys.stderr)
            return 1
        gui_main()
        return 0
    if args.config_path:
        try:
            cfg = load_config(args.config_path)
        except ConfigError as exc:
            print(f"Config error: {exc}", file=sys.stderr)
            return 2
    else:
        try:
            cfg = load_default_config()
        except ConfigError as exc:
            print(f"Config error: {exc}", file=sys.stderr)
            return 2

    input_image = args.input_image or cfg.input.image_path
    if not input_image:
        print("Input image path is required.", file=sys.stderr)
        return 2

    if not Path(input_image).exists():
        print(f"Input image not found: {input_image}", file=sys.stderr)
        return 2

    def on_progress(event: object) -> None:
        """Print job progress to stdout."""
        timestamp = datetime.now().strftime("%H:%M:%S")
        message = f"[{getattr(event, 'phase', '?')}] {getattr(event, 'done', 0)}/{getattr(event, 'total', 0)}"
        msg_txt = getattr(event, "message", "")
        if msg_txt:
            message = f"{message} - {msg_txt}"
        print(f"{timestamp} {message}")

    # Why: --pdf flag overrides output.container to "pdf"
    # How: Replace the output config with container="pdf" when flag is set
    if args.pdf:
        cfg = replace(cfg, output=replace(cfg.output, container="pdf"))

    try:
        result = run_job(
            input_image,
            cfg,
            out_dir=args.out_dir,
            test_page=args.test_page,
            on_progress=on_progress,
        )
    except (ConfigError, LimitExceededError, ImageReadError, ValueError, RuntimeError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    print(f"Plan written to {result.plan.manifest_path}")
    print(f"Pages: {result.page_count}")
    if result.pdf_path:
        resolved = result.pdf_path.resolve()
        size_kb = resolved.stat().st_size / 1024
        print(f"PDF exported to {resolved} ({size_kb:.1f} KB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

