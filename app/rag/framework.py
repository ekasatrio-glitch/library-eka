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
    # Detect outermost container first (array vs object) to avoid matching inner
    # braces inside an array like [{...}] as an object.
    stripped = raw.lstrip()
    if stripped.startswith("["):
        order = (("[", "]"), ("{", "}"))
    else:
        order = (("{", "}"), ("[", "]"))
    for open_c, close_c in order:
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


# ---- DSL assembly helpers ----

def _node_line(kind: str, label: str) -> str:
    return f"[{kind}] {label}"


def _edge_line(frm: str, to: str, reltype: str) -> str:
    arrow = "-|" if reltype == "menghambat" else "->"
    return f"{frm} {arrow} {to} : {reltype}"


def _reltype(raw: Optional[str]) -> str:
    return "menghambat" if str(raw or "").strip().lower() == "menghambat" else "memicu"


def build_framework(
    conn,
    project_id: int,
    variables: Dict[str, Any],
    chat_fn: Optional[Callable] = None,
    search_fn: Optional[Callable] = None,
    crossref_fn: Optional[Callable] = None,
) -> Dict[str, Any]:
    """Build a grounded framework, persist it, and return {dsl, citations, variables}.

    Deps resolve at CALL time (defaults `chat`/`search`/`crossref_lookup`) so the
    endpoint route — which calls this with no deps — picks up patched module
    globals in tests; generator unit tests pass stubs explicitly."""
    from app.core.projects import project_doc_ids

    chat_fn = chat_fn or chat
    search_fn = search_fn or search
    crossref_fn = crossref_fn or crossref_lookup

    doc_ids = project_doc_ids(conn, project_id)
    if not doc_ids:
        raise ValueError("naskah tanpa paper")

    bebas = [str(b).strip() for b in (variables.get("bebas") or []) if str(b).strip()]
    terikat = str(variables.get("terikat") or "").strip()
    diteliti = bebas + ([terikat] if terikat else [])

    # Ordered node declarations + per-label kind, plus citations + edges.
    nodes: Dict[str, str] = {}  # label -> kind (last write wins; diteliti is set first)
    order: List[str] = []       # preserve first-seen order
    citations: Dict[str, Any] = {}
    edges: List[tuple] = []     # (from, to, reltype)

    def add_node(label: str, kind: str) -> None:
        label = label.strip()
        if not label:
            return
        if label not in nodes:
            order.append(label)
        nodes[label] = kind

    for v in diteliti:
        add_node(v, "diteliti")

    # --- Backbone: corpus-grounded mediators between each bebas and terikat ---
    for src_var in bebas:
        if not terikat:
            break
        query = f"{src_var} {terikat}"
        try:
            hits = search_fn(query, top_k=6, filters={"doc_ids": doc_ids}, conn=conn)
        except Exception:
            hits = []
        chain = _parse_json(chat_fn(
            BACKBONE_SYS,
            _backbone_prompt(src_var, terikat, hits),
        )) or []
        if not isinstance(chain, list):
            chain = []
        for item in chain:
            if not isinstance(item, dict):
                continue
            label = str(item.get("label") or "").strip()
            src_idx = item.get("src_idx")
            # Guard: corpus node must cite a real Hit (in-range index).
            if not label or not isinstance(src_idx, int) or not (0 <= src_idx < len(hits)):
                continue  # rejected (anti-hallucination); skip node + its edges
            hit = hits[src_idx]
            page = hit.page_start
            if page is None:
                continue
            add_node(label, "latar*")
            citations[label] = {
                "src": "korpus", "doc_id": hit.doc_id, "page": page,
                "title": getattr(hit, "title", None) or "",
                "quote": "",
            }
            # Insert the mediator into the path: dari -> label -> ke (not a single
            # edge bypassing the node, which would orphan the [latar*] mediator).
            frm = str(item.get("dari") or src_var).strip()
            to = str(item.get("ke") or terikat).strip()
            rel = _reltype(item.get("relasi"))
            edges.append((frm, label, rel))
            edges.append((label, to, rel))

    # --- External latar factors, verified via Crossref ---
    proposals = _parse_json(chat_fn(EXTERNAL_SYS, _external_prompt(diteliti))) or []
    if not isinstance(proposals, list):
        proposals = []
    for item in proposals:
        if not isinstance(item, dict):
            continue
        label = str(item.get("label") or "").strip()
        target = str(item.get("target") or "").strip()
        if not label or not target:
            continue
        # If `target` names no existing node, the label->target edge is dropped
        # later (edge-validity filter), leaving a disconnected [latar] node. That
        # is intentional: per the Core Principle, an unsupported factor is shown
        # (badge), never silently dropped — the user prunes it via the DSL.
        ref = None
        try:
            ref = crossref_fn(label)
        except Exception:
            ref = None
        if ref and ref.get("title"):
            citations[label] = {
                "src": "eksternal", "status": "perlu_verifikasi",
                "ref": {"title": ref.get("title"), "authors": ref.get("authors") or [],
                        "year": ref.get("year"), "doi": ref.get("doi"),
                        "url": ref.get("url")},
            }
        else:
            citations[label] = {"src": "eksternal", "status": "tak_terverifikasi", "ref": None}
        add_node(label, "latar")
        edges.append((label, target, _reltype(item.get("relasi"))))

    # --- Drop edges whose endpoints were never created as nodes (rejected) ---
    valid = set(nodes)
    edges = [(f, t, r) for (f, t, r) in edges if f in valid and t in valid]

    dsl = _assemble_dsl(order, nodes, edges)

    payload_vars = {"bebas": bebas, "terikat": terikat,
                    "populasi": str(variables.get("populasi") or "").strip()}
    conn.execute(
        "INSERT INTO project_framework (project_id, title, dsl, citations, variables, updated_at) "
        "VALUES (?, ?, ?, ?, ?, datetime('now')) "
        "ON CONFLICT(project_id) DO UPDATE SET title=excluded.title, dsl=excluded.dsl, "
        "citations=excluded.citations, variables=excluded.variables, updated_at=excluded.updated_at",
        (project_id, str(variables.get("title") or ""), dsl,
         json.dumps(citations, ensure_ascii=False),
         json.dumps(payload_vars, ensure_ascii=False)),
    )
    conn.commit()
    return {"dsl": dsl, "citations": citations, "variables": payload_vars}


def _backbone_prompt(src_var: str, terikat: str, hits: List[Any]) -> str:
    # Include the chunk excerpt (capped) so the LLM grounds the chain on real
    # content, not just titles — `src_idx` then points at a Hit whose text the
    # node actually came from.
    ctx = "\n\n".join(
        f"[{i}] (hlm {getattr(h, 'page_start', '?')}) {getattr(h, 'title', '') or ''}\n"
        f"{(getattr(h, 'text', '') or '')[:600]}"
        for i, h in enumerate(hits)
    ) or "(konteks kosong)"
    return (
        f"VARIABEL ASAL: {src_var}\nVARIABEL TUJUAN: {terikat}\n\n"
        f"KONTEKS (tiap entri diawali indeks sumber):\n{ctx}\n\n"
        f"Keluarkan JSON array node rantai mekanistik."
    )


def _external_prompt(diteliti: List[str]) -> str:
    return (
        f"VARIABEL DITELITI: {', '.join(diteliti)}\n\n"
        f"Usulkan faktor latar yang relevan namun TIDAK ada di korpus. "
        f"Keluarkan JSON array."
    )


def _assemble_dsl(order: List[str], nodes: Dict[str, str], edges: List[tuple]) -> str:
    """Emit node declarations (diteliti -> latar* -> latar) then edges."""
    lines: List[str] = []
    for kind in ("diteliti", "latar*", "latar"):
        for label in order:
            if nodes.get(label) == kind:
                lines.append(_node_line(kind, label))
    if edges:
        lines.append("")
        for frm, to, rel in edges:
            lines.append(_edge_line(frm, to, rel))
    return "\n".join(lines)


def load_framework(conn, project_id: int) -> Optional[Dict[str, Any]]:
    """Return the persisted framework or None if the project has none."""
    row = conn.execute(
        "SELECT dsl, citations, variables, title, updated_at "
        "FROM project_framework WHERE project_id = ?",
        (project_id,),
    ).fetchone()
    if not row:
        return None
    return {
        "dsl": row[0],
        "citations": json.loads(row[1] or "{}"),
        "variables": json.loads(row[2] or "{}"),
        "title": row[3] or "",
        "updated_at": row[4],
    }
