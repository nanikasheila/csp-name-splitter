from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from .config import Config
from .grid import CellRect
from .merge import MergeResult
from .psd_read import PsdInfo


@dataclass(frozen=True)
class RenderPlan:
    out_dir: Path
    manifest_path: Path


def write_plan(
    out_dir: Path,
    psd_info: PsdInfo,
    cells: list[CellRect],
    cfg: Config,
    selected_pages: list[int],
    merge_result: MergeResult | None = None,
) -> RenderPlan:
    out_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = out_dir / "plan.json"
    page_entries = []
    for page_index in selected_pages:
        cell = cells[page_index]
        page_entries.append(
            {
                "page_index": page_index,
                "row": cell.row,
                "col": cell.col,
                "rect": [cell.x0, cell.y0, cell.x1, cell.y1],
            }
        )
    payload = {
        "psd": {"width": psd_info.width, "height": psd_info.height},
        "grid": {
            "rows": cfg.grid.rows,
            "cols": cfg.grid.cols,
            "order": cfg.grid.order,
            "margin_px": cfg.grid.margin_px,
            "gutter_px": cfg.grid.gutter_px,
        },
        "output": {
            "page_basename": cfg.output.page_basename,
            "layer_stack": list(cfg.output.layer_stack),
            "raster_ext": cfg.output.raster_ext,
            "container": cfg.output.container,
        },
        "merge": _serialize_merge(merge_result),
        "pages": page_entries,
    }
    manifest_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return RenderPlan(out_dir=out_dir, manifest_path=manifest_path)


def _serialize_merge(merge_result: MergeResult | None) -> dict[str, object]:
    if merge_result is None:
        return {"outputs": {}, "unmatched": 0, "warnings": []}
    return {
        "outputs": {key: len(value) for key, value in merge_result.outputs.items()},
        "unmatched": len(merge_result.unmatched),
        "warnings": list(merge_result.warnings),
    }
