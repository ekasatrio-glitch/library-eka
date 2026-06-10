# tests/test_uploads.py
import time
from pathlib import Path
from unittest.mock import patch

import fitz
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core import config as cfg
from app.core import projects as proj
from app.core.db import init_db


def _embed_stub(texts, model=None, base_url=None):
    return [[0.01] * cfg.EMBED_DIM for _ in texts]


def _pdf_bytes(tmp_path, text):
    d = fitz.open()
    p = d.new_page()
    p.insert_text((72, 72), text, fontsize=10)
    out = tmp_path / "tmp.pdf"
    d.save(str(out))
    d.close()
    return out.read_bytes()


def _app_client(tmp_path, monkeypatch):
    import app.core.db as dbmod
    import app.web.projects_routes as pr
    from app.web import uploads

    db = str(tmp_path / "u.db")
    monkeypatch.setattr(dbmod, "DB_PATH", db)
    monkeypatch.setattr(pr, "UPLOAD_DIR", tmp_path / "uploads")
    conn = init_db(db)
    pid = proj.create_project(conn, "P")
    conn.close()

    app = FastAPI()
    app.include_router(pr.router)
    app.include_router(uploads.router)
    return TestClient(app), pid


def _wait_job(client, job_id, timeout=10.0):
    t0 = time.time()
    j = None
    while time.time() - t0 < timeout:
        r = client.get(f"/uploads/{job_id}")
        assert r.status_code == 200, r.text
        j = r.json()
        if j["finished"]:
            return j
        time.sleep(0.05)
    raise AssertionError(f"upload job did not finish in time; last state: {j}")


def test_upload_returns_job_and_completes(tmp_path, monkeypatch):
    client, pid = _app_client(tmp_path, monkeypatch)
    data = _pdf_bytes(tmp_path, "epidemiologi stunting kabupaten")
    with patch("app.ingest.pipeline.embed_texts", side_effect=_embed_stub):
        r = client.post(f"/projects/{pid}/upload",
                        files={"file": ("a.pdf", data, "application/pdf")})
        assert r.status_code == 202, r.text
        job = _wait_job(client, r.json()["job_id"])
    assert job["error"] is None
    assert job["stage"] == "selesai"
    assert job["doc_id"] is not None
    assert job["already"] is False
    papers = client.get(f"/projects/{pid}/papers").json()["papers"]
    assert len(papers) == 1


def test_upload_duplicate_reports_already(tmp_path, monkeypatch):
    client, pid = _app_client(tmp_path, monkeypatch)
    data = _pdf_bytes(tmp_path, "konten identik xyz")
    with patch("app.ingest.pipeline.embed_texts", side_effect=_embed_stub):
        j1 = _wait_job(client, client.post(
            f"/projects/{pid}/upload",
            files={"file": ("a.pdf", data, "application/pdf")}).json()["job_id"])
        j2 = _wait_job(client, client.post(
            f"/projects/{pid}/upload",
            files={"file": ("b.pdf", data, "application/pdf")}).json()["job_id"])
    assert j1["doc_id"] == j2["doc_id"]
    assert j2["already"] is True and j2["error"] is None
    papers = client.get(f"/projects/{pid}/papers").json()["papers"]
    assert len(papers) == 1


def test_unknown_job_404(tmp_path, monkeypatch):
    client, _ = _app_client(tmp_path, monkeypatch)
    assert client.get("/uploads/nope").status_code == 404


def test_upload_rejects_non_pdf(tmp_path, monkeypatch):
    client, pid = _app_client(tmp_path, monkeypatch)
    r = client.post(f"/projects/{pid}/upload",
                    files={"file": ("notes.txt", b"hi", "text/plain")})
    assert r.status_code == 400
