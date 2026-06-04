import tempfile
from pathlib import Path
from unittest.mock import patch

import fitz
from fastapi.testclient import TestClient

from app.core import config as cfg


def make_pdf(path: Path, text: str = "hello world content " * 50, pages: int = 2):
    doc = fitz.open()
    for i in range(pages):
        page = doc.new_page()
        page.insert_text((72, 72), text + f"\npage {i+1}", fontsize=10)
    doc.save(str(path))
    doc.close()


def _embed_stub(texts, model=None, base_url=None):
    out = []
    for _ in texts:
        v = [0.0] * cfg.EMBED_DIM
        v[0] = 1.0
        out.append(v)
    return out


def test_endpoints_smoke(monkeypatch):
    td = tempfile.mkdtemp()
    db = str(Path(td) / "t.db")
    monkeypatch.setattr(cfg, "DB_PATH", db)

    import app.core.db as dbmod
    monkeypatch.setattr(dbmod, "DB_PATH", db)

    from app.web.app import create_app
    pdf = Path(td) / "doc.pdf"
    make_pdf(pdf)

    with patch("app.ingest.pipeline.embed_texts", side_effect=_embed_stub):
        from app.ingest.pipeline import ingest_pdf
        ingest_pdf(pdf)

    app = create_app()
    client = TestClient(app)

    r = client.get("/library")
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["count"] >= 1
    doc_id = data["items"][0]["id"]

    r = client.get(f"/pdf/{doc_id}")
    assert r.status_code == 200
    assert r.headers["content-type"] == "application/pdf"

    r = client.get("/")
    assert r.status_code == 200
    assert "library-eka" in r.text.lower()

    r = client.get("/viewer")
    assert r.status_code == 200

    with patch("app.rag.retriever.embed_one", side_effect=lambda q: _embed_stub([q])[0]), \
         patch("app.rag.ask.chat", return_value="answer [1]"):
        r = client.post("/ask", json={"question": "what?"})
        assert r.status_code == 200, r.text
        res = r.json()
        assert res["answer"].startswith("answer")
        assert len(res["citations"]) >= 1
