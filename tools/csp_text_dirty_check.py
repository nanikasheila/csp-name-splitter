"""Write variants of one split page to find why CSP marks text pages as modified.

Why: Pages written by ``split`` that hold a text layer open in CSP EX 5.1.4
     with the tab already marked "*" (modified); pages with only raster or
     vector layers do not. Each variant changes one suspect, so opening them
     one by one shows which one makes CSP rewrite the page on open.
How: Plans the sheet like ``split`` (basic-frame fit) and writes page N:

     - t1_baseline.clip  as ``split`` writes it today
     - t2_offset48.clip  also scales TLV 0x48 (an origin offset in px that
                         follows the quad 0x40, which is scaled)
     - t3_unscaled.clip  text attributes copied unchanged (text keeps the
                         name sheet's size and position)

Usage::

    python tools/csp_text_dirty_check.py SHEET.clip EMPTY_PAGE.clip OUT_DIR --page 2
"""
from __future__ import annotations

import argparse
from pathlib import Path
import struct
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from name_splitter.csp import page_writer, text_attributes  # noqa: E402
from name_splitter.csp.split_job import SplitOptions, prepare_split  # noqa: E402
from name_splitter.csp.text_attributes import build_tlv, parse_tlv  # noqa: E402

ATTR_ORIGIN = 0x48
original_transform = text_attributes.transform_text_attributes


def _with_origin(blob: bytes, scale: float, dx: float, dy: float) -> bytes:
    items = []
    for tag, value in parse_tlv(original_transform(blob, scale, dx, dy)):
        if tag == ATTR_ORIGIN and len(value) == 8:
            x, y = struct.unpack("<2i", value)
            value = struct.pack("<2i", round(x * scale), round(y * scale))
        items.append((tag, value))
    return build_tlv(items)


def _unchanged(blob: bytes, scale: float, dx: float, dy: float) -> bytes:
    return blob


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("sheet")
    parser.add_argument("template")
    parser.add_argument("out_dir")
    parser.add_argument("--page", type=int, required=True, help="page number that holds a text layer")
    args = parser.parse_args()
    out_dir = Path(args.out_dir)
    prepared = prepare_split(SplitOptions(Path(args.sheet), Path(args.template), out_dir))
    page = next(item for item in prepared.plan.pages if item.number == args.page)
    if not any(content.kind == "text" for content in page.contents):
        print(f"page {args.page} has no text layer", file=sys.stderr)
        return 2
    out_dir.mkdir(parents=True, exist_ok=True)
    variants = {"t1_baseline": original_transform, "t2_offset48": _with_origin, "t3_unscaled": _unchanged}
    for name, transform in variants.items():
        page_writer.transform_text_attributes = transform  # type: ignore[assignment]
        result = page_writer.write_page(Path(args.template), prepared.sheet, page, out_dir / f"{name}.clip")
        print(f"Wrote {result.path}")
    page_writer.transform_text_attributes = original_transform  # type: ignore[assignment]
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
