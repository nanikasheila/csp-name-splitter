"""``plan`` subcommand: show how a name sheet .clip would be split into pages.

Why: Stage 2 of the .clip/.cmc rebuild. The page cells and what goes on each
     page must be checkable before stage 3 writes any .clip file.
How: Reads the sheet (read-only), builds a ``SheetPlan`` and prints it as
     JSON; optionally saves a preview PNG with the page numbers.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from name_splitter.csp import CspFormatError, read_clip
from name_splitter.csp.name_layout import ORDERS
from name_splitter.csp.plan_report import plan_to_dict, render_plan_preview
from name_splitter.csp.split_plan import FITS, centered_trim, plan_sheet


def add_plan_parser(subparsers: argparse._SubParsersAction) -> None:
    """Register the ``plan`` subcommand on an existing subparser set."""
    parser = subparsers.add_parser(
        "plan",
        help="Detect the page cells of a name sheet .clip and show the split plan as JSON",
    )
    parser.add_argument("input_path", help="Name sheet .clip (read-only)")
    parser.add_argument(
        "--page-size", metavar="WxH",
        help="Output page canvas in px (default: the sheet's single-page size)",
    )
    parser.add_argument(
        "--fit", choices=FITS, default="basic",
        help="basic: put each cell's inner frame on the page's basic frame (基本枠, default); "
             "trim: on the trim frame (仕上がり); cell: fit the whole cell into the page canvas",
    )
    parser.add_argument(
        "--trim-size", metavar="WxH",
        help="Trim frame of the output page in px, centred (default: the sheet's trim frame setting)",
    )
    parser.add_argument(
        "--basic-size", metavar="WxH",
        help="Basic frame of the output page in px, centred (default: the sheet's basic frame setting)",
    )
    parser.add_argument("--order", choices=ORDERS, default="rtl_ttb", help="Reading order of the cells")
    parser.add_argument("--first-page", type=int, default=1, help="Page number of the first cell")
    parser.add_argument("--output", dest="output_path", help="Write JSON to this file")
    parser.add_argument("--preview", dest="preview_path", help="Save a PNG with page numbers drawn on the sheet")


def run_plan_subcommand(args: argparse.Namespace) -> int:
    """Execute the ``plan`` subcommand.

    Returns:
        Exit code: 0 on success, 1 on parse error, 2 on usage error.
    """
    input_path = Path(args.input_path)
    if not input_path.exists():
        print(f"Input file not found: {input_path}", file=sys.stderr)
        return 2
    try:
        document = read_clip(input_path)
        width, height = _size_option(args.page_size, "--page-size") or (
            document.canvas.single_page_width_px, document.canvas.height_px)
        trim_size = _size_option(args.trim_size, "--trim-size") or document.canvas.crop_size_px
        trim = centered_trim(width, height, *trim_size) if trim_size else None
        basic_option = _size_option(args.basic_size, "--basic-size")
        basic_size = basic_option or document.canvas.basic_size_px
        offset = (0, 0) if basic_option else document.canvas.basic_offset_px
        basic = centered_trim(width, height, *basic_size, offset=offset) if basic_size else None
        plan = plan_sheet(document, width, height, order=args.order, first_page=args.first_page,
                          fit=args.fit, trim=trim, basic=basic)
    except ValueError as exc:  # CspFormatError is a ValueError too
        label = "Format error" if isinstance(exc, CspFormatError) else "Invalid option"
        print(f"{label}: {exc}", file=sys.stderr)
        return 1 if isinstance(exc, CspFormatError) else 2
    text = json.dumps(plan_to_dict(plan, document), ensure_ascii=False, indent=2)
    if args.output_path:
        Path(args.output_path).write_text(text + "\n", encoding="utf-8")
        print(f"Wrote {args.output_path}")
    else:
        print(text)
    if args.preview_path:
        render_plan_preview(plan, document).save(args.preview_path)
        print(f"Wrote {args.preview_path}", file=sys.stderr if not args.output_path else sys.stdout)
    for warning in plan.warnings:
        print(f"Warning: {warning}", file=sys.stderr)
    return 0


def _size_option(option: str | None, name: str) -> tuple[int, int] | None:
    if not option:
        return None
    parts = option.lower().split("x")
    if len(parts) != 2 or not all(part.strip().isdigit() for part in parts):
        raise ValueError(f"{name} must look like 7016x9921, got {option!r}")
    width, height = (int(part) for part in parts)
    if width <= 0 or height <= 0:
        raise ValueError(f"{name} must be positive")
    return width, height
