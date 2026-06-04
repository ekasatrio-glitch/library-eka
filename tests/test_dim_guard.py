import tempfile
from pathlib import Path

from fastapi.testclient import TestClient

from app.core.db import init_db
from app.web.app import create_app


def _mismatched_db(path: str):
    conn = init_db(path)
    conn.execute("DROP TABLE vec_chunks")
    conn.execute(
        "CREATE VIRTUAL TABLE vec_chunks USING vec0(chunk_id INTEGER PRIMARY KEY, embedding FLOAT[8])"
    )
    conn.commit()
    conn.close()


def test_ask_returns_409_on_dim_mismatch(monkeypatch):
    with tempfile.TemporaryDirectory() as td:
        db = str(Path(td) / "t.db")
        _mismatched_db(db)
        monkeypatch.setattr("app.core.db.DB_PATH", db)
        client = TestClient(create_app())
        r = client.post("/ask", json={"question": "apa itu sedasi?"})
        assert r.status_code == 409
        assert "reembed" in r.json()["detail"].lower()
