"""Opt-in Docling extraction test. Skips if docling isn't installed or its models
can't load (offline CI). The rest of the suite uses pymupdf via conftest."""

import tempfile
from pathlib import Path

import fitz
import pytest

from app.core import config
from app.ingest import extractor


def _mk(path: Path, lines, pages=1):
    doc = fitz.open()
    for _ in range(pages):
        page = doc.new_page()
        y = 72
        for ln in lines:
            page.insert_text((72, y), ln, fontsize=11)
            y += 16
    doc.save(str(path))
    doc.close()


def test_docling_extracts_pages_with_numbers(monkeypatch):
    pytest.importorskip("docling")
    monkeypatch.setattr(config, "EXTRACTOR", "docling")

    with tempfile.TemporaryDirectory() as td:
        pdf = Path(td) / "doc.pdf"
        _mk(pdf, ["Introduction to widgets", "Widgets are useful devices."], pages=2)
        try:
            pages = extractor.extract_pages(pdf)
        except Exception as e:
            pytest.skip(f"docling models unavailable: {e}")

        assert pages, "no pages extracted"
        # Output shape preserved: list of (page_no, text), 1-indexed, ascending.
        nums = [p[0] for p in pages]
        assert nums == sorted(nums)
        assert all(isinstance(p[0], int) and p[0] >= 1 for p in pages)
        assert any("widget" in (p[1] or "").lower() for p in pages)


def test_extractor_falls_back_to_pymupdf_on_docling_error(monkeypatch):
    monkeypatch.setattr(config, "EXTRACTOR", "docling")

    def boom(_path):
        raise RuntimeError("model missing")

    monkeypatch.setattr(extractor, "_extract_docling", boom)

    with tempfile.TemporaryDirectory() as td:
        pdf = Path(td) / "d.pdf"
        _mk(pdf, ["Hello world from pymupdf fallback."], pages=2)
        pages = extractor.extract_pages(pdf)
        assert len(pages) == 2  # pymupdf backend produced output
        assert "hello world" in pages[0][1].lower()
