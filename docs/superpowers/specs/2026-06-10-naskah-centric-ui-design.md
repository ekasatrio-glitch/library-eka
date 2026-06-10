# Naskah-Centric UI — Design Spec

**Date:** 2026-06-10
**Status:** Approved (brainstormed with Eka)

## Problem

The app feels confusing to its primary user (Eka's wife, a non-technical academic). Pain points, confirmed in brainstorming:

1. Too many menus/tabs (Chat, Projects, Draft, Mindmap, plus Library and legacy Tools links).
2. Chat vs Projects redundancy — you can ask questions in two places with unclear difference.
3. Technical jargon in the UI (expand, nudge, project, reembed).
4. No clear workflow: where to start, what order to do things in.

Her actual usage: corpus Q&A, academic drafting, synthesis matrix, browsing/reading PDFs — **almost always within the context of one manuscript**. Mindmap was not in her use cases.

## Decision

**Option A — everything-in-a-project ("Semua-dalam-Naskah").** The project (renamed "naskah" in the UI) becomes the only working context. Global chat, global draft, and the standalone mindmap tab are removed from navigation. Power features stay reachable for Eka at `/tools` (legacy UI, direct URL only).

Target user split: wife is primary (UI optimized for her); Eka is secondary (CLI + `/tools`).

## Information Architecture

Two screens only.

### Screen 1 — Beranda (`/`)

- Card list of naskah (name, paper count, last-modified), one click opens the workspace.
- Prominent "+ Naskah baru" button.
- Small "Semua PDF" link (top corner) → the library browser (list, filters, click-to-page PDF viewer). Library stays global; it is a reference shelf, not a working context.
- First-visit splash (EKG) unchanged.

### Screen 2 — Ruang Kerja (`/p/{id}` view inside the SPA)

Header: `← Naskah Saya | <nama naskah>`. Four inner tabs:

| Tab | Content | Backend |
|---|---|---|
| 💬 **Tanya** (default) | Scoped chat over the naskah's papers. Checkbox "cari juga di luar naskah ini" (= existing `expand`). Discovery nudge shown as "paper lain yang mungkin relevan". Per-naskah conversation history in localStorage. | `POST /projects/{id}/ask` (exists) |
| 📄 **Paper** | Paper list; drag-drop PDF upload with per-file progress bar (stage labels: "membaca halaman" → "mengindeks" → "selesai"); import from library; per-selection "🗺️ Peta konsep" button that renders a mindmap in a modal/panel. | `GET/POST /projects/{id}/papers` (exist); `POST /projects/{id}/upload` reworked async + `GET /uploads/{job_id}` polling; `POST /mindmap` with `doc_ids` (exists) |
| 📝 **Draft** | Vancouver/APA paragraph drafting scoped to the naskah's papers. | `POST /draft` + **new `doc_ids` param** |
| 📊 **Matriks** | Synthesis matrix + XLSX/CSV export, unchanged behavior. | `POST /projects/{id}/matrix`, export routes (exist) |

### Removed from navigation (not from the system)

- Global Chat, global Draft, Mindmap tab → folded into the workspace.
- "Tools lama" link and admin/reembed panel → live only at `/tools` (direct URL).
- Mindmap autosave list stays in localStorage (`mindmaps.js`), surfaced inside the Paper tab's mindmap panel instead of a sidebar.

### Language

All user-facing strings in Indonesian, layperson-friendly:

- "project" → "naskah"
- "expand" → "cari juga di luar naskah ini"
- "nudge" → "paper lain yang mungkin relevan"
- Consistent with existing Indonesian strings (`tidak disebutkan`, etc.).

## Backend Changes

Two changes:

1. **Draft scoping:** add `doc_ids: Optional[List[int]]` to `DraftRequest` in `app/web/routes.py`, pass through as `filters["doc_ids"]` to `draft_paragraph()` — `search()` already supports the filter.

2. **Async upload with progress.** The current `POST /projects/{id}/upload` runs `ingest_pdf()` synchronously in-request (`projects_routes.py`); a 1000-page book takes minutes through Docling and the request times out. Rework using the proven background-job pattern from the admin reembed panel (`admin_routes.py`):
   - `POST /projects/{id}/upload` → save file, register job, return `job_id` immediately.
   - `GET /uploads/{job_id}` → `{stage, done, total, error}` for polling. Stages (Indonesian in UI): "membaca halaman" (pages extracted), "mengindeks" (chunks embedded), "selesai", "gagal: …".
   - `ingest_pdf()` gains an optional `progress` callback parameter, same pattern as `reembed(progress=...)`. Pipeline already knows page and chunk counts.
   - All uploads use this one path — no sync/async branching by file size.
   - On job completion the document is linked to the naskah (hash-dedupe behavior unchanged).

3. **LLM model switcher (admin mini-menu).** Switch the *generation* LLM (DeepSeek / Jatevo / future additions) at runtime — never the embedding model (that stays in the `/tools` reembed panel with its dim-mismatch guards).
   - Choices come from config: an `LLM_CHOICES` entry in `.env` (provider/model list). Adding a model later = edit `.env`, no code change. Default list: the two existing providers.
   - `GET /admin/llm` → `{choices, active}`; `POST /admin/llm` → set active choice.
   - Active choice persisted in the existing `meta` table; `config.llm_config()` consults the override, falls back to current env behavior when unset. Hermes/VPS unaffected (reads its own env).
   - UI: small ⚙ icon in the Beranda corner (next to "Semua PDF") opening a minimal panel — radio list of models + save. Not a main tab; invisible enough not to confuse the primary user.

No DB schema, retrieval, or VPS-sync changes.

## Frontend Changes

All within `templates/new.html` + `static/new/*` (the `/` UI). The legacy `/tools` UI is untouched.

- `new.html`: sidebar 4-nav replaced by Beranda/workspace structure.
- `main.js`: routes between Beranda and workspace views; mounts tabs.
- Reused as-is or lightly parameterized: `chat.js` (already endpoint+nudge parametric), `draft.js` (gains doc_ids), `mindmap.js` (rendered in panel), `citations.js`, `api.js`, `splash.js`.
- `history.js`: conversations keyed by naskah (`scope: projectId`); list filtered per scope. Existing `scope: "global"` conversations remain in localStorage but are no longer surfaced — no data loss, no migration. (Pure module — unit-tested.)
- `projects.js`: becomes the Beranda card list + workspace shell.
- `new.css`: styles for cards, inner tabs, upload dropzone; design tokens unchanged (sky-blue brand, Amber reserved for splash EKG).
- Visual language stays grid.jatevo.ai-style: spacious, calm, chat column with generous whitespace. The home feature cards / question-suggestion boxes (added in `ada7e71`) are **removed** — Beranda is just the naskah list, and the Tanya tab is a clean chat column with no suggestion cards.

The two UIs remain independent: no `/` change touches `/tools`.

## Error Handling (layperson copy)

- LLM/Ollama unavailable (503) → "Mesin penjawab sedang tidak aktif. Minta Eka menyalakannya."
- Upload duplicate (hash dedupe) → "File sudah ada di perpustakaan — langsung ditautkan ke naskah ini."
- Naskah with zero papers → Tanya tab shows: "Tambahkan paper dulu di tab Paper."
- Dim-mismatch 409 (existing guard) → friendly equivalent, still surfaced.

## Testing

**Python (pytest):**
- New: `/draft` with `doc_ids` restricts retrieval to those documents.
- New: async upload — job registered, status polls through stages, document linked on completion, dedupe re-upload reports already-present; failure surfaces in `error`. (Pattern mirrors `test_admin_reembed.py`.)
- New: `ingest_pdf(progress=...)` callback fires with sane done/total.
- New: LLM switcher — `GET/POST /admin/llm` round-trip, persistence in `meta`, `llm_config()` honors override and falls back to env.
- Updated: `tests/test_new_ui.py` — `/` serves grid UI with new structure and Indonesian labels.
- Unchanged endpoints keep their existing tests.

**JS (`node --test tests/js/*.test.mjs`, pure modules only — existing convention):**
- `history.js`: per-scope save/list/filter.
- `api.js`, `citations.js`, `mindmaps.js`: unchanged, existing tests still pass.
- DOM views (Beranda, workspace, tabs): manual verification, per convention.

**Manual end-to-end (as the wife):** open app → create naskah → upload PDF → ask question (with and without "cari di luar") → draft paragraph → build matrix → export.

## Build Order

Each step lands green before the next:

1. Backend: `doc_ids` on `/draft` + test.
2. Backend: `ingest_pdf(progress=...)` callback + async upload job endpoints + tests.
3. `history.js` per-naskah scope + tests.
4. Beranda: naskah card list as the main screen.
5. Ruang kerja: four inner tabs wired to existing endpoints; mindmap as Paper-tab action.
6. Upload UI: drag-drop in Paper tab → async job + progress bar polling.
7. LLM switcher: backend endpoints + meta persistence + ⚙ mini-panel.
8. Copy pass: Indonesian labels + friendly error messages; drop "Tools lama" link from nav.
9. Manual end-to-end verification.

## Risks / Non-Goals

- Low risk: no DB schema, ingest pipeline, retrieval, or VPS sync changes; `/tools` is the intact fallback.
- Non-goals: auth/multi-user, mobile app, changing matrix/extraction logic, deleting any backend capability.
