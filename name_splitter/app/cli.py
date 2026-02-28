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


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="CSP name splitter")
    parser.add_argument("input_image", nargs="?", help="Input image (PNG) exported from CSP")
    parser.add_argument("--config", dest="config_path", help="Path to config.yaml")
    parser.add_argument("--out-dir", dest="out_dir", help="Output directory")
    parser.add_argument("--page", dest="test_page", type=int, help="Render a single page (1-based)")
    parser.add_argument("--pdf", action="store_true", help="Export pages as a single PDF file")
    parser.add_argument("--gui", action="store_true", help="Launch GUI (not implemented yet)")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    if args.gui:
        try:
            from name_splitter.app.gui import main as gui_main
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

    def on_progress(event) -> None:
        timestamp = datetime.now().strftime("%H:%M:%S")
        message = f"[{event.phase}] {event.done}/{event.total}"
        if event.message:
            message = f"{message} - {event.message}"
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
