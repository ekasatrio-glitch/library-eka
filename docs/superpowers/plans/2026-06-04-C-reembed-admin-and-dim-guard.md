# Sub-project C — Reembed Admin + Dim-Mismatch Guard Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Run the corpus reembed from the web as a background job with live progress (panel in `/tools`), and replace the raw sqlite-vec dimension error on query with a clear, actionable 409 message.

**Architecture:** `reembed()` gains an optional progress callback (CLI unchanged). A new `admin_routes.py` runs a single background reembed job (thread + lock + in-memory state) exposed via `POST /admin/reembed/start` and `GET /admin/reembed/status`; a panel in the legacy `/tools` UI starts it and polls. A new `index_health.py` compares the vec table's declared dimension to `config.EMBED_DIM`; `/ask` and `/projects/{id}/ask` call it first and return 409 with guidance on mismatch.

**Tech Stack:** FastAPI, Python `threading`, sqlite-vec, pytest + TestClient, vanilla JS (legacy `app.js`).

**Spec:** `docs/superpowers/specs/2026-06-04-grid-ui-expansion-design.md` (Sub-project C). Independent of A/B.

## Verified facts

- `reembed.reembed(model, dim, batch=32, db_path=None, base_url=None, force=False) -> int` rebuilds `vec_chunks`; prints `done/total` to stderr; sets `meta.embed_model`/`embed_dim`. It opens its own connection via `init_db(db_path)`.
- `app/core/db.py`: `connect(path=None)` and `init_db(path=None)` read the module-level `DB_PATH` when `path is None` (so tests monkeypatch `app.core.db.DB_PATH`). `get_meta(conn, key)`, `set_meta(conn, key, value)` exist.
- Vec table DDL: `CREATE VIRTUAL TABLE vec_chunks USING vec0(chunk_id INTEGER PRIMARY KEY, embedding FLOAT[<dim>])` — readable from `sqlite_master`.
- `app/web/routes.py` `POST /ask` imports `ask` lazily, builds filters via `_filters(req)`, catches `RuntimeError → 503`. `app/web/projects_routes.py` `scoped_ask` already holds `conn = connect()`.
- `app/web/static/app.js` has `postJSON(url, body)` and `getJSON(url)` helpers and `escapeHtml`.
- `app/web/app.py` `create_app()` does `include_router(router)`, `include_router(projects_router)`, `include_router(rename_router)`.

## Files

```
app/ingest/reembed.py            # MODIFY: add progress callback param
app/web/admin_routes.py          # CREATE: /admin/reembed/start + /status (background job)
app/web/app.py                   # MODIFY: include_router(admin_router)
app/web/templates/index.html     # MODIFY: reembed panel in /tools (library tab)
app/web/static/app.js            # MODIFY: wire panel (start + poll)
app/rag/index_health.py          # CREATE: vec_dim(), check_query_dim()
app/web/routes.py                # MODIFY: /ask dim guard (409)
app/web/projects_routes.py       # MODIFY: /projects/{id}/ask dim guard (409)
tests/test_admin_reembed.py      # CREATE
tests/test_index_health.py       # CREATE
tests/test_dim_guard.py          # CREATE
```

---

### Task 1: `reembed()` progress callback

**Files:**
- Modify: `app/ingest/reembed.py`
- Create: `tests/test_admin_reembed.py` (progress part)

- [ ] **Step 1: Write the failing test** — create `tests/test_admin_reembed.py`:

```python
import tempfile
from pathlib import Path
from unittest.mock import patch

import fitz

from app.core import config
from app.core.db import init_db
from app.ingest.pipeline import ingest_pdf
from app.ingest import reembed as reembed_mod


def _embed_stub(texts, model=None, base_url=None):
    return [[0.01] * config.EMBED_DIM for _ in texts]


def _seed(db: str):
    with tempfile.TemporaryDirectory() as td:
        pdf = Path(td) / "a.pdf"
        doc = fitz.open()
        for i in range(3):
            page = doc.new_page()
            page.insert_textbox(page.rect, ("Quantum entanglement Bell test " * 80), fontsize=9)
        doc.save(str(pdf))
        doc.close()
        conn = init_db(db)
        with patch("app.ingest.pipeline.embed_texts", side_effect=_embed_stub):
            ingest_pdf(pdf, conn=conn)
        n = conn.execute("SELECT COUNT(*) FROM chunks").fetchone()[0]
        conn.close()
        return n


def test_reembed_reports_progress():
    with tempfile.TemporaryDirectory() as td:
        db = str(Path(td) / "t.db")
        n_chunks = _seed(db)
        assert n_chunks >= 1
        calls = []
        with patch("app.ingest.reembed.embed_texts", side_effect=_embed_stub):
            rc = reembed_mod.reembed(
                config.EMBED_MODEL, config.EMBED_DIM, batch=1,
                db_path=db, force=True, progress=lambda done, total: calls.append((done, total)),
            )
        assert rc == 0
        assert calls, "progress was never called"
        assert calls[-1] == (n_chunks, n_chunks)          # finishes at total
        assert [d for d, _ in calls] == sorted(d for d, _ in calls)  # monotonic
```

- [ ] **Step 2: Run to verify it fails**

Run: `venv/bin/python -m pytest tests/test_admin_reembed.py::test_reembed_reports_progress -v`
Expected: FAIL — `reembed()` has no `progress` kwarg (TypeError).

- [ ] **Step 3: Add the param** — in `app/ingest/reembed.py`, change the signature:

```python
def reembed(
    model: str,
    dim: int,
    batch: int = 32,
    db_path: Optional[str] = None,
    base_url: Optional[str] = None,
    force: bool = False,
) -> int:
```

to add `progress`:

```python
def reembed(
    model: str,
    dim: int,
    batch: int = 32,
    db_path: Optional[str] = None,
    base_url: Optional[str] = None,
    force: bool = False,
    progress=None,
) -> int:
```

(Add `from typing import Callable, Optional` — the file already imports `Optional`; extend it to `from typing import Callable, Optional` for clarity, though `progress=None` needs no annotation.)

Then in the batch loop, after the existing `print(f"[reembed] {done}/{total}", file=sys.stderr)` line, add:

```python
            if progress:
                progress(done, total)
```

- [ ] **Step 4: Run to verify it passes**

Run: `venv/bin/python -m pytest tests/test_admin_reembed.py::test_reembed_reports_progress -v`
Expected: PASS.

- [ ] **Step 5: Confirm the CLI path is unaffected**

Run: `venv/bin/python -m pytest tests/test_retrieval.py -q`
Expected: PASS (the `dim=8` reembed test still passes — `progress` defaults to None).

- [ ] **Step 6: Commit**

```bash
git add app/ingest/reembed.py tests/test_admin_reembed.py
git commit -m "feat(reembed): optional progress callback"
```

---

### Task 2: `admin_routes.py` — background reembed job

**Files:**
- Create: `app/web/admin_routes.py`
- Modify: `app/web/app.py`
- Modify: `tests/test_admin_reembed.py` (endpoint + concurrency)

- [ ] **Step 1: Write the failing tests** — append to `tests/test_admin_reembed.py`:

```python
import time

from fastapi.testclient import TestClient

from app.web.app import create_app
from app.web import admin_routes


def _reset_job():
    admin_routes._job.update(
        running=False, done=0, total=0, model=None, dim=None, error=None, finished_at=None
    )


def test_reembed_endpoint_runs_to_completion(monkeypatch):
    with tempfile.TemporaryDirectory() as td:
        db = str(Path(td) / "t.db")
        n_chunks = _seed(db)
        monkeypatch.setattr("app.core.db.DB_PATH", db)
        _reset_job()
        client = TestClient(create_app())
        with patch("app.ingest.reembed.embed_texts", side_effect=_embed_stub):
            r = client.post("/admin/reembed/start", json={"force": True})
            assert r.status_code == 200
            assert r.json()["total"] == n_chunks
            # poll until done (bounded)
            for _ in range(100):
                st = client.get("/admin/reembed/status").json()
                if not st["running"]:
                    break
                time.sleep(0.05)
            else:
                raise AssertionError("reembed did not finish in time")
        assert st["error"] is None
        assert st["done"] == n_chunks and st["total"] == n_chunks
        _reset_job()


def test_reembed_rejects_concurrent_start():
    _reset_job()
    admin_routes._job["running"] = True
    client = TestClient(create_app())
    r = client.post("/admin/reembed/start", json={})
    assert r.status_code == 409
    _reset_job()
```

- [ ] **Step 2: Run to verify it fails**

Run: `venv/bin/python -m pytest tests/test_admin_reembed.py -v`
Expected: FAIL — `app.web.admin_routes` does not exist / 404 on `/admin/reembed/start`.

- [ ] **Step 3: Create** `app/web/admin_routes.py`:

```python
"""Admin endpoints: background corpus reembed with progress polling (single job)."""

import threading
import time
from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from app.core import config
from app.core.db import connect
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
```

- [ ] **Step 4: Wire it in** — in `app/web/app.py`, add the import near the other router imports:

```python
from app.web.admin_routes import router as admin_router
```

and inside `create_app()`, after `app.include_router(rename_router)`:

```python
    app.include_router(admin_router)
```

- [ ] **Step 5: Run to verify it passes**

Run: `venv/bin/python -m pytest tests/test_admin_reembed.py -v`
Expected: all pass (progress + endpoint + concurrency).

- [ ] **Step 6: Commit**

```bash
git add app/web/admin_routes.py app/web/app.py tests/test_admin_reembed.py
git commit -m "feat(admin): background reembed job with progress + status endpoints"
```

---

### Task 3: Reembed panel in `/tools`

**Files:**
- Modify: `app/web/templates/index.html`
- Modify: `app/web/static/app.js`

Add a small panel to the library tab (admin-ish controls already live there: retitle, rename). It shows the current vs target model/dim, a Run button, and a progress line that polls.

- [ ] **Step 1: Add the panel markup** — in `app/web/templates/index.html`, inside `<section id="tab-library" ...>`, after the closing `</div>` of the last `.rename-box` (the rename PDF block) and before the section's closing `</section>`, insert:

```html
    <div class="rename-box">
      <h4>Reembed indeks vektor (ganti model embedding)</h4>
      <div class="row">
        <button id="reembed-btn" type="button">Jalankan reembed</button>
        <span id="reembed-status" class="muted"></span>
      </div>
      <div id="reembed-progress" class="muted"></div>
    </div>
```

- [ ] **Step 2: Wire it** — append to `app/web/static/app.js`:

```javascript
// ---------- Reembed admin (Phase C) ----------
const reembedBtn = document.getElementById("reembed-btn");
if (reembedBtn) {
  const statusEl = document.getElementById("reembed-status");
  const progEl = document.getElementById("reembed-progress");
  let polling = null;

  async function pollReembed() {
    try {
      const st = await getJSON("/admin/reembed/status");
      const pct = st.total ? Math.round((st.done / st.total) * 100) : 0;
      progEl.textContent = `${st.done}/${st.total} (${pct}%)` + (st.model ? ` → ${st.model} ${st.dim}-d` : "");
      if (!st.running) {
        clearInterval(polling); polling = null;
        reembedBtn.disabled = false;
        statusEl.textContent = st.error ? ("Gagal: " + st.error) : "Selesai.";
      }
    } catch (err) {
      clearInterval(polling); polling = null;
      reembedBtn.disabled = false;
      statusEl.textContent = "Error: " + err.message;
    }
  }

  reembedBtn.addEventListener("click", async () => {
    if (!confirm("Reembed seluruh korpus dengan model embedding aktif? Bisa lama.")) return;
    reembedBtn.disabled = true;
    statusEl.textContent = "Memulai...";
    progEl.textContent = "";
    try {
      const res = await postJSON("/admin/reembed/start", { force: true });
      statusEl.textContent = `Berjalan (${res.total} chunk)...`;
      polling = setInterval(pollReembed, 1000);
    } catch (err) {
      reembedBtn.disabled = false;
      statusEl.textContent = "Error: " + err.message;
    }
  });
}
```

- [ ] **Step 3: Confirm legacy UI tests still pass** (markup added, none of the asserted ids removed)

Run: `venv/bin/python -m pytest tests/test_web_ui.py -q`
Expected: PASS. (Note: if Sub-project B already ran, `test_web_ui` fetches `/tools`; if not, it fetches `/` — either way the library tab markup is present.)

- [ ] **Step 4: Commit**

```bash
git add app/web/templates/index.html app/web/static/app.js
git commit -m "feat(admin): reembed panel with progress polling in legacy UI"
```

---

### Task 4: `index_health.py` + dim-mismatch guard

**Files:**
- Create: `app/rag/index_health.py`
- Create: `tests/test_index_health.py`
- Modify: `app/web/routes.py`
- Modify: `app/web/projects_routes.py`
- Create: `tests/test_dim_guard.py`

- [ ] **Step 1: Write the failing health test** — create `tests/test_index_health.py`:

```python
import tempfile
from pathlib import Path

from app.core import config
from app.core.db import init_db
from app.rag.index_health import vec_dim, check_query_dim


def test_vec_dim_reads_declared_dimension():
    with tempfile.TemporaryDirectory() as td:
        conn = init_db(str(Path(td) / "t.db"))
        assert vec_dim(conn) == config.EMBED_DIM
        conn.close()


def test_check_query_dim_ok_when_matching():
    with tempfile.TemporaryDirectory() as td:
        conn = init_db(str(Path(td) / "t.db"))
        assert check_query_dim(conn) is None
        conn.close()


def test_check_query_dim_message_on_mismatch():
    with tempfile.TemporaryDirectory() as td:
        conn = init_db(str(Path(td) / "t.db"))
        # Force the vec table to a different dimension than config.EMBED_DIM.
        conn.execute("DROP TABLE vec_chunks")
        conn.execute(
            "CREATE VIRTUAL TABLE vec_chunks USING vec0(chunk_id INTEGER PRIMARY KEY, embedding FLOAT[8])"
        )
        conn.commit()
        assert vec_dim(conn) == 8
        msg = check_query_dim(conn)
        assert msg is not None
        assert "8" in msg and str(config.EMBED_DIM) in msg
        conn.close()
```

- [ ] **Step 2: Run to verify it fails**

Run: `venv/bin/python -m pytest tests/test_index_health.py -v`
Expected: FAIL — module missing.

- [ ] **Step 3: Create** `app/rag/index_health.py`:

```python
"""Vector-index health: detect when the index dimension no longer matches the
configured embedding model (e.g. after switching nomic 768 -> bge-m3 1024 but
before reembedding)."""

import re
import sqlite3
from typing import Optional

from app.core import config


def vec_dim(conn: sqlite3.Connection) -> Optional[int]:
    """Declared dimension of the vec_chunks table, or None if absent/unparseable."""
    row = conn.execute(
        "SELECT sql FROM sqlite_master WHERE name = 'vec_chunks'"
    ).fetchone()
    if not row or not row[0]:
        return None
    m = re.search(r"FLOAT\[(\d+)\]", row[0])
    return int(m.group(1)) if m else None


def check_query_dim(conn: sqlite3.Connection) -> Optional[str]:
    """Return a human message if the index dim != config.EMBED_DIM, else None."""
    d = vec_dim(conn)
    if d is not None and d != config.EMBED_DIM:
        return (
            f"Indeks vektor {d}-d tapi model embedding {config.EMBED_DIM}-d "
            f"({config.EMBED_MODEL}). Jalankan reembed dulu (panel di /tools) "
            f"atau samakan EMBED_DIM."
        )
    return None
```

- [ ] **Step 4: Run to verify it passes**

Run: `venv/bin/python -m pytest tests/test_index_health.py -v`
Expected: 3 pass.

- [ ] **Step 5: Add the guard to `/ask`** — in `app/web/routes.py`, replace the `post_ask` function:

```python
@router.post("/ask")
def post_ask(req: AskRequest) -> JSONResponse:
    from app.rag.ask import ask  # lazy import: requires LLM key
    try:
        result = ask(req.question, top_k=req.top_k, filters=_filters(req))
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))
    return JSONResponse(result)
```

with:

```python
@router.post("/ask")
def post_ask(req: AskRequest) -> JSONResponse:
    from app.rag.ask import ask  # lazy import: requires LLM key
    from app.rag.index_health import check_query_dim

    conn = connect()
    try:
        mismatch = check_query_dim(conn)
    finally:
        conn.close()
    if mismatch:
        raise HTTPException(status_code=409, detail=mismatch)

    try:
        result = ask(req.question, top_k=req.top_k, filters=_filters(req))
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))
    return JSONResponse(result)
```

(`connect` is already imported in `routes.py` via `from app.core.db import connect`.)

- [ ] **Step 6: Add the guard to `/projects/{id}/ask`** — in `app/web/projects_routes.py` `scoped_ask`, it already opens `conn = connect()`. Right after the existing `if not proj.get_project(conn, project_id): raise HTTPException(404, ...)` line, add:

```python
        from app.rag.index_health import check_query_dim
        mismatch = check_query_dim(conn)
        if mismatch:
            raise HTTPException(409, mismatch)
```

(Place it before `doc_ids = proj.project_doc_ids(...)`. The function's `finally: conn.close()` already closes the connection.)

- [ ] **Step 7: Write the guard endpoint test** — create `tests/test_dim_guard.py`:

```python
import tempfile
from pathlib import Path

from fastapi.testclient import TestClient

from app.core.db import init_db
from app.web.app import create_app


def _mismatched_db(path: str):
    conn = init_db(path)
    conn.execute("DROP TABLE vec_chunks")
    conn.execute(
        "CREATE VIRTUAL TABLE vec_chunks USING vec0(chunk_id INTEGER PRIMARY KEY, embedding FLOAT[8])"
    )
    conn.commit()
    conn.close()


def test_ask_returns_409_on_dim_mismatch(monkeypatch):
    with tempfile.TemporaryDirectory() as td:
        db = str(Path(td) / "t.db")
        _mismatched_db(db)
        monkeypatch.setattr("app.core.db.DB_PATH", db)
        client = TestClient(create_app())
        r = client.post("/ask", json={"question": "apa itu sedasi?"})
        assert r.status_code == 409
        assert "reembed" in r.json()["detail"].lower()
```

(The guard fires before `ask()` runs, so no LLM key or embedding is needed.)

- [ ] **Step 8: Run to verify it passes**

Run: `venv/bin/python -m pytest tests/test_dim_guard.py tests/test_index_health.py -v`
Expected: all pass.

- [ ] **Step 9: Commit**

```bash
git add app/rag/index_health.py app/web/routes.py app/web/projects_routes.py tests/test_index_health.py tests/test_dim_guard.py
git commit -m "feat(rag): 409 dim-mismatch guard on /ask and /projects ask"
```

---

### Task 5: Full verification

- [ ] **Step 1: Full automated suite**

Run: `node --test tests/js/*.test.mjs && venv/bin/python -m pytest tests/ -q`
Expected: all JS tests pass; all pytest pass.

- [ ] **Step 2: Manual verification** (`scripts/run.sh`, browser; needs Ollama):
  1. With the existing 768-d DB while config is bge-m3/1024: `/tools` library tab shows the "Reembed indeks vektor" panel. Asking a question (Grid `/` or legacy `/tools`) returns the friendly 409 message ("Indeks vektor 768-d tapi model embedding 1024-d…"), not a raw sqlite error.
  2. Click "Jalankan reembed" → confirm → progress line advances `done/total (%)` and ends "Selesai."
  3. After reembed completes, asking a question works normally (no 409).

- [ ] **Step 3: (verification only — no commit)**

---

## Self-review notes

- **Spec coverage (C):** background job + progress poll (T1 callback, T2 endpoints, T3 panel); panel in `/tools` (T3, library tab); guard on `/ask` + `/projects/{id}/ask` returning a clear 409 (T4). C1 = T1–T3, C2 = T4.
- **Concurrency:** single job guarded by `_lock` + `_job["running"]`; second start → 409 (tested). Worker thread opens its own DB connection inside `reembed()` (sqlite connections aren't shared across threads).
- **Testability:** progress tested on `reembed()` directly; endpoint tested by monkeypatching `app.core.db.DB_PATH` to a seeded temp DB + patching `app.ingest.reembed.embed_texts`; concurrency tested by setting `_job["running"]` directly; guard tested with a forced 8-d vec table (no LLM/embed needed because the guard precedes `ask()`).
- **No placeholders:** every step has exact code/commands. `connect` import already present in `routes.py`; `app.py` import + include added explicitly.
- **Type consistency:** `reembed(..., progress=None)`; `_progress(done, total)` matches the `progress(done, total)` call site in the batch loop; `vec_dim`/`check_query_dim` signatures used identically in tests, routes, and projects_routes.
```
