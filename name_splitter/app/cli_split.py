"""``split`` subcommand: write page .clip files from a name sheet (experimental).

Why: Stage 3 of the .clip/.cmc rebuild. Turns the ``plan`` of a name sheet
     into one .clip per page, keeping layers.
How: The page size and trim frame come from the template page (an empty
     page saved by CSP for the same work). The sheet and the template are
     only read; new files are written to ``--out-dir``.
"""
from __future__ import annotations

import argparse
from pathlib import Path
import sys

from name_splitter.csp import CspFormatError, read_clip
from name_splitter.csp.name_layout import ORDERS
from name_splitter.csp.page_writer import write_page
from name_splitter.csp.split_plan import FITS, centered_trim, plan_sheet


def add_split_parser(subparsers: argparse._SubParsersAction) -> None:
    """Register the ``split`` subcommand on an existing subparser set."""
    parser = subparsers.add_parser(
        "split",
        help="(Experimental) Write one .clip per page of a name sheet, keeping layers",
    )
    parser.add_argument("input_path", help="Name sheet .clip (read-only)")
    parser.add_argument("--template", required=True, help="Empty page .clip saved by CSP for the same work")
    parser.add_argument("--out-dir", required=True, help="Folder for the page files")
    parser.add_argument("--pages", help="Comma-separated page numbers to write (default: pages with content)")
    parser.add_argument("--fit", choices=FITS, default="frame", help="How a cell maps onto the page")
    parser.add_argument("--order", choices=ORDERS, default="rtl_ttb", help="Reading order of the cells")
    parser.add_argument("--first-page", type=int, default=1, help="Page number of the first cell")
    parser.add_argument("--name", default="page{page:04d}.clip", help="File name pattern")


def run_split_subcommand(args: argparse.Namespace) -> int:
    """Execute the ``split`` subcommand.

    Returns:
        Exit code: 0 on success, 1 on parse error, 2 on usage error.
    """
    sheet_path, template_path = Path(args.input_path), Path(args.template)
    for path in (sheet_path, template_path):
        if not path.exists():
            print(f"Input file not found: {path}", file=sys.stderr)
            return 2
    out_dir = Path(args.out_dir)
    if out_dir.resolve() in (sheet_path.resolve().parent, template_path.resolve().parent):
        print("--out-dir must differ from the input folders so originals are never overwritten", file=sys.stderr)
        return 2
    try:
        wanted = _page_numbers(args.pages)
        sheet, template = read_clip(sheet_path), read_clip(template_path)
        width, height = template.canvas.width_px, template.canvas.height_px
        trim_size = template.canvas.crop_size_px
        trim = centered_trim(width, height, *trim_size) if trim_size else None
        plan = plan_sheet(sheet, width, height, order=args.order, first_page=args.first_page,
                          fit=args.fit, trim=trim)
        out_dir.mkdir(parents=True, exist_ok=True)
        for page in plan.pages:
            if (wanted is None and not page.contents) or (wanted is not None and page.number not in wanted):
                continue
            result = write_page(template_path, sheet, page, out_dir / args.name.format(page=page.number))
            print(f"Wrote {result.path} ({len(result.layer_ids)} layers)")
            for warning in result.warnings:
                print(f"Warning: page {page.number}: {warning}", file=sys.stderr)
    except ValueError as exc:  # CspFormatError is a ValueError too
        label = "Format error" if isinstance(exc, CspFormatError) else "Invalid option"
        print(f"{label}: {exc}", file=sys.stderr)
        return 1 if isinstance(exc, CspFormatError) else 2
    for warning in plan.warnings:
        print(f"Warning: {warning}", file=sys.stderr)
    return 0


def _page_numbers(option: str | None) -> set[int] | None:
    if not option:
        return None
    try:
        return {int(part) for part in option.split(",") if part.strip()}
    except ValueError as exc:
        raise ValueError(f"--pages must be comma-separated numbers, got {option!r}") from exc
