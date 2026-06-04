# Design — Mindmap: autosave, riwayat, delete, scope-paper

**Date:** 2026-06-05
**Surface:** Grid UI `/new` (now home `/`) Mindmap view + `/mindmap` backend.

## Goal

The Mindmap view currently throws away each generated map and always retrieves
over the whole corpus. Add four capabilities:

1. **Autosave** — every successfully generated mindmap is saved automatically.
2. **Riwayat** — a list of saved mindmaps the user can reopen.
3. **Delete** — remove a saved mindmap.
4. **Scope-paper** — pick which papers (from the full corpus) feed a mindmap,
   instead of always using the entire corpus.

## Decisions (settled in brainstorming)

- **Storage:** browser `localStorage` (same model as chat history — per-browser,
  NOT synced to the VPS, no backend table). Key `libeka.mindmaps`.
- **Doc source for scope:** pick from the **full corpus** via `GET /library`
  (a checkbox picker in the global Mindmap form). Empty selection = whole corpus.
- **Saved-list location:** the **sidebar** — when the Mindmap tab is active the
  sidebar body shows "Mindmap tersimpan" with the saved list (consistent with the
  chat "Recent" pattern). Sidebar currently reuses the chat body for Draft/Mindmap;
  Mindmap gets its own body, Draft keeps reusing the chat body.

## Architecture

```
mindmaps.js (NEW, pure)         localStorage CRUD store — DOM-free, unit-tested
mindmap.js  (MODIFY, view)      autosave + doc-picker + saved-list render + open/delete
new.html    (MODIFY)            #mindmap-side sidebar body (label + #mindmap-recent)
main.js     (MODIFY)            activate() shows the right sidebar body; build store, mount
new.css     (MODIFY)            doc-picker modal + saved-list styles
mindmap.py  (MODIFY, backend)   build_mindmap(..., doc_ids=None) -> search filters
routes.py   (MODIFY, backend)   MindmapRequest.doc_ids -> forwarded
```

### Storage module — `app/web/static/new/mindmaps.js`

Mirror of `history.js`. `makeMindmapStore(storage)` returns `{ list, get, save, remove }`.

- `KEY = "libeka.mindmaps"`.
- Item shape: `{ id, topic, breadth, markdown, citations, docIds, docLabel, updatedAt }`.
  - `docIds`: array of selected doc ids (`[]` = whole corpus).
  - `docLabel`: precomputed summary string ("semua korpus" or "N paper").
- `list()` returns newest-first (sort by `updatedAt` desc), like history.
- `save(item)` upserts by `id` (filter out same id, push).
- `remove(id)` drops by id.
- **Purity:** no `Date.now()` inside — the view generates `id` and `updatedAt`
  and passes them in (same doctrine as `history.js`, keeps it deterministic and
  unit-testable with an injected storage stub).

### Mindmap view — `app/web/static/new/mindmap.js`

`mountMindmap(viewEl, { store, recentEl })`.

- **Form** gains a "Sumber" control: a button showing the current source summary
  (default "Sumber: semua korpus") that opens a **doc picker modal**.
- **Doc picker modal** (built in JS, appended to `document.body`, hidden by default):
  - On open, `GET /library` once (cache the items for the session), render a
    scrollable checkbox list (title + year). A search box filters client-side.
  - "Pilih semua" / "Kosongkan" helpers. OK applies selection, Batal closes.
  - Closure state `selectedDocs` (array of ids); `[]` = whole corpus.
  - After OK, update the summary text ("Sumber: semua korpus" / "Sumber: N paper").
- **Generate (`submit`)**: POST `/mindmap { topic, breadth, doc_ids: selectedDocs }`
  (omit/empty `doc_ids` ⇒ whole corpus). On success:
  - render the markdown (existing explicit `Markmap.create().fit()` path),
  - build an item with `id = "m" + Date.now()`, `updatedAt = Date.now()`,
    `docLabel` from selection, `store.save(item)`, then `renderRecent()`.
- **Saved-list render (`renderRecent`)**: populate `recentEl` from `store.list()`.
  Each row: topic (click ⇒ open) + 🗑 delete button. Empty ⇒ "Belum ada mindmap."
- **Open**: load item ⇒ set `#mm-topic`, `#mm-breadth`, restore `selectedDocs` +
  summary, set `#mm-md` text, re-render the saved markdown. (Does NOT re-call the
  LLM — just restores what was saved.)
- **Delete**: `store.remove(id)` ⇒ `renderRecent()`.

XSS: titles/topics rendered via `escapeHtml` or `textContent` (markdown stays
`textContent`, as today).

### Shell + nav

- **`new.html`**: inside `.side-body`, after `#projects-side`, add
  ```html
  <div id="mindmap-side" hidden>
    <div class="side-label">Mindmap tersimpan</div>
    <div id="mindmap-recent"></div>
  </div>
  ```
- **`main.js`**: generalize `activate()` to show exactly one sidebar body.
  Current signature `activate(nav, view, showProjectsSide)` becomes
  `activate(nav, view, sideEl)` where `sideEl` ∈ {chatSide, projectsSide, mindmapSide}.
  - `showChat()` → chatSide; `showDraft()` → chatSide (unchanged reuse);
    `showProjects()` → projectsSide; `showMindmap()` → mindmapSide.
  - Build `const mindmaps = makeMindmapStore(window.localStorage)` and
    `mountMindmap(viewMindmap, { store: mindmaps, recentEl: document.getElementById("mindmap-recent") })`.

### Backend — scope

- **`app/rag/mindmap.py`**: `build_mindmap(topic, breadth=4, top_k=6, conn=None, doc_ids=None)`.
  Compute `filters = {"doc_ids": list(doc_ids)} if doc_ids else None` and pass
  `search(q, top_k=top_k, filters=filters, conn=conn)` for every query. `doc_ids`
  None/empty ⇒ no filter (current behaviour). `search()` already supports the
  `doc_ids` filter (`retriever._build_where`).
- **`app/web/routes.py`**: `MindmapRequest` gains `doc_ids: Optional[List[int]] = None`;
  the route calls `build_mindmap(req.topic, breadth=req.breadth, top_k=req.top_k, doc_ids=req.doc_ids)`.

## Data flow

```
user picks papers (modal /library) -> selectedDocs[]
generate -> POST /mindmap {topic,breadth,doc_ids} -> build_mindmap(doc_ids)
         -> search(filters={doc_ids}) over selected papers only
         -> {markdown,citations} -> render + store.save() -> sidebar list updates
reopen   -> store.get(id) -> restore form+selection+markdown (no LLM call)
delete   -> store.remove(id) -> sidebar list updates
```

## Error handling

- `GET /library` failure in the picker ⇒ inline "Gagal memuat daftar paper." in the
  modal; generation still possible with whole corpus.
- `/mindmap` failure ⇒ existing behaviour (error text in `#mm-md`); nothing saved.
- Corrupt `localStorage` JSON ⇒ store returns `[]` (try/catch, like history).

## Testing

- **`tests/js/mindmaps.test.mjs`** (`node:test`, injected storage stub): save upserts
  by id, list is newest-first, get/remove work, corrupt JSON ⇒ `[]`.
- **`tests/test_mindmap_scope.py`** (pytest): patch `app.rag.mindmap.search` (record
  calls) and `app.rag.mindmap.chat` (stub); `build_mindmap(topic, doc_ids=[7])` ⇒
  every `search` call received `filters={"doc_ids":[7]}`; `doc_ids=None` ⇒
  `filters=None`. Plus a route test: `POST /mindmap {topic, doc_ids:[7]}` returns 200
  (with `search`/`chat` patched).
- **`tests/test_new_ui.py`**: shell assertion that `id="mindmap-side"` and
  `id="mindmap-recent"` are present.
- Manual (browser): generate → appears in sidebar; reopen restores; delete removes;
  pick 1 paper → citations only from that paper.

## Out of scope (YAGNI)

- Renaming saved mindmaps.
- Syncing saved mindmaps to the VPS (localStorage only, per decision).
- A mindmap tab inside the Project page (the full-corpus picker covers the need).
- Editing a saved mindmap's markdown by hand.

## Invariants preserved

- `doc_ids` None/empty ⇒ identical to today's whole-corpus behaviour (back-compat).
- Indonesian user-facing strings.
- The two front-ends stay independent — no change to legacy `/tools`.
- Embedding dim guard, page provenance, DB sync untouched.
