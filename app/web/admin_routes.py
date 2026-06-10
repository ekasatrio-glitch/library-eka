"""Admin endpoints: background corpus reembed with progress polling (single job)."""

import threading
import time
from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from app.core import config
from app.core.db import connect, get_meta, set_meta
from app.ingest.reembed import reembed

router = APIRouter(prefix="/admin")

_lock = threading.Lock()
_job: Dict[str, Any] = {
    "running": False, "done": 0, "total": 0,
    "model": None, "dim": None, "error": None, "finished_at": None,
}


class ReembedStart(BaseModel):
    model: Optional[str] = None
    dim: Optional[int] = None
    force: bool = False


def _progress(done: int, total: int) -> None:
    _job["done"] = done
    _job["total"] = total


def _run(model: str, dim: int, force: bool) -> None:
    try:
        reembed(model, dim, force=force, progress=_progress)
    except Exception as e:  # surface any failure to the poller
        _job["error"] = str(e)
    finally:
        _job["running"] = False
        _job["finished_at"] = time.time()


@router.post("/reembed/start")
def start(req: ReembedStart) -> JSONResponse:
    model = req.model or config.EMBED_MODEL
    dim = req.dim or config.EMBED_DIM
    with _lock:
        if _job["running"]:
            raise HTTPException(status_code=409, detail="reembed already running")
        conn = connect()
        try:
            total = conn.execute("SELECT COUNT(*) FROM chunks").fetchone()[0]
        finally:
            conn.close()
        _job.update(running=True, done=0, total=total, model=model, dim=dim,
                    error=None, finished_at=None)
    threading.Thread(target=_run, args=(model, dim, req.force), daemon=True).start()
    return JSONResponse({"started": True, "total": total})


@router.get("/reembed/status")
def status() -> JSONResponse:
    return JSONResponse(dict(_job))


class LlmSet(BaseModel):
    choice: str


@router.get("/llm")
def get_llm() -> JSONResponse:
    conn = connect()
    try:
        active = get_meta(conn, "llm_choice") or (config.LLM_CHOICES[0] if config.LLM_CHOICES else "")
    finally:
        conn.close()
    return JSONResponse({"choices": config.LLM_CHOICES, "active": active})


@router.post("/llm")
def set_llm(req: LlmSet) -> JSONResponse:
    if req.choice not in config.LLM_CHOICES:
        raise HTTPException(status_code=422, detail=f"unknown choice: {req.choice}")
    conn = connect()
    try:
        set_meta(conn, "llm_choice", req.choice)
    finally:
        conn.close()
    return JSONResponse({"active": req.choice})
