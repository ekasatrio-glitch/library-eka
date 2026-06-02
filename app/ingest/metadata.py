import re
from pathlib import Path
from typing import Optional, Tuple

YEAR_RE = re.compile(r"\b(19|20)\d{2}\b")


def guess_metadata(first_page: str, file_path: str | Path) -> Tuple[Optional[str], Optional[str], Optional[int]]:
    """Best-effort (title, authors, year) from first page text + filename."""
    lines = [l.strip() for l in (first_page or "").splitlines() if l.strip()]
    title: Optional[str] = None
    authors: Optional[str] = None
    year: Optional[int] = None

    for line in lines[:15]:
        if 10 < len(line) < 200 and not line.lower().startswith(("abstract", "doi", "http")):
            title = line
            break

    for line in lines[:25]:
        low = line.lower()
        if any(k in low for k in ("author", "by ")):
            authors = line
            break
        if re.search(r"[A-Z][a-z]+\s+[A-Z][a-z]+", line) and "," in line and 5 < len(line) < 250:
            authors = line
            break

    m = YEAR_RE.search(first_page or "")
    if m:
        year = int(m.group(0))
    else:
        m2 = YEAR_RE.search(Path(file_path).stem)
        if m2:
            year = int(m2.group(0))

    if not title:
        title = Path(file_path).stem

    return title, authors, year
