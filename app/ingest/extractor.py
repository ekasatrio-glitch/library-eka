from pathlib import Path
from typing import List, Tuple

import fitz


def extract_pages(pdf_path: str | Path) -> List[Tuple[int, str]]:
    """Return list of (page_number_1based, text)."""
    pages: List[Tuple[int, str]] = []
    with fitz.open(str(pdf_path)) as doc:
        for i, page in enumerate(doc, start=1):
            text = page.get_text("text") or ""
            pages.append((i, text))
    return pages


def first_page_text(pdf_path: str | Path) -> str:
    with fitz.open(str(pdf_path)) as doc:
        if doc.page_count == 0:
            return ""
        return doc[0].get_text("text") or ""
