"""Project/workspace data access. Corpus stays global; projects reference a
subset of `documents` via the `project_documents` join (no duplication)."""

from typing import Any, Dict, List, Optional


def create_project(conn, name: str, description: Optional[str] = None) -> int:
    cur = conn.execute(
        "INSERT INTO projects (name, description) VALUES (?, ?) RETURNING id",
        (name, description),
    )
    pid = cur.fetchone()[0]
    conn.commit()
    return pid


def list_projects(conn) -> List[Dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT p.id, p.name, p.description, p.created_at,
               (SELECT COUNT(*) FROM project_documents pd WHERE pd.project_id = p.id) AS n_papers
        FROM projects p
        ORDER BY p.created_at DESC, p.id DESC
        """
    ).fetchall()
    return [
        {"id": r[0], "name": r[1], "description": r[2], "created_at": r[3], "n_papers": r[4]}
        for r in rows
    ]


def get_project(conn, project_id: int) -> Optional[Dict[str, Any]]:
    r = conn.execute(
        "SELECT id, name, description, created_at FROM projects WHERE id = ?",
        (project_id,),
    ).fetchone()
    if not r:
        return None
    return {"id": r[0], "name": r[1], "description": r[2], "created_at": r[3]}


def delete_project(conn, project_id: int) -> None:
    # ON DELETE CASCADE clears join + codebook; documents/chunks untouched.
    conn.execute("DELETE FROM projects WHERE id = ?", (project_id,))
    conn.commit()


def add_papers(conn, project_id: int, doc_ids: List[int]) -> int:
    """Link existing corpus documents to a project. Idempotent. Returns count linked now."""
    added = 0
    for did in doc_ids:
        cur = conn.execute(
            "INSERT OR IGNORE INTO project_documents (project_id, doc_id) VALUES (?, ?)",
            (project_id, int(did)),
        )
        added += cur.rowcount
    conn.commit()
    return added


def remove_paper(conn, project_id: int, doc_id: int) -> None:
    """Unlink a paper from a project; the paper stays in the global corpus."""
    conn.execute(
        "DELETE FROM project_documents WHERE project_id = ? AND doc_id = ?",
        (project_id, int(doc_id)),
    )
    conn.commit()


def list_papers(conn, project_id: int) -> List[Dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT d.id, d.title, d.authors, d.year, d.folder, d.path, d.status, pd.added_at
        FROM project_documents pd
        JOIN documents d ON d.id = pd.doc_id
        WHERE pd.project_id = ?
        ORDER BY d.year DESC, d.title
        """,
        (project_id,),
    ).fetchall()
    return [
        {
            "id": r[0],
            "title": r[1],
            "authors": r[2],
            "year": r[3],
            "folder": r[4],
            "path": r[5],
            "status": r[6],
            "added_at": r[7],
        }
        for r in rows
    ]


def project_doc_ids(conn, project_id: int) -> List[int]:
    rows = conn.execute(
        "SELECT doc_id FROM project_documents WHERE project_id = ?", (project_id,)
    ).fetchall()
    return [r[0] for r in rows]
