import tempfile
import time
from pathlib import Path
from unittest.mock import patch

import fitz
from fastapi.testclient import TestClient

from app.core import config
from app.core.db import init_db
from app.ingest.pipeline import ingest_pdf
from app.ingest import reembed as reembed_mod
from app.web.app import create_app
from app.web import admin_routes


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


def _reset_job():
    admin_routes._job.update(
        running=False, done=0, total=0, model=None, dim=None, error=None, finished_at=None
    )


def test_reembed_endpoint_runs_to_completion(monkeypatch):
    with tempfile.TemporaryDirectory() as td:
        db = str(Path(td) / "t.db")
        n_chunks = _seed(db)
        monkeypatch.setattr("app.core.db.DB_PATH", db)
        _reset_job()
        client = TestClient(create_app())
        with patch("app.ingest.reembed.embed_texts", side_effect=_embed_stub):
            r = client.post("/admin/reembed/start", json={"force": True})
            assert r.status_code == 200
            assert r.json()["total"] == n_chunks
            # poll until done (bounded)
            for _ in range(100):
                st = client.get("/admin/reembed/status").json()
                if not st["running"]:
                    break
                time.sleep(0.05)
            else:
                raise AssertionError("reembed did not finish in time")
        assert st["error"] is None
        assert st["done"] == n_chunks and st["total"] == n_chunks
        _reset_job()


def test_reembed_rejects_concurrent_start():
    _reset_job()
    admin_routes._job["running"] = True
    client = TestClient(create_app())
    r = client.post("/admin/reembed/start", json={})
    assert r.status_code == 409
    _reset_job()
