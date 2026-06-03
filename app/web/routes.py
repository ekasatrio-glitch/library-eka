from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field

from app.core.db import connect

router = APIRouter()
TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


class AskRequest(BaseModel):
    question: str = Field(..., min_length=1)
    top_k: int = 6
    year_min: Optional[int] = None
    year_max: Optional[int] = None
    folder: Optional[str] = None
    authors_like: Optional[str] = None


def _filters(req: AskRequest) -> Dict[str, Any]:
    f: Dict[str, Any] = {}
    if req.year_min is not None:
        f["year_min"] = req.year_min
    if req.year_max is not None:
        f["year_max"] = req.year_max
    if req.folder:
        f["folder"] = req.folder
    if req.authors_like:
        f["authors_like"] = req.authors_like
    return f


@router.post("/ask")
def post_ask(req: AskRequest) -> JSONResponse:
    from app.rag.ask import ask  # lazy import: requires LLM key
    try:
        result = ask(req.question, top_k=req.top_k, filters=_filters(req))
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))
    return JSONResponse(result)


class DraftRequest(BaseModel):
    topic: str = Field(..., min_length=1)
    top_k: int = 10
    style: str = Field("vancouver", pattern="^(vancouver|apa)$")
    year_min: Optional[int] = None
    year_max: Optional[int] = None


@router.post("/draft")
def post_draft(req: DraftRequest) -> JSONResponse:
    from app.rag.drafting import draft_paragraph
    filters: Dict[str, Any] = {}
    if req.year_min is not None:
        filters["year_min"] = req.year_min
    if req.year_max is not None:
        filters["year_max"] = req.year_max
    try:
        out = draft_paragraph(req.topic, style=req.style, top_k=req.top_k, filters=filters or None)
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))
    return JSONResponse(out)


class MindmapRequest(BaseModel):
    topic: str = Field(..., min_length=1)
    breadth: int = 4
    top_k: int = 6


@router.post("/mindmap")
def post_mindmap(req: MindmapRequest) -> JSONResponse:
    from app.rag.mindmap import build_mindmap
    try:
        out = build_mindmap(req.topic, breadth=req.breadth, top_k=req.top_k)
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))
    return JSONResponse(out)


@router.get("/library")
def get_library(
    q: Optional[str] = None,
    folder: Optional[str] = None,
    year_min: Optional[int] = None,
    year_max: Optional[int] = None,
    limit: int = Query(200, ge=1, le=1000),
) -> JSONResponse:
    conn = connect()
    try:
        clauses: List[str] = []
        params: List[Any] = []
        if q:
            clauses.append("(title LIKE ? OR authors LIKE ?)")
            params += [f"%{q}%", f"%{q}%"]
        if folder:
            clauses.append("folder = ?")
            params.append(folder)
        if year_min is not None:
            clauses.append("year >= ?")
            params.append(year_min)
        if year_max is not None:
            clauses.append("year <= ?")
            params.append(year_max)
        where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
        sql = (
            "SELECT id, title, authors, year, folder, path, status, added_at "
            f"FROM documents {where} ORDER BY added_at DESC LIMIT ?"
        )
        rows = conn.execute(sql, (*params, limit)).fetchall()
        items = [
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
        folders = [
            r[0]
            for r in conn.execute(
                "SELECT DISTINCT folder FROM documents WHERE folder IS NOT NULL ORDER BY folder"
            ).fetchall()
        ]
        return JSONResponse({"items": items, "folders": folders, "count": len(items)})
    finally:
        conn.close()


@router.get("/pdf/{doc_id}")
def get_pdf(doc_id: int):
    conn = connect()
    try:
        row = conn.execute("SELECT path FROM documents WHERE id = ?", (doc_id,)).fetchone()
    finally:
        conn.close()
    if not row:
        raise HTTPException(status_code=404, detail="document not found")
    p = Path(row[0])
    if not p.exists():
        raise HTTPException(status_code=404, detail="file missing on disk")
    return FileResponse(str(p), media_type="application/pdf", filename=p.name)


class RetitleRequest(BaseModel):
    doc_ids: Optional[List[int]] = None  # None = all documents


@router.post("/library/retitle")
def post_retitle(req: RetitleRequest) -> JSONResponse:
    """Re-extract titles (LLM + Crossref) for documents whose ingest-time heuristic
    title was wrong (e.g. picked up a journal banner). Updates the registry."""
    from app.rag.generator import chat
    from app.ingest.title import retitle_document

    conn = connect()
    try:
        if req.doc_ids:
            ids = [int(i) for i in req.doc_ids]
        else:
            ids = [r[0] for r in conn.execute("SELECT id FROM documents ORDER BY id").fetchall()]
        try:
            results = [retitle_document(conn, did, chat) for did in ids]
        except RuntimeError as e:  # missing LLM key
            raise HTTPException(status_code=503, detail=str(e))
        updated = sum(1 for r in results if r.get("status") == "updated")
        return JSONResponse({"updated": updated, "results": results})
    finally:
        conn.close()


@router.get("/", response_class=HTMLResponse)
def index(request: Request):
    return templates.TemplateResponse(request, "index.html", {})


@router.get("/viewer", response_class=HTMLResponse)
def viewer(request: Request):
    return templates.TemplateResponse(request, "viewer.html", {})
