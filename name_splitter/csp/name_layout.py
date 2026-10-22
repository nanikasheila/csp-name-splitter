"""Find the page cells of a name (ネーム) sheet from its vector rectangles.

Why: A name sheet holds many small pages on one canvas. Name templates draw
     each page (or each spread) as a vector rectangle, often with a smaller
     rectangle inside for the trim or basic frame. Reading those rectangles
     gives exact page cells instead of guessing a grid from pixels.
How: 1. Collect axis-aligned closed 4-point vector objects from visible
        vector layers (canvas pixels, layer offset applied).
     2. Keep only sizes that repeat (template cells), so panels drawn freely
        inside a page are not mistaken for pages.
     3. A rectangle holding two inner rectangles side by side is a spread
        and becomes two page cells split at its centre; a rectangle holding
        one inner rectangle is one page cell; inner rectangles are kept as
        the cell's ``frame``.
     4. Cells are ordered by sheet half (double-page canvases), then rows
        top to bottom, then right to left (``rtl_ttb``) or left to right.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from .clip_reader import ClipDocument, ClipLayer
from .vector import VectorObject

SIZE_TOLERANCE = 0.02
EDGE_TOLERANCE_PX = 3.0
MIN_REPEAT = 2
ORDERS = ("rtl_ttb", "ltr_ttb")


@dataclass(frozen=True)
class Rect:
    """Axis-aligned rectangle in canvas pixels."""

    x0: float
    y0: float
    x1: float
    y1: float

    @property
    def width(self) -> float:
        return self.x1 - self.x0

    @property
    def height(self) -> float:
        return self.y1 - self.y0

    @property
    def center(self) -> tuple[float, float]:
        return ((self.x0 + self.x1) / 2, (self.y0 + self.y1) / 2)

    def contains(self, other: "Rect") -> bool:
        return (
            other.x0 >= self.x0 - EDGE_TOLERANCE_PX and other.y0 >= self.y0 - EDGE_TOLERANCE_PX
            and other.x1 <= self.x1 + EDGE_TOLERANCE_PX and other.y1 <= self.y1 + EDGE_TOLERANCE_PX
            and (other.width < self.width or other.height < self.height)
        )

    def as_list(self) -> list[float]:
        return [round(self.x0, 2), round(self.y0, 2), round(self.x1, 2), round(self.y1, 2)]


@dataclass(frozen=True)
class PageCell:
    """One page of the name sheet, in reading order."""

    index: int
    rect: Rect
    frame: Rect | None
    spread_side: str | None


def find_rectangles(document: ClipDocument) -> list[Rect]:
    """Return the rectangles drawn on the visible vector layers of a sheet."""
    rects: list[Rect] = []
    for layer in _visible_vector_layers(document.root.children, True):
        for obj in document.vector_objects(layer):
            rect = as_rectangle(obj)
            if rect is not None:
                rects.append(Rect(rect.x0 + layer.offset_x, rect.y0 + layer.offset_y,
                                  rect.x1 + layer.offset_x, rect.y1 + layer.offset_y))
    return _deduplicate(rects)


def detect_page_cells(rects: list[Rect], canvas_width: float, *, double_page: bool,
                      order: str = "rtl_ttb") -> list[PageCell]:
    """Turn template rectangles into ordered page cells."""
    if order not in ORDERS:
        raise ValueError(f"Unknown order: {order}")
    template = template_rectangles(rects)
    cells: list[tuple[Rect, Rect | None, str | None]] = []
    inner_ids = {id(inner) for outer in template for inner in _children(outer, template)}
    for outer in template:
        if id(outer) in inner_ids:
            continue
        inner = _children(outer, template)
        if len(inner) == 2 and _side_by_side(inner[0], inner[1]):
            cells.extend(_split_spread(outer, inner))
        elif len(inner) == 1:
            cells.append((outer, inner[0], None))
        elif not inner:
            cells.append((outer, None, None))
    ordered = _reading_order(cells, canvas_width, double_page, order)
    return [PageCell(index, rect, frame, side) for index, (rect, frame, side) in enumerate(ordered, start=1)]


def detect_document_cells(document: ClipDocument, order: str = "rtl_ttb") -> list[PageCell]:
    """Convenience wrapper: rectangles of ``document`` → ordered page cells."""
    return detect_page_cells(
        find_rectangles(document), document.canvas.width_px,
        double_page=document.canvas.is_double_page, order=order,
    )


def _visible_vector_layers(layers: Iterable[ClipLayer], parent_visible: bool) -> list[ClipLayer]:
    result: list[ClipLayer] = []
    for layer in layers:
        visible = parent_visible and layer.visible
        if layer.kind == "vector" and visible:
            result.append(layer)
        result.extend(_visible_vector_layers(layer.children, visible))
    return result


def as_rectangle(obj: VectorObject) -> Rect | None:
    """Return the axis-aligned rectangle drawn by ``obj`` (layer-local), if it is one."""
    points = list(obj.points)
    if len(points) == 5 and _close(points[0], points[-1]):
        points = points[:4]
    if not obj.closed or len(points) != 4:
        return None
    xs = sorted(point[0] for point in points)
    ys = sorted(point[1] for point in points)
    if xs[1] - xs[0] > EDGE_TOLERANCE_PX or xs[3] - xs[2] > EDGE_TOLERANCE_PX:
        return None
    if ys[1] - ys[0] > EDGE_TOLERANCE_PX or ys[3] - ys[2] > EDGE_TOLERANCE_PX:
        return None
    rect = Rect((xs[0] + xs[1]) / 2, (ys[0] + ys[1]) / 2, (xs[2] + xs[3]) / 2, (ys[2] + ys[3]) / 2)
    return rect if rect.width > EDGE_TOLERANCE_PX and rect.height > EDGE_TOLERANCE_PX else None


def _close(a: tuple[float, float], b: tuple[float, float]) -> bool:
    return abs(a[0] - b[0]) <= EDGE_TOLERANCE_PX and abs(a[1] - b[1]) <= EDGE_TOLERANCE_PX


def _deduplicate(rects: list[Rect]) -> list[Rect]:
    unique: list[Rect] = []
    for rect in rects:
        if not any(_same_box(rect, other) for other in unique):
            unique.append(rect)
    return unique


def _same_box(a: Rect, b: Rect) -> bool:
    return all(abs(p - q) <= EDGE_TOLERANCE_PX for p, q in zip(a.as_list(), b.as_list()))


def _same_size(a: Rect, b: Rect) -> bool:
    return (abs(a.width - b.width) <= SIZE_TOLERANCE * max(a.width, b.width)
            and abs(a.height - b.height) <= SIZE_TOLERANCE * max(a.height, b.height))


def template_rectangles(rects: list[Rect]) -> list[Rect]:
    """Keep rectangles whose size repeats: the page / spread outlines of a template."""
    return [rect for rect in rects if sum(1 for other in rects if _same_size(rect, other)) >= MIN_REPEAT]


def _children(outer: Rect, rects: list[Rect]) -> list[Rect]:
    """Rectangles directly inside ``outer`` (not inside another child)."""
    inside = [rect for rect in rects if rect is not outer and outer.contains(rect)]
    return [rect for rect in inside if not any(other is not rect and other.contains(rect) for other in inside)]


def _side_by_side(a: Rect, b: Rect) -> bool:
    left, right = sorted((a, b), key=lambda rect: rect.x0)
    return left.x1 <= right.x0 + EDGE_TOLERANCE_PX and abs(left.center[1] - right.center[1]) < left.height / 2


def _split_spread(outer: Rect, inner: list[Rect]) -> list[tuple[Rect, Rect | None, str | None]]:
    middle = outer.center[0]
    left_frame, right_frame = sorted(inner, key=lambda rect: rect.x0)
    return [
        (Rect(outer.x0, outer.y0, middle, outer.y1), left_frame, "left"),
        (Rect(middle, outer.y0, outer.x1, outer.y1), right_frame, "right"),
    ]


def _reading_order(cells: list[tuple[Rect, Rect | None, str | None]], canvas_width: float,
                   double_page: bool, order: str) -> list[tuple[Rect, Rect | None, str | None]]:
    rtl = order == "rtl_ttb"
    halves: list[list[tuple[Rect, Rect | None, str | None]]] = [cells]
    if double_page:
        middle = canvas_width / 2
        left = [cell for cell in cells if cell[0].center[0] < middle]
        right = [cell for cell in cells if cell[0].center[0] >= middle]
        halves = [right, left] if rtl else [left, right]
    result: list[tuple[Rect, Rect | None, str | None]] = []
    for half in halves:
        for row in _rows(half):
            result.extend(sorted(row, key=lambda cell: cell[0].center[0], reverse=rtl))
    return result


def _rows(cells: list[tuple[Rect, Rect | None, str | None]]) -> list[list[tuple[Rect, Rect | None, str | None]]]:
    rows: list[list[tuple[Rect, Rect | None, str | None]]] = []
    for cell in sorted(cells, key=lambda item: item[0].y0):
        center_y = cell[0].center[1]
        for row in rows:
            if row[0][0].y0 <= center_y <= row[0][0].y1:
                row.append(cell)
                break
        else:
            rows.append([cell])
    return rows
