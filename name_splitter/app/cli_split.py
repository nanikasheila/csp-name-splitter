"""``split`` subcommand: write page .clip files from a name sheet (experimental).

Why: Stages 3 and 4 of the .clip/.cmc rebuild. Turns the ``plan`` of a name
     sheet into one .clip per page, keeping layers, and with ``--cmc`` into
     a multi-page work that CSP EX opens as one file.
How: The page size and trim frame come from the template page (an empty
     page saved by CSP for the same work); work settings come from a
     template .cmc (by default the one next to the sheet). Inputs are only
     read; new files are written to ``--out-dir``.
"""
from __future__ import annotations

import argparse
from pathlib import Path
import sys

from name_splitter.csp import CspFormatError
from name_splitter.csp.name_layout import ORDERS
from name_splitter.csp.split_job import SplitOptions, prepare_split, run_split
from name_splitter.csp.split_plan import FITS


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
    parser.add_argument("--fit", choices=FITS, default="basic",
                        help="Page frame each cell's inner frame is enlarged onto: basic (基本枠, default), "
                             "trim (仕上がり) or cell (the whole cell into the canvas)")
    parser.add_argument("--order", choices=ORDERS, default="rtl_ttb", help="Reading order of the cells")
    parser.add_argument("--first-page", type=int, default=1, help="Page number of the first cell")
    parser.add_argument("--name", default="page{page:04d}.clip", help="File name pattern")
    parser.add_argument("--cmc", metavar="NAME",
                        help="Also write NAME.cmc listing every page (empty pages included) as one work")
    parser.add_argument("--story-index", type=int,
                        help="Episode number (話数) for the work and its pages (default: the template .cmc's)")
    parser.add_argument("--cmc-template",
                        help="CSP-made .cmc whose work settings are copied (default: the .cmc next to the sheet)")


def run_split_subcommand(args: argparse.Namespace) -> int:
    """Execute the ``split`` subcommand.

    Returns:
        Exit code: 0 on success, 1 on parse error, 2 on usage error.
    """
    try:
        options = SplitOptions(
            sheet=Path(args.input_path), template=Path(args.template), out_dir=Path(args.out_dir),
            cmc_name=args.cmc, cmc_template=Path(args.cmc_template) if args.cmc_template else None,
            pages=_page_numbers(args.pages), fit=args.fit, order=args.order, first_page=args.first_page,
            story_index=args.story_index, file_name=args.name,
        )
        prepared = prepare_split(options)
        result = run_split(prepared, on_page=lambda done, total, path: print(f"Wrote {path} ({done}/{total})"))
    except FileNotFoundError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    except ValueError as exc:  # CspFormatError is a ValueError too
        label = "Format error" if isinstance(exc, CspFormatError) else "Invalid option"
        print(f"{label}: {exc}", file=sys.stderr)
        return 1 if isinstance(exc, CspFormatError) else 2
    if result.cmc is not None:
        print(f"Wrote {result.cmc} ({len(result.pages)} pages)")
    for warning in result.warnings:
        print(f"Warning: {warning}", file=sys.stderr)
    return 0


def _page_numbers(option: str | None) -> frozenset[int] | None:
    if not option:
        return None
    try:
        return frozenset(int(part) for part in option.split(",") if part.strip())
    except ValueError as exc:
        raise ValueError(f"--pages must be comma-separated numbers, got {option!r}") from exc
