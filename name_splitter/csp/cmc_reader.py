"""Read a CLIP STUDIO PAINT EX multi-page work (.cmc).

Why: The final output of this tool is a multi-page work: a .cmc file next to
     one .clip per page. Reading existing works tells us exactly how CSP
     records page order, page files and default page settings.
How: A .cmc is a plain SQLite database (no chunk container). ``Project``
     holds work-wide settings and ``CanvasNode`` holds the page list as a
     linked list: the root node's ``FirstChildIndex`` points at the first
     page's ``MainId`` and each page's ``NextIndex`` at the following one.
     Page files are referenced by ``LinkPath`` such as ".:page0001.clip"
     (":" is CSP's portable path separator, "." the .cmc's folder).
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import sqlite3

from .errors import CspFormatError

SQLITE_MAGIC = b"SQLite format 3\x00"
PAGE_NODE_TYPE = 2
CSP_PATH_SEPARATOR = ":"


@dataclass(frozen=True)
class CmcPage:
    """One page entry of a multi-page work."""

    order: int
    main_id: int
    link_path: str
    file_name: str
    page_flag: int
    memo: str


@dataclass(frozen=True)
class CmcDefaultPage:
    """Default page settings used when CSP adds a page."""

    unit: int
    width: float
    height: float
    resolution: float
    is_double_page: bool
    template_name: str


@dataclass(frozen=True)
class CmcProject:
    """Parsed .cmc file."""

    path: Path
    internal_version: str
    story_name: str
    author_name: str
    binding_position: int
    start_page: int
    has_cover: bool
    max_canvas_file_index: int
    default_page: CmcDefaultPage
    pages: tuple[CmcPage, ...]

    def page_file_paths(self) -> list[Path]:
        """Resolve each page's .clip path relative to the .cmc folder."""
        return [self.path.parent / page.file_name for page in self.pages]


def read_cmc(path: str | Path) -> CmcProject:
    """Read a .cmc file without modifying it."""
    file_path = Path(path)
    if not file_path.exists():
        raise CspFormatError(f"File not found: {file_path}")
    with file_path.open("rb") as handle:
        if handle.read(len(SQLITE_MAGIC)) != SQLITE_MAGIC:
            raise CspFormatError(f"Not a .cmc (SQLite) file: {file_path}")
    uri = f"{file_path.resolve().as_uri()}?mode=ro&immutable=1"
    connection = sqlite3.connect(uri, uri=True)
    connection.row_factory = sqlite3.Row
    try:
        project = connection.execute("SELECT * FROM Project").fetchone()
        if project is None:
            raise CspFormatError(f"Project row not found: {file_path}")
        nodes = {int(row["MainId"]): row for row in connection.execute("SELECT * FROM CanvasNode")}
    finally:
        connection.close()
    pages = _ordered_pages(nodes, int(project["ProjectRootCanvasNode"]))
    return CmcProject(
        path=file_path,
        internal_version=str(project["ProjectInternalVersion"] or ""),
        story_name=str(project["ComicStoryStoryName"] or ""),
        author_name=str(project["ComicStoryAuthorName"] or ""),
        binding_position=int(project["ComicBindPosition"] or 0),
        start_page=int(project["ComicStartPage"] or 0),
        has_cover=bool(project["ComicCoverExist"]),
        max_canvas_file_index=int(project["MaxCanvasFileIndex"] or 0),
        default_page=CmcDefaultPage(
            unit=int(project["DefaultPageUnit"] or 0),
            width=float(project["DefaultPageWidth"] or 0),
            height=float(project["DefaultPageHeight"] or 0),
            resolution=float(project["DefaultPageResolution"] or 0),
            is_double_page=bool(project["DefaultPageDoublePage"]),
            template_name=str(project["DefaultPageTemplateName"] or ""),
        ),
        pages=tuple(pages),
    )


def link_path_to_file_name(link_path: str) -> str:
    """Convert a CSP link path like ".:page0001.clip" to "page0001.clip"."""
    parts = [part for part in link_path.split(CSP_PATH_SEPARATOR) if part not in ("", ".")]
    if not parts:
        raise CspFormatError(f"Empty page link path: {link_path!r}")
    return str(Path(*parts))


def _ordered_pages(nodes: dict[int, sqlite3.Row], root_id: int) -> list[CmcPage]:
    if root_id not in nodes:
        raise CspFormatError(f"Root canvas node {root_id} not found")
    pages: list[CmcPage] = []
    seen: set[int] = set()
    node_id = int(nodes[root_id]["FirstChildIndex"] or 0)
    while node_id:
        if node_id in seen or node_id not in nodes:
            raise CspFormatError(f"Broken page link to node {node_id}")
        seen.add(node_id)
        row = nodes[node_id]
        if int(row["Type"]) == PAGE_NODE_TYPE:
            link_path = str(row["LinkPath"] or "")
            pages.append(
                CmcPage(
                    order=len(pages) + 1,
                    main_id=node_id,
                    link_path=link_path,
                    file_name=link_path_to_file_name(link_path),
                    page_flag=int(row["PageFlag"] or 0),
                    memo=str(row["Memo"] or ""),
                )
            )
        node_id = int(row["NextIndex"] or 0)
    return pages
