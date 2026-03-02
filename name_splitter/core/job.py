from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from .config import Config
from .errors import LimitExceededError
from .grid import compute_cells
from .merge import MergeResult
from .image_read import ImageInfo, read_image_document
from .pdf_export import export_pdf
from .render import RenderPlan, RenderedPage, render_pages, write_plan


@dataclass(frozen=True)
class ProgressEvent:
    """Progress notification event.

    Why: GUI and CLI need real-time feedback during job execution.
    How: Frozen dataclass with timing fields for speed/ETA display.
    """
    phase: str
    done: int
    total: int
    message: str = ""
    elapsed_seconds: float = 0.0
    pages_per_second: float = 0.0
    eta_seconds: float | None = None


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
    """Job execution result.

    Why: Callers need output metadata for result reports and logging.
    How: Frozen dataclass with elapsed_seconds for processing time display.
    """
    out_dir: Path
    page_count: int
    plan: RenderPlan
    pdf_path: Path | None = None
    elapsed_seconds: float = 0.0


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
    _job_start = time.monotonic()

    def report(phase: str, done: int, total: int, message: str = "") -> None:
        """Progress callback with timing data.

        Why: GUI needs speed/ETA for user feedback during render_pages.
        How: Computes elapsed, speed, and ETA from monotonic clock.
        """
        elapsed = time.monotonic() - _job_start
        speed = 0.0
        eta: float | None = None
        if phase == "render_pages" and done > 0 and elapsed > 0.001:
            speed = done / max(elapsed, 0.001)
            remaining = total - done
            eta = remaining / speed if speed > 0 and remaining > 0 else 0.0
        if on_progress:
            on_progress(ProgressEvent(
                phase=phase, done=done, total=total, message=message,
                elapsed_seconds=elapsed,
                pages_per_second=speed,
                eta_seconds=eta,
            ))

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

    selected_pages = _select_pages(
        len(cells),
        test_page,
        skip=cfg.output.skip_pages,
        odd_even=cfg.output.odd_even,
    )

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

    # Why: Users may want a single PDF containing all rendered pages
    # How: When container is "pdf", call export_pdf after page rendering
    pdf_path: Path | None = None
    if cfg.output.container == "pdf":
        report("export_pdf", 0, 1, "Generating PDF")
        pdf_filename = Path(input_image).stem + ".pdf"
        pdf_path = output_dir / pdf_filename
        primary_layer = cfg.output.layer_stack[0] if cfg.output.layer_stack else "flat"
        # Why: PDF should use target DPI (after resize), not source DPI
        target_dpi = cfg.output.output_dpi if cfg.output.output_dpi > 0 else cfg.grid.dpi
        export_pdf(
            rendered_pages,
            pdf_path,
            layer_name=primary_layer,
            dpi=target_dpi,
        )
        resolved_pdf = pdf_path.resolve()
        pdf_size = resolved_pdf.stat().st_size
        report("export_pdf", 1, 1, f"PDF exported: {resolved_pdf} ({pdf_size:,} bytes)")
        check_cancel()

    elapsed = time.monotonic() - _job_start
    return JobResult(
        out_dir=output_dir, page_count=len(selected_pages),
        plan=plan, pdf_path=pdf_path, elapsed_seconds=elapsed,
    )


def _select_pages(
    total_pages: int,
    test_page: int | None,
    *,
    skip: tuple[int, ...] = (),
    odd_even: str = "all",
) -> list[int]:
    """Select which physical pages to render.

    Why: Users need to skip covers, select odd/even pages, or test
         a single page. All filtering is centralised here so render.py
         stays simple.
    How: test_page takes priority. Otherwise build full list, remove
         skipped pages, then filter by odd/even based on 1-based index.
    """
    if test_page is not None:
        if test_page <= 0 or test_page > total_pages:
            raise ValueError(f"test_page must be between 1 and {total_pages}")
        return [test_page - 1]

    # Build full page list (0-indexed)
    pages = list(range(total_pages))

    # Remove skipped pages (skip is 1-based)
    if skip:
        skip_set = {s - 1 for s in skip if 1 <= s <= total_pages}
        pages = [p for p in pages if p not in skip_set]

    # Filter odd/even (based on 1-based position in remaining pages)
    if odd_even == "odd":
        pages = [p for i, p in enumerate(pages) if (i + 1) % 2 == 1]
    elif odd_even == "even":
        pages = [p for i, p in enumerate(pages) if (i + 1) % 2 == 0]

    return pages


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
