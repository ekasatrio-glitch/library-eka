import tempfile
from pathlib import Path
from unittest.mock import patch

import fitz

from app.core import projects as proj
from app.core.db import init_db
from app.ingest.pipeline import ingest_pdf


def _mk(path: Path, text: str, pages: int = 2):
    doc = fitz.open()
    for i in range(pages):
        page = doc.new_page()
        page.insert_text((72, 72), f"{text} Page {i + 1}", fontsize=10)
    doc.save(str(path))
    doc.close()


def _embed_stub(texts, model=None, base_url=None):
    return [[0.01] * 768 for _ in texts]


def _seed_two_docs(td: Path):
    db = str(td / "t.db")
    conn = init_db(db)
    a, b = td / "a.pdf", td / "b.pdf"
    _mk(a, "alpha quantum")
    _mk(b, "beta biology")
    with patch("app.ingest.pipeline.embed_texts", side_effect=_embed_stub):
        ingest_pdf(a, conn=conn)
        ingest_pdf(b, conn=conn)
    ids = [r[0] for r in conn.execute("SELECT id FROM documents ORDER BY id").fetchall()]
    return conn, ids


def test_project_crud_and_linking_no_duplication():
    with tempfile.TemporaryDirectory() as td:
        conn, ids = _seed_two_docs(Path(td))
        pid = proj.create_project(conn, "HES", "thesis project")
        assert proj.get_project(conn, pid)["name"] == "HES"

        added = proj.add_papers(conn, pid, ids)
        assert added == 2
        # Re-linking is idempotent (no duplication).
        assert proj.add_papers(conn, pid, ids) == 0
        assert sorted(proj.project_doc_ids(conn, pid)) == sorted(ids)

        # Corpus not duplicated: still exactly 2 documents.
        assert conn.execute("SELECT COUNT(*) FROM documents").fetchone()[0] == 2

        proj.remove_paper(conn, pid, ids[0])
        assert proj.project_doc_ids(conn, pid) == [ids[1]]
        # Removing from project leaves the paper in the corpus.
        assert conn.execute("SELECT COUNT(*) FROM documents").fetchone()[0] == 2
        conn.close()


def test_one_paper_in_many_projects():
    with tempfile.TemporaryDirectory() as td:
        conn, ids = _seed_two_docs(Path(td))
        p1 = proj.create_project(conn, "P1")
        p2 = proj.create_project(conn, "P2")
        proj.add_papers(conn, p1, [ids[0]])
        proj.add_papers(conn, p2, [ids[0]])
        assert proj.project_doc_ids(conn, p1) == [ids[0]]
        assert proj.project_doc_ids(conn, p2) == [ids[0]]
        conn.close()


def test_delete_project_cascades_but_keeps_corpus():
    with tempfile.TemporaryDirectory() as td:
        conn, ids = _seed_two_docs(Path(td))
        pid = proj.create_project(conn, "tmp")
        proj.add_papers(conn, pid, ids)
        proj.delete_project(conn, pid)
        assert proj.get_project(conn, pid) is None
        assert conn.execute("SELECT COUNT(*) FROM project_documents").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM documents").fetchone()[0] == 2
        conn.close()


def test_project_api_endpoints(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    import app.core.db as dbmod
    import app.web.projects_routes as pr

    db = str(tmp_path / "api.db")
    monkeypatch.setattr(dbmod, "DB_PATH", db)
    # Seed one corpus doc to import from library.
    conn = init_db(db)
    a = tmp_path / "seed.pdf"
    _mk(a, "gamma history")
    with patch("app.ingest.pipeline.embed_texts", side_effect=_embed_stub):
        ingest_pdf(a, conn=conn)
    seed_id = conn.execute("SELECT id FROM documents").fetchone()[0]
    conn.close()

    from app.web.routes import router as core_router
    from fastapi import FastAPI
    app = FastAPI()
    app.include_router(core_router)
    app.include_router(pr.router)
    client = TestClient(app)

    r = client.post("/projects", json={"name": "Proj", "description": "d"})
    assert r.status_code == 200
    pid = r.json()["id"]

    assert client.get("/projects").json()["projects"][0]["id"] == pid

    r = client.post(f"/projects/{pid}/papers", json={"doc_ids": [seed_id]})
    assert r.status_code == 200 and r.json()["linked"] == 1

    # Upload a new PDF -> ingested into global corpus + linked.
    pdf = tmp_path / "upload.pdf"
    _mk(pdf, "delta economics policy")
    with patch("app.ingest.pipeline.embed_texts", side_effect=_embed_stub):
        with pdf.open("rb") as fh:
            r = client.post(f"/projects/{pid}/upload", files={"file": ("upload.pdf", fh, "application/pdf")})
    assert r.status_code == 200, r.text
    assert len(r.json()["papers"]) == 2

    detail = client.get(f"/projects/{pid}").json()
    assert len(detail["papers"]) == 2

    new_doc = r.json()["doc_id"]
    r = client.delete(f"/projects/{pid}/papers/{new_doc}")
    assert r.status_code == 200 and len(r.json()["papers"]) == 1

    assert client.delete(f"/projects/{pid}").status_code == 200
    assert client.get(f"/projects/{pid}").status_code == 404


def test_scoped_ask_and_nudge(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    from fastapi import FastAPI
    import app.core.db as dbmod
    import app.web.projects_routes as pr

    db = str(tmp_path / "scope.db")
    monkeypatch.setattr(dbmod, "DB_PATH", db)
    conn = init_db(db)
    a, b = tmp_path / "inproj.pdf", tmp_path / "outproj.pdf"
    _mk(a, "quantum entanglement bell")
    _mk(b, "quantum decoherence noise")
    with patch("app.ingest.pipeline.embed_texts", side_effect=_embed_stub):
        ingest_pdf(a, conn=conn)
        ingest_pdf(b, conn=conn)
    ids = [r[0] for r in conn.execute("SELECT id FROM documents ORDER BY id").fetchall()]
    pid = proj.create_project(conn, "P")
    proj.add_papers(conn, pid, [ids[0]])  # only first doc in project
    conn.close()

    app = FastAPI()
    app.include_router(pr.router)
    client = TestClient(app)

    captured = {}

    def fake_ask(question, top_k=6, filters=None, conn=None):
        captured["filters"] = filters
        return {"answer": "ans [1]", "citations": [], "hits": []}

    class FakeHit:
        def __init__(self, doc_id, title):
            self.doc_id, self.title = doc_id, title

    def fake_search(question, top_k=6, conn=None):
        return [FakeHit(ids[0], "inproj"), FakeHit(ids[1], "outproj")]

    with patch("app.rag.ask.ask", side_effect=fake_ask), \
         patch("app.rag.retriever.search", side_effect=fake_search):
        r = client.post(f"/projects/{pid}/ask", json={"question": "quantum?"})
    assert r.status_code == 200
    body = r.json()
    # Scoped: filters restricted to project doc_ids.
    assert captured["filters"] == {"doc_ids": [ids[0]]}
    assert body["scoped"] is True
    # Nudge surfaces the out-of-project doc only.
    assert [n["doc_id"] for n in body["nudge"]] == [ids[1]]

    with patch("app.rag.ask.ask", side_effect=fake_ask), \
         patch("app.rag.retriever.search", side_effect=fake_search):
        r2 = client.post(f"/projects/{pid}/ask", json={"question": "quantum?", "expand": True})
    assert captured["filters"] is None  # expanded -> whole library
    assert r2.json()["scoped"] is False
