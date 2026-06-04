import tempfile
from pathlib import Path
from unittest.mock import patch

import fitz

from app.core import config
from app.core import projects as proj
from app.core.db import ensure_column, init_db
from app.ingest.pipeline import ingest_pdf


def _mk(path: Path, text: str):
    d = fitz.open(); p = d.new_page(); p.insert_text((72, 72), text, fontsize=10)
    d.save(str(path)); d.close()


def _embed(texts, model=None, base_url=None):
    return [[0.01] * config.EMBED_DIM for _ in texts]


def test_slugify():
    assert proj.slugify("Skripsi HES") == "skripsi-hes"
    assert proj.slugify("Méta-Analisis: RCT!!") == "meta-analisis-rct"
    assert proj.slugify("   ") == "project"


def test_project_for_path_matches_subfolder():
    with tempfile.TemporaryDirectory() as td:
        conn = init_db(str(Path(td) / "t.db"))
        base = Path(td) / "base"
        f1 = base / "1-alpha"; f1.mkdir(parents=True)
        f2 = base / "2-beta"; f2.mkdir(parents=True)
        p1 = proj.create_project(conn, "alpha")
        p2 = proj.create_project(conn, "beta")
        proj.set_folder_path(conn, p1, str(f1))
        proj.set_folder_path(conn, p2, str(f2))

        assert proj.project_for_path(conn, str(f1 / "x.pdf")) == p1
        assert proj.project_for_path(conn, str(f2 / "sub" / "y.pdf")) == p2
        assert proj.project_for_path(conn, str(base / "loose.pdf")) is None
        conn.close()


def test_ensure_column_migrates_legacy_projects_table():
    with tempfile.TemporaryDirectory() as td:
        import sqlite3
        db = str(Path(td) / "legacy.db")
        # Simulate a pre-feature projects table (no folder_path).
        raw = sqlite3.connect(db)
        raw.execute("CREATE TABLE projects (id INTEGER PRIMARY KEY, name TEXT, description TEXT, created_at TEXT)")
        raw.execute("INSERT INTO projects (name) VALUES ('old')")
        raw.commit(); raw.close()

        conn = init_db(db)  # runs ensure_column migration
        cols = [r[1] for r in conn.execute("PRAGMA table_info(projects)").fetchall()]
        assert "folder_path" in cols
        assert proj.get_project(conn, 1)["folder_path"] is None
        conn.close()


def test_create_project_endpoint_creates_folder(tmp_path, monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    import app.core.db as dbmod
    import app.web.projects_routes as pr

    db = str(tmp_path / "f.db")
    monkeypatch.setattr(dbmod, "DB_PATH", db)
    monkeypatch.setattr(pr, "PROJECTS_DIR", str(tmp_path / "base"))
    init_db(db).close()

    app = FastAPI(); app.include_router(pr.router)
    client = TestClient(app)

    r = client.post("/projects", json={"name": "Skripsi HES"})
    assert r.status_code == 200
    fp = r.json()["folder_path"]
    pid = r.json()["id"]
    assert fp.endswith(f"{pid}-skripsi-hes")
    assert Path(fp).is_dir()


def test_watcher_worker_links_pdf_in_project_folder(tmp_path, monkeypatch):
    import queue
    import threading
    from app.core import config
    from app.ingest import watcher as w

    monkeypatch.setattr(config, "EXTRACTOR", "pymupdf")
    db = str(tmp_path / "w.db")
    conn = init_db(db)
    pid = proj.create_project(conn, "proj one")
    folder = tmp_path / "base" / f"{pid}-proj-one"
    folder.mkdir(parents=True)
    proj.set_folder_path(conn, pid, str(folder))
    conn.close()

    pdf = folder / "paper.pdf"
    _mk(pdf, "alpha quantum content for linking")

    q: "queue.Queue" = queue.Queue()
    stop = threading.Event()
    with patch("app.ingest.pipeline.embed_texts", side_effect=_embed), \
         patch("app.ingest.watcher._wait_stable", return_value=True):
        t = threading.Thread(target=w._worker, args=(q, stop, w._InFlight(), db), daemon=True)
        t.start()
        q.put(pdf)
        q.join()
        stop.set(); q.put(None); t.join(timeout=5)

    conn = init_db(db)
    # Ingested into corpus AND linked to the project.
    assert conn.execute("SELECT COUNT(*) FROM documents").fetchone()[0] == 1
    assert proj.project_doc_ids(conn, pid)  # non-empty -> linked
    conn.close()
