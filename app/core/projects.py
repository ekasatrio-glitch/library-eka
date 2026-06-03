"""Project/workspace data access. Corpus stays global; projects reference a
subset of `documents` via the `project_documents` join (no duplication)."""

import unicodedata
from pathlib import Path
from typing import Any, Dict, List, Optional


def slugify(name: str, max_len: int = 60) -> str:
    """ASCII-safe folder slug (no regex): NFKD fold -> keep alnum, others -> '-'."""
    s = unicodedata.normalize("NFKD", name or "").encode("ascii", "ignore").decode("ascii")
    out = []
    for ch in s.lower():
        out.append(ch if ch.isalnum() else "-")
    slug = "".join(out)
    while "--" in slug:
        slug = slug.replace("--", "-")
    slug = slug.strip("-")[:max_len].strip("-")
    return slug or "project"


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
        "SELECT id, name, description, created_at, folder_path FROM projects WHERE id = ?",
        (project_id,),
    ).fetchone()
    if not r:
        return None
    return {"id": r[0], "name": r[1], "description": r[2], "created_at": r[3], "folder_path": r[4]}


def set_folder_path(conn, project_id: int, folder_path: str) -> None:
    conn.execute(
        "UPDATE projects SET folder_path = ? WHERE id = ?", (folder_path, project_id)
    )
    conn.commit()


def project_for_path(conn, abspath: str) -> Optional[int]:
    """Return the project whose folder_path is an ancestor of `abspath`, else None."""
    p = Path(abspath).resolve()
    rows = conn.execute(
        "SELECT id, folder_path FROM projects WHERE folder_path IS NOT NULL"
    ).fetchall()
    for pid, folder in rows:
        try:
            if folder and p.is_relative_to(Path(folder).resolve()):
                return pid
        except (ValueError, OSError):
            continue
    return None


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


def list_codebook(conn, project_id: int) -> List[Dict[str, Any]]:
    rows = conn.execute(
        "SELECT tag, category, color FROM project_codebook WHERE project_id = ? ORDER BY tag",
        (project_id,),
    ).fetchall()
    return [{"tag": r[0], "category": r[1], "color": r[2]} for r in rows]


def upsert_codebook_tag(conn, project_id, tag, category=None, color=None) -> None:
    conn.execute(
        "INSERT INTO project_codebook (project_id, tag, category, color) VALUES (?, ?, ?, ?) "
        "ON CONFLICT(project_id, tag) DO UPDATE SET category=excluded.category, color=excluded.color",
        (project_id, tag, category, color),
    )
    conn.commit()


def set_codebook(conn, project_id, entries: List[Dict[str, Any]]) -> int:
    """Replace the project's codebook with `entries` ([{tag, category?, color?}])."""
    conn.execute("DELETE FROM project_codebook WHERE project_id = ?", (project_id,))
    for e in entries:
        if not e.get("tag"):
            continue
        conn.execute(
            "INSERT OR REPLACE INTO project_codebook (project_id, tag, category, color) VALUES (?, ?, ?, ?)",
            (project_id, e["tag"], e.get("category"), e.get("color")),
        )
    conn.commit()
    return len(entries)


def project_doc_ids(conn, project_id: int) -> List[int]:
    rows = conn.execute(
        "SELECT doc_id FROM project_documents WHERE project_id = ?", (project_id,)
    ).fetchall()
    return [r[0] for r in rows]
