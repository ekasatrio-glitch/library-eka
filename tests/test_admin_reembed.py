import tempfile
from pathlib import Path
from unittest.mock import patch

import fitz

from app.core import config
from app.core.db import init_db
from app.ingest.pipeline import ingest_pdf
from app.ingest import reembed as reembed_mod


def _embed_stub(texts, model=None, base_url=None):
    return [[0.01] * config.EMBED_DIM for _ in texts]


def _seed(db: str):
    with tempfile.TemporaryDirectory() as td:
        pdf = Path(td) / "a.pdf"
        doc = fitz.open()
        for i in range(3):
            page = doc.new_page()
            page.insert_textbox(page.rect, ("Quantum entanglement Bell test " * 80), fontsize=9)
        doc.save(str(pdf))
        doc.close()
        conn = init_db(db)
        with patch("app.ingest.pipeline.embed_texts", side_effect=_embed_stub):
            ingest_pdf(pdf, conn=conn)
        n = conn.execute("SELECT COUNT(*) FROM chunks").fetchone()[0]
        conn.close()
        return n


def test_reembed_reports_progress():
    with tempfile.TemporaryDirectory() as td:
        db = str(Path(td) / "t.db")
        n_chunks = _seed(db)
        assert n_chunks >= 1
        calls = []
        with patch("app.ingest.reembed.embed_texts", side_effect=_embed_stub):
            rc = reembed_mod.reembed(
                config.EMBED_MODEL, config.EMBED_DIM, batch=1,
                db_path=db, force=True, progress=lambda done, total: calls.append((done, total)),
            )
        assert rc == 0
        assert calls, "progress was never called"
        assert calls[-1] == (n_chunks, n_chunks)          # finishes at total
        assert [d for d, _ in calls] == sorted(d for d, _ in calls)  # monotonic
