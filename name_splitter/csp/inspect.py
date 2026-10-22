"""Summarize .clip / .cmc files as JSON-ready dictionaries.

Why: Stage 1 of the rebuild is to make the file structure visible. A stable
     JSON summary lets us compare files (for example before and after a
     small edit in CSP) and pin the parser's behaviour in tests.
How: Converts the reader dataclasses to plain dicts. Pixel data is not
     included; only whether a layer stores pixels and its stored size.
"""
from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
from typing import Any

from .clip_reader import ClipDocument, ClipLayer, read_clip
from .cmc_reader import read_cmc
from .errors import CspFormatError

TEXT_PREVIEW_LENGTH = 40


def inspect_file(path: str | Path, *, include_pixels: bool = False) -> dict[str, Any]:
    """Return a JSON-ready summary of a .clip or .cmc file."""
    file_path = Path(path)
    suffix = file_path.suffix.lower()
    if suffix == ".clip":
        return inspect_clip(read_clip(file_path), include_pixels=include_pixels)
    if suffix == ".cmc":
        project = read_cmc(file_path)
        summary = asdict(project)
        summary["path"] = str(project.path)
        summary["format"] = "cmc"
        summary["page_count"] = len(project.pages)
        return summary
    raise CspFormatError(f"Unsupported file type: {file_path.suffix}")


def inspect_clip(document: ClipDocument, *, include_pixels: bool = False) -> dict[str, Any]:
    """Summarize a parsed .clip document."""
    return {
        "format": "clip",
        "path": str(document.path),
        "canvas": asdict(document.canvas),
        "has_preview": document.preview_png is not None,
        "layers": [_layer_summary(document, layer, include_pixels) for layer in document.root.children],
    }


def _layer_summary(document: ClipDocument, layer: ClipLayer, include_pixels: bool) -> dict[str, Any]:
    summary: dict[str, Any] = {
        "id": layer.main_id,
        "name": layer.name,
        "kind": layer.kind,
        "visible": layer.visible,
        "opacity": round(layer.opacity, 4),
        "composite": layer.composite,
        "offset": [layer.offset_x, layer.offset_y],
        "clipping": layer.clipping,
        "has_mask": layer.has_mask,
    }
    if layer.text is not None:
        summary["text"] = layer.text[:TEXT_PREVIEW_LENGTH]
    if layer.kind == "vector":
        objects = document.vector_objects(layer)
        summary["vector"] = {
            "objects": len(objects),
            "closed": sum(1 for obj in objects if obj.closed),
            "bbox": _shift(_union([obj.bbox for obj in objects]), layer),
        }
    blocks = document.text_blocks(layer)
    if blocks:
        summary["text_blocks"] = [
            {"bbox": _shift(block.bbox, layer), "font_size_pt": block.font_size_pt, "font_name": block.font_name}
            for block in blocks
        ]
    if include_pixels and not layer.is_folder:
        image = document.render_layer_pixels(layer)
        summary["stored_pixels"] = None if image is None else {
            "size": list(image.size),
            "bbox": list(image.getbbox() or ()),
        }
    if layer.children:
        summary["children"] = [_layer_summary(document, child, include_pixels) for child in layer.children]
    return summary


def _union(boxes: list[tuple[int, int, int, int]]) -> tuple[int, int, int, int] | None:
    if not boxes:
        return None
    return (
        min(box[0] for box in boxes), min(box[1] for box in boxes),
        max(box[2] for box in boxes), max(box[3] for box in boxes),
    )


def _shift(box: tuple[int, int, int, int] | None, layer: ClipLayer) -> list[int] | None:
    """Convert a layer-local box to canvas pixels by adding the layer offset."""
    if box is None:
        return None
    return [box[0] + layer.offset_x, box[1] + layer.offset_y, box[2] + layer.offset_x, box[3] + layer.offset_y]
