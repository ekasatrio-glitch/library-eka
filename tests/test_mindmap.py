import tempfile
from pathlib import Path
from unittest.mock import patch

import fitz

from app.core.db import init_db
from app.ingest.pipeline import ingest_pdf
from app.rag.mindmap import build_mindmap


def make_pdf(path: Path, text: str, pages: int = 1):
    doc = fitz.open()
    for i in range(pages):
        page = doc.new_page()
        page.insert_text((72, 72), f"{text}\nPage {i+1}", fontsize=10)
    doc.save(str(path))
    doc.close()


def _embed_stub(texts, model=None, base_url=None):
    return [[1.0] + [0.0] * 767 for _ in texts]


def test_mindmap_builds_markdown():
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        db = str(root / "t.db")
        make_pdf(root / "a.pdf", "Insulin glucose pancreas regulation")
        conn = init_db(db)
        with patch("app.ingest.pipeline.embed_texts", side_effect=_embed_stub):
            ingest_pdf(root / "a.pdf", conn=conn)

        chat_outputs = iter([
            '["mekanisme insulin", "resistensi insulin", "terapi", "komplikasi"]',
            "# Diabetes\n## Mekanisme\n- Insulin atur glukosa [1]\n## Terapi\n- metformin [1]\n",
        ])

        with patch("app.rag.retriever.embed_one", side_effect=lambda q: _embed_stub([q])[0]), \
             patch("app.rag.mindmap.chat", side_effect=lambda *a, **kw: next(chat_outputs)):
            res = build_mindmap("diabetes", breadth=4, top_k=3, conn=conn)

        assert res["markdown"].startswith("# Diabetes")
        assert "##" in res["markdown"]
        assert len(res["subtopics"]) == 4
        assert len(res["citations"]) >= 1
        conn.close()
