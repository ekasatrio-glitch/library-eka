# Grid UI Expansion + Cutover + Reembed Admin — Design

**Date:** 2026-06-04
**Status:** Approved (brainstorming complete)

## Overview

Three independent sub-projects extending the Grid-style `/new` UI and the embedding workflow. Each is separately testable and gets its own implementation plan.

**Execution order: A → B → C.** A must precede B so that when `/new` becomes the home (`/`), it already carries Draft + Mindmap. C is independent of A/B.

| Sub-project | Summary |
|---|---|
| **A — Draft + Mindmap in `/new`** | Add Draft and Mindmap as views in the Grid UI (nav grows to Chat · Projects · Draft · Mindmap). Library stays legacy. |
| **B — Cutover `/new` → `/`** | Grid UI becomes `/`; legacy 5-tab UI moves to `/tools`; `/new` redirects to `/`. |
| **C — Reembed admin + dim guard** | Run the corpus reembed from the web as a background job with progress (panel in `/tools`); friendly dim-mismatch message on `/ask` instead of a raw sqlite-vec error. |

## Locked decisions (from brainstorming)

- Cutover: Grid → `/`, legacy → `/tools`, `/new` → redirect to `/` (old bookmarks keep working).
- Reembed: background job + progress polling (not blocking, not CLI-only).
- Reembed panel lives in `/tools`; dim-mismatch guard added to `/ask` + `/projects/{id}/ask`.
- `/new` scope: add Draft + Mindmap only; Library stays in `/tools`.

## Shared facts (verified against current code)

- `POST /draft` `{topic, style, top_k, year_min?, year_max?}` → `{paragraph, citations:[{n,doc_id,title,page_start,page_end,cited,...}], references:[str], style}`. Vancouver references carry the `cited` flag; APA stays all-cited.
- `POST /mindmap` `{topic, breadth, top_k}` → `{markdown, citations, subtopics}`. Rendered with **markmap-autoloader** (`https://cdn.jsdelivr.net/npm/markmap-autoloader@0.16`): a `<div class="markmap"><script type="text/template">…markdown…</script></div>` then `window.markmap.autoLoader.renderAll()`.
- `reembed.reembed(model, dim, batch=32, db_path=None, base_url=None, force=False) -> int` rebuilds `vec_chunks` only; prints `done/total` to stderr; records `embed_model`/`embed_dim` in `meta`.
- Vec table declared dim is readable from `sqlite_master` (`CREATE VIRTUAL TABLE vec_chunks USING vec0(... FLOAT[<dim>])`). `config.EMBED_DIM` is the model's expected dim.
- New UI modules are native ES modules under `static/new/`; pure ones unit-tested with `node:test`, DOM ones verified manually (established pattern).

---

## Sub-project A — Draft + Mindmap in `/new`

**Goal:** Draft (Vancouver/APA paragraph with citations) and Mindmap (MarkMap) become first-class views in the Grid UI, reusing existing backend endpoints. No backend change.

**Files:**
- Modify: `app/web/templates/new.html` — add `nav-draft` + `nav-mindmap` buttons; add `view-draft` + `view-mindmap` sections; add the markmap-autoloader `<script>` before `main.js`.
- Create: `app/web/static/new/draft.js` — `mountDraft(viewEl)`: topic textarea + style select (vancouver/apa) + submit → `postJSON("/draft", …)`; render the paragraph (with `[n]`/`(n)` cite-pills via `citations.js`) + a references list split into cited vs "Diambil, tidak dikutip" (reuse the `cited` flag).
- Create: `app/web/static/new/mindmap.js` — `mountMindmap(viewEl)`: topic textarea + breadth + submit → `postJSON("/mindmap", …)`; render markdown into a markmap container and call `window.markmap.autoLoader.renderAll()`.
- Modify: `app/web/static/new/main.js` — register `draft`/`mindmap` views in the nav switcher; mount the two modules; update the sidebar footer (Draft/Mindmap are now internal nav, so the footer keeps only `Library ↗` → `/tools#tab-library`).
- Modify: `app/web/static/new/new.css` — minimal styles for the draft/mindmap forms + markmap container sizing (reuse existing tokens; mirror the legacy `#mindmap-svg` 75vh sizing).

**Nav model:** sidebar nav becomes Chat · Projects · Draft · Mindmap (each toggles its view + the relevant sidebar body section; Draft/Mindmap have no sidebar body beyond the nav). The Chat↔Projects sidebar-body switching already exists; Draft/Mindmap reuse the Chat sidebar body (Recent stays visible) or show an empty side body — keep it simple: Draft/Mindmap show the Chat sidebar body (Recent) so the sidebar never goes blank.

**Citations in Draft:** reuse `citations.js` `renderAnswerHtml`/`sourcesBlock`. The paragraph uses `(n)` for Vancouver — `pillsForAnswer(paragraph, citations, style)` must handle the paren style too. Extend `pillsForAnswer` to accept an optional marker style (`"square"` default, `"paren"` for Vancouver) so the same renderer serves chat and draft. This is the one citations.js change; covered by a new node:test.

**Tests:**
- `tests/js/citations.test.mjs` — add cases for `pillsForAnswer(text, cits, "paren")` turning `(2)` into a pill, leaving out-of-range `(2020)` as text.
- `tests/test_new_ui.py` — assert `nav-draft`, `nav-mindmap`, `view-draft`, `view-mindmap`, and the markmap-autoloader script are present in `/new`.
- `node --check` draft.js + mindmap.js; manual verify: draft renders pills + cited/uncited; mindmap renders a MarkMap.

**Out of scope:** Library in `/new` (stays legacy); any backend change.

---

## Sub-project B — Cutover `/new` → `/`

**Goal:** Make the Grid UI the default at `/`, move the legacy 5-tab UI to `/tools`, and redirect `/new` → `/` so existing links survive.

**Files:**
- Modify: `app/web/routes.py`
  - `GET /` → render `new.html` (was `index.html`).
  - `GET /tools` → render `index.html` (the legacy UI).
  - `GET /new` → `RedirectResponse("/")` (302).
- Modify: `app/web/templates/new.html` — sidebar footer `Library ↗` → `/tools#tab-library` (after A, Draft/Mindmap are internal).
- Modify: `tests/test_web_ui.py` — its `_html()` fetches `/`; point it at `/tools` (the legacy markup now lives there).
- Modify: `tests/test_new_ui.py` — `/` now serves the Grid shell, so the shell assertions can target `/` (or keep `/new` since it redirects — follow redirects). `test_old_index_untouched` becomes "legacy served at /tools" (assert `GET /tools` 200 + a legacy id like `tab-mindmap`). Add a test that `GET /new` redirects to `/`.

**Routing contract after cutover:**
- `/` → Grid UI (Chat/Projects/Draft/Mindmap)
- `/tools` → legacy UI (all five tabs incl. Library, rename, etc.)
- `/new` → 302 → `/`
- `/viewer`, `/pdf/{id}`, all API routes — unchanged.

**Tests:** route assertions above; full pytest green.

**Out of scope:** deleting the legacy UI; moving Library/rename out of legacy.

---

## Sub-project C — Reembed admin + dim-mismatch guard

**Goal:** Trigger a corpus reembed from the web as a background job with live progress, and replace the raw sqlite-vec dimension error on query with a clear, actionable message.

### C1 — Background reembed job

**Files:**
- Modify: `app/ingest/reembed.py` — add an optional `progress: Callable[[int, int], None] | None = None` param to `reembed()`, called as `progress(done, total)` after each batch (alongside the existing stderr print). No behavior change when `progress` is None; CLI untouched.
- Create: `app/web/admin_routes.py` — a new `APIRouter` with:
  - `POST /admin/reembed/start` `{model?, dim?, force?}` (defaults from `config.EMBED_MODEL`/`config.EMBED_DIM`) → starts the job in a background thread if none is running; returns `{started: true, total}` or `409 {error: "already running"}`.
  - `GET /admin/reembed/status` → `{running, done, total, model, dim, error, finished_at?}`.
  - Job state is a single module-level object guarded by a lock (one job at a time; this is a single-user local app). The worker thread opens its own DB connection (sqlite connections are not shareable across threads).
- Modify: `app/web/app.py` — `include_router(admin_router)`.
- Modify: `app/web/templates/index.html` (legacy `/tools`) — add a small "Reembed index" panel: current `meta.embed_model`/`embed_dim` vs `config` target, a "Run reembed" button, and a progress bar that polls `/admin/reembed/status`.
- Modify: `app/web/static/app.js` — wire the panel (start + poll until `running` is false; show done/total + final state).

**Concurrency contract:** at most one reembed job process-wide. Starting while running → 409. Status is readable any time. The job re-embeds via Ollama with the configured model; the user must have it pulled (existing requirement).

**Tests:**
- `tests/test_admin_reembed.py` — `reembed(progress=cb)` calls `cb(done, total)` with monotonic progress (use the existing `_embed_stub` pattern + a tiny seeded DB); start endpoint returns `total` and flips status `running`→done; a second concurrent start returns 409. Patch the embedder so the job is fast and offline.

### C2 — Dim-mismatch guard

**Files:**
- Create: `app/rag/index_health.py` — `vec_dim(conn) -> int | None` (parse `FLOAT[<n>]` from `sqlite_master`), and `check_query_dim(conn) -> str | None` returning a human message when `vec_dim != config.EMBED_DIM`, else `None`.
- Modify: `app/rag/retriever.py` OR the route layer — before searching, if `check_query_dim` returns a message, raise a typed error. Cleanest: raise `RuntimeError(message)` from `search()`'s entry when dims mismatch, so the existing `except RuntimeError → 503` in routes surfaces it. **Decision:** add an explicit guard in `routes.py:/ask` and `projects_routes.py:/ask` that calls `check_query_dim` and returns `409 {detail: <message>}` before calling `ask()` — clearer status than 503 and no retriever coupling.
- Message example: `"Indeks vektor 768-d tapi model embedding 1024-d (bge-m3). Jalankan reembed dulu (panel di /tools) atau samakan EMBED_DIM."`

**Tests:**
- `tests/test_index_health.py` — `vec_dim` reads the declared dim; `check_query_dim` returns `None` when matching, a message when not.
- `tests/test_web.py` (or new) — seed a DB whose vec table is 8-d while `config.EMBED_DIM` is monkeypatched to a different value; `POST /ask` returns 409 with the guidance message (no raw sqlite error).

**Out of scope:** auto-running reembed on mismatch (explicit user action only); VPS-side reembed.

---

## Cross-cutting

- **Testing reality:** Python via pytest (route + job + health); pure JS via `node:test` (citations paren style); DOM JS + CSS verified manually. Run JS tests with the glob form `node --test tests/js/*.test.mjs` (Node 24).
- **No new persistent state** beyond the in-memory reembed job object; `meta.embed_model`/`embed_dim` already exist.
- **Legacy untouched except additions:** sub-project C adds a panel to `index.html`/`app.js`; B re-points routes; neither rewrites legacy behavior.
- **Decomposition:** three separate implementation plans (A, B, C), executed A → B → C. C may be split into C1 (job) and C2 (guard) tasks within its plan.
