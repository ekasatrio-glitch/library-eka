from dataclasses import dataclass, asdict
from typing import Any, Dict, List, Optional

from app.core.db import connect, serialize_vec
from app.ingest.embedder import embed_one


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
    distance: float

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def _build_where(filters: Optional[Dict[str, Any]]) -> tuple[str, list]:
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


def search(
    question: str,
    top_k: int = 6,
    filters: Optional[Dict[str, Any]] = None,
    conn=None,
    over_fetch: int = 4,
) -> List[Hit]:
    """Vector search then join chunks+documents, applying optional metadata filters."""
    qvec = embed_one(question)
    blob = serialize_vec(qvec)

    own = conn is None
    if own:
        conn = connect()

    try:
        where, params = _build_where(filters)
        fetch_n = top_k * over_fetch
        sql = f"""
            SELECT
                c.id AS chunk_id,
                d.id AS doc_id,
                d.title AS title,
                d.path AS path,
                c.page_start AS page_start,
                c.page_end AS page_end,
                d.year AS year,
                d.authors AS authors,
                c.text AS text,
                v.distance AS distance
            FROM vec_chunks v
            JOIN chunks c ON c.id = v.chunk_id
            JOIN documents d ON d.id = c.doc_id
            WHERE v.embedding MATCH ? AND k = ?{where}
            ORDER BY v.distance ASC
            LIMIT ?
        """
        rows = conn.execute(sql, (blob, fetch_n, *params, top_k)).fetchall()
        return [
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
                distance=float(r[9]),
            )
            for r in rows
        ]
    finally:
        if own:
            conn.close()
