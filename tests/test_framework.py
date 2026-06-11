import json
import tempfile
from pathlib import Path
from unittest.mock import patch

import fitz

from app.core import config
from app.core import projects as proj
from app.core.db import init_db
from app.ingest.pipeline import ingest_pdf
from app.rag import framework


def test_parse_title_extracts_variables():
    def fake_chat(system, user):
        return json.dumps({
            "bebas": ["Dosis norepinefrin", "Gula darah sewaktu"],
            "terikat": "Syndecan-1",
            "populasi": "pasien sepsis",
        })

    out = framework.parse_title(
        "Pengaruh dosis norepinefrin dan gula darah terhadap syndecan-1 pada pasien sepsis",
        chat_fn=fake_chat,
    )
    assert out["bebas"] == ["Dosis norepinefrin", "Gula darah sewaktu"]
    assert out["terikat"] == "Syndecan-1"
    assert out["populasi"] == "pasien sepsis"


def test_parse_title_malformed_json_is_fail_safe():
    def fake_chat(system, user):
        return "maaf saya tidak bisa"

    out = framework.parse_title("judul apa pun", chat_fn=fake_chat)
    assert out == {"bebas": [], "terikat": "", "populasi": ""}


# ---- Helpers ----

def _mk(path: Path, text: str, pages: int = 2):
    doc = fitz.open()
    for i in range(pages):
        page = doc.new_page()
        page.insert_text((72, 72), f"{text} Page {i + 1}", fontsize=10)
    doc.save(str(path))
    doc.close()


def _embed_stub(texts, model=None, base_url=None):
    return [[0.01] * config.EMBED_DIM for _ in texts]


class _FakeHit:
    def __init__(self, doc_id, title, ps, pe):
        self.doc_id, self.title, self.page_start, self.page_end = doc_id, title, ps, pe


def _seed_project(td: Path):
    conn = init_db(str(td / "t.db"))
    a = td / "p.pdf"
    _mk(a, "glycocalyx degradation in sepsis norepinephrine")
    with patch("app.ingest.pipeline.embed_texts", side_effect=_embed_stub):
        ingest_pdf(a, conn=conn)
    doc_id = conn.execute("SELECT id FROM documents").fetchone()[0]
    pid = proj.create_project(conn, "P")
    proj.add_papers(conn, pid, [doc_id])
    return conn, pid, doc_id


def _vars():
    return {"bebas": ["Dosis norepinefrin"], "terikat": "Syndecan-1", "populasi": "sepsis"}


# ---- Tests ----

def test_build_framework_grounds_corpus_node_and_verifies_external():
    with tempfile.TemporaryDirectory() as td:
        conn, pid, doc_id = _seed_project(Path(td))

        def fake_search(q, top_k=6, filters=None, conn=None):
            return [_FakeHit(doc_id, "Sepsis paper", 7, 7)]

        calls = {"n": 0}
        def fake_chat(system, user):
            calls["n"] += 1
            if system == framework.BACKBONE_SYS:
                return json.dumps([{
                    "label": "Kerusakan glikokaliks", "relasi": "memicu",
                    "dari": "Dosis norepinefrin", "ke": "Syndecan-1", "src_idx": 0,
                }])
            if system == framework.EXTERNAL_SYS:
                return json.dumps([{
                    "label": "ROS", "relasi": "memicu", "target": "Kerusakan glikokaliks",
                }])
            return "[]"

        def fake_crossref(query, timeout=6.0):
            return {"title": "The endothelial glycocalyx", "authors": ["Chappell D"],
                    "year": 2008, "doi": "10.1/x", "url": "https://doi.org/10.1/x"}

        out = framework.build_framework(
            conn, pid, _vars(),
            chat_fn=fake_chat, search_fn=fake_search, crossref_fn=fake_crossref,
        )
        assert "[diteliti] Dosis norepinefrin" in out["dsl"]
        assert "[diteliti] Syndecan-1" in out["dsl"]
        assert "[latar*] Kerusakan glikokaliks" in out["dsl"]
        cit = out["citations"]["Kerusakan glikokaliks"]
        assert cit["src"] == "korpus" and cit["doc_id"] == doc_id and cit["page"] == 7
        ros = out["citations"]["ROS"]
        assert ros["src"] == "eksternal" and ros["status"] == "perlu_verifikasi"
        assert ros["ref"]["doi"] == "10.1/x"
        assert "Dosis norepinefrin -> Kerusakan glikokaliks : memicu" in out["dsl"]
        # Both backbone and external prompts must have been issued.
        assert calls["n"] == 2
        conn.close()


def test_build_framework_external_miss_is_unverified_not_dropped():
    with tempfile.TemporaryDirectory() as td:
        conn, pid, doc_id = _seed_project(Path(td))

        def fake_search(q, top_k=6, filters=None, conn=None):
            return []

        def fake_chat(system, user):
            if system == framework.EXTERNAL_SYS:
                return json.dumps([{"label": "Albumin", "relasi": "menghambat",
                                    "target": "Syndecan-1"}])
            return "[]"

        def fake_crossref(query, timeout=6.0):
            return None

        out = framework.build_framework(
            conn, pid, _vars(),
            chat_fn=fake_chat, search_fn=fake_search, crossref_fn=fake_crossref,
        )
        alb = out["citations"]["Albumin"]
        assert alb["src"] == "eksternal" and alb["status"] == "tak_terverifikasi"
        assert alb["ref"] is None
        assert "[latar] Albumin" in out["dsl"]
        conn.close()


def test_build_framework_rejects_out_of_range_src_idx():
    with tempfile.TemporaryDirectory() as td:
        conn, pid, doc_id = _seed_project(Path(td))

        def fake_search(q, top_k=6, filters=None, conn=None):
            return [_FakeHit(doc_id, "Sepsis paper", 7, 7)]

        def fake_chat(system, user):
            if system == framework.BACKBONE_SYS:
                return json.dumps([{
                    "label": "Node hantu", "relasi": "memicu",
                    "dari": "Dosis norepinefrin", "ke": "Syndecan-1", "src_idx": 5,
                }])
            return "[]"

        out = framework.build_framework(
            conn, pid, _vars(),
            chat_fn=fake_chat, search_fn=fake_search, crossref_fn=lambda q, timeout=6.0: None,
        )
        assert "Node hantu" not in out["dsl"]
        assert "Node hantu" not in out["citations"]
        conn.close()


def test_build_framework_no_papers_raises():
    with tempfile.TemporaryDirectory() as td:
        conn = init_db(str(Path(td) / "t.db"))
        pid = proj.create_project(conn, "Empty")
        try:
            framework.build_framework(
                conn, pid, _vars(),
                chat_fn=lambda s, u: "[]", search_fn=lambda *a, **k: [],
                crossref_fn=lambda q, timeout=6.0: None,
            )
            assert False, "expected ValueError"
        except ValueError as e:
            assert "naskah tanpa paper" in str(e)
        conn.close()


def test_build_framework_persist_load_roundtrip_and_upsert():
    with tempfile.TemporaryDirectory() as td:
        conn, pid, doc_id = _seed_project(Path(td))
        deps = dict(chat_fn=lambda s, u: "[]",
                    search_fn=lambda *a, **k: [],
                    crossref_fn=lambda q, timeout=6.0: None)
        framework.build_framework(conn, pid, _vars(), **deps)
        loaded = framework.load_framework(conn, pid)
        assert loaded is not None
        assert "[diteliti] Dosis norepinefrin" in loaded["dsl"]
        assert loaded["variables"]["terikat"] == "Syndecan-1"
        framework.build_framework(conn, pid, _vars(), **deps)
        assert conn.execute(
            "SELECT COUNT(*) FROM project_framework WHERE project_id=?", (pid,)
        ).fetchone()[0] == 1
        conn.close()


def test_load_framework_none_after_project_delete():
    with tempfile.TemporaryDirectory() as td:
        conn, pid, doc_id = _seed_project(Path(td))
        framework.build_framework(
            conn, pid, _vars(),
            chat_fn=lambda s, u: "[]", search_fn=lambda *a, **k: [],
            crossref_fn=lambda q, timeout=6.0: None)
        proj.delete_project(conn, pid)
        assert framework.load_framework(conn, pid) is None
        conn.close()


def _client(monkeypatch, td):
    db = str(Path(td) / "web.db")
    from app.core import config as cfg
    monkeypatch.setattr(cfg, "DB_PATH", db)
    import app.core.db as dbmod
    monkeypatch.setattr(dbmod, "DB_PATH", db)
    from fastapi.testclient import TestClient
    from app.web.app import create_app
    return TestClient(create_app()), db


def test_endpoint_parse_title_422_on_empty(monkeypatch):
    with tempfile.TemporaryDirectory() as td:
        client, _ = _client(monkeypatch, td)
        from app.core.db import connect
        conn = connect(); pid = proj.create_project(conn, "P"); conn.close()
        r = client.post(f"/projects/{pid}/framework/parse-title", json={"title": ""})
        assert r.status_code == 422


def test_endpoint_parse_title_ok(monkeypatch):
    with tempfile.TemporaryDirectory() as td:
        client, _ = _client(monkeypatch, td)
        from app.core.db import connect
        conn = connect(); pid = proj.create_project(conn, "P"); conn.close()
        with patch("app.rag.framework.chat", lambda s, u: json.dumps(
                {"bebas": ["A"], "terikat": "B", "populasi": "P"})):
            r = client.post(f"/projects/{pid}/framework/parse-title", json={"title": "judul"})
        assert r.status_code == 200
        assert r.json()["variables"]["terikat"] == "B"


def test_endpoint_build_400_without_papers(monkeypatch):
    with tempfile.TemporaryDirectory() as td:
        client, _ = _client(monkeypatch, td)
        from app.core.db import connect
        conn = connect(); pid = proj.create_project(conn, "P"); conn.close()
        r = client.post(f"/projects/{pid}/framework",
                        json={"variables": _vars(), "title": "judul"})
        assert r.status_code == 400
        assert "naskah tanpa paper" in r.json()["detail"]


def test_endpoint_get_empty_is_not_404(monkeypatch):
    with tempfile.TemporaryDirectory() as td:
        client, _ = _client(monkeypatch, td)
        from app.core.db import connect
        conn = connect(); pid = proj.create_project(conn, "P"); conn.close()
        r = client.get(f"/projects/{pid}/framework")
        assert r.status_code == 200
        body = r.json()
        assert body == {"dsl": "", "citations": {}, "variables": {},
                        "title": "", "updated_at": None}
