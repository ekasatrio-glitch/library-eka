"""Clean-title extraction for renaming (Phase 14). Semantic, NOT regex.

Reliability order:
  1. LLM extraction from first-page text (+ largest-font line and embedded
     /Title metadata as hints) -> strict JSON {title, authors, year}.
  2. Crossref canonicalization (optional, online) for the official record.
  3. Offline fallback: LLM result only.

All string cleaning uses unicodedata + str.translate + str.split — no regex,
because PDF layouts are too varied for patterns.
"""

import json
import unicodedata
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

# Characters illegal in file names across macOS/Windows -> replaced with '-'.
_ILLEGAL = '/\\:*?"<>|'
_TRANS = {ord(c): "-" for c in _ILLEGAL}
# Also strip control characters.
_TRANS.update({i: None for i in range(0, 32)})


def clean_component(s: Optional[str], max_len: int = 120) -> str:
    """Normalize one filename component without regex."""
    if not s:
        return ""
    s = unicodedata.normalize("NFKC", str(s))
    s = " ".join(s.split())          # collapse whitespace/newlines
    s = s.translate(_TRANS)          # map illegal/control chars
    s = " ".join(s.split())          # re-collapse if translate left gaps
    s = s.strip(" .-")               # no leading/trailing dots/spaces/dashes
    if len(s) > max_len:
        s = s[:max_len].rstrip(" .-")
    return s


def font_hints(pdf_path) -> Dict[str, Optional[str]]:
    """Largest-font line on page 1 + embedded /Title metadata, as title candidates."""
    import fitz

    largest_text, largest_size = None, -1.0
    meta_title = None
    with fitz.open(str(pdf_path)) as doc:
        if doc.page_count == 0:
            return {"largest_font": None, "meta_title": None}
        meta_title = (doc.metadata or {}).get("title") or None
        d = doc[0].get_text("dict")
        for block in d.get("blocks", []):
            for line in block.get("lines", []):
                for span in line.get("spans", []):
                    txt = (span.get("text") or "").strip()
                    size = float(span.get("size") or 0)
                    if len(txt) >= 6 and size > largest_size:
                        largest_size, largest_text = size, txt
    return {"largest_font": largest_text, "meta_title": meta_title}


_SYS = (
    "Anda pengekstrak metadata bibliografi. Dari TEKS halaman pertama paper, "
    "tentukan judul resmi, daftar penulis, dan tahun terbit. Gunakan PETUNJUK "
    "(baris font terbesar, /Title) bila membantu, tapi jangan mengarang. "
    "Kembalikan HANYA JSON: {\"title\": \"...\", \"authors\": [\"...\"], \"year\": 2020}. "
    "Jika tahun tak diketahui, year = null. Jika penulis tak diketahui, authors = []."
)


def _parse_json(raw: str) -> Dict[str, Any]:
    raw = (raw or "").strip()
    if raw.startswith("```"):
        raw = raw.strip("`")
        if raw[:4].lower() == "json":
            raw = raw[4:]
    start, end = raw.find("{"), raw.rfind("}")
    if start != -1 and end != -1 and end > start:
        raw = raw[start : end + 1]
    try:
        obj = json.loads(raw)
        return obj if isinstance(obj, dict) else {}
    except Exception:
        return {}


def crossref_lookup(query: str, timeout: float = 6.0) -> Optional[Dict[str, Any]]:
    """Canonicalize via Crossref bibliographic query. Returns None if offline/none."""
    if not query or not query.strip():
        return None
    try:
        import httpx

        r = httpx.get(
            "https://api.crossref.org/works",
            params={"query.bibliographic": query, "rows": 1},
            timeout=timeout,
            headers={"User-Agent": "library-eka/1.0 (mailto:noreply@example.com)"},
        )
        r.raise_for_status()
        items = (r.json().get("message", {}) or {}).get("items", [])
        if not items:
            return None
        it = items[0]
        title = (it.get("title") or [None])[0]
        authors: List[str] = []
        for a in it.get("author", []) or []:
            fam = a.get("family") or ""
            giv = a.get("given") or ""
            name = (f"{giv} {fam}").strip() or fam
            if name:
                authors.append(name)
        year = None
        for k in ("published-print", "published-online", "issued", "created"):
            parts = (it.get(k, {}) or {}).get("date-parts", [[None]])
            if parts and parts[0] and parts[0][0]:
                year = parts[0][0]
                break
        return {"title": title, "authors": authors, "year": year}
    except Exception:
        return None


def extract_meta(
    pdf_path,
    chat_fn: Callable,
    use_crossref: bool = True,
    first_page: Optional[str] = None,
) -> Dict[str, Any]:
    """Return {title, authors(list), year} for renaming. Crossref overrides when found."""
    from app.ingest.extractor import first_page_text

    fp = first_page if first_page is not None else first_page_text(pdf_path)
    hints = font_hints(pdf_path) if first_page is None else {"largest_font": None, "meta_title": None}

    prompt = (
        f"PETUNJUK baris font terbesar: {hints.get('largest_font')}\n"
        f"PETUNJUK /Title: {hints.get('meta_title')}\n\n"
        f"TEKS HALAMAN PERTAMA:\n{(fp or '')[:4000]}\n\n"
        f"Keluarkan JSON {{title, authors, year}}."
    )
    meta = _parse_json(chat_fn(_SYS, prompt))

    title = meta.get("title")
    authors = meta.get("authors") or []
    if isinstance(authors, str):
        authors = [authors]
    year = meta.get("year")

    if use_crossref:
        cr = crossref_lookup(title or hints.get("largest_font") or (fp or "")[:200])
        if cr and cr.get("title"):
            title = cr["title"]
            authors = cr.get("authors") or authors
            year = cr.get("year") or year

    return {"title": title, "authors": authors, "year": year}


def authors_label(authors: List[str]) -> str:
    """Short author label: 'Surname' / 'Surname dkk.' (Indonesian 'et al.')."""
    if not authors:
        return "Anon"
    first = authors[0].strip()
    surname = first.split()[-1] if first.split() else first
    return surname if len(authors) == 1 else f"{surname} dkk."


def build_filename(meta: Dict[str, Any], pattern: str, suffix: str = ".pdf") -> str:
    """Compose a clean filename from the rename pattern. Never raises on missing fields."""
    title = clean_component(meta.get("title")) or "Untitled"
    year = meta.get("year")
    year_s = str(year) if year else "n.d."
    authors = authors_label(meta.get("authors") or [])
    name = pattern.format(authors=authors, year=year_s, title=title)
    name = clean_component(name, max_len=180)
    if not name:
        name = "Untitled"
    return name + suffix
