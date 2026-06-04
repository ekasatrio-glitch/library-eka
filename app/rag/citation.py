import re
from dataclasses import dataclass, asdict
from typing import Dict, List

from app.rag.retriever import Hit


@dataclass
class Citation:
    n: int
    doc_id: int
    chunk_id: int
    title: str
    page_start: int
    page_end: int
    path: str
    cited: bool = True

    def to_dict(self) -> Dict:
        return asdict(self)


def build_citations(hits: List[Hit]) -> List[Citation]:
    return [
        Citation(
            n=i + 1,
            doc_id=h.doc_id,
            chunk_id=h.chunk_id,
            title=h.title or "(untitled)",
            page_start=h.page_start,
            page_end=h.page_end,
            path=h.path,
        )
        for i, h in enumerate(hits)
    ]


# [3], [1, 2], [4-6] — chat answers
_SQUARE = re.compile(r"\[(\d+(?:\s*[,\-–]\s*\d+)*)\]")
# (3), (1,2) — Vancouver drafts; years like (2020) parse but fail range validation
_PAREN = re.compile(r"\((\d+(?:\s*[,\-–]\s*\d+)*)\)")


def extract_cited_ns(text: str, style: str = "square") -> set:
    """Collect citation numbers the LLM actually used in `text`.
    style: 'square' for [n] (chat), 'paren' for (n) (Vancouver)."""
    pat = _SQUARE if style == "square" else _PAREN
    ns: set = set()
    for m in pat.finditer(text):
        for part in re.split(r"\s*,\s*", m.group(1)):
            rng = re.fullmatch(r"(\d+)\s*[\-–]\s*(\d+)", part.strip())
            if rng:
                ns.update(range(int(rng.group(1)), int(rng.group(2)) + 1))
            elif part.strip().isdigit():
                ns.add(int(part.strip()))
    return ns


def mark_cited(citations: List[Citation], ns: set) -> List[Citation]:
    """Flag citations whose number appears in `ns`. If no number is valid
    (LLM emitted no markers, or only out-of-range ones like years), keep
    everything cited=True so the UI falls back to the single classic list."""
    valid = {n for n in ns if 1 <= n <= len(citations)}
    if not valid:
        return citations
    for c in citations:
        c.cited = c.n in valid
    return citations


def format_context(hits: List[Hit]) -> str:
    parts: List[str] = []
    for i, h in enumerate(hits, start=1):
        page = f"p.{h.page_start}" if h.page_start == h.page_end else f"p.{h.page_start}-{h.page_end}"
        parts.append(f"[{i}] {h.title or '(untitled)'} ({page})\n{h.text}\n")
    return "\n---\n".join(parts)
