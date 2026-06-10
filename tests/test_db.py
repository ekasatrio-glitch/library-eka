import tempfile
from pathlib import Path

from app.core import config
from app.core import projects as proj
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


def test_project_framework_table_and_cascade():
    with tempfile.TemporaryDirectory() as td:
        conn = init_db(str(Path(td) / "t.db"))
        pid = proj.create_project(conn, "P")
        conn.execute(
            "INSERT INTO project_framework (project_id, title, dsl, citations, variables) "
            "VALUES (?, ?, ?, ?, ?)",
            (pid, "Judul", "[diteliti] A", "{}", "{}"),
        )
        conn.commit()
        row = conn.execute(
            "SELECT title, dsl FROM project_framework WHERE project_id=?", (pid,)
        ).fetchone()
        assert row == ("Judul", "[diteliti] A")

        # Upsert: second write to same project_id updates, not duplicates.
        conn.execute(
            "INSERT INTO project_framework (project_id, dsl) VALUES (?, ?) "
            "ON CONFLICT(project_id) DO UPDATE SET dsl=excluded.dsl",
            (pid, "[diteliti] B"),
        )
        conn.commit()
        assert conn.execute(
            "SELECT COUNT(*) FROM project_framework WHERE project_id=?", (pid,)
        ).fetchone()[0] == 1

        # CASCADE: deleting the project removes its framework row.
        proj.delete_project(conn, pid)
        assert conn.execute(
            "SELECT COUNT(*) FROM project_framework WHERE project_id=?", (pid,)
        ).fetchone()[0] == 0
        conn.close()
