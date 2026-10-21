"""``inspect`` subcommand: dump the structure of .clip / .cmc files as JSON.

Why: Stage 1 of the .clip/.cmc rebuild needs a quick way to see what CSP
     stored (layer tree, page list) and to diff two files.
How: Delegates to ``name_splitter.csp.inspect_file`` and prints JSON.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from name_splitter.csp import CspFormatError, inspect_file


def add_inspect_parser(subparsers: argparse._SubParsersAction) -> None:
    """Register the ``inspect`` subcommand on an existing subparser set."""
    parser = subparsers.add_parser(
        "inspect",
        help="Show the structure of a .clip or .cmc file as JSON",
    )
    parser.add_argument("input_path", help="Path to a .clip or .cmc file (read-only)")
    parser.add_argument(
        "--pixels", action="store_true",
        help="Also decode raster layers and report their stored size and bounds",
    )
    parser.add_argument(
        "--output", dest="output_path",
        help="Write JSON to this file instead of standard output",
    )


def run_inspect_subcommand(args: argparse.Namespace) -> int:
    """Execute the ``inspect`` subcommand.

    Returns:
        Exit code: 0 on success, 1 on parse error, 2 on usage error.
    """
    input_path = Path(args.input_path)
    if not input_path.exists():
        print(f"Input file not found: {input_path}", file=sys.stderr)
        return 2
    try:
        summary = inspect_file(input_path, include_pixels=args.pixels)
    except CspFormatError as exc:
        print(f"Format error: {exc}", file=sys.stderr)
        return 1
    text = json.dumps(summary, ensure_ascii=False, indent=2)
    if args.output_path:
        Path(args.output_path).write_text(text + "\n", encoding="utf-8")
        print(f"Wrote {args.output_path}")
    else:
        print(text)
    return 0
