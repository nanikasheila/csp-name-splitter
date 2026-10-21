"""Plan how a name (ネーム) sheet is split into pages, keeping its layers.

Why: Stage 2 of the rebuild. Before writing any .clip, we decide for every
     page cell which layers and which parts of them belong to it, and how
     coordinates map from the sheet to the page canvas. Keeping this as a
     plain data plan makes it testable and lets the user check it (JSON and
     a preview image) before files are generated.
How: Page cells come from :mod:`name_layout`. By default each cell's inner
     frame is scaled uniformly onto the page's trim frame (仕上がり線), centred;
     ``fit="cell"`` fits the whole cell into the canvas instead. Contents are assigned by
     where they are on the sheet:

     - raster layers: every cell that one of their stored 256px blocks
       touches gets a crop of the layer;
     - vector layers: each object goes to the cell holding its bbox centre;
       layers made only of the template rectangles are left out;
     - text layers: each text block with an absolute bbox goes to the cell
       holding its centre. Blocks inside balloons store a bbox relative to
       an unidentified anchor, so such a layer follows its balloons and is
       copied whole when they fall in several cells (with a warning).
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .clip_reader import ClipDocument, ClipLayer
from .name_layout import PageCell, Rect, as_rectangle, detect_page_cells, find_rectangles, template_rectangles

Box = tuple[float, float, float, float]
FITS = ("frame", "cell")


@dataclass(frozen=True)
class CellTransform:
    """Maps sheet pixels to page pixels: ``page = sheet * scale + d``."""

    scale: float
    dx: float
    dy: float

    def map_box(self, box: Box) -> Box:
        return (box[0] * self.scale + self.dx, box[1] * self.scale + self.dy,
                box[2] * self.scale + self.dx, box[3] * self.scale + self.dy)


@dataclass(frozen=True)
class PlannedContent:
    """The part of one source layer that goes onto a page."""

    layer_id: int
    name: str
    kind: str
    folder_path: tuple[str, ...]
    crop: Box | None = None
    items: tuple[int, ...] = ()
    whole_layer: bool = False


@dataclass(frozen=True)
class PlannedPage:
    number: int
    cell: PageCell
    transform: CellTransform
    contents: tuple[PlannedContent, ...]


@dataclass
class SheetPlan:
    page_width: int
    page_height: int
    pages: list[PlannedPage]
    fit: str = "frame"
    trim: Rect | None = None
    template_layer_ids: list[int] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def fit_cell(cell: Rect, page_width: int, page_height: int) -> CellTransform:
    """Uniformly scale ``cell`` to fit the page canvas, centred."""
    scale = min(page_width / cell.width, page_height / cell.height)
    dx = (page_width - cell.width * scale) / 2 - cell.x0 * scale
    dy = (page_height - cell.height * scale) / 2 - cell.y0 * scale
    return CellTransform(scale=scale, dx=dx, dy=dy)


def fit_frame(frame: Rect, trim: Rect) -> CellTransform:
    """Uniformly scale a cell's inner ``frame`` onto the page's ``trim`` frame, centred.

    Why: The inner frame of a name template stands for the finished page
         (仕上がり), so it should land on the trim line of the real page.
    """
    scale = min(trim.width / frame.width, trim.height / frame.height)
    frame_x, frame_y = frame.center
    trim_x, trim_y = trim.center
    return CellTransform(scale=scale, dx=trim_x - frame_x * scale, dy=trim_y - frame_y * scale)


def centered_trim(page_width: int, page_height: int, trim_width: int, trim_height: int) -> Rect:
    """The trim frame of a page, centred on the canvas (CSP's default placement)."""
    x0, y0 = (page_width - trim_width) / 2, (page_height - trim_height) / 2
    return Rect(x0, y0, x0 + trim_width, y0 + trim_height)


def plan_sheet(document: ClipDocument, page_width: int, page_height: int, *,
               order: str = "rtl_ttb", first_page: int = 1, fit: str = "frame",
               trim: Rect | None = None) -> SheetPlan:
    """Build the split plan of one name sheet.

    ``fit="frame"`` maps each cell's inner frame onto ``trim`` (cells without
    an inner frame fall back to ``fit="cell"``); ``fit="cell"`` fits the whole
    cell into the page canvas.
    """
    if fit not in FITS:
        raise ValueError(f"Unknown fit: {fit}")
    rects = find_rectangles(document)
    cells = detect_page_cells(rects, document.canvas.width_px,
                              double_page=document.canvas.is_double_page, order=order)
    plan = SheetPlan(page_width=page_width, page_height=page_height, pages=[], fit=fit, trim=trim)
    if fit == "frame" and trim is None:
        plan.warnings.append("No trim frame size known: cells are fitted to the whole page instead")
    if not cells:
        plan.warnings.append("No page cells found: the sheet has no repeated vector rectangles")
        return plan
    template = template_rectangles(rects)
    per_cell: dict[int, list[PlannedContent]] = {cell.index: [] for cell in cells}
    for layer, path in _leaf_layers(document.root.children, (), True):
        if layer.kind == "vector" and _is_template_layer(document, layer, template):
            plan.template_layer_ids.append(layer.main_id)
            continue
        for index, content in _assign(document, layer, path, cells, plan.warnings):
            per_cell[index].append(content)
    for cell in cells:
        plan.pages.append(PlannedPage(
            number=first_page + cell.index - 1, cell=cell,
            transform=_transform(cell, plan),
            contents=tuple(per_cell[cell.index]),
        ))
    if fit == "frame" and trim is not None and any(cell.frame is None for cell in cells):
        plan.warnings.append("Some cells have no inner frame: they are fitted to the whole page instead")
    return plan


def _transform(cell: PageCell, plan: SheetPlan) -> CellTransform:
    if plan.fit == "frame" and plan.trim is not None and cell.frame is not None:
        return fit_frame(cell.frame, plan.trim)
    return fit_cell(cell.rect, plan.page_width, plan.page_height)


def _leaf_layers(layers: tuple[ClipLayer, ...], path: tuple[str, ...],
                 visible: bool) -> list[tuple[ClipLayer, tuple[str, ...]]]:
    result: list[tuple[ClipLayer, tuple[str, ...]]] = []
    for layer in layers:
        if layer.kind in ("paper", "story_info"):
            continue
        if layer.is_folder:
            result.extend(_leaf_layers(layer.children, path + (layer.name,), visible and layer.visible))
        elif visible and layer.visible:
            result.append((layer, path))
    return result


def _is_template_layer(document: ClipDocument, layer: ClipLayer, template: list[Rect]) -> bool:
    objects = document.vector_objects(layer)
    if not objects:
        return False
    for obj in objects:
        rect = as_rectangle(obj)
        if rect is None:
            return False
        moved = Rect(rect.x0 + layer.offset_x, rect.y0 + layer.offset_y,
                     rect.x1 + layer.offset_x, rect.y1 + layer.offset_y)
        if not any(_near(moved, other) for other in template):
            return False
    return True


def _assign(document: ClipDocument, layer: ClipLayer, path: tuple[str, ...], cells: list[PageCell],
            warnings: list[str]) -> list[tuple[int, PlannedContent]]:
    if layer.kind == "raster":
        boxes = document.occupied_pixel_boxes(layer)
        touched = [cell for cell in cells if any(_overlaps(cell.rect, box) for box in boxes)]
        return [(cell.index, _content(layer, path, crop=_box(cell.rect))) for cell in touched]
    if layer.kind == "vector":
        object_boxes = [_offset_box(obj.bbox, layer) for obj in document.vector_objects(layer)]
        return _group_items(object_boxes, cells, layer, path)
    if layer.kind == "text":
        return _assign_text(document, layer, path, cells, warnings)
    return []


def _assign_text(document: ClipDocument, layer: ClipLayer, path: tuple[str, ...], cells: list[PageCell],
                 warnings: list[str]) -> list[tuple[int, PlannedContent]]:
    balloons = [_offset_box(obj.bbox, layer) for obj in document.vector_objects(layer)]
    if not balloons:
        boxes = [_offset_box(block.bbox, layer) for block in document.text_blocks(layer) if block.bbox]
        return _group_items(boxes, cells, layer, path)
    touched = sorted({cell.index for box in balloons for cell in cells if _holds_center(cell.rect, box)})
    if len(touched) > 1:
        warnings.append(f"Text layer {layer.main_id} ({layer.name!r}) has balloons on pages "
                        f"{touched}; it is copied whole to each of them")
    return [(index, _content(layer, path, whole_layer=True)) for index in touched]


def _content(layer: ClipLayer, path: tuple[str, ...], *, crop: Box | None = None,
             items: tuple[int, ...] = (), whole_layer: bool = False) -> PlannedContent:
    return PlannedContent(layer_id=layer.main_id, name=layer.name, kind=layer.kind, folder_path=path,
                          crop=crop, items=items, whole_layer=whole_layer)


def _group_items(boxes: list[Box], cells: list[PageCell], layer: ClipLayer,
                 path: tuple[str, ...]) -> list[tuple[int, PlannedContent]]:
    grouped: dict[int, list[int]] = {}
    for item, box in enumerate(boxes):
        for cell in cells:
            if _holds_center(cell.rect, box):
                grouped.setdefault(cell.index, []).append(item)
                break
    return [(index, _content(layer, path, items=tuple(items))) for index, items in sorted(grouped.items())]


def _offset_box(box: tuple[int, int, int, int], layer: ClipLayer) -> Box:
    return (box[0] + layer.offset_x, box[1] + layer.offset_y, box[2] + layer.offset_x, box[3] + layer.offset_y)


def _box(rect: Rect) -> Box:
    return (rect.x0, rect.y0, rect.x1, rect.y1)


def _overlaps(rect: Rect, box: Box) -> bool:
    return box[0] < rect.x1 and box[2] > rect.x0 and box[1] < rect.y1 and box[3] > rect.y0


def _holds_center(rect: Rect, box: Box) -> bool:
    x, y = (box[0] + box[2]) / 2, (box[1] + box[3]) / 2
    return rect.x0 <= x < rect.x1 and rect.y0 <= y < rect.y1


def _near(a: Rect, b: Rect) -> bool:
    return all(abs(p - q) <= 3.0 for p, q in zip(a.as_list(), b.as_list()))
