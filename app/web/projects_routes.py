"""Project/workspace endpoints (Phase 10) + scoped chat/matrix wiring (Phase 11-13)."""

import shutil
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, Field

from app.core.config import PROJECTS_DIR, ROOT
from app.core.db import connect
from app.core import projects as proj
from app.ingest.pipeline import file_hash
from app.web.uploads import start_upload_job

router = APIRouter(prefix="/projects")

UPLOAD_DIR = Path(ROOT) / "data" / "uploads"


def ensure_project_folder(conn, project: dict) -> str:
    """Create (and record) the project's watched folder; idempotent. Returns path."""
    if project.get("folder_path"):
        Path(project["folder_path"]).mkdir(parents=True, exist_ok=True)
        return project["folder_path"]
    folder = Path(PROJECTS_DIR) / f"{project['id']}-{proj.slugify(project['name'])}"
    folder.mkdir(parents=True, exist_ok=True)
    proj.set_folder_path(conn, project["id"], str(folder))
    project["folder_path"] = str(folder)
    return str(folder)


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
        p = proj.get_project(conn, pid)
        ensure_project_folder(conn, p)  # auto-create the watched folder
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
        ensure_project_folder(conn, p)  # backfill folder for pre-feature projects
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


@router.post("/{project_id}/upload", status_code=202)
async def upload_pdf(project_id: int, file: UploadFile = File(...)) -> JSONResponse:
    """Save the PDF, then ingest in a background job. Poll GET /uploads/{job_id}."""
    conn = connect()
    try:
        if not proj.get_project(conn, project_id):
            raise HTTPException(404, "project not found")
    finally:
        conn.close()
    if not (file.filename or "").lower().endswith(".pdf"):
        raise HTTPException(400, "only .pdf accepted")

    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    # Name the stored file by content hash, NOT the client filename: two
    # different PDFs sharing a filename would otherwise overwrite each other
    # on disk and (via upsert-by-path) clobber the first document's registry
    # row. Hash naming also dedups identical re-uploads to the same path.
    tmp = UPLOAD_DIR / f".incoming-{uuid.uuid4().hex}.pdf"
    with tmp.open("wb") as out:
        shutil.copyfileobj(file.file, out)
    h = file_hash(tmp)
    dest = UPLOAD_DIR / f"{h}.pdf"
    # Atomic replace: dest is hash-named so same content — overwrite is harmless.
    tmp.replace(dest)

    job_id = start_upload_job(dest, project_id, file.filename or dest.name)
    return JSONResponse({"job_id": job_id}, status_code=202)


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
        from app.rag.index_health import check_query_dim
        mismatch = check_query_dim(conn)
        if mismatch:
            raise HTTPException(409, mismatch)
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


class ParseTitleRequest(BaseModel):
    title: str = Field("", min_length=0)


class FrameworkRequest(BaseModel):
    variables: Dict[str, Any] = Field(default_factory=dict)
    title: str = ""


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


def _view_or_404(conn, project_id, view):
    from app.rag.matrix import load_matrix, shape_view

    if not proj.get_project(conn, project_id):
        raise HTTPException(404, "project not found")
    return shape_view(load_matrix(conn, project_id), view)


@router.get("/{project_id}/matrix/export.csv")
def export_csv(project_id: int, view: str = "matrix") -> Response:
    from app.web.export import to_csv

    conn = connect()
    try:
        data = to_csv(_view_or_404(conn, project_id, view))
    finally:
        conn.close()
    return Response(
        content=data,
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="matrix-{project_id}-{view}.csv"'},
    )


@router.get("/{project_id}/matrix/export.xlsx")
def export_xlsx(project_id: int, view: str = "matrix") -> Response:
    from app.web.export import to_xlsx

    conn = connect()
    try:
        v = _view_or_404(conn, project_id, view)
        codebook = proj.list_codebook(conn, project_id)
        data = to_xlsx(v, codebook=codebook)
    finally:
        conn.close()
    return Response(
        content=data,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="matrix-{project_id}-{view}.xlsx"'},
    )


@router.post("/{project_id}/framework/parse-title")
def framework_parse_title(project_id: int, req: ParseTitleRequest) -> JSONResponse:
    from app.rag.framework import parse_title

    if not (req.title or "").strip():
        raise HTTPException(422, "title kosong")
    conn = connect()
    try:
        if not proj.get_project(conn, project_id):
            raise HTTPException(404, "project not found")
        try:
            variables = parse_title(req.title)
        except RuntimeError as e:  # missing LLM key etc.
            raise HTTPException(503, str(e))
        return JSONResponse({"variables": variables})
    finally:
        conn.close()


@router.post("/{project_id}/framework")
def framework_build(project_id: int, req: FrameworkRequest) -> JSONResponse:
    from app.rag.framework import build_framework

    conn = connect()
    try:
        if not proj.get_project(conn, project_id):
            raise HTTPException(404, "project not found")
        variables = dict(req.variables)
        variables["title"] = req.title
        try:
            out = build_framework(conn, project_id, variables)
        except ValueError as e:  # naskah tanpa paper
            raise HTTPException(400, str(e))
        except RuntimeError as e:
            raise HTTPException(503, str(e))
        return JSONResponse(out)
    finally:
        conn.close()


@router.get("/{project_id}/framework")
def framework_get(project_id: int) -> JSONResponse:
    from app.rag.framework import load_framework

    conn = connect()
    try:
        if not proj.get_project(conn, project_id):
            raise HTTPException(404, "project not found")
        out = load_framework(conn, project_id)
        if out is None:
            out = {"dsl": "", "citations": {}, "variables": {}, "title": "", "updated_at": None}
        return JSONResponse(out)
    finally:
        conn.close()


class CodebookSet(BaseModel):
    entries: List[Dict[str, Any]] = Field(default_factory=list)


@router.get("/{project_id}/codebook")
def get_codebook(project_id: int) -> JSONResponse:
    conn = connect()
    try:
        if not proj.get_project(conn, project_id):
            raise HTTPException(404, "project not found")
        return JSONResponse({"codebook": proj.list_codebook(conn, project_id)})
    finally:
        conn.close()


@router.post("/{project_id}/codebook")
def post_codebook(project_id: int, req: CodebookSet) -> JSONResponse:
    conn = connect()
    try:
        if not proj.get_project(conn, project_id):
            raise HTTPException(404, "project not found")
        proj.set_codebook(conn, project_id, req.entries)
        return JSONResponse({"codebook": proj.list_codebook(conn, project_id)})
    finally:
        conn.close()


@router.post("/{project_id}/codebook/bootstrap")
async def bootstrap_codebook(project_id: int, file: UploadFile = File(...)) -> JSONResponse:
    """Learn tag vocabulary (+ colors) from an old matrix sheet/CSV -> closed coding."""
    from app.web.export import bootstrap_codebook_from_bytes

    conn = connect()
    try:
        if not proj.get_project(conn, project_id):
            raise HTTPException(404, "project not found")
        data = await file.read()
        entries = bootstrap_codebook_from_bytes(data, file.filename or "")
        if not entries:
            raise HTTPException(422, "no 'tag' column found in uploaded file")
        proj.set_codebook(conn, project_id, entries)
        return JSONResponse({"learned": len(entries), "codebook": proj.list_codebook(conn, project_id)})
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
