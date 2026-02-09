from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from .config import Config
from .grid import CellRect
from .merge import MergeResult
from .image_ops import ImageData
from .image_read import ImageInfo


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
    image_info: ImageInfo,
    cells: list[CellRect],
    cfg: Config,
    selected_pages: list[int],
    merge_result: MergeResult | None = None,
) -> RenderPlan:
    # plan.yamlを書き出す（JSON互換性のため、JSONでも保存可能だが、デフォルトはYAML）
    out_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = out_dir / "plan.yaml"
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
        "source": {"width": image_info.width, "height": image_info.height},
        "grid": {
            "rows": cfg.grid.rows,
            "cols": cfg.grid.cols,
            "order": cfg.grid.order,
            "margin_px": cfg.grid.margin_px,  # Legacy
            "margin_top_px": cfg.grid.margin_top_px,
            "margin_bottom_px": cfg.grid.margin_bottom_px,
            "margin_left_px": cfg.grid.margin_left_px,
            "margin_right_px": cfg.grid.margin_right_px,
            "gutter_px": cfg.grid.gutter_px,
            "gutter_unit": cfg.grid.gutter_unit,
            "margin_unit": cfg.grid.margin_unit,
            "dpi": cfg.grid.dpi,
            "page_size_name": cfg.grid.page_size_name,
            "orientation": cfg.grid.orientation,
            "page_width_px": cfg.grid.page_width_px,
            "page_height_px": cfg.grid.page_height_px,
            "page_size_unit": cfg.grid.page_size_unit,
        },
        "output": {
            "page_basename": cfg.output.page_basename,
            "layer_stack": list(cfg.output.layer_stack),
            "raster_ext": cfg.output.raster_ext,
            "container": cfg.output.container,
            "layout": cfg.output.layout,
        },
        "merge": _serialize_merge(merge_result),
        "pages": page_entries,
    }
    try:
        import yaml  # type: ignore
        manifest_path.write_text(yaml.dump(payload, allow_unicode=True, sort_keys=False), encoding="utf-8")
    except ImportError:
        # Fallback to JSON if PyYAML not available
        manifest_path = out_dir / "plan.json"
        manifest_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return RenderPlan(out_dir=out_dir, manifest_path=manifest_path)


def render_pages(
    out_dir: Path,
    image_info: ImageInfo,
    cells: list[CellRect],
    cfg: Config,
    selected_pages: list[int],
    merge_result: MergeResult,
    on_page: Callable[[RenderedPage, int, int], None] | None = None,
) -> list[RenderedPage]:
    # 合成済み画像をセル単位で切り出して保存
    if not merge_result.output_images:
        raise RuntimeError("No merged images available for rendering")
    out_dir.mkdir(parents=True, exist_ok=True)
    pages: list[RenderedPage] = []
    total_pages = len(selected_pages)
    for index, page_index in enumerate(selected_pages, start=1):
        cell = cells[page_index]
        page_name = cfg.output.page_basename.format(page=page_index + 1)
        page_dir = out_dir / page_name
        layer_paths: dict[str, Path] = {}
        for layer_name in cfg.output.layer_stack:
            image = merge_result.output_images.get(layer_name)
            if image is None:
                # 指定レイヤーがない場合は透明で埋める
                image = ImageData.blank(image_info.width, image_info.height)
            cropped = image.crop(cell.x0, cell.y0, cell.x1, cell.y1)
            if cfg.output.layout == "layers":
                layer_dir = out_dir / layer_name
                layer_dir.mkdir(parents=True, exist_ok=True)
                path = layer_dir / f"{page_name}.{cfg.output.raster_ext}"
            else:
                page_dir.mkdir(parents=True, exist_ok=True)
                path = page_dir / f"{layer_name}.{cfg.output.raster_ext}"
            cropped.save(path)
            layer_paths[layer_name] = path
        rendered = RenderedPage(page_index=page_index, page_dir=page_dir, layer_paths=layer_paths)
        pages.append(rendered)
        if on_page:
            on_page(rendered, index, total_pages)
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
