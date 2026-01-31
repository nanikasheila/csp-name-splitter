from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from .config import Config
from .errors import LimitExceededError
from .grid import compute_cells
from .merge import MergeResult
from .image_read import ImageInfo, read_image_document
from .render import RenderPlan, RenderedPage, render_pages, write_plan


@dataclass(frozen=True)
class ProgressEvent:
    # 進捗通知のイベント
    phase: str
    done: int
    total: int
    message: str = ""


class CancelToken:
    def __init__(self) -> None:
        # キャンセルフラグ
        self._cancelled = False

    def cancel(self) -> None:
        # キャンセルを要求
        self._cancelled = True

    @property
    def cancelled(self) -> bool:
        # キャンセル状態を取得
        return self._cancelled


@dataclass(frozen=True)
class JobResult:
    # ジョブ実行結果
    out_dir: Path
    page_count: int
    plan: RenderPlan


def run_job(
    input_image: str,
    cfg: Config,
    *,
    out_dir: str | None = None,
    test_page: int | None = None,
    on_progress: Callable[[ProgressEvent], None] | None = None,
    cancel_token: CancelToken | None = None,
) -> JobResult:
    # 画像読み込みからレンダリングまでの一連処理
    def report(phase: str, done: int, total: int, message: str = "") -> None:
        # 進捗コールバック通知
        if on_progress:
            on_progress(ProgressEvent(phase=phase, done=done, total=total, message=message))

    def check_cancel() -> None:
        # キャンセルされていれば中断
        if cancel_token and cancel_token.cancelled:
            raise RuntimeError("Job cancelled")

    report("load_image", 0, 1, "Reading image")
    image_doc = read_image_document(input_image)
    image_info = image_doc.info
    report("load_image", 1, 1, "Image loaded")
    check_cancel()

    _enforce_limits(image_info, cfg)

    primary_layer = cfg.output.layer_stack[0] if cfg.output.layer_stack else "flat"
    merge_result = MergeResult(
        outputs={primary_layer: []},
        unmatched=[],
        warnings=[],
        output_images={primary_layer: image_doc.image},
    )

    report("grid", 0, 1, "Computing grid")
    cells = compute_cells(image_info.width, image_info.height, cfg.grid)
    report("grid", 1, 1, "Grid computed")
    check_cancel()

    selected_pages = _select_pages(len(cells), test_page)

    output_dir = _resolve_out_dir(input_image, cfg, out_dir)
    report("render_plan", 0, 1, "Writing plan")
    plan = write_plan(output_dir, image_info, cells, cfg, selected_pages, merge_result=merge_result)
    report("render_plan", 1, 1, f"Plan written: {plan.manifest_path}")
    check_cancel()

    report("render_pages", 0, len(selected_pages), "Rendering pages")

    def on_render_page(rendered: RenderedPage, done: int, total: int) -> None:
        report("render_pages", done, total, f"Rendered page {rendered.page_index + 1}")

    rendered_pages = render_pages(
        output_dir,
        image_info,
        cells,
        cfg,
        selected_pages,
        merge_result=merge_result,
        on_page=on_render_page,
    )
    report("render_pages", len(selected_pages), len(selected_pages), "Pages rendered")
    check_cancel()

    return JobResult(out_dir=output_dir, page_count=len(selected_pages), plan=plan)


def _select_pages(total_pages: int, test_page: int | None) -> list[int]:
    # test_page指定がある場合は対象ページのみ返す
    if test_page is None:
        return list(range(total_pages))
    if test_page <= 0 or test_page > total_pages:
        raise ValueError(f"test_page must be between 1 and {total_pages}")
    return [test_page - 1]


def _resolve_out_dir(input_image: str, cfg: Config, override: str | None) -> Path:
    # 出力ディレクトリを決定
    if override:
        return Path(override)
    if cfg.output.out_dir:
        return Path(cfg.output.out_dir)
    image_path = Path(input_image)
    return image_path.with_suffix("").with_name(f"{image_path.stem}_pages")


def _enforce_limits(info: ImageInfo, cfg: Config) -> None:
    # サイズ上限チェック
    if info.width > cfg.limits.max_dim_px or info.height > cfg.limits.max_dim_px:
        raise LimitExceededError(
            f"Input size {info.width}x{info.height} exceeds limit {cfg.limits.max_dim_px}px"
        )
