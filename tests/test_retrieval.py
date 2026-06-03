import tempfile
from pathlib import Path
from unittest.mock import patch

import fitz

from app.core.db import backfill_fts, init_db, sparse_search
from app.ingest.pipeline import ingest_pdf


def _mk(path: Path, text: str, pages: int = 2):
    doc = fitz.open()
    for i in range(pages):
        page = doc.new_page()
        page.insert_text((72, 72), f"{text} Page {i + 1}", fontsize=10)
    doc.save(str(path))
    doc.close()


def _embed_stub(texts, model=None, base_url=None):
    out = []
    for t in texts:
        v = [0.0] * 768
        low = t.lower()
        v[0] = 1.0 if "quantum" in low else 0.0
        v[1] = 1.0 if "biology" in low else 0.0
        out.append(v)
    return out


def _seed(td: Path):
    db = str(td / "t.db")
    a, b = td / "quantum.pdf", td / "biology.pdf"
    _mk(a, "quantum entanglement bell inequality measurement")
    _mk(b, "biology cell mitosis dna replication")
    conn = init_db(db)
    with patch("app.ingest.pipeline.embed_texts", side_effect=_embed_stub):
        ingest_pdf(a, conn=conn)
        ingest_pdf(b, conn=conn)
    return conn


def test_fts_in_sync_with_chunks():
    with tempfile.TemporaryDirectory() as td:
        conn = _seed(Path(td))
        nc = conn.execute("SELECT COUNT(*) FROM chunks").fetchone()[0]
        nf = conn.execute("SELECT COUNT(*) FROM chunks_fts").fetchone()[0]
        assert nc == nf and nc >= 2
        conn.close()


def test_sparse_search_keyword():
    with tempfile.TemporaryDirectory() as td:
        conn = _seed(Path(td))
        res = sparse_search(conn, "quantum inequality", 10)
        assert res, "no sparse hits"
        top_text = conn.execute(
            "SELECT text FROM chunks WHERE id = ?", (res[0][0],)
        ).fetchone()[0].lower()
        assert "quantum" in top_text
        conn.close()


def test_delete_keeps_fts_synced():
    with tempfile.TemporaryDirectory() as td:
        conn = _seed(Path(td))
        conn.execute("DELETE FROM chunks WHERE doc_id = 1")
        conn.commit()
        assert sparse_search(conn, "quantum", 10) == []
        conn.close()


def test_backfill_rebuilds_when_out_of_sync():
    with tempfile.TemporaryDirectory() as td:
        conn = _seed(Path(td))
        # Simulate a legacy DB whose FTS index drifted: drop one indexed row.
        cid, ctext = conn.execute("SELECT id, text FROM chunks LIMIT 1").fetchone()
        conn.execute(
            "INSERT INTO chunks_fts(chunks_fts, rowid, text) VALUES ('delete', ?, ?)",
            (cid, ctext),
        )
        conn.commit()
        nc = conn.execute("SELECT COUNT(*) FROM chunks").fetchone()[0]
        # Real indexed count lives in the _docsize shadow table, not COUNT(*).
        assert conn.execute("SELECT COUNT(*) FROM chunks_fts_docsize").fetchone()[0] == nc - 1
        n = backfill_fts(conn)
        assert n == nc
        assert conn.execute("SELECT COUNT(*) FROM chunks_fts_docsize").fetchone()[0] == nc
        assert sparse_search(conn, "quantum", 10), "backfill did not restore index"
        conn.close()
