import tempfile
from pathlib import Path
from unittest.mock import patch

import fitz

from app.core import config
from app.core.db import get_meta, init_db
from app.ingest import reingest as ri
from app.ingest.pipeline import ingest_pdf


def _mk(path: Path, text: str, pages: int = 2):
    doc = fitz.open()
    for i in range(pages):
        page = doc.new_page()
        page.insert_text((72, 72), f"{text} Page {i + 1}", fontsize=10)
    doc.save(str(path))
    doc.close()


def _embed(texts, model=None, base_url=None):
    return [[0.02] * config.EMBED_DIM for _ in texts]


def test_reingest_all_rebuilds_chunks_fts_and_is_idempotent():
    with tempfile.TemporaryDirectory() as td:
        tdp = Path(td)
        db = str(tdp / "t.db")
        conn = init_db(db)
        a, b = tdp / "a.pdf", tdp / "b.pdf"
        _mk(a, "alpha content one")
        _mk(b, "beta content two")
        with patch("app.ingest.pipeline.embed_texts", side_effect=_embed):
            ingest_pdf(a, conn=conn)
            ingest_pdf(b, conn=conn)

        doc_rows_before = conn.execute("SELECT id, path, content_hash FROM documents ORDER BY id").fetchall()
        chunks_before = conn.execute("SELECT COUNT(*) FROM chunks").fetchone()[0]

        calls = {"n": 0}

        def counting_embed(texts):
            calls["n"] += 1
            return _embed(texts)

        res = ri.reingest_all(conn, embed_fn=counting_embed)
        assert res["status"] == "done" and res["migrated"] == 2
        assert calls["n"] > 0

        # documents preserved (path, hash, count) — only chunks/vectors rebuilt.
        doc_rows_after = conn.execute("SELECT id, path, content_hash FROM documents ORDER BY id").fetchall()
        assert doc_rows_after == doc_rows_before

        # chunk count sane; FTS5 and vec consistent with chunks.
        n_chunks = conn.execute("SELECT COUNT(*) FROM chunks").fetchone()[0]
        n_vec = conn.execute("SELECT COUNT(*) FROM vec_chunks").fetchone()[0]
        n_fts = conn.execute("SELECT COUNT(*) FROM chunks_fts_docsize").fetchone()[0]
        assert n_chunks > 0 and n_vec == n_chunks and n_fts == n_chunks

        # Migration flag set -> idempotent: second run skips, no new embeds.
        assert get_meta(conn, ri.MIGRATION_KEY) == ri.MIGRATION_TAG
        before = calls["n"]
        res2 = ri.reingest_all(conn, embed_fn=counting_embed)
        assert res2["status"] == "skip" and calls["n"] == before

        # --force re-runs.
        res3 = ri.reingest_all(conn, force=True, embed_fn=counting_embed)
        assert res3["status"] == "done" and calls["n"] > before
        conn.close()


def test_reingest_empty_corpus_is_noop():
    with tempfile.TemporaryDirectory() as td:
        db = str(Path(td) / "t.db")
        conn = init_db(db)
        res = ri.reingest_all(conn, embed_fn=_embed)
        assert res["status"] == "done" and res["total"] == 0 and res["migrated"] == 0
        assert get_meta(conn, ri.MIGRATION_KEY) == ri.MIGRATION_TAG
        conn.close()


def test_reingest_embed_length_mismatch_does_not_lose_chunks():
    """A short embedder result must NOT delete existing chunks or set the flag."""
    with tempfile.TemporaryDirectory() as td:
        db = str(Path(td) / "t.db")
        conn = init_db(db)
        a = Path(td) / "a.pdf"
        # Many rendered lines across pages -> enough chars for multiple chunks.
        doc = fitz.open()
        for _pg in range(3):
            page = doc.new_page()
            tw = fitz.TextWriter(page.rect)
            for ln in range(50):
                tw.append((60, 60 + ln * 14), f"line {ln} alpha beta gamma delta epsilon zeta eta theta")
            tw.write_text(page)
        doc.save(str(a)); doc.close()

        with patch("app.ingest.pipeline.embed_texts", side_effect=_embed):
            ingest_pdf(a, conn=conn)
        chunks_before = conn.execute("SELECT COUNT(*) FROM chunks").fetchone()[0]
        assert chunks_before > 1

        def bad_embed(texts):
            return [[0.0] * config.EMBED_DIM]  # too few vectors (1 < n chunks)

        res = ri.reingest_all(conn, embed_fn=bad_embed)
        assert res["status"] == "partial" and res["errors"] == 1
        # Old chunks intact (delete happens only after a valid embed).
        assert conn.execute("SELECT COUNT(*) FROM chunks").fetchone()[0] == chunks_before
        # Flag NOT set -> a corrected re-run will retry.
        assert get_meta(conn, ri.MIGRATION_KEY) != ri.MIGRATION_TAG
        conn.close()
