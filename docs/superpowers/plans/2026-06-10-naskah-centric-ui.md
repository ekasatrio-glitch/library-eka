# Naskah-Centric UI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Restructure the `/` grid UI around a two-screen, naskah-centric flow (Beranda → Ruang Kerja) for a non-technical primary user, with async PDF upload + progress, scoped drafting, and a runtime LLM switcher.

**Architecture:** Frontend rework of `templates/new.html` + `static/new/*` (ES modules, no build step). Three small backend additions: `doc_ids` on `/draft`, background upload jobs with progress polling (pattern copied from the admin reembed job), and `GET/POST /admin/llm` persisting the active generation model in the `meta` table. Legacy `/tools` UI untouched.

**Tech Stack:** Python/FastAPI, SQLite (existing `meta` table), vanilla ES modules, `node:test` for pure JS modules, pytest for backend.

**Spec:** `docs/superpowers/specs/2026-06-10-naskah-centric-ui-design.md`

**Conventions you must follow:**
- Always `source venv/bin/activate` first.
- Python tests: `python -m pytest tests/test_X.py -v`. JS tests: `node --test tests/js/*.test.mjs` (glob form, never a bare dir).
- Tests force `EXTRACTOR=pymupdf` via autouse fixture in `tests/conftest.py` — already handled, don't fight it.
- DB isolation in tests: `monkeypatch.setattr(dbmod, "DB_PATH", db)` where `import app.core.db as dbmod` (see `tests/test_projects.py`).
- Embedding stub in tests: patch `app.ingest.pipeline.embed_texts` (see `_embed_stub` in `tests/test_projects.py`).
- User-facing strings in Indonesian.

## File Structure

| File | Action | Responsibility |
|---|---|---|
| `app/web/routes.py` | Modify | `/draft` gains `doc_ids` |
| `app/ingest/pipeline.py` | Modify | `ingest_pdf(progress=...)`, batched embedding |
| `app/web/uploads.py` | Create | Background upload-job registry + `GET /uploads/{job_id}` |
| `app/web/projects_routes.py` | Modify | `POST /projects/{id}/upload` becomes async (202 + job_id) |
| `app/web/app.py` | Modify | include uploads router |
| `app/core/config.py` | Modify | `LLM_CHOICES`, `llm_config(choice)` |
| `app/rag/generator.py` | Modify | reads `meta.llm_choice` override |
| `app/web/admin_routes.py` | Modify | `GET/POST /admin/llm` |
| `app/web/templates/new.html` | Rewrite | topbar + single `#screen` shell |
| `app/web/static/new/main.js` | Rewrite | entry: splash, routing Beranda ↔ Ruang Kerja |
| `app/web/static/new/beranda.js` | Create | naskah card list screen |
| `app/web/static/new/workspace.js` | Create | workspace shell + 4 tabs (Tanya/Paper/Draft/Matriks) |
| `app/web/static/new/papers.js` | Create | Paper tab: list, upload, import, peta konsep |
| `app/web/static/new/picker.js` | Create | library doc-picker modal (Promise-based) |
| `app/web/static/new/upload.js` | Create | upload POST + job polling (pure-ish, testable) |
| `app/web/static/new/admin.js` | Create | ⚙ LLM switcher panel |
| `app/web/static/new/chat.js` | Rewrite | drop HOME_CARDS; add expand toggle, placeholder, friendly errors |
| `app/web/static/new/draft.js` | Modify | `getDocIds` scoping |
| `app/web/static/new/mindmap.js` | Rewrite | `openMindmapModal({docIds, store})` instead of a view |
| `app/web/static/new/history.js` | Modify | `list(scope)` filter |
| `app/web/static/new/api.js` | Modify | add `friendlyError` |
| `app/web/static/new/projects.js` | Delete | superseded by beranda/workspace/papers |
| `app/web/static/new/new.css` | Modify | shell/cards/tabs/dropzone/progress styles |
| `tests/test_draft_scope.py` | Create | doc_ids passthrough |
| `tests/test_pipeline.py` | Modify | progress-callback test |
| `tests/test_uploads.py` | Create | async job flow |
| `tests/test_projects.py` | Modify | 3 upload tests adapt to job polling |
| `tests/test_llm_switcher.py` | Create | config + endpoints + generator override |
| `tests/test_new_ui.py` | Rewrite | new shell assertions |
| `tests/js/history.test.mjs` | Modify | scope tests |
| `tests/js/api.test.mjs` | Modify | friendlyError tests |
| `tests/js/upload.test.mjs` | Create | STAGE_LABELS + pollJob |
| `CLAUDE.md` | Modify | update Web section description |

---

### Task 1: `/draft` accepts `doc_ids`

**Files:**
- Modify: `app/web/routes.py` (DraftRequest ~line 58, post_draft ~line 66)
- Create: `tests/test_draft_scope.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_draft_scope.py
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.web.routes import router


def _client():
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


def _fake_draft(topic, style="vancouver", top_k=10, filters=None):
    _fake_draft.captured = filters
    return {"paragraph": "p (1)", "references": ["r"], "citations": []}


def test_draft_passes_doc_ids():
    with patch("app.rag.drafting.draft_paragraph", side_effect=_fake_draft):
        r = _client().post("/draft", json={"topic": "stunting", "doc_ids": [3, 7]})
    assert r.status_code == 200, r.text
    assert _fake_draft.captured == {"doc_ids": [3, 7]}


def test_draft_without_doc_ids_keeps_filters_none():
    with patch("app.rag.drafting.draft_paragraph", side_effect=_fake_draft):
        r = _client().post("/draft", json={"topic": "stunting"})
    assert r.status_code == 200
    assert _fake_draft.captured is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_draft_scope.py -v`
Expected: FAIL — `_fake_draft.captured is None` vs `{"doc_ids": ...}` mismatch on the first test (unknown field `doc_ids` is ignored by pydantic, so filters stays None).

- [ ] **Step 3: Implement**

In `app/web/routes.py`, add to `DraftRequest`:

```python
class DraftRequest(BaseModel):
    topic: str = Field(..., min_length=1)
    top_k: int = 10
    style: str = Field("vancouver", pattern="^(vancouver|apa)$")
    year_min: Optional[int] = None
    year_max: Optional[int] = None
    doc_ids: Optional[List[int]] = None
```

(`List` is already imported? Check the imports at top of `routes.py`; if not: `from typing import List`.)

In `post_draft`, after the year filters:

```python
    if req.doc_ids:
        filters["doc_ids"] = req.doc_ids
```

- [ ] **Step 4: Run tests to verify pass**

Run: `python -m pytest tests/test_draft_scope.py -v`
Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add app/web/routes.py tests/test_draft_scope.py
git commit -m "feat(draft): accept doc_ids to scope drafting to a naskah"
```

---

### Task 2: `ingest_pdf` progress callback + batched embedding

**Files:**
- Modify: `app/ingest/pipeline.py:40-89`
- Test: `tests/test_pipeline.py` (append)

- [ ] **Step 1: Write the failing test**

Append to `tests/test_pipeline.py` (reuse that file's existing pdf-making/stub helpers if present; otherwise use this self-contained version):

```python
def test_ingest_progress_callback(tmp_path, monkeypatch):
    import fitz
    from unittest.mock import patch
    from app.core import config as cfg
    from app.core.db import init_db
    from app.ingest.pipeline import ingest_pdf

    def _stub(texts, model=None, base_url=None):
        return [[0.01] * cfg.EMBED_DIM for _ in texts]

    pdf = tmp_path / "big.pdf"
    doc = fitz.open()
    for _ in range(4):
        page = doc.new_page()
        page.insert_textbox(page.rect, ("Stunting intervensi gizi balita " * 120), fontsize=9)
    doc.save(str(pdf))
    doc.close()

    conn = init_db(str(tmp_path / "p.db"))
    calls = []
    with patch("app.ingest.pipeline.embed_texts", side_effect=_stub):
        ok, reason = ingest_pdf(pdf, conn=conn,
                                progress=lambda s, d, t: calls.append((s, d, t)))
    conn.close()
    assert ok, reason
    assert calls[0][0] == "membaca"
    idx = [c for c in calls if c[0] == "mengindeks"]
    assert idx, "no mengindeks progress"
    assert idx[-1][1] == idx[-1][2] > 0          # ends at done == total
    dones = [d for _, d, _ in idx]
    assert dones == sorted(dones)                # monotonic
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_pipeline.py::test_ingest_progress_callback -v`
Expected: FAIL — `TypeError: ingest_pdf() got an unexpected keyword argument 'progress'`.

- [ ] **Step 3: Implement**

In `app/ingest/pipeline.py`, change `ingest_pdf`:

```python
def ingest_pdf(pdf_path: str | Path, conn=None, progress=None) -> tuple[bool, str]:
    """Ingest single PDF. Returns (processed, reason).

    progress(stage, done, total) is called with stage "membaca" (extraction
    started) then "mengindeks" (per-batch embedding) — drives the upload UI bar.
    """
    path = Path(pdf_path).resolve()
    if not path.exists():
        return False, f"missing: {path}"

    def report(stage: str, done: int, total: int) -> None:
        if progress:
            progress(stage, done, total)

    own_conn = conn is None
    if own_conn:
        conn = init_db()

    try:
        h = file_hash(path)
        if document_exists(conn, h) is not None:
            return False, "skip (already ingested)"

        report("membaca", 0, 0)
        pages = extract_pages(path)
        if not pages:
            return False, "no pages"

        fp_text = pages[0][1] if pages else ""
        title, authors, year = guess_metadata(fp_text, path)

        doc_id = upsert_document(
            conn,
            path=str(path),
            content_hash=h,
            title=title,
            authors=authors,
            year=year,
            folder=str(path.parent),
            status="processing",
        )

        delete_chunks(conn, doc_id)  # clear stale chunks on re-ingest (hash changed)
        chunks = chunk_pages(pages)
        if not chunks:
            set_document_status(conn, doc_id, "empty")
            return False, "no chunks"

        texts = [c.text for c in chunks]
        report("mengindeks", 0, len(texts))
        embeddings: List[list] = []
        BATCH = 8
        for i in range(0, len(texts), BATCH):
            embeddings.extend(embed_texts(texts[i:i + BATCH]))
            report("mengindeks", min(i + BATCH, len(texts)), len(texts))
        for c, emb in zip(chunks, embeddings):
            insert_chunk(conn, doc_id, c.page_start, c.page_end, c.text, emb)

        set_document_status(conn, doc_id, "done")
        return True, f"ingested ({len(chunks)} chunks)"
    except EmbeddingError as e:
        return False, f"embed error: {e}"
    finally:
        if own_conn:
            conn.close()
```

(Only the `report` helper, the two `report(...)` call sites, and the batched-embedding loop are new; everything else byte-identical.)

- [ ] **Step 4: Run the full pipeline + watcher tests (batching must not break anything)**

Run: `python -m pytest tests/test_pipeline.py tests/test_watcher.py tests/test_reingest.py -v`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add app/ingest/pipeline.py tests/test_pipeline.py
git commit -m "feat(ingest): optional progress callback with batched embedding"
```

---

### Task 3: Background upload jobs + status endpoint

**Files:**
- Create: `app/web/uploads.py`
- Modify: `app/web/projects_routes.py:120-156` (upload endpoint)
- Modify: `app/web/app.py` (include router)
- Create: `tests/test_uploads.py`
- Modify: `tests/test_projects.py` (3 upload tests)

- [ ] **Step 1: Write the failing test**

```python
# tests/test_uploads.py
import time
from pathlib import Path
from unittest.mock import patch

import fitz
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core import config as cfg
from app.core import projects as proj
from app.core.db import init_db


def _embed_stub(texts, model=None, base_url=None):
    return [[0.01] * cfg.EMBED_DIM for _ in texts]


def _pdf_bytes(tmp_path, text):
    d = fitz.open()
    p = d.new_page()
    p.insert_text((72, 72), text, fontsize=10)
    out = tmp_path / "tmp.pdf"
    d.save(str(out))
    d.close()
    return out.read_bytes()


def _app_client(tmp_path, monkeypatch):
    import app.core.db as dbmod
    import app.web.projects_routes as pr
    from app.web import uploads

    db = str(tmp_path / "u.db")
    monkeypatch.setattr(dbmod, "DB_PATH", db)
    monkeypatch.setattr(pr, "UPLOAD_DIR", tmp_path / "uploads")
    conn = init_db(db)
    pid = proj.create_project(conn, "P")
    conn.close()

    app = FastAPI()
    app.include_router(pr.router)
    app.include_router(uploads.router)
    return TestClient(app), pid


def _wait_job(client, job_id, timeout=10.0):
    t0 = time.time()
    while time.time() - t0 < timeout:
        r = client.get(f"/uploads/{job_id}")
        assert r.status_code == 200, r.text
        j = r.json()
        if j["finished"]:
            return j
        time.sleep(0.05)
    raise AssertionError("upload job did not finish in time")


def test_upload_returns_job_and_completes(tmp_path, monkeypatch):
    client, pid = _app_client(tmp_path, monkeypatch)
    data = _pdf_bytes(tmp_path, "epidemiologi stunting kabupaten")
    with patch("app.ingest.pipeline.embed_texts", side_effect=_embed_stub):
        r = client.post(f"/projects/{pid}/upload",
                        files={"file": ("a.pdf", data, "application/pdf")})
        assert r.status_code == 202, r.text
        job = _wait_job(client, r.json()["job_id"])
    assert job["error"] is None
    assert job["stage"] == "selesai"
    assert job["doc_id"] is not None
    assert job["already"] is False
    papers = client.get(f"/projects/{pid}/papers").json()["papers"]
    assert len(papers) == 1


def test_upload_duplicate_reports_already(tmp_path, monkeypatch):
    client, pid = _app_client(tmp_path, monkeypatch)
    data = _pdf_bytes(tmp_path, "konten identik xyz")
    with patch("app.ingest.pipeline.embed_texts", side_effect=_embed_stub):
        j1 = _wait_job(client, client.post(
            f"/projects/{pid}/upload",
            files={"file": ("a.pdf", data, "application/pdf")}).json()["job_id"])
        j2 = _wait_job(client, client.post(
            f"/projects/{pid}/upload",
            files={"file": ("b.pdf", data, "application/pdf")}).json()["job_id"])
    assert j1["doc_id"] == j2["doc_id"]
    assert j2["already"] is True and j2["error"] is None
    papers = client.get(f"/projects/{pid}/papers").json()["papers"]
    assert len(papers) == 1


def test_unknown_job_404(tmp_path, monkeypatch):
    client, _ = _app_client(tmp_path, monkeypatch)
    assert client.get("/uploads/nope").status_code == 404


def test_upload_rejects_non_pdf(tmp_path, monkeypatch):
    client, pid = _app_client(tmp_path, monkeypatch)
    r = client.post(f"/projects/{pid}/upload",
                    files={"file": ("notes.txt", b"hi", "text/plain")})
    assert r.status_code == 400
```

**Important:** the `patch("app.ingest.pipeline.embed_texts", ...)` context must stay open while polling — the job thread runs during `_wait_job`.

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_uploads.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.web.uploads'`.

- [ ] **Step 3: Create `app/web/uploads.py`**

```python
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
            _, reason = ingest_pdf(pdf_path, conn=conn, progress=progress)
            doc_id = document_exists(conn, h)
            if doc_id is None:
                job["error"] = reason
                return
            job["doc_id"] = doc_id
        proj.add_papers(conn, project_id, [job["doc_id"]])
        job["stage"] = "selesai"
    except Exception as e:  # surface any failure to the poller
        job["error"] = str(e)
    finally:
        job["finished"] = True
        conn.close()


@router.get("/{job_id}")
def status(job_id: str) -> JSONResponse:
    job = _jobs.get(job_id)
    if job is None:
        raise HTTPException(404, "job not found")
    return JSONResponse(dict(job))
```

- [ ] **Step 4: Rework the upload endpoint in `app/web/projects_routes.py`**

Add import near the top: `from app.web.uploads import start_upload_job`.
Replace the body of `upload_pdf` (keep the hash-naming comment):

```python
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
    if dest.exists():
        tmp.unlink(missing_ok=True)
    else:
        tmp.rename(dest)

    job_id = start_upload_job(dest, project_id, file.filename or dest.name)
    return JSONResponse({"job_id": job_id}, status_code=202)
```

(`document_exists` import in projects_routes becomes unused — remove it from the import line if nothing else uses it; `ingest_pdf` likewise. Check with `grep -n "document_exists\|ingest_pdf" app/web/projects_routes.py` before removing.)

- [ ] **Step 5: Register the router in `app/web/app.py`**

```python
from app.web.uploads import router as uploads_router
```
and inside `create_app()` after the other includes:
```python
    app.include_router(uploads_router)
```

- [ ] **Step 6: Run new tests**

Run: `python -m pytest tests/test_uploads.py -v`
Expected: 4 passed.

- [ ] **Step 7: Adapt the 3 existing upload tests in `tests/test_projects.py`**

They assert the old synchronous response. Add this helper near the top of the file (after `_embed_stub`):

```python
def _wait_job(client, job_id, timeout=10.0):
    import time
    t0 = time.time()
    while time.time() - t0 < timeout:
        j = client.get(f"/uploads/{job_id}").json()
        if j["finished"]:
            return j
        time.sleep(0.05)
    raise AssertionError("upload job did not finish in time")
```

Each test app that posts uploads must also include the uploads router:
```python
from app.web import uploads
app.include_router(uploads.router)
```

Then update the three call sites:

1. In the main flow test (~line 117): replace

```python
    with patch("app.ingest.pipeline.embed_texts", side_effect=_embed_stub):
        with pdf.open("rb") as fh:
            r = client.post(f"/projects/{pid}/upload", files={"file": ("upload.pdf", fh, "application/pdf")})
    assert r.status_code == 200, r.text
    assert len(r.json()["papers"]) == 2
```
with
```python
    with patch("app.ingest.pipeline.embed_texts", side_effect=_embed_stub):
        with pdf.open("rb") as fh:
            r = client.post(f"/projects/{pid}/upload", files={"file": ("upload.pdf", fh, "application/pdf")})
        assert r.status_code == 202, r.text
        job = _wait_job(client, r.json()["job_id"])
    assert job["error"] is None
    assert len(client.get(f"/projects/{pid}/papers").json()["papers"]) == 2
```
and where the old code read `new_doc = r.json()["doc_id"]`, use `new_doc = job["doc_id"]`.

2. `test_upload_same_filename_different_content_no_clobber` (~line 218): keep both posts inside the patch, wait for both jobs inside the patch, then `d1, d2 = j1["doc_id"], j2["doc_id"]`.

3. `test_upload_identical_content_dedups` (~line 253): same change; assert `j1["doc_id"] == j2["doc_id"]` and `j2["already"] is True`.

- [ ] **Step 8: Run the whole projects + uploads suite**

Run: `python -m pytest tests/test_projects.py tests/test_uploads.py tests/test_project_folders.py -v`
Expected: all pass.

- [ ] **Step 9: Commit**

```bash
git add app/web/uploads.py app/web/projects_routes.py app/web/app.py tests/test_uploads.py tests/test_projects.py
git commit -m "feat(upload): background ingest jobs with progress polling

Sync in-request ingest timed out on large PDFs (1000-page books take
minutes through Docling). Upload now returns 202 + job_id; the UI polls
GET /uploads/{job_id} for stage/done/total."
```

---

### Task 4: LLM switcher (config + generator override + admin endpoints)

**Files:**
- Modify: `app/core/config.py` (LLM_CHOICES, llm_config)
- Modify: `app/rag/generator.py` (`_client_and_model`)
- Modify: `app/web/admin_routes.py` (GET/POST /admin/llm)
- Create: `tests/test_llm_switcher.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_llm_switcher.py
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core import config as cfg
from app.core.db import init_db, set_meta


def test_llm_config_choice_overrides_provider(monkeypatch):
    monkeypatch.setattr(cfg, "JATEVO_BASE_URL", "https://jatevo.example")
    monkeypatch.setattr(cfg, "JATEVO_API_KEY", "jk")
    key, base, model = cfg.llm_config("jatevo:llama-3.3-70b")
    assert (key, base, model) == ("jk", "https://jatevo.example", "llama-3.3-70b")


def test_llm_config_choice_without_model_uses_env_default(monkeypatch):
    key, base, model = cfg.llm_config("deepseek")
    assert base == cfg.DEEPSEEK_BASE_URL
    assert model  # falls back to DEEPSEEK_MODEL env default


def _client(tmp_path, monkeypatch):
    import app.core.db as dbmod
    from app.web.admin_routes import router

    db = str(tmp_path / "m.db")
    monkeypatch.setattr(dbmod, "DB_PATH", db)
    init_db(db).close()
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


def test_admin_llm_get_set_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setattr(cfg, "LLM_CHOICES", ["deepseek", "jatevo"])
    client = _client(tmp_path, monkeypatch)

    r = client.get("/admin/llm")
    assert r.status_code == 200
    assert r.json() == {"choices": ["deepseek", "jatevo"], "active": "deepseek"}

    assert client.post("/admin/llm", json={"choice": "jatevo"}).status_code == 200
    assert client.get("/admin/llm").json()["active"] == "jatevo"

    assert client.post("/admin/llm", json={"choice": "gpt-99"}).status_code == 422


def test_generator_uses_meta_choice(tmp_path, monkeypatch):
    import app.core.db as dbmod
    from app.rag import generator

    db = str(tmp_path / "g.db")
    monkeypatch.setattr(dbmod, "DB_PATH", db)
    conn = init_db(db)
    set_meta(conn, "llm_choice", "deepseek:custom-model")
    conn.close()
    monkeypatch.setattr(cfg, "DEEPSEEK_API_KEY", "dk")

    with patch("app.rag.generator.OpenAI"):
        _, model = generator._client_and_model()
    assert model == "custom-model"
```

- [ ] **Step 2: Run to verify failure**

Run: `python -m pytest tests/test_llm_switcher.py -v`
Expected: FAIL — `llm_config() takes 0 positional arguments`, 404 on `/admin/llm`.

- [ ] **Step 3: Implement config changes** (`app/core/config.py`)

Add `from typing import Optional` to the imports. Below `LLM_PROVIDER`:

```python
# Generation-model choices selectable at runtime from the admin mini-menu.
# Each entry is "provider" or "provider:model"; the active one is persisted in
# the meta table (key "llm_choice"). Add models here, no code change needed.
LLM_CHOICES = [c.strip() for c in os.getenv("LLM_CHOICES", "deepseek,jatevo").split(",") if c.strip()]
```

Replace `llm_config`:

```python
def llm_config(choice: Optional[str] = None) -> tuple[str, str, str]:
    """Resolve (api_key, base_url, model). choice = "provider[:model]" overrides
    the LLM_PROVIDER env; without a model suffix the provider's env default is used."""
    provider, _, model = (choice or LLM_PROVIDER).partition(":")
    provider = provider.strip().lower()
    if provider == "jatevo":
        if not JATEVO_BASE_URL:
            raise RuntimeError(
                "LLM_PROVIDER=jatevo but JATEVO_BASE_URL is empty — set it in .env "
                "(empty base_url silently falls back to api.openai.com)"
            )
        return JATEVO_API_KEY, JATEVO_BASE_URL, model or os.getenv("JATEVO_MODEL", "jatevo-default")
    return DEEPSEEK_API_KEY, DEEPSEEK_BASE_URL, model or os.getenv("DEEPSEEK_MODEL", "deepseek-chat")
```

Note: `cfg.llm_config` reads module globals (`JATEVO_BASE_URL` etc.) so monkeypatching `cfg.JATEVO_BASE_URL` works — but ONLY if `llm_config` references the module attribute. The current code does (module-level names resolve at call time). Don't convert these to locals captured at import.

- [ ] **Step 4: Implement generator override** (`app/rag/generator.py`)

Add import: `from app.core.db import connect, get_meta`. Replace `_client_and_model`:

```python
def _active_choice() -> Optional[str]:
    """meta.llm_choice set from the admin mini-menu; None = env default."""
    try:
        conn = connect()
        try:
            return get_meta(conn, "llm_choice")
        finally:
            conn.close()
    except Exception:
        return None


def _client_and_model() -> tuple[OpenAI, str]:
    api_key, base_url, model = llm_config(_active_choice())
    if not api_key:
        raise RuntimeError("LLM API key missing — set DEEPSEEK_API_KEY or JATEVO_API_KEY in .env")
    client = OpenAI(api_key=api_key, base_url=base_url or None)
    return client, model
```

- [ ] **Step 5: Implement admin endpoints** (`app/web/admin_routes.py`)

Add to imports: `from app.core.db import connect, get_meta, set_meta` (connect already imported). Append:

```python
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
```

- [ ] **Step 6: Run tests**

Run: `python -m pytest tests/test_llm_switcher.py tests/test_admin_reembed.py -v`
Expected: all pass (reembed suite proves admin router untouched).

- [ ] **Step 7: Add `LLM_CHOICES` to `.env.example`**

```
# Runtime-selectable generation models (admin ⚙ menu): provider[:model], comma-separated
LLM_CHOICES=deepseek,jatevo
```

- [ ] **Step 8: Commit**

```bash
git add app/core/config.py app/rag/generator.py app/web/admin_routes.py tests/test_llm_switcher.py .env.example
git commit -m "feat(admin): runtime LLM switcher persisted in meta table"
```

---

### Task 5: `history.js` per-scope filtering

**Files:**
- Modify: `app/web/static/new/history.js`
- Test: `tests/js/history.test.mjs` (append)

- [ ] **Step 1: Write the failing tests** (append to `tests/js/history.test.mjs`)

```javascript
test('list(scope) filters by scope', () => {
  const h = makeHistory(fakeStorage());
  h.save({ id: 'a', title: 'g', scope: 'global', messages: [], updatedAt: 1 });
  h.save({ id: 'b', title: 'p1', scope: '7', messages: [], updatedAt: 2 });
  h.save({ id: 'c', title: 'p2', scope: '7', messages: [], updatedAt: 3 });
  assert.deepEqual(h.list('7').map(c => c.id), ['c', 'b']);
  assert.deepEqual(h.list('global').map(c => c.id), ['a']);
});

test('list() without scope returns everything', () => {
  const h = makeHistory(fakeStorage());
  h.save({ id: 'a', title: 'g', scope: 'global', messages: [], updatedAt: 1 });
  h.save({ id: 'b', title: 'p', scope: '7', messages: [], updatedAt: 2 });
  assert.equal(h.list().length, 2);
});
```

- [ ] **Step 2: Run to verify failure**

Run: `node --test tests/js/*.test.mjs`
Expected: the two new tests fail (`list('7')` returns all 3).

- [ ] **Step 3: Implement** — in `history.js` replace `list()`:

```javascript
    list(scope) {
      const all = readAll().slice().sort((a, b) => (b.updatedAt || 0) - (a.updatedAt || 0));
      return scope === undefined ? all : all.filter(c => c.scope === scope);
    },
```

- [ ] **Step 4: Run to verify pass**

Run: `node --test tests/js/*.test.mjs`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add app/web/static/new/history.js tests/js/history.test.mjs
git commit -m "feat(ui): history.list(scope) filters conversations per naskah"
```

---

### Task 6: `api.js` friendlyError

**Files:**
- Modify: `app/web/static/new/api.js`
- Test: `tests/js/api.test.mjs` (append)

- [ ] **Step 1: Write the failing tests** (append; the file already imports from api.js — extend the import to include `friendlyError`)

```javascript
test('friendlyError maps 503 to layperson message', () => {
  assert.match(friendlyError(new Error('503: upstream down')), /Mesin penjawab sedang tidak aktif/);
});

test('friendlyError maps 409 to index-sync message', () => {
  assert.match(friendlyError(new Error('409: dim mismatch')), /tidak sinkron/);
});

test('friendlyError passes through other errors', () => {
  assert.match(friendlyError(new Error('404: nope')), /Terjadi kesalahan/);
});
```

- [ ] **Step 2: Run to verify failure**

Run: `node --test tests/js/*.test.mjs`
Expected: FAIL — `friendlyError` is not exported.

- [ ] **Step 3: Implement** — append to `api.js`:

```javascript
// Map raw HTTP errors to layperson Indonesian. Keep technical detail out of the
// primary user's face; Eka can read the server logs.
export function friendlyError(err) {
  const m = String((err && err.message) || err);
  if (m.startsWith("503")) return "Mesin penjawab sedang tidak aktif. Minta Eka menyalakannya.";
  if (m.startsWith("409")) return "Indeks perpustakaan sedang tidak sinkron. Minta Eka membukanya di /tools.";
  return "Terjadi kesalahan: " + m;
}
```

- [ ] **Step 4: Run to verify pass**

Run: `node --test tests/js/*.test.mjs` — all pass.

- [ ] **Step 5: Commit**

```bash
git add app/web/static/new/api.js tests/js/api.test.mjs
git commit -m "feat(ui): friendlyError maps HTTP failures to layperson copy"
```

---

### Task 7: `upload.js` (client upload + polling, pure parts tested)

**Files:**
- Create: `app/web/static/new/upload.js`
- Create: `tests/js/upload.test.mjs`

- [ ] **Step 1: Write the failing tests**

```javascript
// tests/js/upload.test.mjs
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { STAGE_LABELS, pollJob } from '../../app/web/static/new/upload.js';

test('stage labels are layperson Indonesian', () => {
  assert.equal(STAGE_LABELS.membaca, 'membaca halaman…');
  assert.equal(STAGE_LABELS.mengindeks, 'mengindeks…');
  assert.equal(STAGE_LABELS.selesai, 'selesai');
  assert.ok(STAGE_LABELS.antri);
});

test('pollJob ticks until finished and resolves with last job', async () => {
  const states = [
    { stage: 'membaca', done: 0, total: 0, finished: false },
    { stage: 'mengindeks', done: 4, total: 8, finished: false },
    { stage: 'selesai', done: 8, total: 8, finished: true },
  ];
  let i = 0;
  const ticks = [];
  const job = await pollJob('j1', j => ticks.push(j.stage), {
    delayMs: 0,
    fetchJson: async url => {
      assert.equal(url, '/uploads/j1');
      return states[i++];
    },
  });
  assert.equal(job.stage, 'selesai');
  assert.deepEqual(ticks, ['membaca', 'mengindeks', 'selesai']);
});
```

- [ ] **Step 2: Run to verify failure**

Run: `node --test tests/js/*.test.mjs`
Expected: FAIL — cannot find module upload.js.

- [ ] **Step 3: Implement `app/web/static/new/upload.js`**

```javascript
// PDF upload + ingest-job polling. Pure logic injectable for node:test;
// postFile is the FormData counterpart of api.js postJSON.
import { getJSON } from "./api.js";

export const STAGE_LABELS = {
  antri: "menunggu giliran…",
  membaca: "membaca halaman…",
  mengindeks: "mengindeks…",
  selesai: "selesai",
};

export async function postFile(url, file) {
  const fd = new FormData();
  fd.append("file", file, file.name);
  const r = await fetch(url, { method: "POST", body: fd });
  if (!r.ok) throw new Error(`${r.status}: ${await r.text()}`);
  return r.json();
}

export async function pollJob(jobId, onTick, { delayMs = 1000, fetchJson = getJSON } = {}) {
  for (;;) {
    const job = await fetchJson(`/uploads/${jobId}`);
    onTick(job);
    if (job.finished) return job;
    await new Promise(res => setTimeout(res, delayMs));
  }
}
```

- [ ] **Step 4: Run to verify pass**

Run: `node --test tests/js/*.test.mjs` — all pass.

- [ ] **Step 5: Commit**

```bash
git add app/web/static/new/upload.js tests/js/upload.test.mjs
git commit -m "feat(ui): upload helper with injectable job polling"
```

---

### Task 8: Shell — `new.html`, `main.js`, `beranda.js`, CSS, server-HTML tests

**Files:**
- Rewrite: `app/web/templates/new.html` (body shell only; head/splash/scripts kept)
- Rewrite: `app/web/static/new/main.js`
- Create: `app/web/static/new/beranda.js`
- Modify: `app/web/static/new/new.css` (append shell styles)
- Rewrite: `tests/test_new_ui.py`

Note: after this task the app boots to Beranda but workspace tabs are stubs until Task 9. That's fine — commit boundary is "shell renders, tests green".

- [ ] **Step 1: Rewrite the failing server-HTML tests** (`tests/test_new_ui.py`, full replacement)

```python
from fastapi.testclient import TestClient

from app.web.app import create_app


def _html():
    client = TestClient(create_app())
    r = client.get("/")
    assert r.status_code == 200
    return r.text


def test_root_renders_naskah_shell():
    html = _html()
    assert "library-eka" in html
    assert 'id="screen"' in html
    assert 'id="admin-gear"' in html
    assert 'type="module"' in html and "/static/new/main.js" in html


def test_old_tab_nav_is_gone():
    html = _html()
    for el in ('id="nav-chat"', 'id="nav-projects"', 'id="nav-draft"',
               'id="nav-mindmap"', 'id="sidebar"'):
        assert el not in html, f"legacy element still present: {el}"


def test_splash_kept():
    html = _html()
    for el in ('id="splash"', 'id="splash-close"', 'id="splash-enter"'):
        assert el in html


def test_semua_pdf_link_present():
    assert "/tools#tab-library" in _html()


def test_tools_still_serves_legacy_ui():
    client = TestClient(create_app())
    r = client.get("/tools")
    assert r.status_code == 200
    assert "/static/app.js" in r.text
```

- [ ] **Step 2: Run to verify failure**

Run: `python -m pytest tests/test_new_ui.py -v`
Expected: `test_root_renders_naskah_shell` and `test_old_tab_nav_is_gone` FAIL against the current template.

- [ ] **Step 3: Rewrite `new.html` body**

Keep `<head>` (fonts, css link), the `<noscript>`, the full splash `<div class="splash">…</div>`, and both `<script>` tags exactly as they are. Replace only the `<div class="app">…</div>` block with:

```html
<div class="app app-shell">
  <header class="topbar">
    <div class="brand">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M4 4h7a2 2 0 0 1 2 2v14a2 2 0 0 0-2-2H4z"/><path d="M20 4h-7a2 2 0 0 0-2 2v14a2 2 0 0 1 2-2h7z"/><path d="M12.5 10h1.5l1 2 1.5-3 1 1H19"/></svg>
      <span>library-eka</span>
    </div>
    <div class="top-actions">
      <a class="top-link" href="/tools#tab-library">Semua PDF ↗</a>
      <button class="gear" id="admin-gear" type="button" title="Pengaturan model" aria-label="Pengaturan model">⚙</button>
    </div>
  </header>
  <main class="screen" id="screen"></main>
</div>
```

Also update the `<noscript>` text to: `UI ini perlu JavaScript. Aktifkan JS, atau pakai antarmuka lama di <a href="/tools">/tools</a>.` (already says this — keep).

- [ ] **Step 4: Rewrite `main.js`**

```javascript
// Entry: splash, topbar gear, screen routing (Beranda <-> Ruang Kerja).
import { makeHistory } from "./history.js";
import { makeMindmapStore } from "./mindmaps.js";
import { mountSplash } from "./splash.js";
import { mountBeranda } from "./beranda.js";
import { mountWorkspace } from "./workspace.js";
import { wireAdminGear } from "./admin.js";

const history = makeHistory(window.localStorage);
const mindmaps = makeMindmapStore(window.localStorage);
const screen = document.getElementById("screen");

mountSplash(document, window.localStorage);
wireAdminGear(document.getElementById("admin-gear"));

function showBeranda() {
  mountBeranda(screen, { onOpen: openNaskah });
}
function openNaskah(pid) {
  mountWorkspace(screen, pid, { history, mindmaps, onBack: showBeranda });
}

showBeranda();
```

Until Tasks 9–11 land, create minimal stub modules so the page boots (each replaced later):

```javascript
// workspace.js (stub — replaced in Task 9)
export async function mountWorkspace(screen, pid) {
  screen.innerHTML = `<p style="padding:24px">Ruang kerja naskah ${pid} — segera.</p>`;
}
```
```javascript
// admin.js (stub — replaced in Task 11)
export function wireAdminGear() {}
```

- [ ] **Step 5: Create `beranda.js`**

```javascript
// Beranda: naskah card list + create. Calm grid style, no suggestion cards.
import { escapeHtml, getJSON, postJSON, friendlyError } from "./api.js";

export async function mountBeranda(screen, { onOpen }) {
  screen.innerHTML = `
    <div class="beranda">
      <div class="beranda-head">
        <h1>Naskah Saya</h1>
        <button class="df-btn" id="b-new" type="button">+ Naskah baru</button>
      </div>
      <div class="naskah-cards" id="b-cards">Memuat…</div>
    </div>`;
  screen.querySelector("#b-new").addEventListener("click", async () => {
    const name = prompt("Nama naskah baru:");
    if (!name || !name.trim()) return;
    const p = await postJSON("/projects", { name: name.trim() });
    onOpen(p.id);
  });
  const cards = screen.querySelector("#b-cards");
  try {
    const { projects } = await getJSON("/projects");
    cards.innerHTML = projects.map(p =>
      `<button class="naskah-card" data-pid="${p.id}" type="button">` +
      `<b>${escapeHtml(p.name)}</b>` +
      `<small>${escapeHtml(p.description || "")}</small></button>`).join("")
      || `<p class="gap">Belum ada naskah. Mulai dengan "+ Naskah baru".</p>`;
    cards.querySelectorAll("[data-pid]").forEach(el =>
      el.addEventListener("click", () => onOpen(Number(el.dataset.pid))));
  } catch (e) {
    cards.textContent = friendlyError(e);
  }
}
```

- [ ] **Step 6: Append shell styles to `new.css`**

```css
/* ===== naskah-centric shell (2026-06) ===== */
.app-shell{flex-direction:column}
.topbar{display:flex;align-items:center;justify-content:space-between;padding:10px 20px;border-bottom:1px solid #E2E8F0;background:#fff}
.topbar .brand{padding:0}
.top-actions{display:flex;gap:14px;align-items:center}
.top-link{font-size:13px;color:var(--brand);text-decoration:none}
.gear{background:none;border:none;cursor:pointer;font-size:16px;line-height:1}
.screen{flex:1;overflow:auto;display:flex;flex-direction:column}
.beranda{max-width:880px;width:100%;margin:0 auto;padding:36px 20px}
.beranda-head{display:flex;justify-content:space-between;align-items:center;margin-bottom:22px}
.naskah-cards{display:grid;grid-template-columns:repeat(auto-fill,minmax(230px,1fr));gap:14px}
.naskah-card{text-align:left;padding:18px;border:1px solid #E2E8F0;border-radius:12px;background:#fff;cursor:pointer;display:flex;flex-direction:column;gap:6px;font:inherit}
.naskah-card:hover{border-color:var(--brand)}
.ws{display:flex;flex-direction:column;flex:1;min-height:0}
.ws-head{padding:12px 20px 0;border-bottom:1px solid #E2E8F0}
.ws-back{background:none;border:none;color:var(--brand);cursor:pointer;padding:0;font:inherit;font-size:13px}
.ws-title{font-size:20px;font-weight:600;margin:6px 0 10px}
.ws-tabs{display:flex;gap:6px}
.ws-panel{flex:1;min-height:0;display:flex;flex-direction:column;overflow:auto}
.tanya{display:flex;flex:1;min-height:0}
.tanya-side{width:220px;border-right:1px solid #E2E8F0;padding:10px;overflow:auto;flex-shrink:0}
.tanya-main{flex:1;display:flex;flex-direction:column;min-width:0}
.expand-row{display:block;font-size:12px;color:#64748B;padding:6px 2px 0;cursor:pointer}
.paper-actions{display:flex;gap:8px;padding:16px 20px 0;flex-wrap:wrap}
.paper-rows{padding:8px 20px}
.paper-row{display:flex;align-items:center;gap:10px;padding:8px 4px;border-bottom:1px solid #F1F5F9}
.dropzone{border:2px dashed #CBD5E1;border-radius:12px;padding:24px;text-align:center;color:#64748B;margin:14px 20px}
.dropzone.drag{border-color:var(--brand);color:var(--brand)}
.upload-job{display:flex;align-items:center;gap:10px;margin:6px 20px;font-size:13px}
.upload-bar{flex:1;height:8px;background:#E2E8F0;border-radius:4px;overflow:hidden}
.upload-bar i{display:block;height:100%;background:var(--brand);width:0;transition:width .3s}
.mm-wide{width:min(860px,92vw)}
```

(If `.app` is `display:flex` row in the existing CSS, `.app-shell{flex-direction:column}` flips it; verify visually.)

- [ ] **Step 7: Run server-HTML tests**

Run: `python -m pytest tests/test_new_ui.py tests/test_web_ui.py -v`
Expected: all pass (`test_web_ui.py` covers the untouched `/tools`).

- [ ] **Step 8: Commit**

```bash
git add app/web/templates/new.html app/web/static/new/main.js app/web/static/new/beranda.js app/web/static/new/workspace.js app/web/static/new/admin.js app/web/static/new/new.css tests/test_new_ui.py
git commit -m "feat(ui): naskah-centric shell — topbar + Beranda card list"
```

---

### Task 9: Workspace — 4 tabs (Tanya / Paper / Draft / Matriks)

**Files:**
- Rewrite: `app/web/static/new/workspace.js` (replaces stub)
- Create: `app/web/static/new/papers.js`
- Create: `app/web/static/new/picker.js`
- Rewrite: `app/web/static/new/chat.js`
- Modify: `app/web/static/new/draft.js`
- Rewrite: `app/web/static/new/mindmap.js`
- Delete: `app/web/static/new/projects.js`

These are DOM modules — manual verification per project convention (only pure modules get node:test). JS suite must still pass (it imports api/citations/history/mindmaps/splash/upload only — confirm `grep -l projects.js tests/js/` is empty before deleting).

- [ ] **Step 1: Rewrite `chat.js`** (full file)

```javascript
// Chat surface. mountChat(container, opts) renders an empty state + thread + input.
// opts: { endpoint(question, {expand})->Promise(result), examples:[string],
//         placeholder:string, emptyTitle:string, emptyText:string,
//         showNudge:bool, expandToggle:bool,
//         initial:[{q,a,citations}], onExchange(messages), onAddPaper(docId) }
import { escapeHtml, friendlyError } from "./api.js";
import { renderAnswerHtml } from "./citations.js";

export function mountChat(container, opts) {
  const examples = opts.examples || [];
  const egHtml = examples.length
    ? `<div class="eg">${examples.map(e => `<button class="ecard" type="button">${escapeHtml(e)}</button>`).join("")}</div>`
    : "";
  const expandHtml = opts.expandToggle
    ? `<label class="expand-row"><input type="checkbox" id="expand"> cari juga di luar naskah ini</label>`
    : "";
  container.innerHTML = `
    <div class="scroll"><div class="inner" id="thread">
      <div class="empty" id="empty">
        <h1>${escapeHtml(opts.emptyTitle || "Tanya")}</h1>
        <p>${escapeHtml(opts.emptyText || "Tanya apa saja. Jawaban disertai sumber yang bisa diklik ke halaman PDF.")}</p>
        ${egHtml}
      </div>
    </div></div>
    <div class="input"><div class="input-in">
      <textarea id="q" rows="1" placeholder="${escapeHtml(opts.placeholder || "Tulis pertanyaan… (Enter kirim · Shift+Enter baris baru)")}"></textarea>
      <button class="send" id="send" type="button" aria-label="Kirim">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="22" y1="2" x2="11" y2="13"/><polygon points="22 2 15 22 11 13 2 9 22 2"/></svg>
      </button>
    </div>${expandHtml}</div>`;

  const thread = container.querySelector("#thread");
  let empty = container.querySelector("#empty");
  const ta = container.querySelector("#q");
  const send = container.querySelector("#send");
  const expandCb = container.querySelector("#expand");
  const messages = [];

  function clearEmpty() { if (empty) { empty.remove(); empty = null; } }

  function bubbleUser(q) {
    const d = document.createElement("div");
    d.className = "msg msg-u";
    d.innerHTML = `<div class="bub"></div>`;
    d.querySelector(".bub").textContent = q;
    thread.appendChild(d);
  }
  function bubbleAI(html) {
    const d = document.createElement("div");
    d.className = "msg msg-a";
    d.innerHTML = `<div class="ai">${html}</div>`;
    thread.appendChild(d);
    return d.querySelector(".ai");
  }
  function nudgeHtml(nudge) {
    if (!opts.showNudge || !(nudge || []).length) return "";
    return `<div class="nudge">${nudge.length} paper lain yang mungkin relevan: ` +
      nudge.map(n => `<button data-add="${n.doc_id}" type="button">+ ${escapeHtml(n.title || "(tanpa judul)")}</button>`).join("") +
      `</div>`;
  }

  async function submit() {
    const q = ta.value.trim();
    if (!q) return;
    clearEmpty();
    ta.value = "";
    bubbleUser(q);
    const pending = bubbleAI("…");
    try {
      const res = await opts.endpoint(q, { expand: !!(expandCb && expandCb.checked) });
      pending.innerHTML = renderAnswerHtml(res.answer, res.citations || []) + nudgeHtml(res.nudge);
      pending.querySelectorAll("button[data-add]").forEach(b =>
        b.addEventListener("click", () => { opts.onAddPaper && opts.onAddPaper(Number(b.dataset.add)); b.remove(); }));
      messages.push({ q, a: res.answer, citations: res.citations || [] });
      if (opts.onExchange) opts.onExchange(messages);
    } catch (err) {
      pending.textContent = friendlyError(err);
    }
    const sc = container.querySelector(".scroll");
    sc.scrollTop = sc.scrollHeight;
  }

  (opts.initial || []).forEach(m => {
    clearEmpty();
    bubbleUser(m.q);
    bubbleAI(renderAnswerHtml(m.a, m.citations || []));
    messages.push({ q: m.q, a: m.a, citations: m.citations || [] });
  });

  send.addEventListener("click", submit);
  ta.addEventListener("keydown", e => {
    if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); submit(); }
  });
  container.querySelectorAll(".ecard").forEach(c =>
    c.addEventListener("click", () => { ta.value = c.textContent; submit(); }));
}
```

(HOME_CARDS and the `data-go` nav handler are gone; endpoint now receives `(q, {expand})`.)

- [ ] **Step 2: Create `picker.js`** (extracted from old mindmap.js openPicker, Promise-based)

```javascript
// Library doc-picker modal. Resolves with the chosen doc_id array, or null on cancel.
import { escapeHtml, getJSON } from "./api.js";

let libraryCache = null;

export function openLibraryPicker({ preselected = [], title = "Pilih paper" } = {}) {
  return new Promise(resolve => {
    const overlay = document.createElement("div");
    overlay.className = "mm-modal";
    overlay.innerHTML = `
      <div class="mm-modal-box">
        <div class="mm-modal-head">
          <strong>${escapeHtml(title)}</strong>
          <input id="mm-pick-search" placeholder="Cari judul…" />
        </div>
        <div id="mm-pick-list" class="mm-pick-list">Memuat…</div>
        <div class="mm-modal-foot">
          <button id="mm-pick-all" type="button" class="df-btn ghost">Pilih semua</button>
          <button id="mm-pick-none" type="button" class="df-btn ghost">Kosongkan</button>
          <span class="grow"></span>
          <button id="mm-pick-cancel" type="button" class="df-btn ghost">Batal</button>
          <button id="mm-pick-ok" type="button" class="df-btn">Terapkan</button>
        </div>
      </div>`;
    document.body.appendChild(overlay);
    const listEl = overlay.querySelector("#mm-pick-list");
    const searchEl = overlay.querySelector("#mm-pick-search");
    const chosen = new Set(preselected);

    function rowHtml(it) {
      const yr = it.year ? ` (${it.year})` : "";
      return `<label class="mm-pick-row"><input type="checkbox" data-id="${it.id}"${chosen.has(it.id) ? " checked" : ""}/>` +
        `<span>${escapeHtml(it.title || "(tanpa judul)")}${escapeHtml(yr)}</span></label>`;
    }
    function paint(items) {
      listEl.innerHTML = items.map(rowHtml).join("") || `<div class="side-empty">Tidak ada paper.</div>`;
      listEl.querySelectorAll("input[data-id]").forEach(cb =>
        cb.addEventListener("change", () => {
          const id = Number(cb.dataset.id);
          if (cb.checked) chosen.add(id); else chosen.delete(id);
        }));
    }
    function close(result) { overlay.remove(); resolve(result); }

    (async () => {
      try {
        if (!libraryCache) libraryCache = (await getJSON("/library")).items || [];
        paint(libraryCache);
      } catch {
        listEl.innerHTML = `<div class="side-empty">Gagal memuat daftar paper.</div>`;
      }
    })();

    searchEl.addEventListener("input", () => {
      const q = searchEl.value.toLowerCase();
      paint((libraryCache || []).filter(it => (it.title || "").toLowerCase().includes(q)));
    });
    overlay.querySelector("#mm-pick-all").addEventListener("click", () => {
      (libraryCache || []).forEach(it => chosen.add(it.id));
      paint(libraryCache || []);
    });
    overlay.querySelector("#mm-pick-none").addEventListener("click", () => {
      chosen.clear(); paint(libraryCache || []);
    });
    overlay.querySelector("#mm-pick-cancel").addEventListener("click", () => close(null));
    overlay.addEventListener("click", e => { if (e.target === overlay) close(null); });
    overlay.querySelector("#mm-pick-ok").addEventListener("click", () => close([...chosen]));
  });
}
```

- [ ] **Step 3: Rewrite `mindmap.js`** as a modal

```javascript
// Peta-konsep modal: generate a markmap from given papers; autosave + reopen + delete.
import { escapeHtml, postJSON, friendlyError } from "./api.js";

function renderMindmap(host, markdown) {
  host.innerHTML = "";
  const mk = window.markmap;
  if (mk && mk.Markmap && mk.Transformer) {
    const svgEl = document.createElementNS("http://www.w3.org/2000/svg", "svg");
    svgEl.classList.add("markmap-svg");
    host.appendChild(svgEl);
    const { root } = new mk.Transformer().transform(markdown);
    const inst = mk.Markmap.create(svgEl, undefined, root);
    requestAnimationFrame(() => inst.fit());
    return;
  }
  const div = document.createElement("div");
  div.className = "markmap";
  const tpl = document.createElement("script");
  tpl.type = "text/template";
  tpl.textContent = markdown;
  div.appendChild(tpl);
  host.appendChild(div);
  if (mk && mk.autoLoader) mk.autoLoader.renderAll();
}

export function openMindmapModal({ docIds = [], store = null, scopeLabel = "" } = {}) {
  const overlay = document.createElement("div");
  overlay.className = "mm-modal";
  overlay.innerHTML = `
    <div class="mm-modal-box mm-wide">
      <div class="mm-modal-head">
        <strong>🗺️ Peta konsep</strong>
        <span class="gap">${escapeHtml(scopeLabel || (docIds.length + " paper"))}</span>
        <span class="grow"></span>
        <button id="mm-close" type="button" class="df-btn ghost">Tutup</button>
      </div>
      <form class="df-form" id="mm-form">
        <textarea id="mm-topic" rows="2" placeholder="Topik peta konsep…"></textarea>
        <div class="df-row">
          <input id="mm-breadth" type="number" min="2" max="8" value="4" title="Jumlah cabang" />
          <button class="df-btn" id="mm-submit" type="button">Buat peta</button>
        </div>
      </form>
      <div id="mm-saved" class="mm-pick-list"></div>
      <div id="mm-svg" class="markmap-wrap"></div>
    </div>`;
  document.body.appendChild(overlay);
  const topic = overlay.querySelector("#mm-topic");
  const breadth = overlay.querySelector("#mm-breadth");
  const svg = overlay.querySelector("#mm-svg");
  const savedEl = overlay.querySelector("#mm-saved");
  const close = () => overlay.remove();
  overlay.querySelector("#mm-close").addEventListener("click", close);
  overlay.addEventListener("click", e => { if (e.target === overlay) close(); });

  function renderSaved() {
    if (!store) { savedEl.hidden = true; return; }
    const items = store.list();
    savedEl.innerHTML = items.length
      ? items.map(m =>
          `<div class="recent-row"><button class="recent-open" data-mid="${m.id}" type="button">${escapeHtml(m.topic)}</button>` +
          `<button class="recent-del" data-del="${m.id}" title="Hapus" type="button">🗑</button></div>`).join("")
      : `<div class="side-empty">Belum ada peta tersimpan.</div>`;
    savedEl.querySelectorAll("[data-mid]").forEach(b =>
      b.addEventListener("click", () => {
        const m = store.get(b.dataset.mid);
        if (!m) return;
        topic.value = m.topic || "";
        breadth.value = m.breadth || 4;
        if (m.markdown) renderMindmap(svg, m.markdown);
      }));
    savedEl.querySelectorAll("[data-del]").forEach(b =>
      b.addEventListener("click", () => { store.remove(b.dataset.del); renderSaved(); }));
  }

  overlay.querySelector("#mm-submit").addEventListener("click", async () => {
    const t = topic.value.trim();
    if (!t) return;
    svg.innerHTML = "Menyusun peta…";
    try {
      const body = { topic: t, breadth: Number(breadth.value) || 4 };
      if (docIds.length) body.doc_ids = docIds;
      const res = await postJSON("/mindmap", body);
      renderMindmap(svg, res.markdown);
      if (store) {
        const now = Date.now();
        store.save({
          id: "m" + now, topic: t, breadth: Number(breadth.value) || 4,
          markdown: res.markdown, citations: res.citations || [],
          docIds: docIds.slice(), docLabel: scopeLabel, updatedAt: now,
        });
        renderSaved();
      }
    } catch (err) {
      svg.textContent = friendlyError(err);
    }
  });

  renderSaved();
}
```

- [ ] **Step 4: Modify `draft.js`** — signature + scoping + friendly errors. Change the mount signature and `submit`:

```javascript
export function mountDraft(viewEl, opts = {}) {
```
and in `submit()` replace the postJSON call with:
```javascript
      const body = { topic: t, style };
      const ids = opts.getDocIds ? opts.getDocIds() : [];
      if (ids && ids.length) body.doc_ids = ids;
      const res = await postJSON("/draft", body);
```
and the catch with:
```javascript
      para.innerHTML = `<div class="ai">${escapeHtml(friendlyError(err))}</div>`;
```
(add `friendlyError` to the api.js import). Update the placeholder to `"Topik paragraf akademik dari paper naskah ini…"`.

- [ ] **Step 5: Create `papers.js`**

```javascript
// Paper tab: list with checkboxes, upload with progress, import from library,
// peta-konsep launcher. onChanged() tells the workspace to refresh counts.
import { escapeHtml, getJSON, postJSON, friendlyError } from "./api.js";
import { openLibraryPicker } from "./picker.js";
import { openMindmapModal } from "./mindmap.js";
import { postFile, pollJob, STAGE_LABELS } from "./upload.js";

export function mountPapers(panel, pid, deps = {}) { // deps: {mindmaps, onChanged}
  let papers = [];
  const selected = new Set();

  async function refresh() {
    ({ papers } = await getJSON(`/projects/${pid}/papers`));
    selected.clear();
    render();
    if (deps.onChanged) deps.onChanged(papers);
  }

  function render() {
    panel.innerHTML = `
      <div class="paper-actions">
        <button class="df-btn" id="pp-upload" type="button">⬆ Unggah PDF</button>
        <input id="pp-file" type="file" accept="application/pdf" multiple hidden>
        <button class="df-btn ghost" id="pp-import" type="button">+ Dari Semua PDF</button>
        <button class="df-btn ghost" id="pp-map" type="button">🗺️ Peta konsep</button>
      </div>
      <div class="dropzone" id="pp-drop">Seret PDF ke sini untuk menambahkan ke naskah</div>
      <div id="pp-jobs"></div>
      <div class="paper-rows" id="pp-list">${papers.map(d =>
        `<div class="paper-row"><input type="checkbox" data-sel="${d.id}">` +
        `<span>${escapeHtml(d.title || "(tanpa judul)")}${d.year ? " · " + d.year : ""}</span>` +
        `<span class="grow"></span>` +
        `<button class="recent-del" data-rm="${d.id}" title="Keluarkan dari naskah" type="button">✕</button></div>`).join("")
        || `<p class="gap">Belum ada paper. Unggah PDF atau ambil dari Semua PDF.</p>`}</div>`;

    panel.querySelectorAll("[data-sel]").forEach(cb =>
      cb.addEventListener("change", () => {
        const id = Number(cb.dataset.sel);
        if (cb.checked) selected.add(id); else selected.delete(id);
      }));
    panel.querySelectorAll("[data-rm]").forEach(b =>
      b.addEventListener("click", async () => {
        await fetch(`/projects/${pid}/papers/${b.dataset.rm}`, { method: "DELETE" });
        refresh();
      }));

    const fileInput = panel.querySelector("#pp-file");
    panel.querySelector("#pp-upload").addEventListener("click", () => fileInput.click());
    fileInput.addEventListener("change", () => uploadAll([...fileInput.files]));

    const drop = panel.querySelector("#pp-drop");
    drop.addEventListener("dragover", e => { e.preventDefault(); drop.classList.add("drag"); });
    drop.addEventListener("dragleave", () => drop.classList.remove("drag"));
    drop.addEventListener("drop", e => {
      e.preventDefault();
      drop.classList.remove("drag");
      uploadAll([...e.dataTransfer.files].filter(f => /\.pdf$/i.test(f.name)));
    });

    panel.querySelector("#pp-import").addEventListener("click", async () => {
      const ids = await openLibraryPicker({
        preselected: papers.map(p => p.id),
        title: "Ambil paper dari Semua PDF",
      });
      if (!ids) return;
      const add = ids.filter(id => !papers.some(p => p.id === id));
      if (add.length) await postJSON(`/projects/${pid}/papers`, { doc_ids: add });
      refresh();
    });

    panel.querySelector("#pp-map").addEventListener("click", () => {
      const ids = selected.size ? [...selected] : papers.map(p => p.id);
      openMindmapModal({
        docIds: ids,
        store: deps.mindmaps,
        scopeLabel: selected.size ? `${selected.size} paper terpilih` : "semua paper naskah",
      });
    });
  }

  async function uploadAll(files) {
    const jobsEl = panel.querySelector("#pp-jobs");
    await Promise.all(files.map(async file => {
      const row = document.createElement("div");
      row.className = "upload-job";
      row.innerHTML = `<span class="uj-name">${escapeHtml(file.name)}</span>` +
        `<div class="upload-bar"><i></i></div><span class="uj-stage">mengunggah…</span>`;
      jobsEl.appendChild(row);
      const bar = row.querySelector("i");
      const stageEl = row.querySelector(".uj-stage");
      try {
        const { job_id } = await postFile(`/projects/${pid}/upload`, file);
        const job = await pollJob(job_id, j => {
          stageEl.textContent = STAGE_LABELS[j.stage] || j.stage;
          bar.style.width = j.total ? Math.round(100 * j.done / j.total) + "%" : "10%";
        });
        if (job.error) {
          stageEl.textContent = "gagal: " + job.error;
        } else {
          bar.style.width = "100%";
          stageEl.textContent = job.already
            ? "sudah ada di perpustakaan — ditautkan ke naskah ini"
            : "selesai";
        }
      } catch (err) {
        stageEl.textContent = friendlyError(err);
      }
    }));
    refresh();
  }

  refresh();
  return { refresh };
}
```

- [ ] **Step 6: Rewrite `workspace.js`** (replaces stub)

```javascript
// Ruang kerja satu naskah: tab Tanya / Paper / Draft / Matriks.
import { escapeHtml, getJSON, postJSON, friendlyError } from "./api.js";
import { mountChat } from "./chat.js";
import { mountDraft } from "./draft.js";
import { mountPapers } from "./papers.js";

function cell(v) {
  const text = (v && typeof v === "object") ? (v.text ?? "") : (v ?? "");
  const s = String(text);
  const gap = /tidak disebutkan|tidak dilaporkan|tidak ada paper/i.test(s);
  return `<td${gap ? ' class="gap"' : ""}>${escapeHtml(s)}</td>`;
}

function matrixTable(res) {
  const rows = res.rows || [];
  if (!rows.length) return `<p class="gap">Belum ada hasil. Klik "Bangun matriks".</p>`;
  const cols = res.columns || Object.keys(rows[0].fields || {});
  return `<table class="matrix"><thead><tr><th>Sumber</th><th>Tahun</th><th>Skema</th>` +
    cols.map(c => `<th>${escapeHtml(c)}</th>`).join("") + `</tr></thead><tbody>` +
    rows.map(r => `<tr><td>${escapeHtml(r.source || "")}</td><td>${r.year || ""}</td><td>${escapeHtml(r.schema || "")}</td>` +
      cols.map(c => cell((r.fields || {})[c])).join("") + `</tr>`).join("") +
    `</tbody></table>`;
}

export async function mountWorkspace(screen, pid, deps) { // deps: {history, mindmaps, onBack}
  let p;
  try {
    p = await getJSON(`/projects/${pid}`);
  } catch (e) {
    screen.innerHTML = `<p style="padding:24px">${escapeHtml(friendlyError(e))}</p>`;
    return;
  }
  let paperIds = (p.papers || []).map(d => d.id);

  screen.innerHTML = `
    <div class="ws">
      <div class="ws-head">
        <button class="ws-back" id="ws-back" type="button">← Naskah Saya</button>
        <div class="ws-title">${escapeHtml(p.name)}</div>
        <div class="ws-tabs">
          <button class="tab active" data-tab="tanya" type="button">💬 Tanya</button>
          <button class="tab" data-tab="paper" type="button">📄 Paper (<span id="ws-count">${paperIds.length}</span>)</button>
          <button class="tab" data-tab="draft" type="button">📝 Draft</button>
          <button class="tab" data-tab="matriks" type="button">📊 Matriks</button>
        </div>
      </div>
      <div class="ws-panel" data-panel="tanya"></div>
      <div class="ws-panel" data-panel="paper" hidden></div>
      <div class="ws-panel" data-panel="draft" hidden></div>
      <div class="ws-panel" data-panel="matriks" hidden></div>
    </div>`;

  screen.querySelector("#ws-back").addEventListener("click", deps.onBack);
  const panels = screen.querySelectorAll(".ws-panel");
  screen.querySelectorAll(".ws-tabs .tab").forEach(t =>
    t.addEventListener("click", () => {
      screen.querySelectorAll(".ws-tabs .tab").forEach(x => x.classList.remove("active"));
      t.classList.add("active");
      panels.forEach(pn => { pn.hidden = pn.dataset.panel !== t.dataset.tab; });
    }));

  // ----- Tanya (default): per-naskah history sidebar + scoped chat -----
  const tanyaPanel = screen.querySelector('[data-panel="tanya"]');
  tanyaPanel.innerHTML = `
    <div class="tanya">
      <aside class="tanya-side">
        <button class="side-btn" id="t-new" type="button">+ Percakapan baru</button>
        <div class="side-label">Riwayat</div>
        <div id="t-recent"></div>
      </aside>
      <div class="tanya-main" id="t-chat"></div>
    </div>`;
  const scope = String(pid);
  const chatEl = tanyaPanel.querySelector("#t-chat");
  const recentEl = tanyaPanel.querySelector("#t-recent");
  let convId = null;

  function renderRecent() {
    const items = deps.history.list(scope);
    recentEl.innerHTML = items.map(c =>
      `<div class="hist${c.id === convId ? " active" : ""}" data-cid="${c.id}">` +
      `<span>${escapeHtml(c.title || "(tanpa judul)")}</span>` +
      `<button class="del" data-del="${c.id}" type="button" title="Hapus">✕</button></div>`).join("")
      || `<div class="gap" style="padding:6px 11px">Belum ada percakapan.</div>`;
    recentEl.querySelectorAll("[data-cid]").forEach(el =>
      el.addEventListener("click", e => {
        if (e.target.matches("[data-del]")) return;
        openConv(el.dataset.cid);
      }));
    recentEl.querySelectorAll("[data-del]").forEach(b =>
      b.addEventListener("click", () => {
        deps.history.remove(b.dataset.del);
        if (convId === b.dataset.del) newConv(); else renderRecent();
      }));
  }
  function persist(messages) {
    if (!messages.length) return;
    deps.history.save({
      id: convId, title: messages[0].q.slice(0, 48), scope,
      messages, updatedAt: Date.now(),
    });
    renderRecent();
  }
  function chatOpts(initial) {
    return {
      examples: [],
      expandToggle: true,
      showNudge: true,
      placeholder: "Tanya tentang paper di naskah ini…",
      emptyText: paperIds.length
        ? "Tanya apa saja tentang paper di naskah ini. Jawaban disertai sumber yang bisa diklik ke halaman PDF."
        : "Tambahkan paper dulu di tab Paper, lalu tanya apa saja di sini.",
      initial,
      endpoint: (q, o) => postJSON(`/projects/${pid}/ask`, { question: q, expand: !!(o && o.expand) }),
      onExchange: persist,
      onAddPaper: async id => { await postJSON(`/projects/${pid}/papers`, { doc_ids: [id] }); papersTab.refresh(); },
    };
  }
  function newConv() {
    convId = "c" + Date.now();
    mountChat(chatEl, chatOpts());
    renderRecent();
  }
  function openConv(id) {
    const c = deps.history.get(id);
    if (!c) return;
    convId = id;
    mountChat(chatEl, chatOpts(c.messages));
    renderRecent();
  }
  tanyaPanel.querySelector("#t-new").addEventListener("click", newConv);

  // ----- Paper -----
  const papersTab = mountPapers(screen.querySelector('[data-panel="paper"]'), pid, {
    mindmaps: deps.mindmaps,
    onChanged: papers => {
      paperIds = papers.map(d => d.id);
      screen.querySelector("#ws-count").textContent = paperIds.length;
    },
  });

  // ----- Draft (scoped to current naskah papers) -----
  mountDraft(screen.querySelector('[data-panel="draft"]'), { getDocIds: () => paperIds });

  // ----- Matriks (ported from old projects.js) -----
  const mx = screen.querySelector('[data-panel="matriks"]');
  mx.innerHTML = `
    <div class="paper-actions">
      <button class="df-btn" id="m-build" type="button">Bangun matriks</button>
      <select id="m-view"><option value="matrix">matriks</option><option value="linimasa">linimasa</option><option value="tema">tema</option></select>
      <a class="df-btn ghost" id="x-xlsx" target="_blank">⬇ Excel</a>
      <a class="df-btn ghost" id="x-csv" target="_blank">⬇ CSV</a>
    </div>
    <div id="m-out" style="padding:12px 20px"></div>`;
  const out = mx.querySelector("#m-out");
  const viewSel = mx.querySelector("#m-view");
  function exportLinks() {
    mx.querySelector("#x-xlsx").href = `/projects/${pid}/matrix/export.xlsx?view=${viewSel.value}`;
    mx.querySelector("#x-csv").href = `/projects/${pid}/matrix/export.csv?view=${viewSel.value}`;
  }
  mx.querySelector("#m-build").addEventListener("click", async () => {
    out.textContent = "Mengekstrak matriks dari paper naskah…";
    try { out.innerHTML = matrixTable(await postJSON(`/projects/${pid}/matrix`, { view: viewSel.value })); }
    catch (e) { out.textContent = friendlyError(e); }
    exportLinks();
  });
  viewSel.addEventListener("change", exportLinks);
  exportLinks();
  // Show the persisted matrix on open (no re-extraction).
  getJSON(`/projects/${pid}/matrix?view=matrix`).then(res => {
    if ((res.rows || []).length) out.innerHTML = matrixTable(res);
  }).catch(() => {});

  newConv();
}
```

- [ ] **Step 7: Delete `projects.js`**

```bash
grep -rn "projects.js" app/web/static/new/ tests/js/   # must return nothing except maybe this plan
git rm app/web/static/new/projects.js
```

- [ ] **Step 8: Run both suites** (JS catches import breakage; Python catches template/server drift)

Run: `node --test tests/js/*.test.mjs && python -m pytest tests/test_new_ui.py -v`
Expected: all pass.

- [ ] **Step 9: Manual smoke** — `scripts/run.sh`, open `http://127.0.0.1:8765`: Beranda renders, create naskah, all four tabs switch, chat history persists per naskah, matrix builds (needs LLM key + Ollama; if offline, verify the friendly error copy shows instead).

- [ ] **Step 10: Commit**

```bash
git add -A app/web/static/new tests/js
git commit -m "feat(ui): ruang kerja naskah — Tanya/Paper/Draft/Matriks tabs

Global chat/draft/mindmap views removed; chat is per-naskah with expand
checkbox, draft scoped via doc_ids, mindmap is a Paper-tab modal."
```

---

### Task 10: Upload UI verification (already wired in Task 9)

The dropzone/progress code landed in `papers.js`. This task verifies it end-to-end against the real backend.

- [ ] **Step 1: Manual verification with a real PDF**

1. `scripts/run.sh` (Ollama must be up).
2. Open a naskah → tab Paper → drag a small PDF in: bar progresses through "membaca halaman…" → "mengindeks…" → "selesai"; paper appears in list.
3. Drag the SAME PDF again: row shows "sudah ada di perpustakaan — ditautkan ke naskah ini"; list count unchanged.
4. Drag a large PDF (≥100 pages if available): bar advances during "mengindeks…" (batch progress visible), UI stays responsive.

- [ ] **Step 2: Run the backend upload suite once more**

Run: `python -m pytest tests/test_uploads.py tests/test_projects.py -v`
Expected: all pass.

- [ ] **Step 3: Commit** (only if manual fixes were needed; otherwise skip)

---

### Task 11: ⚙ Admin LLM panel

**Files:**
- Rewrite: `app/web/static/new/admin.js` (replaces stub)

- [ ] **Step 1: Implement `admin.js`**

```javascript
// ⚙ mini-panel: pick the active generation model (GET/POST /admin/llm).
// Deliberately tucked away — the primary user never needs it.
import { escapeHtml, getJSON, postJSON, friendlyError } from "./api.js";

export function wireAdminGear(btn) {
  if (!btn) return;
  btn.addEventListener("click", async () => {
    const overlay = document.createElement("div");
    overlay.className = "mm-modal";
    overlay.innerHTML = `
      <div class="mm-modal-box">
        <div class="mm-modal-head"><strong>Model penjawab</strong></div>
        <div id="adm-list" class="mm-pick-list">Memuat…</div>
        <div class="mm-modal-foot">
          <span class="grow"></span>
          <button id="adm-cancel" type="button" class="df-btn ghost">Batal</button>
          <button id="adm-save" type="button" class="df-btn">Simpan</button>
        </div>
      </div>`;
    document.body.appendChild(overlay);
    const list = overlay.querySelector("#adm-list");
    const close = () => overlay.remove();
    overlay.addEventListener("click", e => { if (e.target === overlay) close(); });
    overlay.querySelector("#adm-cancel").addEventListener("click", close);
    try {
      const { choices, active } = await getJSON("/admin/llm");
      list.innerHTML = choices.map(c =>
        `<label class="mm-pick-row"><input type="radio" name="llm" value="${escapeHtml(c)}"${c === active ? " checked" : ""}/>` +
        `<span>${escapeHtml(c)}</span></label>`).join("");
    } catch (e) {
      list.textContent = friendlyError(e);
    }
    overlay.querySelector("#adm-save").addEventListener("click", async () => {
      const sel = overlay.querySelector('input[name="llm"]:checked');
      try {
        if (sel) await postJSON("/admin/llm", { choice: sel.value });
        close();
      } catch (e) {
        list.textContent = friendlyError(e);
      }
    });
  });
}
```

- [ ] **Step 2: Manual verification** — ⚙ opens panel, radios reflect `/admin/llm`, save persists (reopen shows new active; `sqlite3 data/library.db "SELECT value FROM meta WHERE key='llm_choice'"` confirms).

- [ ] **Step 3: Commit**

```bash
git add app/web/static/new/admin.js
git commit -m "feat(ui): admin gear panel for runtime LLM switching"
```

---

### Task 12: Final pass — copy, docs, full suites, E2E

**Files:**
- Modify: `CLAUDE.md` (Web section)
- Possibly touch: any straggling EN strings in `static/new/*`

- [ ] **Step 1: Copy sweep** — `grep -n` through `static/new/*.js` and `new.html` for leftover English/jargon user-facing strings (`project`, `expand`, `corpus`, `papers` as labels). All visible labels Indonesian; code identifiers stay English.

- [ ] **Step 2: Update `CLAUDE.md`** — replace the "Two front-ends" bullet for `/` (grid UI) with:

```markdown
- **Grid-style** `/` (`templates/new.html` + `static/new/*`) — naskah-centric two-screen UI: Beranda (naskah card list) → Ruang Kerja with inner tabs Tanya (scoped chat + expand checkbox + per-naskah localStorage history), Paper (async upload with progress polling via `/uploads/{job_id}`, import picker, peta-konsep modal), Draft (doc_ids-scoped), Matriks (+ export). Modules: `api.js`/`history.js`/`upload.js`/`citations.js`/`mindmaps.js`/`splash.js` are pure & unit-tested; `main/beranda/workspace/papers/picker/mindmap/chat/draft/admin` are DOM views verified manually. ⚙ gear = runtime LLM switcher (`/admin/llm`, persisted in `meta.llm_choice`).
- **Legacy** `/tools` (`templates/index.html` + `static/app.js`) — all five tabs + admin reembed panel. Unchanged; reachable by direct URL only (no nav link).
```

- [ ] **Step 3: Full suites**

Run: `python -m pytest tests/ -v`
Expected: all pass.
Run: `node --test tests/js/*.test.mjs`
Expected: all pass.

- [ ] **Step 4: Manual end-to-end as the primary user**

1. Fresh browser profile (splash shows) → Enter.
2. Beranda → "+ Naskah baru" → buka.
3. Tab Paper → upload PDF → progress → selesai.
4. Tab Tanya → tanya → jawaban + sumber klik-ke-halaman; centang "cari juga di luar naskah ini" → tanya lagi → nudge muncul → "+" menambah paper.
5. Tab Draft → topik → paragraf + referensi.
6. Tab Matriks → bangun → ekspor Excel.
7. ← Naskah Saya → riwayat percakapan tetap ada saat naskah dibuka lagi.
8. `/tools` masih utuh.

- [ ] **Step 5: Commit**

```bash
git add CLAUDE.md app/web/static/new
git commit -m "docs: CLAUDE.md reflects naskah-centric UI; final copy pass"
```

---

## Self-Review Notes (already applied)

- Spec coverage: Beranda/workspace (T8/T9), upload async + progress (T3/T7/T9/T10), draft scoping (T1/T9), mindmap-as-modal (T9), LLM switcher (T4/T11), Indonesian copy + friendly errors (T6/T9/T12), suggestion cards removed (chat.js rewrite drops HOME_CARDS), `/tools` untouched (T8 test), history per naskah no-migration (T5; old `scope:"global"` rows simply unlisted).
- Type consistency: `progress(stage, done, total)` used identically in pipeline/uploads/tests; job dict keys (`stage,done,total,error,doc_id,already,finished`) match `pollJob` consumers; `list(scope)` matches workspace `deps.history.list(scope)`; `endpoint(q, {expand})` matches chat.js and workspace.
- Known judgment calls: `papers.js` uses raw `fetch` for DELETE (api.js has no deleteJSON; acceptable, same file already uses fetch via upload.js helpers). `posttFile`-style typos checked. Beranda shows description, not paper count (`/projects` list payload has no count — don't invent one).
