"""Split a name sheet .clip into page .clip files (and a .cmc work) in one call.

Why: The ``split`` command and the GUI run the same steps; keeping them here
     means both check inputs the same way and report the same progress.
How: :func:`prepare_split` validates the inputs and builds the plan (fast,
     nothing written), so a caller can show it first. :func:`run_split`
     writes the pages one by one, reporting each through ``on_page`` and
     stopping between pages when ``cancelled`` returns True. Inputs are only
     read; the output folder must differ from every input folder.
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from .clip_reader import ClipDocument, read_clip
from .cmc_writer import work_canvas_values, write_cmc
from .page_writer import write_page
from .split_plan import FITS, SheetPlan, centered_trim, plan_sheet


@dataclass(frozen=True)
class SplitOptions:
    """Everything one split run needs."""

    sheet: Path
    template: Path
    out_dir: Path
    cmc_name: str | None = None
    cmc_template: Path | None = None
    pages: frozenset[int] | None = None
    fit: str = "basic"
    order: str = "rtl_ttb"
    first_page: int = 1
    story_index: int | None = None
    file_name: str = "page{page:04d}.clip"


@dataclass
class PreparedSplit:
    """Inputs read and the plan built; nothing written yet."""

    options: SplitOptions
    sheet: ClipDocument
    plan: SheetPlan
    cmc_template: Path | None


@dataclass
class SplitResult:
    pages: list[Path] = field(default_factory=list)
    cmc: Path | None = None
    warnings: list[str] = field(default_factory=list)
    cancelled: bool = False


def find_cmc_template(sheet: Path) -> Path | None:
    """The .cmc next to the sheet, when there is exactly one."""
    found = sorted(sheet.parent.glob("*.cmc"))
    return found[0] if len(found) == 1 else None


def prepare_split(options: SplitOptions) -> PreparedSplit:
    """Check the inputs and build the split plan.

    Raises:
        FileNotFoundError: an input file does not exist.
        ValueError: an option is invalid (CspFormatError for broken files).
    """
    if options.fit not in FITS:
        raise ValueError(f"Unknown fit: {options.fit}")
    cmc_template = options.cmc_template
    if options.cmc_name and cmc_template is None:
        cmc_template = find_cmc_template(options.sheet)
        if cmc_template is None:
            raise ValueError("A .cmc work needs a template .cmc (none, or several, next to the sheet)")
    if options.cmc_name is not None and not options.cmc_name.strip():
        raise ValueError("The work name is empty")
    inputs = [options.sheet, options.template] + ([cmc_template] if cmc_template else [])
    for path in inputs:
        if not path.exists():
            raise FileNotFoundError(f"Input file not found: {path}")
    if options.out_dir.resolve() in {path.resolve().parent for path in inputs}:
        raise ValueError("The output folder must differ from the input folders so originals are never overwritten")
    sheet, template = read_clip(options.sheet), read_clip(options.template)
    width, height = template.canvas.width_px, template.canvas.height_px
    trim_size = template.canvas.crop_size_px
    trim = centered_trim(width, height, *trim_size) if trim_size else None
    basic_size = template.canvas.basic_size_px
    basic = (centered_trim(width, height, *basic_size, offset=template.canvas.basic_offset_px)
             if basic_size else None)
    plan = plan_sheet(sheet, width, height, order=options.order, first_page=options.first_page,
                      fit=options.fit, trim=trim, basic=basic)
    return PreparedSplit(options=options, sheet=sheet, plan=plan, cmc_template=cmc_template)


def run_split(prepared: PreparedSplit, on_page: Callable[[int, int, Path], None] | None = None,
              cancelled: Callable[[], bool] | None = None) -> SplitResult:
    """Write the planned pages (and the .cmc); ``on_page(done, total, path)`` after each page."""
    options = prepared.options
    make_work = bool(options.cmc_name) and prepared.cmc_template is not None
    pages = [page for page in sorted(prepared.plan.pages, key=lambda item: item.number)
             if (page.number in options.pages if options.pages is not None else make_work or bool(page.contents))]
    overrides: dict[str, object] = {}
    if options.story_index is not None:
        overrides = {"ComicStoryUseStoryIndex": 1, "ComicStoryStoryIndex": options.story_index}
    work_values = work_canvas_values(prepared.cmc_template) if make_work and prepared.cmc_template else {}
    work_values.update(overrides)
    result = SplitResult(warnings=list(prepared.plan.warnings))
    options.out_dir.mkdir(parents=True, exist_ok=True)
    for position, page in enumerate(pages):
        if cancelled is not None and cancelled():
            result.cancelled = True
            return result
        written = write_page(options.template, prepared.sheet, page,
                             options.out_dir / options.file_name.format(page=page.number),
                             page_index=position if make_work else None, canvas_values=work_values)
        result.pages.append(written.path)
        result.warnings.extend(f"page {page.number}: {warning}" for warning in written.warnings)
        if on_page is not None:
            on_page(position + 1, len(pages), written.path)
    if make_work and prepared.cmc_template is not None and options.cmc_name:
        if not result.pages:
            raise ValueError("No pages to put in the work")
        result.cmc = write_cmc(prepared.cmc_template, result.pages, options.out_dir / f"{options.cmc_name}.cmc",
                               project_values=overrides)
    return result
