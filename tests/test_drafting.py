import tempfile
from pathlib import Path
from unittest.mock import patch

import fitz

from app.core.db import init_db
from app.ingest.pipeline import ingest_pdf
from app.rag.drafting import draft_paragraph


def make_pdf(path: Path, text: str, pages: int = 1):
    doc = fitz.open()
    for i in range(pages):
        page = doc.new_page()
        # insert_textbox fills the whole page so PyMuPDF extracts substantial text
        # (insert_text clips at page bounds and produces very little text).
        page.insert_textbox(page.rect, f"{text}\nPage {i+1}", fontsize=8)
    doc.save(str(path))
    doc.close()


def _embed_stub(texts, model=None, base_url=None):
    return [[1.0] + [0.0] * 767 for _ in texts]


def test_vancouver_draft():
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        db = str(root / "t.db")
        a = root / "a.pdf"
        make_pdf(a, "Vaccine efficacy mRNA")
        conn = init_db(db)
        with patch("app.ingest.pipeline.embed_texts", side_effect=_embed_stub):
            ingest_pdf(a, conn=conn)

        with patch("app.rag.retriever.embed_one", side_effect=lambda q: _embed_stub([q])[0]), \
             patch("app.rag.drafting.chat", return_value="mRNA vaksin efektif (1). Bukti uji klinis (1)."):
            res = draft_paragraph("mRNA vaksin", style="vancouver", top_k=3, conn=conn)

        assert "(1)" in res["paragraph"]
        assert res["style"] == "vancouver"
        assert len(res["references"]) >= 1
        assert res["references"][0].startswith("1. ")
        conn.close()


def test_apa_draft_style():
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        db = str(root / "t.db")
        a = root / "a.pdf"
        make_pdf(a, "Cell biology 2022")
        conn = init_db(db)
        with patch("app.ingest.pipeline.embed_texts", side_effect=_embed_stub):
            ingest_pdf(a, conn=conn)

        with patch("app.rag.retriever.embed_one", side_effect=lambda q: _embed_stub([q])[0]), \
             patch("app.rag.drafting.chat", return_value="Sel terdiri organel (Anon, 2022)."):
            res = draft_paragraph("biologi sel", style="apa", top_k=3, conn=conn)

        assert res["style"] == "apa"
        assert res["references"]
        conn.close()


def test_draft_vancouver_marks_cited():
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        db = str(root / "t.db")
        a = root / "a.pdf"
        make_pdf(a, "Vaccine efficacy mRNA clinical trial evidence " * 100, pages=4)
        conn = init_db(db)
        with patch("app.ingest.pipeline.embed_texts", side_effect=_embed_stub):
            ingest_pdf(a, conn=conn)

        with patch("app.rag.retriever.embed_one", side_effect=lambda q: _embed_stub([q])[0]), \
             patch("app.rag.drafting.chat", return_value="Sintesis bukti menunjukkan efek (2)."):
            res = draft_paragraph("mRNA vaksin", style="vancouver", top_k=3, conn=conn)

        cits = res["citations"]
        assert len(cits) >= 2, "need >=2 retrieved chunks for this test"
        assert all("cited" in c for c in cits)
        assert [c["cited"] for c in cits] == [c["n"] == 2 for c in cits]
        conn.close()


def test_draft_apa_keeps_all_cited():
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        db = str(root / "t.db")
        a = root / "a.pdf"
        make_pdf(a, "Cell biology 2022", pages=2)
        conn = init_db(db)
        with patch("app.ingest.pipeline.embed_texts", side_effect=_embed_stub):
            ingest_pdf(a, conn=conn)

        with patch("app.rag.retriever.embed_one", side_effect=lambda q: _embed_stub([q])[0]), \
             patch("app.rag.drafting.chat", return_value="Sel terdiri organel (Anon, 2022)."):
            res = draft_paragraph("biologi sel", style="apa", top_k=3, conn=conn)

        # APA has no numeric markers -> everything stays cited=True
        # (the literal "(2022)" is out of range and must be ignored).
        assert all(c["cited"] for c in res["citations"])
        conn.close()
