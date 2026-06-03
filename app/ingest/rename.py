"""Title-based PDF rename (Phase 14): plan -> preview -> apply -> undo.

Registry safety: each rename moves the file in place AND updates documents.path in
one DB transaction. content_hash is unchanged, so dedup-by-hash means the file is
NOT re-embedded; the watcher/startup scan will match by hash and we keep the path
authoritative here. Collisions get a numeric suffix; an undo log records old->new.
"""

import os
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from app.core.config import CROSSREF_ENABLED, RENAME_PATTERN
from app.ingest.title import build_filename, extract_meta


def _unique_target(directory: Path, filename: str, taken: set) -> Path:
    """Resolve a non-colliding target path (append ' (n)' before suffix)."""
    stem = Path(filename).stem
    suffix = Path(filename).suffix
    candidate = directory / filename
    n = 2
    while str(candidate) in taken or (candidate.exists()):
        candidate = directory / f"{stem} ({n}){suffix}"
        n += 1
    return candidate


def plan_renames(
    conn,
    chat_fn: Callable,
    doc_ids: Optional[List[int]] = None,
    pattern: Optional[str] = None,
    use_crossref: Optional[bool] = None,
) -> List[Dict[str, Any]]:
    """Compute old->new for each document. Does NOT touch disk or DB."""
    pattern = pattern or RENAME_PATTERN
    use_crossref = CROSSREF_ENABLED if use_crossref is None else use_crossref

    if doc_ids:
        q = f"SELECT id, path FROM documents WHERE id IN ({','.join('?' * len(doc_ids))})"
        rows = conn.execute(q, [int(i) for i in doc_ids]).fetchall()
    else:
        rows = conn.execute("SELECT id, path FROM documents ORDER BY id").fetchall()

    taken: set = set()
    plan: List[Dict[str, Any]] = []
    for doc_id, old_path in rows:
        op = Path(old_path)
        entry: Dict[str, Any] = {"doc_id": doc_id, "old_path": str(op), "new_path": None}
        if not op.exists():
            entry["status"] = "missing"
            plan.append(entry)
            continue
        try:
            meta = extract_meta(op, chat_fn, use_crossref=use_crossref)
            filename = build_filename(meta, pattern, suffix=op.suffix or ".pdf")
        except Exception as e:  # extraction must never abort the whole batch
            entry["status"] = f"error: {e}"
            plan.append(entry)
            continue

        target = op.with_name(filename)
        if target == op:
            entry["new_path"] = str(op)
            entry["status"] = "unchanged"
            plan.append(entry)
            continue

        target = _unique_target(op.parent, filename, taken)
        taken.add(str(target))
        entry["new_path"] = str(target)
        entry["status"] = "rename"
        entry["meta"] = meta
        plan.append(entry)
    return plan


def apply_renames(conn, plan: List[Dict[str, Any]], batch: str) -> Dict[str, Any]:
    """Execute the 'rename' entries. File move + path update are one transaction."""
    applied, skipped, errors = [], [], []
    for entry in plan:
        if entry.get("status") != "rename":
            skipped.append(entry)
            continue
        old_path = Path(entry["old_path"])
        new_path = Path(entry["new_path"])
        if not old_path.exists():
            errors.append({**entry, "error": "source vanished"})
            continue
        if new_path.exists():
            errors.append({**entry, "error": "target exists"})
            continue
        try:
            os.rename(old_path, new_path)
        except OSError as e:
            errors.append({**entry, "error": str(e)})
            continue
        try:
            conn.execute(
                "UPDATE documents SET path = ? WHERE id = ?",
                (str(new_path), entry["doc_id"]),
            )
            conn.execute(
                "INSERT INTO rename_log (doc_id, old_path, new_path, batch) VALUES (?, ?, ?, ?)",
                (entry["doc_id"], str(old_path), str(new_path), batch),
            )
            conn.commit()
        except Exception as e:
            conn.rollback()
            # Revert the disk move to keep file/registry consistent. If the revert
            # itself fails, surface it loudly — the file is orphaned at new_path
            # while the registry still points at old_path.
            revert_err = None
            try:
                os.rename(new_path, old_path)
            except OSError as re:
                revert_err = str(re)
            err = {**entry, "error": f"db: {e}"}
            if revert_err:
                err["revert_failed"] = revert_err
                err["orphaned_at"] = str(new_path)
            errors.append(err)
            continue
        applied.append(entry)
    return {"batch": batch, "applied": applied, "skipped": skipped, "errors": errors}


def undo_last(conn) -> Dict[str, Any]:
    """Revert the most recent un-undone rename batch."""
    row = conn.execute(
        "SELECT batch FROM rename_log WHERE undone = 0 AND batch IS NOT NULL "
        "ORDER BY id DESC LIMIT 1"
    ).fetchone()
    if not row:
        return {"reverted": [], "batch": None}
    batch = row[0]
    entries = conn.execute(
        "SELECT id, doc_id, old_path, new_path FROM rename_log "
        "WHERE batch = ? AND undone = 0 ORDER BY id DESC",
        (batch,),
    ).fetchall()
    reverted, errors = [], []
    for log_id, doc_id, old_path, new_path in entries:
        np, op = Path(new_path), Path(old_path)
        if op.exists():
            # Original already present: only safe if the renamed file isn't also
            # there (would mean an unrelated file sits at old_path).
            if np.exists():
                errors.append({"doc_id": doc_id, "error": "both old and new paths exist; skipped"})
                continue
        elif np.exists():
            try:
                os.rename(np, op)
            except OSError as e:
                errors.append({"doc_id": doc_id, "error": str(e)})
                continue
        else:
            # Neither file exists — can't safely restore; don't rewrite the registry.
            errors.append({"doc_id": doc_id, "error": "neither old nor new path exists; skipped"})
            continue
        conn.execute("UPDATE documents SET path = ? WHERE id = ?", (str(op), doc_id))
        conn.execute("UPDATE rename_log SET undone = 1 WHERE id = ?", (log_id,))
        conn.commit()
        reverted.append({"doc_id": doc_id, "old_path": old_path, "new_path": new_path})
    return {"reverted": reverted, "errors": errors, "batch": batch}
