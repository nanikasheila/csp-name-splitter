from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from .config import Config
from .grid import CellRect
from .merge import MergeResult
from .image_ops import ImageData
from .psd_read import PsdInfo


@dataclass(frozen=True)
class RenderPlan:
    # plan.jsonの出力情報
    out_dir: Path
    manifest_path: Path


@dataclass(frozen=True)
class RenderedPage:
    # レンダリング済みページ情報
    page_index: int
    page_dir: Path
    layer_paths: dict[str, Path]


def write_plan(
    out_dir: Path,
    psd_info: PsdInfo,
    cells: list[CellRect],
    cfg: Config,
    selected_pages: list[int],
    merge_result: MergeResult | None = None,
) -> RenderPlan:
    # plan.jsonを書き出す
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


def render_pages(
    out_dir: Path,
    psd_info: PsdInfo,
    cells: list[CellRect],
    cfg: Config,
    selected_pages: list[int],
    merge_result: MergeResult,
) -> list[RenderedPage]:
    # 合成済み画像をセル単位で切り出して保存
    if not merge_result.output_images:
        raise RuntimeError("No merged images available for rendering")
    out_dir.mkdir(parents=True, exist_ok=True)
    pages: list[RenderedPage] = []
    for page_index in selected_pages:
        cell = cells[page_index]
        page_name = cfg.output.page_basename.format(page=page_index + 1)
        page_dir = out_dir / page_name
        page_dir.mkdir(parents=True, exist_ok=True)
        layer_paths: dict[str, Path] = {}
        for layer_name in cfg.output.layer_stack:
            image = merge_result.output_images.get(layer_name)
            if image is None:
                # 指定レイヤーがない場合は透明で埋める
                image = ImageData.blank(psd_info.width, psd_info.height)
            cropped = image.crop(cell.x0, cell.y0, cell.x1, cell.y1)
            path = page_dir / f"{layer_name}.{cfg.output.raster_ext}"
            cropped.save(path)
            layer_paths[layer_name] = path
        pages.append(RenderedPage(page_index=page_index, page_dir=page_dir, layer_paths=layer_paths))
    return pages


def _serialize_merge(merge_result: MergeResult | None) -> dict[str, object]:
    # マージ結果をplan.json向けに整形
    if merge_result is None:
        return {"outputs": {}, "unmatched": 0, "warnings": []}
    return {
        "outputs": {key: len(value) for key, value in merge_result.outputs.items()},
        "unmatched": len(merge_result.unmatched),
        "warnings": list(merge_result.warnings),
    }
