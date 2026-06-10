"""Kerangka teori (theoretical framework) generator.

Builds a grounded causal graph from a research title, obeying the project's
Core Principles: NOT LLM-driven. Every corpus node is cited to a real
doc_id + page; a node claimed `src:korpus` without a supporting doc_id is
REJECTED at assembly. External citations never come from LLM memory — always
through Crossref.

All dependencies are injectable so the generator is testable without a live
model or network: `chat_fn`, `search_fn`, `crossref_fn`.
"""

import json
from typing import Any, Callable, Dict, List, Optional

from app.rag.generator import chat
from app.rag.retriever import search
from app.ingest.title import crossref_lookup

# ---- Prompts (Bahasa Indonesia, module constants) ----

PARSE_TITLE_SYS = (
    "Ekstrak variabel bebas (daftar), terikat (satu), dan populasi dari judul "
    "penelitian. Kembalikan HANYA JSON {\"bebas\":[],\"terikat\":\"\",\"populasi\":\"\"}. "
    "Jangan mengarang variabel yang tidak ada di judul."
)

BACKBONE_SYS = (
    "Susun rantai mekanistik antar variabel HANYA dari KONTEKS yang diberikan. "
    "Tiap node sertakan: label (ringkas), relasi (memicu|menghambat), dari (label "
    "asal), ke (label tujuan), src_idx (indeks sumber konteks yang mendukung). "
    "Kembalikan HANYA JSON array. Jangan pakai pengetahuan di luar KONTEKS. "
    "Jika konteks tak cukup, kembalikan []."
)

EXTERNAL_SYS = (
    "Usulkan faktor latar relevan yang TIDAK ada di konteks korpus (pengetahuan "
    "domain). Tiap usulan: label, relasi (memicu|menghambat), target (label tujuan). "
    "Kembalikan HANYA JSON array. Usulan ini akan diverifikasi ke Crossref — "
    "jangan mengarang referensi atau sitasi."
)


def _parse_json(raw: str) -> Any:
    """Strip code-fence then load JSON; fail-safe to None on error (matrix.py pattern)."""
    raw = (raw or "").strip()
    if raw.startswith("```"):
        raw = raw.strip("`")
        if raw[:4].lower() == "json":
            raw = raw[4:]
    # Try object first, then array.
    for open_c, close_c in (("{", "}"), ("[", "]")):
        start, end = raw.find(open_c), raw.rfind(close_c)
        if start != -1 and end != -1 and end > start:
            try:
                return json.loads(raw[start : end + 1])
            except Exception:
                continue
    return None


def parse_title(title: str, chat_fn: Optional[Callable] = None) -> Dict[str, Any]:
    """Title -> {"bebas":[str], "terikat":str, "populasi":str}. Fail-safe to empties.

    `chat_fn` is resolved at CALL time (default `chat`) so endpoint tests can
    patch `app.rag.framework.chat`. Passing it explicitly bypasses the module
    global (used by the generator unit tests)."""
    chat_fn = chat_fn or chat
    obj = _parse_json(chat_fn(PARSE_TITLE_SYS, f"JUDUL: {title}\n\nKeluarkan JSON."))
    if not isinstance(obj, dict):
        return {"bebas": [], "terikat": "", "populasi": ""}
    bebas = obj.get("bebas") or []
    if isinstance(bebas, str):
        bebas = [bebas]
    return {
        "bebas": [str(b).strip() for b in bebas if str(b).strip()],
        "terikat": str(obj.get("terikat") or "").strip(),
        "populasi": str(obj.get("populasi") or "").strip(),
    }
