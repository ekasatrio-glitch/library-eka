from typing import Any, Dict, List, Optional

from app.rag.citation import Citation, build_citations, format_context
from app.rag.generator import chat
from app.rag.retriever import Hit, search

SYSTEM = (
    "Anda asisten riset. Jawab HANYA berdasarkan KONTEKS yang diberikan. "
    "Tiap klaim WAJIB diikuti penanda sumber numerik seperti [1], [2] sesuai konteks. "
    "Dilarang mengarang sitasi atau fakta di luar konteks. "
    "Hanya jika TIDAK ADA bukti relevan sama sekali, katakan tidak cukup informasi. "
    "Jika ada bukti, jawab langsung tanpa menambah catatan tentang keterbatasan konteks. "
    "Jawab ringkas, akurat, dalam Bahasa Indonesia kecuali kutipan asli."
)

USER_TMPL = """PERTANYAAN:
{question}

KONTEKS:
{context}

Tulis jawaban ringkas (3-8 kalimat) dengan sitasi [n] mengikuti konteks."""


def ask(
    question: str,
    top_k: int = 6,
    filters: Optional[Dict[str, Any]] = None,
    conn=None,
) -> Dict[str, Any]:
    hits: List[Hit] = search(question, top_k=top_k, filters=filters, conn=conn)
    citations: List[Citation] = build_citations(hits)
    if not hits:
        return {
            "answer": "Tidak ada bukti relevan dalam korpus.",
            "citations": [],
            "hits": [],
        }
    ctx = format_context(hits)
    answer = chat(SYSTEM, USER_TMPL.format(question=question, context=ctx))
    return {
        "answer": answer,
        "citations": [c.to_dict() for c in citations],
        "hits": [h.to_dict() for h in hits],
    }
