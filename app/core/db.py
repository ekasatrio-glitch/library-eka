import sqlite3
import struct
from pathlib import Path
from typing import Iterable, Optional

import sqlite_vec

from app.core.config import DB_PATH, EMBED_DIM

SCHEMA = """
CREATE TABLE IF NOT EXISTS documents (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    path TEXT UNIQUE NOT NULL,
    content_hash TEXT NOT NULL,
    title TEXT,
    authors TEXT,
    year INTEGER,
    folder TEXT,
    added_at TEXT DEFAULT CURRENT_TIMESTAMP,
    status TEXT DEFAULT 'pending'
);

CREATE INDEX IF NOT EXISTS idx_documents_hash ON documents(content_hash);
CREATE INDEX IF NOT EXISTS idx_documents_folder ON documents(folder);
CREATE INDEX IF NOT EXISTS idx_documents_year ON documents(year);

CREATE TABLE IF NOT EXISTS chunks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    doc_id INTEGER NOT NULL,
    page_start INTEGER NOT NULL,
    page_end INTEGER NOT NULL,
    text TEXT NOT NULL,
    char_len INTEGER NOT NULL,
    FOREIGN KEY (doc_id) REFERENCES documents(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_chunks_doc ON chunks(doc_id);
"""


def connect(path: Optional[str] = None) -> sqlite3.Connection:
    db_path = Path(path or DB_PATH)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.enable_load_extension(True)
    sqlite_vec.load(conn)
    conn.enable_load_extension(False)
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db(path: Optional[str] = None) -> sqlite3.Connection:
    conn = connect(path)
    conn.executescript(SCHEMA)
    conn.execute(
        f"CREATE VIRTUAL TABLE IF NOT EXISTS vec_chunks USING vec0("
        f"chunk_id INTEGER PRIMARY KEY, embedding FLOAT[{EMBED_DIM}])"
    )
    conn.commit()
    return conn


def serialize_vec(vec: Iterable[float]) -> bytes:
    arr = list(vec)
    return struct.pack(f"{len(arr)}f", *arr)


def document_exists(conn: sqlite3.Connection, content_hash: str) -> Optional[int]:
    row = conn.execute(
        "SELECT id FROM documents WHERE content_hash = ?", (content_hash,)
    ).fetchone()
    return row[0] if row else None


def upsert_document(
    conn: sqlite3.Connection,
    path: str,
    content_hash: str,
    title: Optional[str] = None,
    authors: Optional[str] = None,
    year: Optional[int] = None,
    folder: Optional[str] = None,
    status: str = "pending",
) -> int:
    cur = conn.execute(
        """
        INSERT INTO documents (path, content_hash, title, authors, year, folder, status)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(path) DO UPDATE SET
            content_hash=excluded.content_hash,
            title=COALESCE(excluded.title, documents.title),
            authors=COALESCE(excluded.authors, documents.authors),
            year=COALESCE(excluded.year, documents.year),
            folder=COALESCE(excluded.folder, documents.folder),
            status=excluded.status
        RETURNING id
        """,
        (path, content_hash, title, authors, year, folder, status),
    )
    doc_id = cur.fetchone()[0]
    conn.commit()
    return doc_id


def insert_chunk(
    conn: sqlite3.Connection,
    doc_id: int,
    page_start: int,
    page_end: int,
    text: str,
    embedding: Iterable[float],
) -> int:
    cur = conn.execute(
        "INSERT INTO chunks (doc_id, page_start, page_end, text, char_len) VALUES (?, ?, ?, ?, ?)",
        (doc_id, page_start, page_end, text, len(text)),
    )
    chunk_id = cur.lastrowid
    conn.execute(
        "INSERT INTO vec_chunks (chunk_id, embedding) VALUES (?, ?)",
        (chunk_id, serialize_vec(embedding)),
    )
    conn.commit()
    return chunk_id


def delete_chunks(conn: sqlite3.Connection, doc_id: int) -> None:
    """Remove all chunks + vec rows for a document (used before re-ingest)."""
    conn.execute(
        "DELETE FROM vec_chunks WHERE chunk_id IN (SELECT id FROM chunks WHERE doc_id = ?)",
        (doc_id,),
    )
    conn.execute("DELETE FROM chunks WHERE doc_id = ?", (doc_id,))
    conn.commit()


def set_document_status(conn: sqlite3.Connection, doc_id: int, status: str) -> None:
    conn.execute("UPDATE documents SET status = ? WHERE id = ?", (status, doc_id))
    conn.commit()


def delete_document(conn: sqlite3.Connection, doc_id: int) -> None:
    conn.execute(
        "DELETE FROM vec_chunks WHERE chunk_id IN (SELECT id FROM chunks WHERE doc_id = ?)",
        (doc_id,),
    )
    conn.execute("DELETE FROM chunks WHERE doc_id = ?", (doc_id,))
    conn.execute("DELETE FROM documents WHERE id = ?", (doc_id,))
    conn.commit()
