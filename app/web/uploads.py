"""Background PDF-upload ingest jobs with progress polling (multi-job registry).

Same pattern as the admin reembed job (admin_routes.py) but keyed per upload so
several files can ingest concurrently. The worker thread opens its own SQLite
connection (connections are not shareable across threads)."""

import threading
import uuid
from pathlib import Path
from typing import Any, Dict

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse

from app.core import projects as proj
from app.core.db import connect, document_exists
from app.ingest.pipeline import file_hash, ingest_pdf

router = APIRouter(prefix="/uploads")

_lock = threading.Lock()
_jobs: Dict[str, Dict[str, Any]] = {}


def start_upload_job(pdf_path: Path, project_id: int, filename: str) -> str:
    job_id = uuid.uuid4().hex
    with _lock:
        # Evict oldest finished jobs when registry exceeds ~50 finished entries.
        # Unfinished jobs are never evicted.
        finished = [k for k, v in _jobs.items() if v["finished"]]
        for k in finished[:-50] if len(finished) > 50 else []:
            del _jobs[k]
        _jobs[job_id] = {
            "stage": "antri", "done": 0, "total": 0, "error": None,
            "doc_id": None, "project_id": project_id, "filename": filename,
            "already": False, "finished": False,
        }
    threading.Thread(target=_run, args=(job_id, Path(pdf_path), project_id),
                     daemon=True).start()
    return job_id


def _run(job_id: str, pdf_path: Path, project_id: int) -> None:
    job = _jobs[job_id]

    def progress(stage: str, done: int, total: int) -> None:
        job["stage"], job["done"], job["total"] = stage, done, total

    conn = connect()
    try:
        h = file_hash(pdf_path)
        existing = document_exists(conn, h)
        if existing is not None:
            job["already"] = True
            job["doc_id"] = existing
        else:
            ok, reason = ingest_pdf(pdf_path, conn=conn, progress=progress)
            if not ok:
                job["error"] = reason
                job["stage"] = "gagal"
                return
            job["doc_id"] = document_exists(conn, h)
        proj.add_papers(conn, project_id, [job["doc_id"]])
        job["stage"] = "selesai"
    except Exception as e:  # surface any failure to the poller
        job["error"] = str(e) or repr(e)
        job["stage"] = "gagal"
    finally:
        job["finished"] = True
        conn.close()


@router.get("/{job_id}")
def status(job_id: str) -> JSONResponse:
    job = _jobs.get(job_id)
    if job is None:
        raise HTTPException(404, "job not found")
    return JSONResponse(dict(job))
