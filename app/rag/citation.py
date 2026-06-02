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


def format_context(hits: List[Hit]) -> str:
    parts: List[str] = []
    for i, h in enumerate(hits, start=1):
        page = f"p.{h.page_start}" if h.page_start == h.page_end else f"p.{h.page_start}-{h.page_end}"
        parts.append(f"[{i}] {h.title or '(untitled)'} ({page})\n{h.text}\n")
    return "\n---\n".join(parts)
