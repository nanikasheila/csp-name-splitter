from __future__ import annotations

import argparse
import sys
from pathlib import Path

from name_splitter.core import (
    ConfigError,
    LimitExceededError,
    PsdReadError,
    load_config,
    load_default_config,
    run_job,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="CSP name splitter")
    parser.add_argument("input_psd", nargs="?", help="Input PSD exported from CSP")
    parser.add_argument("--config", dest="config_path", help="Path to config.yaml")
    parser.add_argument("--out-dir", dest="out_dir", help="Output directory")
    parser.add_argument("--page", dest="test_page", type=int, help="Render a single page (1-based)")
    parser.add_argument("--gui", action="store_true", help="Launch GUI (not implemented yet)")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    if args.gui:
        print("GUI mode is not implemented yet.")
        return 1

    if not args.input_psd:
        print("Input PSD path is required.", file=sys.stderr)
        return 2

    input_psd = args.input_psd
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

    if not Path(input_psd).exists():
        print(f"Input PSD not found: {input_psd}", file=sys.stderr)
        return 2

    def on_progress(event) -> None:  # type: ignore[no-untyped-def]
        message = f"[{event.phase}] {event.done}/{event.total}"
        if event.message:
            message = f"{message} - {event.message}"
        print(message)

    try:
        result = run_job(
            input_psd,
            cfg,
            out_dir=args.out_dir,
            test_page=args.test_page,
            on_progress=on_progress,
        )
    except (ConfigError, LimitExceededError, PsdReadError, ValueError, RuntimeError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    print(f"Plan written to {result.plan.manifest_path}")
    print(f"Pages: {result.page_count}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
