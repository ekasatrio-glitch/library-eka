import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import fitz
import pytest

from app.core.db import backfill_fts, init_db, sparse_search
from app.ingest.pipeline import ingest_pdf
from app.rag import reranker
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


def _hit(text):
    return SimpleNamespace(text=text)


def test_rerank_none_is_passthrough():
    hits = [_hit("a"), _hit("b"), _hit("c")]
    out = reranker.rerank("q", hits, top_k=2, backend="none")
    assert [h.text for h in out] == ["a", "b"]


def test_rerank_reorders_and_truncates():
    hits = [_hit("a"), _hit("b"), _hit("c")]
    # Fake backend ranks index 2, then 0, then 1.
    with patch.object(reranker, "_rerank_flashrank", return_value=[2, 0, 1]):
        out = reranker.rerank("q", hits, top_k=2, backend="flashrank")
    assert [h.text for h in out] == ["c", "a"]


def test_rerank_falls_back_on_error():
    hits = [_hit("a"), _hit("b"), _hit("c")]
    with patch.object(reranker, "_rerank_flashrank", side_effect=RuntimeError("no model")):
        out = reranker.rerank("q", hits, top_k=2, backend="flashrank")
    assert [h.text for h in out] == ["a", "b"]  # fusion order preserved


def test_flashrank_live_smoke():
    pytest.importorskip("flashrank")
    hits = [
        _hit("The cat sat on the mat."),
        _hit("Quantum entanglement links distant particles."),
        _hit("Photosynthesis converts light to energy."),
    ]
    try:
        out = reranker.rerank("quantum physics entanglement", hits, top_k=1, backend="flashrank")
    except Exception as e:  # model download blocked in CI/offline
        pytest.skip(f"flashrank model unavailable: {e}")
    assert "quantum" in out[0].text.lower()


def test_reembed_migrates_and_is_idempotent():
    from app.ingest import reembed as reembed_mod
    from app.core.db import get_meta

    calls = {"n": 0}

    def fake_embed(texts, model=None, base_url=None):
        calls["n"] += 1
        return [[0.5] * 8 for _ in texts]  # new dim = 8

    with tempfile.TemporaryDirectory() as td:
        conn = _seed(Path(td))
        db = conn.execute("PRAGMA database_list").fetchone()[2]
        conn.close()
        n_chunks_db = init_db(db).execute("SELECT COUNT(*) FROM chunks").fetchone()[0]

        with patch.object(reembed_mod, "embed_texts", side_effect=fake_embed):
            rc = reembed_mod.reembed("fakemodel", dim=8, batch=2, db_path=db)
            assert rc == 0
            first_calls = calls["n"]
            assert first_calls > 0

            c = init_db(db)
            n_vec = c.execute("SELECT COUNT(*) FROM vec_chunks").fetchone()[0]
            assert n_vec == n_chunks_db
            assert get_meta(c, "embed_model") == "fakemodel"
            assert get_meta(c, "embed_dim") == "8"
            # vec table really is 8-dim now
            assert "FLOAT[8]" in c.execute(
                "SELECT sql FROM sqlite_master WHERE name='vec_chunks'"
            ).fetchone()[0]
            c.close()

            # Second run: same target + complete index -> skip, no new embed calls.
            reembed_mod.reembed("fakemodel", dim=8, batch=2, db_path=db)
            assert calls["n"] == first_calls

            # Force re-embeds.
            reembed_mod.reembed("fakemodel", dim=8, batch=2, db_path=db, force=True)
            assert calls["n"] > first_calls
