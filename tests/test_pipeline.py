import tempfile
from pathlib import Path
from unittest.mock import patch

import fitz

from app.core.db import init_db
from app.ingest.chunker import chunk_pages
from app.ingest.extractor import extract_pages
from app.ingest.metadata import guess_metadata
from app.ingest.pipeline import ingest_pdf, find_pdfs


def make_pdf(path: Path, n_pages: int = 3, words_per_page: int = 400):
    doc = fitz.open()
    for i in range(n_pages):
        page = doc.new_page()
        text = " ".join(f"word{i}_{j}" for j in range(words_per_page))
        page.insert_text((72, 72), f"Page {i+1}\n{text}", fontsize=10)
    doc.save(str(path))
    doc.close()


def test_extract_and_chunk():
    with tempfile.TemporaryDirectory() as td:
        pdf = Path(td) / "a.pdf"
        make_pdf(pdf, n_pages=3)
        pages = extract_pages(pdf)
        assert len(pages) == 3
        assert all(t for _, t in pages)
        chunks = chunk_pages(pages, chunk_tokens=200, overlap_tokens=40)
        assert len(chunks) >= 1
        assert all(c.page_start >= 1 and c.page_end >= c.page_start for c in chunks)


def test_metadata_guess():
    txt = "Awesome Title On Quantum Stuff\nJane Doe, John Smith\nPublished 2023\nAbstract: ..."
    title, authors, year = guess_metadata(txt, "/tmp/foo.pdf")
    assert title and "Quantum" in title
    assert year == 2023


def test_pipeline_idempotent():
    with tempfile.TemporaryDirectory() as td:
        pdf = Path(td) / "doc.pdf"
        make_pdf(pdf, n_pages=2)
        db = str(Path(td) / "t.db")
        conn = init_db(db)

        def fake_embed(texts, model=None, base_url=None):
            return [[0.001 * i] * 768 for i, _ in enumerate(texts, 1)]

        with patch("app.ingest.pipeline.embed_texts", side_effect=fake_embed):
            ok, msg = ingest_pdf(pdf, conn=conn)
            assert ok, msg
            ok2, msg2 = ingest_pdf(pdf, conn=conn)
            assert not ok2 and "skip" in msg2

        rows = conn.execute("SELECT COUNT(*) FROM documents").fetchone()
        assert rows[0] == 1
        n_chunks = conn.execute("SELECT COUNT(*) FROM chunks").fetchone()[0]
        assert n_chunks >= 1
        n_vec = conn.execute("SELECT COUNT(*) FROM vec_chunks").fetchone()[0]
        assert n_vec == n_chunks
        conn.close()


def test_find_pdfs():
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        sub = root / "sub"
        sub.mkdir()
        (root / "a.pdf").write_bytes(b"%PDF-1.4\n")
        (sub / "b.pdf").write_bytes(b"%PDF-1.4\n")
        (root / "ignore.txt").write_text("nope")
        found = find_pdfs([root])
        assert len(found) == 2
