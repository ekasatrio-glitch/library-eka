"""Synthesis matrix engine (Phase 12).

Per-paper structured extraction, scoped to a project, obeying the Core Principles:
- Every field is grounded in the paper itself; unknown -> explicit gap string
  ("tidak disebutkan" / "tidak dilaporkan" for meta-analysis). No guessing.
- Weaknesses are split: author-stated limitations vs. critical suggestions
  (the latter clearly tagged "saran — perlu verifikasi").
- Supporting papers come ONLY from the corpus (semantic match across PDFs),
  cited to real title + page — never from LLM memory.
- Notes are draft suggestions, clearly marked; the user rewrites them.

LLM calls go through `chat`; corpus lookups through `search`. Both are injectable
so the engine is testable without a live model.
"""

import json
from typing import Any, Callable, Dict, List, Optional

GAP = "tidak disebutkan dalam paper"
GAP_META = "tidak dilaporkan"
SUGGEST_PREFIX = "saran — perlu verifikasi: "

# ---- Field schemas (keys are stable; labels shown in UI/export) ----

EMPIRIS_FIELDS = [
    "main_finding",
    "definisi_operasional",
    "mekanisme",
    "kontroversi",
    "kelemahan_penulis",
    "kelemahan_saran",
    "tag",
    "notes",
]

REVIEW_FIELDS = [
    "jenis_cakupan",
    "pertanyaan_tujuan",
    "sintesis_utama",
    "tema_argumen",
    "definisi_konsep",
    "konsensus_perdebatan",
    "gap_penelitian",
    "studi_kunci",
    "kelemahan_penulis",
    "kelemahan_saran",
    "tag",
    "notes",
]

META_EXTRA = [
    "pico",
    "protokol",
    "jumlah_studi_peserta",
    "effect_measure",
    "pooled_estimate",
    "model_metode",
    "heterogenitas",
    "subgrup_metaregresi",
    "analisis_sensitivitas",
    "bias_publikasi",
    "penilaian_kualitas",
    "studi_dimasukkan",
    "kontroversi_ma",
]
META_FIELDS = META_EXTRA + REVIEW_FIELDS

# LLM extracts text fields; these are filled separately (corpus / derived), so we
# do NOT ask the model for them.
CORPUS_FIELDS = {"paper_pendukung"}
DERIVED_FIELDS = {"kelemahan_tidak_dilaporkan"}

SCHEMAS: Dict[str, List[str]] = {
    "empiris": EMPIRIS_FIELDS,
    "review": REVIEW_FIELDS,
    "meta-analisis": META_FIELDS,
}

# Meta signals strong enough to call meta-analysis; review signals otherwise.
_META_SIGNALS = ("meta-analysis", "meta analisis", "pooled", "random-effects",
                 "random effects", "i²", "i2 =", "forest plot", "prospero")
_REVIEW_SIGNALS = ("systematic review", "tinjauan sistematis", "scoping review",
                   "narrative review", "tinjauan pustaka", "literature review",
                   "prisma")


def detect_schema(title: str, text: str, override: Optional[str] = None) -> str:
    """Heuristic paper-type detection with manual override."""
    if override in SCHEMAS:
        return override
    blob = f"{title or ''}\n{text or ''}".lower()
    if any(s in blob for s in _META_SIGNALS):
        return "meta-analisis"
    if any(s in blob for s in _REVIEW_SIGNALS):
        return "review"
    return "empiris"


def paper_text(conn, doc_id: int, max_chars: int = 12000) -> List[Dict[str, Any]]:
    """Return ordered chunks [{text, page_start, page_end}] for a document, capped."""
    rows = conn.execute(
        "SELECT text, page_start, page_end FROM chunks WHERE doc_id = ? ORDER BY id",
        (doc_id,),
    ).fetchall()
    out, total = [], 0
    for t, ps, pe in rows:
        out.append({"text": t, "page_start": ps, "page_end": pe})
        total += len(t)
        if total >= max_chars:
            break
    return out


def _llm_fields(schema: str) -> List[str]:
    """Fields the LLM should extract (exclude corpus/derived ones)."""
    return [f for f in SCHEMAS[schema] if f not in CORPUS_FIELDS and f not in DERIVED_FIELDS]


_SYS = (
    "Anda ekstraktor matriks sintesis literatur yang SANGAT ketat. "
    "Ekstrak HANYA dari TEKS PAPER yang diberikan. DILARANG menebak, mengarang, "
    "atau memakai pengetahuan luar. Jika paper tidak menyatakan suatu field, "
    "isi PERSIS dengan string gap yang diberikan. "
    "Pisahkan kelemahan: 'kelemahan_penulis' = limitasi yang DINYATAKAN penulis; "
    "'kelemahan_saran' = saran kritis Anda yang HARUS diawali 'saran — perlu verifikasi: '. "
    "'notes' = draft interpretasi singkat bertanda '(draft)'. "
    "Kembalikan HANYA satu objek JSON dengan kunci yang diminta, nilai berupa string."
)


def _build_prompt(schema: str, title: str, year, chunks: List[Dict[str, Any]]) -> str:
    gap = GAP_META if schema == "meta-analisis" else GAP
    fields = _llm_fields(schema)
    ctx = "\n\n".join(
        f"[hlm {c['page_start']}-{c['page_end']}] {c['text']}" for c in chunks
    )
    return (
        f"JENIS PAPER: {schema}\n"
        f"JUDUL: {title}\nTAHUN: {year}\n\n"
        f"FIELD WAJIB (kunci JSON): {', '.join(fields)}\n"
        f"STRING GAP untuk field yang tidak dinyatakan paper: \"{gap}\"\n\n"
        f"TEKS PAPER:\n{ctx}\n\n"
        f"Keluarkan satu objek JSON dengan persis kunci di atas."
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


def extract_paper(
    conn,
    doc_id: int,
    chat_fn: Callable,
    search_fn: Callable,
    override: Optional[str] = None,
    support_k: int = 3,
) -> Dict[str, Any]:
    """Extract one paper's matrix row. Returns {source, year, schema, fields, refs}."""
    drow = conn.execute(
        "SELECT title, authors, year FROM documents WHERE id = ?", (doc_id,)
    ).fetchone()
    title = (drow[0] if drow else None) or "(untitled)"
    authors = drow[1] if drow else None
    year = drow[2] if drow else None

    chunks = paper_text(conn, doc_id)
    full_text = " ".join(c["text"] for c in chunks)
    schema = detect_schema(title, full_text, override)
    gap = GAP_META if schema == "meta-analisis" else GAP

    raw = chat_fn(_SYS, _build_prompt(schema, title, year, chunks))
    parsed = _parse_json(raw)

    fields: Dict[str, Any] = {}
    refs: Dict[str, Any] = {}
    page_ref = [{"doc_id": doc_id, "page_start": c["page_start"], "page_end": c["page_end"]} for c in chunks[:1]]

    for key in _llm_fields(schema):
        val = parsed.get(key)
        if val is None or (isinstance(val, str) and not val.strip()):
            val = gap
        val = str(val).strip()
        # Enforce suggestion marker on the critical-suggestion column.
        if key == "kelemahan_saran" and val and val != gap and not val.lower().startswith("saran"):
            val = SUGGEST_PREFIX + val
        fields[key] = val
        if val != gap:
            refs[key] = page_ref  # grounded to this paper

    # Supporting papers: corpus-only semantic match, excluding self. Real cites.
    support = _supporting_papers(conn, doc_id, title, fields, search_fn, support_k)
    fields["paper_pendukung"] = support["text"]
    if support["refs"]:
        refs["paper_pendukung"] = support["refs"]

    # Meta-analysis: any "tidak dilaporkan" field flows into the weakness column.
    if schema == "meta-analisis":
        missing = [k for k in META_EXTRA if fields.get(k) == GAP_META]
        if missing:
            fields["kelemahan_tidak_dilaporkan"] = (
                "Tidak dilaporkan: " + ", ".join(missing)
            )

    source = f"{authors} ({year})" if authors else f"{title} ({year})" if year else title
    return {
        "doc_id": doc_id,
        "source": source,
        "title": title,
        "year": year,
        "schema": schema,
        "fields": fields,
        "refs": refs,
    }


def _supporting_papers(conn, doc_id, title, fields, search_fn, k) -> Dict[str, Any]:
    """Find corpus papers (not this one) whose content matches this paper's finding."""
    query = fields.get("main_finding") or fields.get("sintesis_utama") or title
    if not query or query.startswith("tidak "):
        query = title
    try:
        hits = search_fn(query, top_k=k + 4, conn=conn)
    except Exception:
        return {"text": GAP, "refs": []}
    parts, refs, seen = [], [], set()
    for h in hits:
        if h.doc_id == doc_id or h.doc_id in seen:
            continue
        seen.add(h.doc_id)
        page = h.page_start if h.page_start == h.page_end else f"{h.page_start}-{h.page_end}"
        parts.append(f"{h.title or '(untitled)'} (hlm {page})")
        refs.append({"doc_id": h.doc_id, "page_start": h.page_start, "page_end": h.page_end})
        if len(parts) >= k:
            break
    if not parts:
        return {"text": "tidak ada paper pendukung di korpus", "refs": []}
    return {"text": "; ".join(parts), "refs": refs}


def snap_tag(tag: str, codebook: List[str]) -> str:
    """Closed coding: map a free tag onto the project codebook vocabulary.

    Exact (case-insensitive) match wins; else substring either direction; else
    keep the original tag but flag it for review (so it isn't silently invented).
    """
    if not codebook or not tag or tag.startswith("tidak "):
        return tag
    low = tag.strip().lower()
    for c in codebook:
        if c.lower() == low:
            return c
    for c in codebook:
        if c.lower() in low or low in c.lower():
            return c
    return f"{tag} (perlu verifikasi tag)"


def build_matrix(
    conn,
    project_id: int,
    chat_fn: Callable,
    search_fn: Callable,
    overrides: Optional[Dict[int, str]] = None,
) -> List[Dict[str, Any]]:
    """Extract + persist a row per project paper. Returns the list of rows."""
    from app.core.projects import list_codebook, project_doc_ids

    overrides = overrides or {}
    codebook = [c["tag"] for c in list_codebook(conn, project_id)]
    rows: List[Dict[str, Any]] = []
    for doc_id in project_doc_ids(conn, project_id):
        row = extract_paper(conn, doc_id, chat_fn, search_fn, override=overrides.get(doc_id))
        if codebook and "tag" in row["fields"]:
            row["fields"]["tag"] = snap_tag(row["fields"]["tag"], codebook)
        conn.execute(
            "INSERT INTO project_matrix (project_id, doc_id, schema, data) VALUES (?, ?, ?, ?) "
            "ON CONFLICT(project_id, doc_id) DO UPDATE SET schema=excluded.schema, "
            "data=excluded.data, updated_at=CURRENT_TIMESTAMP",
            (project_id, doc_id, row["schema"], json.dumps(row, ensure_ascii=False)),
        )
        rows.append(row)
    conn.commit()
    return rows


def load_matrix(conn, project_id: int) -> List[Dict[str, Any]]:
    rows = conn.execute(
        "SELECT data FROM project_matrix WHERE project_id = ? ORDER BY doc_id",
        (project_id,),
    ).fetchall()
    return [json.loads(r[0]) for r in rows]


def matrix_columns(rows: List[Dict[str, Any]]) -> List[str]:
    """Ordered union of field keys across rows (canonical order)."""
    order = META_FIELDS + EMPIRIS_FIELDS + ["paper_pendukung", "kelemahan_tidak_dilaporkan"]
    seen, cols = set(), []
    for key in order:
        if key in seen:
            continue
        if any(key in r.get("fields", {}) for r in rows):
            seen.add(key)
            cols.append(key)
    return cols


def shape_view(rows: List[Dict[str, Any]], view: str = "matrix") -> Dict[str, Any]:
    """Reshape the SAME data into matrix | linimasa (by year) | tema (by tag)."""
    if view == "linimasa":
        rows = sorted(rows, key=lambda r: (r.get("year") is None, r.get("year") or 0))
    elif view == "tema":
        rows = sorted(rows, key=lambda r: (r.get("fields", {}).get("tag") or "~").lower())
    return {"view": view, "columns": matrix_columns(rows), "rows": rows}
