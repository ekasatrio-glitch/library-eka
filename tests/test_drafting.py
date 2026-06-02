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
        page.insert_text((72, 72), f"{text}\nPage {i+1}", fontsize=10)
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
