import tempfile
from pathlib import Path
from unittest.mock import patch

import fitz

from app.core.db import init_db
from app.ingest.pipeline import ingest_pdf
from app.rag.ask import ask
from app.rag.retriever import search


def make_pdf(path: Path, text: str, pages: int = 1):
    doc = fitz.open()
    for i in range(pages):
        page = doc.new_page()
        page.insert_text((72, 72), f"{text}\nPage {i+1}", fontsize=10)
    doc.save(str(path))
    doc.close()


def _embed_stub(texts, model=None, base_url=None):
    # Map a few topic keywords to distinct unit-ish vectors in 768-d.
    out = []
    for t in texts:
        v = [0.0] * 768
        lower = t.lower()
        if "quantum" in lower:
            v[0] = 1.0
        elif "biology" in lower:
            v[1] = 1.0
        elif "history" in lower:
            v[2] = 1.0
        else:
            v[3] = 1.0
        out.append(v)
    return out


def test_search_grounded():
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        db = str(root / "t.db")
        a = root / "quantum.pdf"
        b = root / "biology.pdf"
        make_pdf(a, "Quantum entanglement Bell test inequality measurement", pages=2)
        make_pdf(b, "Biology cell mitosis DNA replication", pages=2)

        conn = init_db(db)
        with patch("app.ingest.pipeline.embed_texts", side_effect=_embed_stub):
            ok, _ = ingest_pdf(a, conn=conn)
            assert ok
            ok2, _ = ingest_pdf(b, conn=conn)
            assert ok2

        with patch("app.rag.retriever.embed_one", side_effect=lambda q: _embed_stub([q])[0]):
            hits = search("quantum entanglement", top_k=3, conn=conn)
        assert hits, "no hits"
        assert any("quantum" in (h.title or "").lower() or "quantum" in h.text.lower() for h in hits)
        conn.close()


def test_ask_with_mock_llm():
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        db = str(root / "t.db")
        a = root / "quantum.pdf"
        make_pdf(a, "Quantum entanglement Bell test inequality measurement", pages=2)
        conn = init_db(db)
        with patch("app.ingest.pipeline.embed_texts", side_effect=_embed_stub):
            ingest_pdf(a, conn=conn)

        def fake_chat(system, user, **kw):
            return "Quantum entanglement is correlation [1]."

        with patch("app.rag.retriever.embed_one", side_effect=lambda q: _embed_stub([q])[0]), \
             patch("app.rag.ask.chat", side_effect=fake_chat):
            res = ask("what is entanglement?", top_k=2, conn=conn)

        assert res["answer"].startswith("Quantum")
        assert len(res["citations"]) >= 1
        cit = res["citations"][0]
        for k in ("n", "doc_id", "title", "page_start", "page_end", "path"):
            assert k in cit
        conn.close()
