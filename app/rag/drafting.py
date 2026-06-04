from typing import Any, Dict, List, Optional

from app.rag.citation import build_citations, extract_cited_ns, format_context, mark_cited
from app.rag.generator import chat
from app.rag.retriever import Hit, search

VANCOUVER_SYS = (
    "Anda penulis akademik medis. Tulis SATU paragraf akademik 6-12 kalimat dalam Bahasa Indonesia "
    "yang mensintesis KONTEKS. WAJIB: tiap klaim diikuti penanda numerik gaya Vancouver: (1), (2). "
    "Penomoran HARUS cocok dengan urutan KONTEKS yang diberikan ([1]→(1), dst). "
    "Dilarang menyebut sumber di luar KONTEKS. Jika bukti tidak cukup untuk suatu klaim, hilangkan klaim itu."
)

APA_SYS = (
    "Anda penulis akademik. Tulis SATU paragraf 6-12 kalimat dalam Bahasa Indonesia mensintesis KONTEKS. "
    "WAJIB: tiap klaim diikuti sitasi gaya APA (Penulis, Tahun) berdasarkan field 'authors'/'year' tiap sumber; "
    "jika authors kosong, gunakan judul pendek. Dilarang menyebut sumber di luar KONTEKS."
)


def _format_reference(idx: int, h: Hit, style: str) -> str:
    title = h.title or "(untitled)"
    authors = h.authors or "Anon"
    year = h.year if h.year else "n.d."
    page = f"p.{h.page_start}" if h.page_start == h.page_end else f"p.{h.page_start}-{h.page_end}"
    if style == "apa":
        return f"{authors} ({year}). {title}. [{page}]. {h.path}"
    return f"{idx}. {authors}. {title}. {year}. [{page}]. {h.path}"


def draft_paragraph(
    topic: str,
    style: str = "vancouver",
    top_k: int = 10,
    filters: Optional[Dict[str, Any]] = None,
    conn=None,
) -> Dict[str, Any]:
    style = style.lower()
    if style not in ("vancouver", "apa"):
        style = "vancouver"

    hits = search(topic, top_k=top_k, filters=filters, conn=conn)
    citations = build_citations(hits)
    if not hits:
        return {
            "paragraph": "Tidak ada bukti relevan untuk topik ini dalam korpus.",
            "citations": [],
            "references": [],
            "style": style,
        }

    ctx = format_context(hits)
    sys = VANCOUVER_SYS if style == "vancouver" else APA_SYS
    user = (
        f"TOPIK: {topic}\n\nKONTEKS:\n{ctx}\n\nTulis satu paragraf padat dengan sitasi sesuai aturan."
    )
    paragraph = chat(sys, user, temperature=0.25, max_tokens=900)
    if style == "vancouver":
        mark_cited(citations, extract_cited_ns(paragraph, style="paren"))
    refs = [_format_reference(i + 1, h, style) for i, h in enumerate(hits)]
    return {
        "paragraph": paragraph,
        "citations": [c.to_dict() for c in citations],
        "references": refs,
        "style": style,
    }
