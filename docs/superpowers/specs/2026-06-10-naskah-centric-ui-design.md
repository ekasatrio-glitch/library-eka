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
| 📄 **Paper** | Paper list; drag-drop PDF upload; import from library; per-selection "🗺️ Peta konsep" button that renders a mindmap in a modal/panel. | `GET/POST /projects/{id}/papers`, `POST /projects/{id}/upload` (exist); `POST /mindmap` with `doc_ids` (exists) |
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

Exactly one: add `doc_ids: Optional[List[int]]` to `DraftRequest` in `app/web/routes.py`, pass through as `filters["doc_ids"]` to `draft_paragraph()` — `search()` already supports the filter. No DB, ingest, retrieval, or VPS-sync changes. No new endpoints.

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
2. `history.js` per-naskah scope + tests.
3. Beranda: naskah card list as the main screen.
4. Ruang kerja: four inner tabs wired to existing endpoints; mindmap as Paper-tab action.
5. Upload UI: drag-drop in Paper tab → `POST /projects/{id}/upload`.
6. Copy pass: Indonesian labels + friendly error messages; drop "Tools lama" link from nav.
7. Manual end-to-end verification.

## Risks / Non-Goals

- Low risk: no DB schema, ingest pipeline, retrieval, or VPS sync changes; `/tools` is the intact fallback.
- Non-goals: auth/multi-user, mobile app, changing matrix/extraction logic, deleting any backend capability.
