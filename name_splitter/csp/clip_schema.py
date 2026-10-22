"""Schema helpers for editing the SQLite database inside a .clip file.

Why: CSP creates tables and columns only when a file first needs them (an
     empty page has no ``VectorObjectList`` table). Before copying a vector
     or text layer from a name sheet into a page template, the template must
     gain the same tables and columns, together with their entries in
     CSP's own schema tables, or CSP would not know them.
How: ``ParamScheme`` lists every column with its type and, for id columns,
     the table it links to. ``ElemScheme`` keeps the highest ``MainId`` used
     per table (``MaxIndex``). Missing tables and columns are created from
     the source file's definitions and their scheme rows are copied.
"""
from __future__ import annotations

from dataclasses import dataclass
import sqlite3

PARAM_SCHEME = "ParamScheme"
ELEM_SCHEME = "ElemScheme"
OWNER_CANVAS = 2
OWNER_LAYER = 4
# Self-links (linked lists) that ParamScheme does not list as links.
CHAIN_COLUMNS = {("MipmapInfo", "NextIndex"), ("BrushStyle", "NextIndex")}


@dataclass(frozen=True)
class ColumnInfo:
    table: str
    name: str
    link_table: str | None
    owner_type: int


def table_names(database: sqlite3.Connection) -> set[str]:
    return {str(row[0]) for row in database.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}


def column_names(database: sqlite3.Connection, table: str) -> list[str]:
    return [str(row[1]) for row in database.execute(f'PRAGMA table_info("{table}")')]


def column_infos(database: sqlite3.Connection, table: str) -> dict[str, ColumnInfo]:
    """ParamScheme information for the columns of ``table``."""
    infos: dict[str, ColumnInfo] = {}
    rows = database.execute(
        f"SELECT LabelName, LinkTable, OwnerType FROM {PARAM_SCHEME} WHERE TableName = ?", (table,))
    for label, link, owner in rows:
        link_table = str(link) if link else None
        if (table, str(label)) in CHAIN_COLUMNS:
            link_table = table
        infos[str(label)] = ColumnInfo(table, str(label), link_table, int(owner or 0))
    for table_name, label in CHAIN_COLUMNS:
        if table_name == table and label not in infos:
            infos[label] = ColumnInfo(table, label, table, 0)
    return infos


def external_columns(database: sqlite3.Connection) -> set[tuple[str, str]]:
    """(table, column) pairs whose values are external chunk ids."""
    return {(str(table), str(column))
            for table, column in database.execute("SELECT TableName, ColumnName FROM ExternalTableAndColumnName")}


def merge_schema(target: sqlite3.Connection, source: sqlite3.Connection, tables: list[str],
                 columns: set[str] | None = None) -> None:
    """Give ``target`` every table / column of ``tables`` that ``source`` has.

    With ``columns``, only those columns are added to tables ``target`` already has.
    """
    existing = table_names(target)
    for table in tables:
        if table not in table_names(source):
            continue
        if table not in existing:
            sql = source.execute("SELECT sql FROM sqlite_master WHERE type = 'table' AND name = ?",
                                 (table,)).fetchone()[0]
            target.execute(sql)
            _copy_scheme_rows(target, source, table, None)
            _ensure_elem_scheme(target, source, table)
            continue
        have = set(column_names(target, table))
        for _, name, declared_type, _, default, _ in source.execute(f'PRAGMA table_info("{table}")'):
            if name in have or (columns is not None and name not in columns):
                continue
            definition = f'"{name}" {declared_type}'
            if default is not None:
                definition += f" DEFAULT {default}"
            target.execute(f'ALTER TABLE "{table}" ADD COLUMN {definition}')
            _copy_scheme_rows(target, source, table, str(name))


def allocate_id(database: sqlite3.Connection, table: str) -> int:
    """Return a new ``MainId`` for ``table`` and record it in ElemScheme."""
    row = database.execute(f"SELECT MaxIndex FROM {ELEM_SCHEME} WHERE TableName = ?", (table,)).fetchone()
    used = database.execute(f'SELECT COALESCE(MAX(MainId), 0) FROM "{table}"').fetchone()[0]
    new_id = max(int(row[0]) if row else 0, int(used or 0)) + 1
    if row is None:
        database.execute(f"INSERT INTO {ELEM_SCHEME} (TableName, ElemType, MaxIndex) VALUES (?, 0, ?)",
                         (table, new_id))
    else:
        database.execute(f"UPDATE {ELEM_SCHEME} SET MaxIndex = ? WHERE TableName = ?", (new_id, table))
    return new_id


def _copy_scheme_rows(target: sqlite3.Connection, source: sqlite3.Connection, table: str,
                      column: str | None) -> None:
    columns = [name for name in column_names(source, PARAM_SCHEME) if name != "_PW_ID"]
    common = [name for name in columns if name in set(column_names(target, PARAM_SCHEME))]
    query = f"SELECT {', '.join(common)} FROM {PARAM_SCHEME} WHERE TableName = ?"
    params: tuple[str, ...] = (table,)
    if column is not None:
        query += " AND LabelName = ?"
        params = (table, column)
    present = {str(row[0]) for row in target.execute(
        f"SELECT LabelName FROM {PARAM_SCHEME} WHERE TableName = ?", (table,))}
    placeholders = ", ".join("?" for _ in common)
    label_index = common.index("LabelName")
    for row in source.execute(query, params).fetchall():
        if str(row[label_index]) in present:
            continue
        target.execute(f"INSERT INTO {PARAM_SCHEME} ({', '.join(common)}) VALUES ({placeholders})", tuple(row))


def _ensure_elem_scheme(target: sqlite3.Connection, source: sqlite3.Connection, table: str) -> None:
    if target.execute(f"SELECT 1 FROM {ELEM_SCHEME} WHERE TableName = ?", (table,)).fetchone():
        return
    row = source.execute(f"SELECT ElemType FROM {ELEM_SCHEME} WHERE TableName = ?", (table,)).fetchone()
    target.execute(f"INSERT INTO {ELEM_SCHEME} (TableName, ElemType, MaxIndex) VALUES (?, ?, 0)",
                   (table, int(row[0]) if row else 0))
