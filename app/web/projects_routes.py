"""Project/workspace endpoints (Phase 10) + scoped chat/matrix wiring (Phase 11-13)."""

import shutil
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from app.core.config import ROOT
from app.core.db import connect, document_exists
from app.core import projects as proj
from app.ingest.pipeline import file_hash, ingest_pdf

router = APIRouter(prefix="/projects")

UPLOAD_DIR = Path(ROOT) / "data" / "uploads"


class ProjectCreate(BaseModel):
    name: str = Field(..., min_length=1)
    description: Optional[str] = None


class AddPapers(BaseModel):
    doc_ids: List[int] = Field(default_factory=list)


class ScopedAsk(BaseModel):
    question: str = Field(..., min_length=1)
    top_k: int = 6
    expand: bool = False  # True = search the whole library, not just the project


@router.post("")
def create(req: ProjectCreate) -> JSONResponse:
    conn = connect()
    try:
        pid = proj.create_project(conn, req.name, req.description)
        return JSONResponse({"id": pid, **proj.get_project(conn, pid)})
    finally:
        conn.close()


@router.get("")
def index() -> JSONResponse:
    conn = connect()
    try:
        return JSONResponse({"projects": proj.list_projects(conn)})
    finally:
        conn.close()


@router.get("/{project_id}")
def detail(project_id: int) -> JSONResponse:
    conn = connect()
    try:
        p = proj.get_project(conn, project_id)
        if not p:
            raise HTTPException(404, "project not found")
        p["papers"] = proj.list_papers(conn, project_id)
        return JSONResponse(p)
    finally:
        conn.close()


@router.delete("/{project_id}")
def remove(project_id: int) -> JSONResponse:
    conn = connect()
    try:
        if not proj.get_project(conn, project_id):
            raise HTTPException(404, "project not found")
        proj.delete_project(conn, project_id)
        return JSONResponse({"deleted": project_id})
    finally:
        conn.close()


@router.get("/{project_id}/papers")
def papers(project_id: int) -> JSONResponse:
    conn = connect()
    try:
        if not proj.get_project(conn, project_id):
            raise HTTPException(404, "project not found")
        return JSONResponse({"papers": proj.list_papers(conn, project_id)})
    finally:
        conn.close()


@router.post("/{project_id}/papers")
def add_from_library(project_id: int, req: AddPapers) -> JSONResponse:
    """Link existing corpus documents (selected doc_ids) to the project."""
    conn = connect()
    try:
        if not proj.get_project(conn, project_id):
            raise HTTPException(404, "project not found")
        added = proj.add_papers(conn, project_id, req.doc_ids)
        return JSONResponse({"linked": added, "papers": proj.list_papers(conn, project_id)})
    finally:
        conn.close()


@router.post("/{project_id}/upload")
async def upload_pdf(project_id: int, file: UploadFile = File(...)) -> JSONResponse:
    """Drop a new PDF: ingest into the GLOBAL corpus once (dedup by hash), link to project."""
    conn = connect()
    try:
        if not proj.get_project(conn, project_id):
            raise HTTPException(404, "project not found")
        if not (file.filename or "").lower().endswith(".pdf"):
            raise HTTPException(400, "only .pdf accepted")

        UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
        dest = UPLOAD_DIR / Path(file.filename).name
        with dest.open("wb") as out:
            shutil.copyfileobj(file.file, out)

        # Ingest into global corpus (idempotent: skips if hash already present).
        processed, reason = ingest_pdf(dest, conn=conn)
        h = file_hash(dest)
        doc_id = document_exists(conn, h)
        if doc_id is None:
            raise HTTPException(422, f"ingest failed: {reason}")
        proj.add_papers(conn, project_id, [doc_id])
        return JSONResponse(
            {"doc_id": doc_id, "ingested": processed, "reason": reason,
             "papers": proj.list_papers(conn, project_id)}
        )
    finally:
        conn.close()


@router.post("/{project_id}/ask")
def scoped_ask(project_id: int, req: ScopedAsk) -> JSONResponse:
    """Project-scoped RAG. Default retrieves only from project papers; `expand`
    widens to the whole library. Adds a discovery `nudge`: other library papers
    that look relevant but aren't in the project (computed without polluting the
    main answer)."""
    from app.rag.ask import ask
    from app.rag.retriever import search

    conn = connect()
    try:
        if not proj.get_project(conn, project_id):
            raise HTTPException(404, "project not found")
        doc_ids = proj.project_doc_ids(conn, project_id)
        scoped = bool(doc_ids) and not req.expand
        filters = {"doc_ids": doc_ids} if scoped else None
        try:
            result = ask(req.question, top_k=req.top_k, filters=filters, conn=conn)
        except RuntimeError as e:
            raise HTTPException(503, str(e))

        nudge: List[Dict[str, Any]] = []
        if scoped:
            in_proj = set(doc_ids)
            seen: set = set()
            for h in search(req.question, top_k=req.top_k, conn=conn):
                if h.doc_id not in in_proj and h.doc_id not in seen:
                    seen.add(h.doc_id)
                    nudge.append({"doc_id": h.doc_id, "title": h.title})
        result["nudge"] = nudge
        result["scoped"] = scoped
        return JSONResponse(result)
    finally:
        conn.close()


class MatrixRequest(BaseModel):
    view: str = "matrix"  # matrix | linimasa | tema
    overrides: Dict[int, str] = Field(default_factory=dict)  # doc_id -> forced schema


@router.post("/{project_id}/matrix")
def post_matrix(project_id: int, req: MatrixRequest) -> JSONResponse:
    """Build (extract + persist) the synthesis matrix for the project, grounded."""
    from app.rag.generator import chat
    from app.rag.matrix import build_matrix, shape_view
    from app.rag.retriever import search

    conn = connect()
    try:
        if not proj.get_project(conn, project_id):
            raise HTTPException(404, "project not found")
        try:
            rows = build_matrix(conn, project_id, chat_fn=chat, search_fn=search,
                                overrides={int(k): v for k, v in req.overrides.items()})
        except RuntimeError as e:  # missing LLM key etc.
            raise HTTPException(503, str(e))
        return JSONResponse(shape_view(rows, req.view))
    finally:
        conn.close()


@router.get("/{project_id}/matrix")
def get_matrix(project_id: int, view: str = "matrix") -> JSONResponse:
    """Return the persisted matrix (no re-extraction) in the requested view."""
    from app.rag.matrix import load_matrix, shape_view

    conn = connect()
    try:
        if not proj.get_project(conn, project_id):
            raise HTTPException(404, "project not found")
        return JSONResponse(shape_view(load_matrix(conn, project_id), view))
    finally:
        conn.close()


@router.delete("/{project_id}/papers/{doc_id}")
def remove_paper(project_id: int, doc_id: int) -> JSONResponse:
    conn = connect()
    try:
        if not proj.get_project(conn, project_id):
            raise HTTPException(404, "project not found")
        proj.remove_paper(conn, project_id, doc_id)
        return JSONResponse({"removed": doc_id, "papers": proj.list_papers(conn, project_id)})
    finally:
        conn.close()
