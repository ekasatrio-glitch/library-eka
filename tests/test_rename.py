import json
import tempfile
from pathlib import Path
from unittest.mock import patch

import fitz

from app.core.db import init_db
from app.ingest.pipeline import ingest_pdf
from app.ingest import rename as rn
from app.ingest import title as ti


def _mk(path: Path, text: str, pages: int = 1):
    doc = fitz.open()
    for i in range(pages):
        page = doc.new_page()
        page.insert_text((72, 72), f"{text} Page {i + 1}", fontsize=10)
    doc.save(str(path))
    doc.close()


def _embed(texts, model=None, base_url=None):
    return [[0.01] * 768 for _ in texts]


# ---- pure string handling (no regex) ----

def test_clean_component_strips_illegal_and_whitespace():
    assert ti.clean_component("  Hello / World : Test  ") == "Hello - World - Test"
    assert ti.clean_component("a\n\nb\tc") == "a b c"
    assert ti.clean_component("...trim-..") == "trim"
    assert ti.clean_component(None) == ""
    assert len(ti.clean_component("x" * 500, max_len=50)) == 50


def test_authors_label_and_filename():
    assert ti.authors_label([]) == "Anon"
    assert ti.authors_label(["Jane Doe"]) == "Doe"
    assert ti.authors_label(["Jane Doe", "John Smith"]) == "Doe dkk."
    name = ti.build_filename(
        {"title": "Quantum: A Study?", "authors": ["Jane Doe"], "year": 2021},
        "{authors} ({year}) - {title}",
    )
    assert name == "Doe (2021) - Quantum- A Study.pdf"
    # Missing year -> n.d., no crash.
    n2 = ti.build_filename({"title": "T", "authors": [], "year": None}, "{authors} ({year}) - {title}")
    assert n2 == "Anon (n.d.) - T.pdf"


def test_extract_meta_offline_uses_llm_only():
    with tempfile.TemporaryDirectory() as td:
        pdf = Path(td) / "x.pdf"
        _mk(pdf, "Some Paper Title here by authors")

        def fake_chat(system, user):
            return json.dumps({"title": "Real Title", "authors": ["A B"], "year": 2019})

        meta = ti.extract_meta(pdf, fake_chat, use_crossref=False)
        assert meta["title"] == "Real Title" and meta["year"] == 2019


# ---- plan / apply / undo, registry-safe ----

def _seed(td: Path):
    db = str(td / "t.db")
    conn = init_db(db)
    pdf = (td / "messy_name.pdf").resolve()  # ingest stores resolved paths
    _mk(pdf, "content for hashing")
    with patch("app.ingest.pipeline.embed_texts", side_effect=_embed):
        ingest_pdf(pdf, conn=conn)
    doc_id = conn.execute("SELECT id FROM documents").fetchone()[0]
    chash = conn.execute("SELECT content_hash FROM documents").fetchone()[0]
    return conn, db, doc_id, chash, pdf


def test_apply_rename_updates_registry_without_reembed_and_undo():
    with tempfile.TemporaryDirectory() as td:
        conn, db, doc_id, chash, pdf = _seed(Path(td))
        n_vec_before = conn.execute("SELECT COUNT(*) FROM vec_chunks").fetchone()[0]

        def fake_chat(system, user):
            return json.dumps({"title": "Clean Title", "authors": ["Jane Doe"], "year": 2020})

        plan = rn.plan_renames(conn, fake_chat, use_crossref=False)
        assert plan[0]["status"] == "rename"
        new_path = Path(plan[0]["new_path"])
        assert new_path.name == "Doe (2020) - Clean Title.pdf"

        res = rn.apply_renames(conn, plan, batch="b1")
        assert len(res["applied"]) == 1 and not res["errors"]

        # File moved on disk.
        assert new_path.exists() and not pdf.exists()
        # Registry path updated; hash unchanged (no re-embed).
        row = conn.execute("SELECT path, content_hash FROM documents WHERE id=?", (doc_id,)).fetchone()
        assert row[0] == str(new_path) and row[1] == chash
        assert conn.execute("SELECT COUNT(*) FROM vec_chunks").fetchone()[0] == n_vec_before
        assert conn.execute("SELECT COUNT(*) FROM chunks WHERE doc_id=?", (doc_id,)).fetchone()[0] > 0

        # Undo restores original path + file.
        u = rn.undo_last(conn)
        assert len(u["reverted"]) == 1
        assert pdf.exists() and not new_path.exists()
        assert conn.execute("SELECT path FROM documents WHERE id=?", (doc_id,)).fetchone()[0] == str(pdf)
        conn.close()


def test_rename_collision_gets_suffix():
    with tempfile.TemporaryDirectory() as td:
        tdp = Path(td)
        db = str(tdp / "t.db")
        conn = init_db(db)
        a, b = tdp / "a.pdf", tdp / "b.pdf"
        _mk(a, "alpha unique content one")
        _mk(b, "beta unique content two")
        with patch("app.ingest.pipeline.embed_texts", side_effect=_embed):
            ingest_pdf(a, conn=conn)
            ingest_pdf(b, conn=conn)

        # Both resolve to the same target name -> second must get a suffix.
        def fake_chat(system, user):
            return json.dumps({"title": "Same Title", "authors": ["X"], "year": 2020})

        plan = rn.plan_renames(conn, fake_chat, use_crossref=False)
        names = sorted(Path(p["new_path"]).name for p in plan if p["status"] == "rename")
        assert names == ["X (2020) - Same Title (2).pdf", "X (2020) - Same Title.pdf"]
        res = rn.apply_renames(conn, plan, batch="c1")
        assert len(res["applied"]) == 2 and not res["errors"]
        # Both files exist, distinct names.
        existing = sorted(p.name for p in tdp.glob("*.pdf"))
        assert existing == ["X (2020) - Same Title (2).pdf", "X (2020) - Same Title.pdf"]
        conn.close()


def test_retitle_document_updates_registry():
    import json
    from app.ingest import title as ti
    with tempfile.TemporaryDirectory() as td:
        conn, db, doc_id, chash, pdf = _seed(Path(td))
        # Heuristic gave a wrong title at ingest.
        conn.execute("UPDATE documents SET title='Open Access' WHERE id=?", (doc_id,))
        conn.commit()

        def fake_chat(system, user):
            return json.dumps({"title": "The Real Paper Title", "authors": ["Jane Doe", "John Roe"], "year": 2021})

        res = ti.retitle_document(conn, doc_id, fake_chat, use_crossref=False)
        assert res["status"] == "updated"
        row = conn.execute("SELECT title, authors, year FROM documents WHERE id=?", (doc_id,)).fetchone()
        assert row[0] == "The Real Paper Title"
        assert row[1] == "Jane Doe; John Roe" and row[2] == 2021
        conn.close()
