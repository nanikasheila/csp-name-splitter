"""CSF chunk container reader shared by CLIP STUDIO PAINT .clip files.

Why: A .clip file is not a plain database. It is a chunked container
     ("CSFCHUNK") that wraps an SQLite database (layer and canvas metadata)
     and a set of external binary chunks (compressed pixel blocks, vector
     data). Every higher-level reader needs this container parsed first.
How: Walks the big-endian chunk headers once, records where each chunk
     lives, and exposes the embedded SQLite database as a read-only
     connection. The input file is never modified.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import sqlite3
import struct
import tempfile

from .errors import CspFormatError

FILE_MAGIC = b"CSFCHUNK"
CHUNK_HEADER_SIZE = 16
FILE_HEADER_SIZE = 24
EXTERNAL_ID_LENGTH = 40

CHUNK_HEAD = b"CHNKHead"
CHUNK_EXTERNAL = b"CHNKExta"
CHUNK_SQLITE = b"CHNKSQLi"
CHUNK_FOOTER = b"CHNKFoot"


@dataclass(frozen=True)
class ChunkLocation:
    """Position of one chunk body inside the container file."""

    tag: str
    header_offset: int
    body_offset: int
    body_length: int


@dataclass(frozen=True)
class CsfContainer:
    """Parsed CSF container: raw bytes plus the index of its chunks."""

    path: Path
    data: bytes
    chunks: tuple[ChunkLocation, ...]
    external_chunks: dict[str, ChunkLocation]

    @property
    def sqlite_bytes(self) -> bytes:
        """Return the embedded SQLite database image."""
        for chunk in self.chunks:
            if chunk.tag == CHUNK_SQLITE.decode():
                return self.data[chunk.body_offset:chunk.body_offset + chunk.body_length]
        raise CspFormatError(f"SQLite chunk not found: {self.path}")

    def external_payload(self, external_id: str) -> bytes | None:
        """Return the payload of an external chunk (after its id header).

        Returns None when the id is not stored in the file, which CSP uses
        for offscreens that have no pixel data (for example an empty layer).
        """
        chunk = self.external_chunks.get(external_id)
        if chunk is None:
            return None
        body = self.data[chunk.body_offset:chunk.body_offset + chunk.body_length]
        # Body layout: u64 id length (40) + id + payload
        return body[8 + EXTERNAL_ID_LENGTH:]


def read_csf_container(path: str | Path) -> CsfContainer:
    """Read a CSF chunk container (.clip) from disk."""
    file_path = Path(path)
    if not file_path.exists():
        raise CspFormatError(f"File not found: {file_path}")
    data = file_path.read_bytes()
    return parse_csf_container(data, file_path)


def parse_csf_container(data: bytes, path: Path | None = None) -> CsfContainer:
    """Parse CSF container bytes into a chunk index."""
    source = path or Path("<memory>")
    if len(data) < FILE_HEADER_SIZE or data[:8] != FILE_MAGIC:
        raise CspFormatError(f"Not a CLIP STUDIO file (missing CSFCHUNK header): {source}")
    declared_size, first_chunk = struct.unpack(">QQ", data[8:24])
    if declared_size != len(data):
        raise CspFormatError(
            f"File size mismatch: header says {declared_size}, actual {len(data)}: {source}"
        )
    chunks: list[ChunkLocation] = []
    externals: dict[str, ChunkLocation] = {}
    position = first_chunk
    while position < len(data):
        if position + CHUNK_HEADER_SIZE > len(data):
            raise CspFormatError(f"Truncated chunk header at {position}: {source}")
        tag = data[position:position + 8]
        if not tag.startswith(b"CHNK"):
            raise CspFormatError(f"Unexpected chunk tag {tag!r} at {position}: {source}")
        (length,) = struct.unpack(">Q", data[position + 8:position + 16])
        body_offset = position + CHUNK_HEADER_SIZE
        if body_offset + length > len(data):
            raise CspFormatError(f"Chunk {tag!r} at {position} overruns the file: {source}")
        location = ChunkLocation(tag.decode("ascii"), position, body_offset, length)
        chunks.append(location)
        if tag == CHUNK_EXTERNAL:
            id_start = body_offset + 8
            external_id = data[id_start:id_start + EXTERNAL_ID_LENGTH].decode("ascii")
            externals[external_id] = location
        if tag == CHUNK_FOOTER:
            break
        position = body_offset + length
    return CsfContainer(path=source, data=data, chunks=tuple(chunks), external_chunks=externals)


def open_sqlite_bytes(database: bytes) -> sqlite3.Connection:
    """Open an SQLite database image as an in-memory connection.

    Why: The database lives inside the container, so it has no path of its
         own. Working on an in-memory copy guarantees the source file is
         never touched.
    How: Uses ``Connection.deserialize`` when available (Python 3.11+),
         otherwise loads a temporary file into memory with the backup API.
    """
    connection = sqlite3.connect(":memory:")
    if hasattr(connection, "deserialize"):
        connection.deserialize(database)
    else:
        _load_database_via_backup(database, connection)
    connection.row_factory = sqlite3.Row
    return connection


def _load_database_via_backup(database: bytes, target: sqlite3.Connection) -> None:
    """Copy an SQLite database image into ``target`` through a temporary file."""
    with tempfile.NamedTemporaryFile(suffix=".sqlite", delete=False) as handle:
        handle.write(database)
        temp_path = Path(handle.name)
    try:
        source = sqlite3.connect(str(temp_path))
        try:
            source.backup(target)
        finally:
            source.close()
    finally:
        temp_path.unlink(missing_ok=True)
