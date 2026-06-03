"""Title-based rename endpoints (Phase 14): preview -> apply (confirmed) -> undo."""

from typing import List, Optional

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from app.core.db import connect

router = APIRouter(prefix="/rename")


def _chat():
    from app.rag.generator import chat
    return chat


@router.get("/preview")
def preview(doc_ids: Optional[str] = None) -> JSONResponse:
    """Preview old->new names. `doc_ids` is an optional comma-separated list."""
    from app.ingest.rename import plan_renames

    ids = [int(x) for x in doc_ids.split(",") if x.strip()] if doc_ids else None
    conn = connect()
    try:
        try:
            plan = plan_renames(conn, _chat(), doc_ids=ids)
        except RuntimeError as e:  # missing LLM key
            raise HTTPException(503, str(e))
        # Drop heavy 'meta' from the wire payload.
        clean = [{k: v for k, v in p.items() if k != "meta"} for p in plan]
        return JSONResponse({"plan": clean, "count": sum(1 for p in plan if p.get("status") == "rename")})
    finally:
        conn.close()


class ApplyRequest(BaseModel):
    doc_ids: Optional[List[int]] = None
    batch: str = Field("manual", min_length=1)


@router.post("/apply")
def apply(req: ApplyRequest) -> JSONResponse:
    from app.ingest.rename import apply_renames, plan_renames

    conn = connect()
    try:
        try:
            plan = plan_renames(conn, _chat(), doc_ids=req.doc_ids)
        except RuntimeError as e:
            raise HTTPException(503, str(e))
        result = apply_renames(conn, plan, batch=req.batch)
        return JSONResponse(
            {
                "applied": len(result["applied"]),
                "errors": result["errors"],
                "skipped": len(result["skipped"]),
                "batch": result["batch"],
            }
        )
    finally:
        conn.close()


@router.post("/undo")
def undo() -> JSONResponse:
    from app.ingest.rename import undo_last

    conn = connect()
    try:
        return JSONResponse(undo_last(conn))
    finally:
        conn.close()
