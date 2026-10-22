"""Write a CLIP STUDIO PAINT EX multi-page work (.cmc) for page files.

Why: Stage 4 of the rebuild. The page .clip files written by ``split`` only
     become one work in CSP EX once a .cmc next to them lists them in order.
How: A CSP-made .cmc of the same work is the template, so every work-wide
     setting (binding, start page, story info, default page) is kept. Its
     page list (``CanvasNode``, a linked list under the root node) is
     replaced by one node per page file; page nodes copy the template's
     first page node and then get the new link, order and page size.
     The template file is only read.
"""
from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
import re
import sqlite3
import tempfile

from .clip_schema import column_names
from .cmc_reader import PAGE_NODE_TYPE, SQLITE_MAGIC
from .container import open_sqlite_bytes, read_csf_container
from .errors import CspFormatError

PAGE_NUMBER = re.compile(r"(\d+)\.clip$", re.IGNORECASE)


@dataclass(frozen=True)
class PageLink:
    """What a page node records about its page file."""

    file_name: str
    spread: bool
    unit: int
    width: float
    height: float
    resolution: float
    modified: datetime


def page_link(path: str | Path) -> PageLink:
    """Read the size and modification time CSP caches for a page file."""
    file_path = Path(path)
    database = open_sqlite_bytes(read_csf_container(file_path).sqlite_bytes)
    try:
        row = database.execute("SELECT * FROM Canvas").fetchone()
        if row is None:
            raise CspFormatError(f"Canvas row not found: {file_path}")
        spread = bool(row["CanvasDoublePage"]) if "CanvasDoublePage" in row.keys() else False
        return PageLink(
            file_name=file_path.name,
            spread=spread,
            unit=int(row["CanvasUnit"]),
            width=float(row["CanvasWidth"]),
            height=float(row["CanvasHeight"]),
            resolution=float(row["CanvasResolution"]),
            modified=datetime.fromtimestamp(file_path.stat().st_mtime),
        )
    finally:
        database.close()


def write_cmc(template: str | Path, pages: Sequence[str | Path], output: str | Path) -> Path:
    """Write ``output`` (.cmc) listing ``pages`` in order, with ``template``'s settings.

    Every page file must already exist in the folder of ``output``, because
    CSP resolves page links relative to the .cmc.
    """
    output_path = Path(output)
    if not pages:
        raise ValueError("A work needs at least one page")
    links = []
    for page in pages:
        page_path = Path(page)
        if page_path.resolve().parent != output_path.resolve().parent:
            raise ValueError(f"Page {page_path} must be in the folder of {output_path}")
        links.append(page_link(page_path))
    database = _load_template(Path(template))
    try:
        _replace_pages(database, links)
        _save(database, output_path)
    finally:
        database.close()
    return output_path


def _load_template(path: Path) -> sqlite3.Connection:
    with path.open("rb") as handle:
        if handle.read(len(SQLITE_MAGIC)) != SQLITE_MAGIC:
            raise CspFormatError(f"Not a .cmc (SQLite) file: {path}")
    source = sqlite3.connect(f"{path.resolve().as_uri()}?mode=ro&immutable=1", uri=True)
    database = sqlite3.connect(":memory:")
    try:
        source.backup(database)
    finally:
        source.close()
    database.row_factory = sqlite3.Row
    return database


def _replace_pages(database: sqlite3.Connection, links: list[PageLink]) -> None:
    project = database.execute("SELECT * FROM Project").fetchone()
    if project is None:
        raise CspFormatError("Project row not found in the template .cmc")
    root_id = int(project["ProjectRootCanvasNode"])
    base = database.execute("SELECT * FROM CanvasNode WHERE Type = ? ORDER BY MainId LIMIT 1",
                            (PAGE_NODE_TYPE,)).fetchone()
    base_values = dict(zip(base.keys(), tuple(base))) if base is not None else {}
    database.execute("DELETE FROM CanvasNode WHERE MainId != ?", (root_id,))
    node_ids = [node for node in range(1, len(links) + 2) if node != root_id][:len(links)]
    columns = set(column_names(database, "CanvasNode"))
    for position, (node_id, link) in enumerate(zip(node_ids, links)):
        values = dict(base_values)
        values.update(_node_values(link))
        values.update(_PW_ID=node_id, MainId=node_id, Type=PAGE_NODE_TYPE,
                      NextIndex=node_ids[position + 1] if position + 1 < len(node_ids) else 0)
        names = [name for name in values if name in columns]
        database.execute(
            f'INSERT INTO CanvasNode ({", ".join(f"[{name}]" for name in names)}) '
            f'VALUES ({", ".join("?" for _ in names)})',
            [values[name] for name in names],
        )
    root_values = {"FirstChildIndex": node_ids[0], "SelectedIndex": node_ids[0]}
    for name, value in root_values.items():
        if name in columns:
            database.execute(f'UPDATE CanvasNode SET "{name}" = ? WHERE MainId = ?', (value, root_id))
    if "ElemScheme" in {str(row[0]) for row in database.execute("SELECT name FROM sqlite_master")}:
        database.execute("UPDATE ElemScheme SET MaxIndex = ? WHERE TableName = 'CanvasNode'",
                         (max(node_ids + [root_id]),))
    if "MaxCanvasFileIndex" in project.keys():
        database.execute("UPDATE Project SET MaxCanvasFileIndex = ?", (_max_file_index(links),))
    database.commit()


def _node_values(link: PageLink) -> dict[str, object]:
    stamp = link.modified
    return {
        "FirstChildIndex": 0, "SelectedIndex": 0, "CanvasIndex": 0,
        "PageFlag": int(link.spread), "Memo": "", "BookBindMemo": "",
        "LinkPath": f".:{link.file_name}",
        "LinkWriteYear": stamp.year, "LinkWriteMonth": stamp.month, "LinkWriteDay": stamp.day,
        "LinkWriteHour": stamp.hour, "LinkWriteMinute": stamp.minute, "LinkWriteSecond": stamp.second,
        "LinkIsFolder": 0, "LinkUnit": link.unit, "LinkWidth": link.width, "LinkHeight": link.height,
        "LinkResolution": link.resolution,
    }


def _max_file_index(links: list[PageLink]) -> int:
    numbers = [int(match.group(1)) for link in links if (match := PAGE_NUMBER.search(link.file_name))]
    return max(numbers) if numbers else len(links)


def _save(database: sqlite3.Connection, output: Path) -> None:
    """Write the database to ``output`` through a temporary file in the same folder."""
    with tempfile.NamedTemporaryFile(dir=output.parent, suffix=".cmc.tmp", delete=False) as handle:
        temp_path = Path(handle.name)
    try:
        target = sqlite3.connect(temp_path)
        try:
            database.backup(target)
        finally:
            target.close()
        temp_path.replace(output)
    finally:
        temp_path.unlink(missing_ok=True)
