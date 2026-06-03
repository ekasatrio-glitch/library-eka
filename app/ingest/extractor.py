"""PDF text extraction.

Output interface (UNCHANGED, consumed by the chunker): extract_pages returns a
list of (page_number_1based, text). Backend is selectable via config.EXTRACTOR:

  docling (default) — correct multi-column reading order, tables exported as
                      markdown inline (so quantitative data is indexed), optional
                      OCR for scanned PDFs. Per-page provenance preserved.
  pymupdf           — fast plain-text fallback (original Phase 2 behavior).

Docling errors (missing models, bad PDF) fall back to pymupdf so ingestion never
hard-fails. Page numbers per chunk stay accurate either way (citations rely on it).
"""

import logging
from collections import defaultdict
from pathlib import Path
from typing import List, Tuple

import fitz

from app.core import config

log = logging.getLogger("extractor")

_CONVERTER = None


def extract_pages(pdf_path: str | Path) -> List[Tuple[int, str]]:
    """Return list of (page_number_1based, text)."""
    if config.EXTRACTOR == "docling":
        try:
            return _extract_docling(pdf_path)
        except Exception as e:  # model/IO/parse failure -> degrade, never abort
            log.warning("docling extraction failed (%s); falling back to pymupdf", e)
    return _extract_pymupdf(pdf_path)


def first_page_text(pdf_path: str | Path) -> str:
    """First-page text for metadata/title hints. Always pymupdf (light, no models)."""
    with fitz.open(str(pdf_path)) as doc:
        if doc.page_count == 0:
            return ""
        return doc[0].get_text("text") or ""


# ---------- pymupdf backend ----------

def _extract_pymupdf(pdf_path: str | Path) -> List[Tuple[int, str]]:
    pages: List[Tuple[int, str]] = []
    with fitz.open(str(pdf_path)) as doc:
        for i, page in enumerate(doc, start=1):
            text = page.get_text("text") or ""
            pages.append((i, text))
    return pages


# ---------- docling backend ----------

def _converter():
    global _CONVERTER
    if _CONVERTER is None:
        from docling.datamodel.base_models import InputFormat
        from docling.datamodel.pipeline_options import PdfPipelineOptions
        from docling.document_converter import DocumentConverter, PdfFormatOption

        opts = PdfPipelineOptions()
        opts.do_ocr = config.OCR
        opts.do_table_structure = True
        _CONVERTER = DocumentConverter(
            format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=opts)}
        )
    return _CONVERTER


def _page_of(item) -> int | None:
    prov = getattr(item, "prov", None)
    if prov:
        return getattr(prov[0], "page_no", None)
    return None


def _text_of(item, doc) -> str:
    # Tables -> markdown so their contents get indexed and can feed matrix fields.
    if item.__class__.__name__ in ("TableItem",) or hasattr(item, "export_to_markdown"):
        try:
            return item.export_to_markdown(doc)
        except TypeError:
            try:
                return item.export_to_markdown()
            except Exception:
                return ""
        except Exception:
            return ""
    return getattr(item, "text", "") or ""


def _extract_docling(pdf_path: str | Path) -> List[Tuple[int, str]]:
    doc = _converter().convert(str(pdf_path)).document
    # iterate_items yields elements in reading order (handles multi-column).
    page_parts: dict[int, list] = defaultdict(list)
    last_page = 1
    for item, _level in doc.iterate_items():
        pg = _page_of(item) or last_page
        last_page = pg
        txt = _text_of(item, doc)
        if txt and txt.strip():
            page_parts[pg].append(txt.strip())
    if not page_parts:
        return []
    return [(pg, "\n".join(parts)) for pg in sorted(page_parts) for parts in [page_parts[pg]]]
