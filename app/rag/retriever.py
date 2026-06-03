from dataclasses import dataclass, asdict
from typing import Any, Dict, List, Optional, Tuple

from app.core.db import connect, serialize_vec, sparse_search
from app.ingest.embedder import embed_one

RRF_K = 60  # Reciprocal Rank Fusion constant (standard default).


@dataclass
class Hit:
    chunk_id: int
    doc_id: int
    title: Optional[str]
    path: str
    page_start: int
    page_end: int
    year: Optional[int]
    authors: Optional[str]
    text: str
    distance: float  # dense vector distance (float('inf') if sparse-only hit)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def _build_where(filters: Optional[Dict[str, Any]]) -> Tuple[str, list]:
    if not filters:
        return "", []
    clauses: List[str] = []
    params: List[Any] = []
    if (y := filters.get("year_min")) is not None:
        clauses.append("d.year >= ?")
        params.append(int(y))
    if (y := filters.get("year_max")) is not None:
        clauses.append("d.year <= ?")
        params.append(int(y))
    if (f := filters.get("folder")) is not None:
        clauses.append("d.folder = ?")
        params.append(f)
    if (a := filters.get("authors_like")) is not None:
        clauses.append("d.authors LIKE ?")
        params.append(f"%{a}%")
    if (i := filters.get("doc_id")) is not None:
        clauses.append("d.id = ?")
        params.append(int(i))
    if not clauses:
        return "", []
    return " AND " + " AND ".join(clauses), params


def _dense_rank(conn, question: str, n: int, where: str, params: list) -> List[Tuple[int, float]]:
    """Dense (sqlite-vec) KNN. Returns [(chunk_id, distance)] best-first."""
    qvec = embed_one(question)
    blob = serialize_vec(qvec)
    sql = f"""
        SELECT c.id AS chunk_id, v.distance AS distance
        FROM vec_chunks v
        JOIN chunks c ON c.id = v.chunk_id
        JOIN documents d ON d.id = c.doc_id
        WHERE v.embedding MATCH ? AND k = ?{where}
        ORDER BY v.distance ASC
        LIMIT ?
    """
    rows = conn.execute(sql, (blob, n, *params, n)).fetchall()
    return [(r[0], float(r[1])) for r in rows]


def rrf_fuse(rankings: List[List[int]], top_n: int, k: int = RRF_K) -> List[int]:
    """Reciprocal Rank Fusion: score(id) = Σ 1/(k + rank). Higher score = better."""
    scores: Dict[int, float] = {}
    for ranking in rankings:
        for rank, cid in enumerate(ranking):
            scores[cid] = scores.get(cid, 0.0) + 1.0 / (k + rank + 1)
    ordered = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)
    return [cid for cid, _ in ordered[:top_n]]


def _fetch_hits(conn, chunk_ids: List[int], dist: Dict[int, float]) -> List[Hit]:
    """Materialize Hit rows for chunk_ids, preserving the given order."""
    if not chunk_ids:
        return []
    placeholders = ",".join("?" * len(chunk_ids))
    rows = conn.execute(
        f"""
        SELECT c.id, d.id, d.title, d.path, c.page_start, c.page_end, d.year, d.authors, c.text
        FROM chunks c
        JOIN documents d ON d.id = c.doc_id
        WHERE c.id IN ({placeholders})
        """,
        chunk_ids,
    ).fetchall()
    by_id = {r[0]: r for r in rows}
    hits: List[Hit] = []
    for cid in chunk_ids:
        r = by_id.get(cid)
        if r is None:
            continue
        hits.append(
            Hit(
                chunk_id=r[0],
                doc_id=r[1],
                title=r[2],
                path=r[3],
                page_start=r[4],
                page_end=r[5],
                year=r[6],
                authors=r[7],
                text=r[8],
                distance=dist.get(cid, float("inf")),
            )
        )
    return hits


def hybrid_search(
    question: str,
    top_k: int = 6,
    filters: Optional[Dict[str, Any]] = None,
    conn=None,
    pool: int = 50,
) -> List[Hit]:
    """Dense (sqlite-vec) + sparse (FTS5/BM25) fused with RRF.

    `pool` is the per-path candidate count fused before truncating to top_k.
    Metadata filters apply to both paths. Returns Hit rows in fused order.
    """
    own = conn is None
    if own:
        conn = connect()
    try:
        where, params = _build_where(filters)
        dense = _dense_rank(conn, question, pool, where, params)
        sparse = sparse_search(conn, question, pool, where, params)
        fused = rrf_fuse([[c for c, _ in dense], [c for c, _ in sparse]], top_n=top_k)
        dist = {c: d for c, d in dense}
        return _fetch_hits(conn, fused, dist)
    finally:
        if own:
            conn.close()


def search(
    question: str,
    top_k: int = 6,
    filters: Optional[Dict[str, Any]] = None,
    conn=None,
    over_fetch: int = 8,
) -> List[Hit]:
    """Default retrieval: hybrid (dense + sparse, RRF-fused).

    Kept name/signature for callers; `over_fetch` sizes the per-path candidate pool.
    """
    pool = max(top_k * over_fetch, 20)
    return hybrid_search(question, top_k=top_k, filters=filters, conn=conn, pool=pool)
