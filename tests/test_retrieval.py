import tempfile
from pathlib import Path
from unittest.mock import patch

import fitz

from app.core.db import backfill_fts, init_db, sparse_search
from app.ingest.pipeline import ingest_pdf
from app.rag.retriever import hybrid_search, rrf_fuse


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


def test_rrf_fuse_orders_by_combined_rank():
    # id 1: dense#0 + sparse#1 (best combined); id 3: dense#2 + sparse#0.
    fused = rrf_fuse([[1, 2, 3], [3, 1, 4]], top_n=4)
    assert fused[0] == 1
    assert fused[1] == 3
    assert set(fused) == {1, 2, 3, 4}


def test_hybrid_semantic_query():
    with tempfile.TemporaryDirectory() as td:
        conn = _seed(Path(td))
        with patch("app.rag.retriever.embed_one", side_effect=lambda q: _embed_stub([q])[0]):
            hits = hybrid_search("quantum entanglement", top_k=3, conn=conn)
        assert hits and "quantum" in hits[0].text.lower()
        conn.close()


def test_hybrid_exact_term_rescued_by_sparse():
    # Stub dense embedding is blind to "mitosis" (vector all-zero); FTS5 sparse
    # path must surface the biology chunk and RRF must rank it first.
    with tempfile.TemporaryDirectory() as td:
        conn = _seed(Path(td))
        with patch("app.rag.retriever.embed_one", side_effect=lambda q: _embed_stub([q])[0]):
            hits = hybrid_search("mitosis", top_k=3, conn=conn)
        assert hits, "no hybrid hits"
        assert "mitosis" in hits[0].text.lower()
        conn.close()


def test_hybrid_respects_filters_both_paths():
    with tempfile.TemporaryDirectory() as td:
        conn = _seed(Path(td))
        # Tag the biology doc with a year; filter it out.
        conn.execute("UPDATE documents SET year = 2000 WHERE path LIKE '%biology.pdf'")
        conn.execute("UPDATE documents SET year = 2020 WHERE path LIKE '%quantum.pdf'")
        conn.commit()
        with patch("app.rag.retriever.embed_one", side_effect=lambda q: _embed_stub([q])[0]):
            hits = hybrid_search("mitosis", top_k=5, filters={"year_min": 2010}, conn=conn)
        # mitosis lives only in the 2000 biology doc -> filtered out of both paths.
        assert all("mitosis" not in h.text.lower() for h in hits)
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
