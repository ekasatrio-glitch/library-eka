import json
from typing import Any, Dict, List, Optional

from app.rag.citation import build_citations, format_context
from app.rag.generator import chat
from app.rag.retriever import Hit, search

EXPAND_SYS = (
    "Anda generator subtopik. Diberi topik utama, hasilkan {n} subtopik singkat (3-6 kata) "
    "yang saling melengkapi untuk eksplorasi mindmap. Kembalikan HANYA JSON array string. "
    "Jangan tambahkan komentar atau penjelasan."
)

OUTLINE_SYS = (
    "Anda menyusun outline mindmap berbasis KONTEKS. Keluarkan markdown hierarki:\n"
    "- baris pertama: '# <topik>'\n"
    "- level 2 (##): tiap subtopik\n"
    "- level 3 (-): poin penting (3-6 per subtopik), tiap poin diakhiri tag sumber [n]\n"
    "Hanya gunakan informasi dari KONTEKS. Jangan karang. Bahasa Indonesia."
)


def _expand_subtopics(topic: str, n: int) -> List[str]:
    raw = chat(EXPAND_SYS.format(n=n), f"Topik: {topic}", temperature=0.4, max_tokens=300)
    raw = raw.strip()
    if raw.startswith("```"):
        raw = raw.strip("`").lstrip("json").strip()
    try:
        arr = json.loads(raw)
        if isinstance(arr, list):
            return [str(x) for x in arr][:n]
    except Exception:
        pass
    return [line.strip("-• ").strip() for line in raw.splitlines() if line.strip()][:n]


def build_mindmap(
    topic: str,
    breadth: int = 4,
    top_k: int = 6,
    conn=None,
) -> Dict[str, Any]:
    subs = _expand_subtopics(topic, breadth)

    all_hits: List[Hit] = []
    seen: set[int] = set()
    for q in [topic, *subs]:
        for h in search(q, top_k=top_k, conn=conn):
            if h.chunk_id in seen:
                continue
            seen.add(h.chunk_id)
            all_hits.append(h)

    if not all_hits:
        return {
            "markdown": f"# {topic}\n\n_Tidak ada bukti relevan._",
            "citations": [],
            "subtopics": subs,
        }

    ctx = format_context(all_hits)
    md = chat(OUTLINE_SYS, f"TOPIK: {topic}\nSUBTOPIK:\n- " + "\n- ".join(subs) + f"\n\nKONTEKS:\n{ctx}", temperature=0.3, max_tokens=1500)
    citations = build_citations(all_hits)
    return {
        "markdown": md.strip(),
        "citations": [c.to_dict() for c in citations],
        "subtopics": subs,
    }
