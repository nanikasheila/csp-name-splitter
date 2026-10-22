"""Show a split plan as JSON and as a preview image.

Why: Before any page file is generated, the user should be able to check
     which page number each cell gets and what goes on it.
How: ``plan_to_dict`` makes a JSON-ready summary; ``render_plan_preview``
     draws the cells and their page numbers over the sheet's CSP preview.
"""
from __future__ import annotations

import io
from typing import Any

from PIL import Image, ImageDraw

from .clip_reader import ClipDocument
from .split_plan import SheetPlan

PREVIEW_COLOR = (230, 30, 30)
FRAME_COLOR = (30, 90, 230)


def plan_to_dict(plan: SheetPlan, document: ClipDocument) -> dict[str, Any]:
    """Return a JSON-ready summary of a sheet plan."""
    return {
        "sheet": str(document.path),
        "sheet_size_px": [document.canvas.width_px, document.canvas.height_px],
        "page_size_px": [plan.page_width, plan.page_height],
        "fit": plan.fit,
        "trim_px": plan.trim.as_list() if plan.trim else None,
        "template_layer_ids": plan.template_layer_ids,
        "warnings": plan.warnings,
        "pages": [
            {
                "number": page.number,
                "cell": page.cell.rect.as_list(),
                "frame": page.cell.frame.as_list() if page.cell.frame else None,
                "spread_side": page.cell.spread_side,
                "transform": {
                    "scale": round(page.transform.scale, 6),
                    "dx": round(page.transform.dx, 3),
                    "dy": round(page.transform.dy, 3),
                },
                "contents": [
                    {
                        "layer_id": content.layer_id,
                        "name": content.name,
                        "kind": content.kind,
                        "folder_path": list(content.folder_path),
                        **({"crop": [round(value, 2) for value in content.crop]} if content.crop else {}),
                        **({"items": list(content.items)} if content.items else {}),
                        **({"whole_layer": True} if content.whole_layer else {}),
                    }
                    for content in page.contents
                ],
            }
            for page in plan.pages
        ],
    }


def render_plan_preview(plan: SheetPlan, document: ClipDocument) -> Image.Image:
    """Draw page cells and numbers on the sheet preview (or a blank canvas)."""
    image = _sheet_preview(document)
    scale = image.width / max(document.canvas.width_px, 1)
    draw = ImageDraw.Draw(image)
    for page in plan.pages:
        rect = [value * scale for value in page.cell.rect.as_list()]
        draw.rectangle(rect, outline=PREVIEW_COLOR, width=2)
        if page.cell.frame:
            draw.rectangle([value * scale for value in page.cell.frame.as_list()], outline=FRAME_COLOR)
        label = str(page.number) + ("*" if page.contents else "")
        draw.text((rect[0] + 4, rect[1] + 4), label, fill=PREVIEW_COLOR)
    return image


def _sheet_preview(document: ClipDocument) -> Image.Image:
    if document.preview_png:
        try:
            return Image.open(io.BytesIO(document.preview_png)).convert("RGB")
        except OSError:
            pass  # unreadable preview: fall back to a blank sheet
    size = (max(document.canvas.width_px // 8, 1), max(document.canvas.height_px // 8, 1))
    return Image.new("RGB", size, "white")
