import tempfile
from pathlib import Path

from app.core import config
from app.core.db import (
    init_db,
    upsert_document,
    insert_chunk,
    document_exists,
    delete_document,
)


def test_init_and_insert():
    with tempfile.TemporaryDirectory() as td:
        db_path = str(Path(td) / "t.db")
        conn = init_db(db_path)

        tables = {
            r[0]
            for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type IN ('table','virtual')"
            )
        }
        assert "documents" in tables
        assert "chunks" in tables
        assert "vec_chunks" in tables

        doc_id = upsert_document(
            conn, "/x/a.pdf", "hash123", title="Test", folder="/x"
        )
        assert doc_id > 0
        assert document_exists(conn, "hash123") == doc_id

        emb = [0.01] * config.EMBED_DIM
        chunk_id = insert_chunk(conn, doc_id, 1, 2, "hello world", emb)
        assert chunk_id > 0

        rows = conn.execute(
            "SELECT chunk_id, distance FROM vec_chunks "
            "WHERE embedding MATCH ? ORDER BY distance LIMIT 5",
            (b"".join(b"\x0a\xd7\x23\x3c" for _ in range(config.EMBED_DIM)),),
        ).fetchall()
        assert len(rows) >= 1

        delete_document(conn, doc_id)
        assert document_exists(conn, "hash123") is None
        conn.close()
