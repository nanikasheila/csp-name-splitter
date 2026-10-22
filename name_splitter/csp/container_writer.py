"""Write CSF chunk containers (.clip) from a database and external chunks.

Why: Stage 3 writes page .clip files by editing a CSP-made template. The
     edited SQLite database and the new or kept external chunks must be put
     back into the container exactly the way CSP lays it out.
How: Observed layout (big endian)::

         "CSFCHUNK" u64 file size  u64 24
         CHNKHead  u64 40: u64 256, u64 offset of the CHNKSQLi chunk, u64 16, 16-byte file id
         CHNKExta  u64 n:  u64 40, 40-char external id, payload   (repeated)
         CHNKSQLi  u64 n:  SQLite database image
         CHNKFoot  u64 0

     ``ExternalChunk.Offset`` holds the file position of each CHNKExta
     header. Because the external chunks come before the database, their
     offsets do not depend on the database size.
"""
from __future__ import annotations

from pathlib import Path
import sqlite3
import struct
import tempfile

from .container import (
    CHUNK_EXTERNAL,
    CHUNK_FOOTER,
    CHUNK_HEAD,
    CHUNK_SQLITE,
    CHUNK_HEADER_SIZE,
    EXTERNAL_ID_LENGTH,
    FILE_HEADER_SIZE,
    FILE_MAGIC,
    CsfContainer,
)
from .errors import CspFormatError

HEAD_VERSION = 256
HEAD_ID_LENGTH = 16
HEAD_BODY = struct.Struct(">QQQ16s")


def head_file_id(container: CsfContainer) -> bytes:
    """Return the 16-byte file id stored in a container's CHNKHead chunk."""
    head = next((chunk for chunk in container.chunks if chunk.tag == CHUNK_HEAD.decode()), None)
    if head is None or head.body_length != HEAD_BODY.size:
        raise CspFormatError(f"Unexpected CHNKHead chunk in {container.path}")
    file_id: bytes = HEAD_BODY.unpack_from(container.data, head.body_offset)[3]
    return file_id


def assemble_container(database: sqlite3.Connection, externals: list[tuple[str, bytes]],
                       file_id: bytes) -> bytes:
    """Build container bytes; updates ``ExternalChunk`` offsets in ``database``.

    ``externals`` is written in the given order. Rows of ``ExternalChunk``
    whose id is not in ``externals`` are removed, new ids are added.
    """
    if len(file_id) != HEAD_ID_LENGTH:
        raise ValueError("file_id must be 16 bytes")
    head_chunk_size = CHUNK_HEADER_SIZE + HEAD_BODY.size
    offset = FILE_HEADER_SIZE + head_chunk_size
    external_chunks: list[bytes] = []
    offsets: dict[str, int] = {}
    for external_id, payload in externals:
        encoded_id = external_id.encode("ascii")
        if len(encoded_id) != EXTERNAL_ID_LENGTH:
            raise ValueError(f"External id must be {EXTERNAL_ID_LENGTH} characters: {external_id!r}")
        body = struct.pack(">Q", EXTERNAL_ID_LENGTH) + encoded_id + payload
        chunk = CHUNK_EXTERNAL + struct.pack(">Q", len(body)) + body
        offsets[external_id] = offset
        external_chunks.append(chunk)
        offset += len(chunk)
    _update_external_index(database, offsets)
    sqlite_bytes = serialize_database(database)
    head = CHUNK_HEAD + struct.pack(">Q", HEAD_BODY.size) + HEAD_BODY.pack(
        HEAD_VERSION, offset, HEAD_ID_LENGTH, file_id)
    sqlite_chunk = CHUNK_SQLITE + struct.pack(">Q", len(sqlite_bytes)) + sqlite_bytes
    footer = CHUNK_FOOTER + struct.pack(">Q", 0)
    body = head + b"".join(external_chunks) + sqlite_chunk + footer
    return FILE_MAGIC + struct.pack(">QQ", FILE_HEADER_SIZE + len(body), FILE_HEADER_SIZE) + body


def serialize_database(database: sqlite3.Connection) -> bytes:
    """Return the database image (``Connection.serialize`` or a backup copy)."""
    database.commit()
    if hasattr(database, "serialize"):
        return bytes(database.serialize())
    with tempfile.TemporaryDirectory() as folder:
        path = Path(folder) / "clip.sqlite"
        target = sqlite3.connect(str(path))
        try:
            database.backup(target)
        finally:
            target.close()
        return path.read_bytes()


def _update_external_index(database: sqlite3.Connection, offsets: dict[str, int]) -> None:
    existing = {str(row[0]) for row in database.execute("SELECT ExternalID FROM ExternalChunk")}
    for external_id in existing - offsets.keys():
        database.execute("DELETE FROM ExternalChunk WHERE ExternalID = ?", (external_id,))
    for external_id, offset in offsets.items():
        if external_id in existing:
            database.execute("UPDATE ExternalChunk SET Offset = ? WHERE ExternalID = ?", (offset, external_id))
        else:
            database.execute("INSERT INTO ExternalChunk (ExternalID, Offset) VALUES (?, ?)", (external_id, offset))
