from dataclasses import dataclass
from typing import List, Tuple


@dataclass
class Chunk:
    text: str
    page_start: int
    page_end: int


def _approx_tokens(text: str) -> int:
    return max(1, len(text) // 4)


def chunk_pages(
    pages: List[Tuple[int, str]],
    chunk_tokens: int = 1000,
    overlap_tokens: int = 200,
) -> List[Chunk]:
    """Sliding-window chunks across concatenated pages, preserving page spans.

    Tokens approximated as chars/4 for speed; precise tokenization unnecessary here.
    """
    if not pages:
        return []

    spans: List[Tuple[int, int, int]] = []
    cursor = 0
    parts: List[str] = []
    for pg_no, txt in pages:
        if not txt:
            continue
        start = cursor
        parts.append(txt)
        cursor += len(txt) + 1
        spans.append((start, cursor - 1, pg_no))
        parts.append("\n")

    full = "\n".join(p for p in parts if p != "\n")
    if not full.strip():
        return []

    chunk_chars = chunk_tokens * 4
    overlap_chars = overlap_tokens * 4
    step = max(1, chunk_chars - overlap_chars)

    chunks: List[Chunk] = []
    i = 0
    n = len(full)
    while i < n:
        j = min(n, i + chunk_chars)
        text = full[i:j].strip()
        if text:
            page_start = _page_for_offset(spans, i)
            page_end = _page_for_offset(spans, max(i, j - 1))
            chunks.append(Chunk(text=text, page_start=page_start, page_end=page_end))
        if j >= n:
            break
        i += step
    return chunks


def _page_for_offset(spans: List[Tuple[int, int, int]], off: int) -> int:
    for start, end, pg in spans:
        if start <= off <= end:
            return pg
    return spans[-1][2] if spans else 1
