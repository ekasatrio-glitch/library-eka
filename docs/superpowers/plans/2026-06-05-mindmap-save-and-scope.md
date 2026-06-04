# Mindmap Save & Scope Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add autosave, a reopenable saved-list, delete, and paper-scoped retrieval to the Grid Mindmap view — saved in `localStorage`, scope picked from the full corpus.

**Architecture:** New pure `mindmaps.js` localStorage store (mirrors `history.js`, unit-tested). `mindmap.js` view gains autosave + a `/library` doc-picker modal + saved-list render/open/delete. The shell gets a `#mindmap-side` sidebar body; `main.js` switches sidebar bodies per view. Backend `build_mindmap()` and `MindmapRequest` gain an optional `doc_ids` that becomes a `search()` filter (None/empty ⇒ whole corpus, unchanged).

**Tech Stack:** Vanilla ES modules, `node:test` (pure store), pytest + Starlette TestClient (backend scope + shell), markmap (existing).

**Spec:** `docs/superpowers/specs/2026-06-05-mindmap-save-and-scope-design.md`

## Backend contracts (verified)

- `app/rag/retriever.py` `search(question, top_k, filters=None, conn=None)`; `_build_where` honors `filters["doc_ids"]` (a list) → `c.doc_id IN (...)`.
- `app/rag/mindmap.py` `build_mindmap(topic, breadth=4, top_k=6, conn=None)` loops `for q in [topic, *subs]: search(q, top_k=top_k, conn=conn)`; calls `chat(...)` (LLM) twice (`_expand_subtopics` + outline).
- `app/web/routes.py` `MindmapRequest{topic, breadth=4, top_k=6}`; route `post_mindmap` calls `build_mindmap(req.topic, breadth=req.breadth, top_k=req.top_k)`.
- `GET /library` → `{items:[{id,title,authors,year,folder,path,status,added_at}], folders:[...]}`.

## Frontend contracts (verified)

- `history.js` `makeHistory(storage)` → `{list,get,save,remove}`, KEY `libeka.conversations`, caller supplies `id`/`updatedAt`.
- `mindmap.js` `mountMindmap(viewEl)` builds form (`#mm-topic`,`#mm-breadth`,`#mm-submit`,`#mm-md`,`#mm-svg`) + `renderMindmap(host, markdown)` (explicit `Markmap.create().fit()` + autoloader fallback).
- `new.html` `.side-body` holds `#chat-side` and `#projects-side` (hidden). `main.js` refs `chatSide`,`projectsSide`; `activate(nav, view, showProjectsSide)`; `showChat/showProjects/showDraft/showMindmap`; `mountMindmap(viewMindmap)` at boot.
- `api.js` exports `escapeHtml`, `getJSON`, `postJSON`.

## Files

```
app/web/static/new/mindmaps.js   # CREATE: makeMindmapStore(storage) localStorage CRUD
tests/js/mindmaps.test.mjs       # CREATE: store unit tests
app/rag/mindmap.py               # MODIFY: build_mindmap(..., doc_ids=None) -> search filters
app/web/routes.py                # MODIFY: MindmapRequest.doc_ids -> build_mindmap
tests/test_mindmap_scope.py      # CREATE: doc_ids filter wiring + route 200
app/web/templates/new.html       # MODIFY: #mindmap-side sidebar body
app/web/static/new/main.js       # MODIFY: activate() sidebar-body switch + store + mount opts
app/web/static/new/mindmap.js    # MODIFY: autosave + doc picker + saved-list + open/delete
app/web/static/new/new.css       # MODIFY: doc-picker modal + saved-list styles
tests/test_new_ui.py             # MODIFY: assert #mindmap-side / #mindmap-recent
```

---

### Task 1: `mindmaps.js` localStorage store (pure)

**Files:**
- Create: `app/web/static/new/mindmaps.js`
- Create: `tests/js/mindmaps.test.mjs`

- [ ] **Step 1: Write the failing tests** — create `tests/js/mindmaps.test.mjs`:

```javascript
import { test } from "node:test";
import assert from "node:assert/strict";
import { makeMindmapStore } from "../../app/web/static/new/mindmaps.js";

function fakeStorage() {
  const m = new Map();
  return {
    getItem: k => (m.has(k) ? m.get(k) : null),
    setItem: (k, v) => m.set(k, String(v)),
  };
}

function item(over = {}) {
  return {
    id: "m1", topic: "sedasi", breadth: 4, markdown: "# sedasi",
    citations: [], docIds: [], docLabel: "semua korpus", updatedAt: 100, ...over,
  };
}

test("save then get returns the item", () => {
  const s = makeMindmapStore(fakeStorage());
  s.save(item());
  assert.equal(s.get("m1").topic, "sedasi");
});

test("save upserts by id (no duplicate)", () => {
  const s = makeMindmapStore(fakeStorage());
  s.save(item());
  s.save(item({ topic: "sedasi v2", updatedAt: 200 }));
  assert.equal(s.list().length, 1);
  assert.equal(s.get("m1").topic, "sedasi v2");
});

test("list is newest-first by updatedAt", () => {
  const s = makeMindmapStore(fakeStorage());
  s.save(item({ id: "a", updatedAt: 100 }));
  s.save(item({ id: "b", updatedAt: 300 }));
  s.save(item({ id: "c", updatedAt: 200 }));
  assert.deepEqual(s.list().map(x => x.id), ["b", "c", "a"]);
});

test("remove drops by id", () => {
  const s = makeMindmapStore(fakeStorage());
  s.save(item({ id: "a" }));
  s.save(item({ id: "b" }));
  s.remove("a");
  assert.deepEqual(s.list().map(x => x.id), ["b"]);
});

test("get missing returns null", () => {
  const s = makeMindmapStore(fakeStorage());
  assert.equal(s.get("nope"), null);
});

test("corrupt storage yields empty list", () => {
  const st = fakeStorage();
  st.setItem("libeka.mindmaps", "{not json");
  const s = makeMindmapStore(st);
  assert.deepEqual(s.list(), []);
});
```

- [ ] **Step 2: Run to verify it fails**

Run: `node --test tests/js/mindmaps.test.mjs`
Expected: FAIL — module `mindmaps.js` not found.

- [ ] **Step 3: Create** `app/web/static/new/mindmaps.js`:

```javascript
// Saved mindmaps in localStorage. DOM-free; storage injected so it is unit-testable.
// Callers pass id/updatedAt (no Date.now() inside => deterministic), like history.js.

const KEY = "libeka.mindmaps";

export function makeMindmapStore(storage) {
  function readAll() {
    try {
      const v = JSON.parse(storage.getItem(KEY) || "[]");
      return Array.isArray(v) ? v : [];
    } catch {
      return [];
    }
  }
  function writeAll(arr) {
    storage.setItem(KEY, JSON.stringify(arr));
  }
  return {
    list() {
      return readAll().slice().sort((a, b) => (b.updatedAt || 0) - (a.updatedAt || 0));
    },
    get(id) {
      return readAll().find(m => m.id === id) || null;
    },
    save(mm) {
      const arr = readAll().filter(m => m.id !== mm.id);
      arr.push(mm);
      writeAll(arr);
    },
    remove(id) {
      writeAll(readAll().filter(m => m.id !== id));
    },
  };
}
```

- [ ] **Step 4: Run to verify it passes**

Run: `node --test tests/js/mindmaps.test.mjs`
Expected: 6 pass.

- [ ] **Step 5: Confirm full JS suite still green**

Run: `node --test tests/js/*.test.mjs`
Expected: all pass (21 existing + 6 new = 27).

- [ ] **Step 6: Commit**

```bash
git add app/web/static/new/mindmaps.js tests/js/mindmaps.test.mjs
git commit -m "feat(ui): mindmaps.js localStorage store for saved mindmaps"
```

---

### Task 2: Backend — `build_mindmap(doc_ids)` scope filter

**Files:**
- Modify: `app/rag/mindmap.py`
- Create: `tests/test_mindmap_scope.py`

- [ ] **Step 1: Write the failing test** — create `tests/test_mindmap_scope.py`:

```python
from unittest.mock import patch

from app.rag import mindmap as mm


def _stub_chat(sys, user, **kw):
    # _expand_subtopics expects a JSON array; outline call returns markdown.
    if "subtopik" in sys.lower() and "JSON" in sys:
        return '["sub a", "sub b"]'
    return "# topik\n\n## sub a\n- poin"


class _Hit:
    def __init__(self, cid):
        self.chunk_id = cid
        self.doc_id = 7
        self.title = "Paper"
        self.page_start = 1
        self.page_end = 1
        self.text = "ctx"
        self.score = 1.0


def test_build_mindmap_passes_doc_ids_filter():
    calls = []

    def fake_search(q, top_k=6, conn=None, filters=None):
        calls.append(filters)
        return [_Hit(1)]

    with patch("app.rag.mindmap.search", side_effect=fake_search), \
         patch("app.rag.mindmap.chat", side_effect=_stub_chat), \
         patch("app.rag.mindmap.build_citations", return_value=[]), \
         patch("app.rag.mindmap.format_context", return_value="CTX"):
        mm.build_mindmap("sedasi", breadth=2, doc_ids=[7])

    assert calls, "search was never called"
    assert all(f == {"doc_ids": [7]} for f in calls), calls


def test_build_mindmap_no_doc_ids_means_no_filter():
    calls = []

    def fake_search(q, top_k=6, conn=None, filters=None):
        calls.append(filters)
        return [_Hit(1)]

    with patch("app.rag.mindmap.search", side_effect=fake_search), \
         patch("app.rag.mindmap.chat", side_effect=_stub_chat), \
         patch("app.rag.mindmap.build_citations", return_value=[]), \
         patch("app.rag.mindmap.format_context", return_value="CTX"):
        mm.build_mindmap("sedasi", breadth=2)

    assert calls and all(f is None for f in calls), calls
```

- [ ] **Step 2: Run to verify it fails**

Run: `venv/bin/python -m pytest tests/test_mindmap_scope.py -v`
Expected: FAIL — `build_mindmap()` has no `doc_ids` kwarg (TypeError).

- [ ] **Step 3: Edit `app/rag/mindmap.py`** — change the signature:

```python
def build_mindmap(
    topic: str,
    breadth: int = 4,
    top_k: int = 6,
    conn=None,
) -> Dict[str, Any]:
    subs = _expand_subtopics(topic, breadth)
```

to:

```python
def build_mindmap(
    topic: str,
    breadth: int = 4,
    top_k: int = 6,
    conn=None,
    doc_ids: Optional[List[int]] = None,
) -> Dict[str, Any]:
    subs = _expand_subtopics(topic, breadth)
    filters = {"doc_ids": list(doc_ids)} if doc_ids else None
```

Then change the retrieval loop line:

```python
        for h in search(q, top_k=top_k, conn=conn):
```

to:

```python
        for h in search(q, top_k=top_k, filters=filters, conn=conn):
```

(`Optional` and `List` are already imported at the top: `from typing import Any, Dict, List, Optional`.)

- [ ] **Step 4: Run to verify it passes**

Run: `venv/bin/python -m pytest tests/test_mindmap_scope.py -v`
Expected: 2 pass.

- [ ] **Step 5: Confirm the existing mindmap path is unaffected**

Run: `venv/bin/python -m pytest tests/ -q -k mindmap`
Expected: PASS (new scope tests + any existing mindmap tests).

- [ ] **Step 6: Commit**

```bash
git add app/rag/mindmap.py tests/test_mindmap_scope.py
git commit -m "feat(mindmap): scope retrieval to selected papers via doc_ids"
```

---

### Task 3: Route — `MindmapRequest.doc_ids`

**Files:**
- Modify: `app/web/routes.py`
- Modify: `tests/test_mindmap_scope.py` (append route test)

- [ ] **Step 1: Append the failing route test** to `tests/test_mindmap_scope.py`:

```python
from fastapi.testclient import TestClient

from app.web.app import create_app


def test_mindmap_route_forwards_doc_ids():
    seen = {}

    def fake_build(topic, breadth=4, top_k=6, doc_ids=None):
        seen["topic"] = topic
        seen["doc_ids"] = doc_ids
        return {"markdown": "# x", "citations": [], "subtopics": []}

    with patch("app.rag.mindmap.build_mindmap", side_effect=fake_build):
        client = TestClient(create_app())
        r = client.post("/mindmap", json={"topic": "sedasi", "doc_ids": [7, 9]})
    assert r.status_code == 200
    assert seen["doc_ids"] == [7, 9]
```

(The route imports `build_mindmap` lazily inside the function; patching
`app.rag.mindmap.build_mindmap` is what the import resolves to.)

- [ ] **Step 2: Run to verify it fails**

Run: `venv/bin/python -m pytest tests/test_mindmap_scope.py::test_mindmap_route_forwards_doc_ids -v`
Expected: FAIL — `doc_ids` is dropped (extra field ignored), so `seen["doc_ids"]` is None.

- [ ] **Step 3: Edit `app/web/routes.py`** — change `MindmapRequest`:

```python
class MindmapRequest(BaseModel):
    topic: str = Field(..., min_length=1)
    breadth: int = 4
    top_k: int = 6
```

to:

```python
class MindmapRequest(BaseModel):
    topic: str = Field(..., min_length=1)
    breadth: int = 4
    top_k: int = 6
    doc_ids: Optional[List[int]] = None
```

Then change the `post_mindmap` body call:

```python
    out = build_mindmap(req.topic, breadth=req.breadth, top_k=req.top_k)
```

to:

```python
    out = build_mindmap(req.topic, breadth=req.breadth, top_k=req.top_k, doc_ids=req.doc_ids)
```

(`Optional` and `List` are already imported in `routes.py` — confirm with
`grep -n "from typing import" app/web/routes.py`; if `List` is missing, add it.)

- [ ] **Step 4: Run to verify it passes**

Run: `venv/bin/python -m pytest tests/test_mindmap_scope.py -v`
Expected: 3 pass.

- [ ] **Step 5: Commit**

```bash
git add app/web/routes.py tests/test_mindmap_scope.py
git commit -m "feat(web): /mindmap accepts doc_ids to scope retrieval"
```

---

### Task 4: Shell — `#mindmap-side` sidebar body

**Files:**
- Modify: `app/web/templates/new.html`

- [ ] **Step 1: Add the sidebar body** — in `app/web/templates/new.html`, find the `#projects-side` block inside `.side-body`:

```html
      <div id="projects-side" hidden>
        <div class="side-label">Projects</div>
```

Locate the closing `</div>` of that `#projects-side` block (it wraps the
`+ Proyek baru` button), and immediately AFTER that closing `</div>`, insert:

```html
      <div id="mindmap-side" hidden>
        <div class="side-label">Mindmap tersimpan</div>
        <div id="mindmap-recent"></div>
      </div>
```

(If unsure where `#projects-side` ends, the next sibling is `<div class="side-foot">`
— insert the new block right before `<div class="side-foot">`.)

- [ ] **Step 2: Verify shell still renders**

Run: `venv/bin/python -m pytest tests/test_new_ui.py -v`
Expected: all pass (no assertions broken).

- [ ] **Step 3: Commit**

```bash
git add app/web/templates/new.html
git commit -m "feat(ui): mindmap-side sidebar body for saved mindmaps list"
```

---

### Task 5: `main.js` — sidebar-body switch + store + mount opts

**Files:**
- Modify: `app/web/static/new/main.js`

`activate()` currently shows chat vs projects sidebar via a boolean. Generalize it
to show exactly one of three sidebar bodies, and pass the store + recent element to
`mountMindmap`.

- [ ] **Step 1: Add imports + element refs + store** — at the top of `main.js`, after the existing `import { mountMindmap } from "./mindmap.js";` line, add:

```javascript
import { makeMindmapStore } from "./mindmaps.js";
```

After the line `const navMindmap = document.getElementById("nav-mindmap");`, add:

```javascript
const mindmapSide = document.getElementById("mindmap-side");
const mindmapRecent = document.getElementById("mindmap-recent");
const mindmaps = makeMindmapStore(window.localStorage);
```

- [ ] **Step 2: Rewrite `activate()` and the `show*` helpers** — replace the existing block:

```javascript
function activate(nav, view, showProjectsSide) {
  NAVS.forEach(n => n.classList.toggle("active", n === nav));
  VIEWS.forEach(v => { v.hidden = v !== view; });
  // Draft/Mindmap reuse the Chat sidebar body (Recent) so the sidebar is never blank.
  chatSide.hidden = showProjectsSide;
  projectsSide.hidden = !showProjectsSide;
}
function showChat() { activate(navChat, viewChat, false); }
function showProjects() { activate(navProjects, viewProjects, true); }
function showDraft() { activate(navDraft, viewDraft, false); }
function showMindmap() { activate(navMindmap, viewMindmap, false); }
```

with:

```javascript
const SIDES = [chatSide, projectsSide, mindmapSide];
function activate(nav, view, sideEl) {
  NAVS.forEach(n => n.classList.toggle("active", n === nav));
  VIEWS.forEach(v => { v.hidden = v !== view; });
  // Show exactly one sidebar body. Draft reuses the Chat body (Recent).
  SIDES.forEach(s => { s.hidden = s !== sideEl; });
}
function showChat() { activate(navChat, viewChat, chatSide); }
function showProjects() { activate(navProjects, viewProjects, projectsSide); }
function showDraft() { activate(navDraft, viewDraft, chatSide); }
function showMindmap() { activate(navMindmap, viewMindmap, mindmapSide); }
```

- [ ] **Step 3: Pass store + recentEl to `mountMindmap`** — replace:

```javascript
mountMindmap(viewMindmap);
```

with:

```javascript
mountMindmap(viewMindmap, { store: mindmaps, recentEl: mindmapRecent });
```

- [ ] **Step 4: Syntax check all modules**

Run: `for f in "app/web/static/new/"*.js; do node --check "$f" || echo "FAIL $f"; done`
Expected: no FAIL lines.

- [ ] **Step 5: Commit**

```bash
git add app/web/static/new/main.js
git commit -m "feat(ui): main.js switches sidebar bodies; wires mindmap store"
```

---

### Task 6: `mindmap.js` — autosave + doc picker + saved-list + open/delete

**Files:**
- Modify: `app/web/static/new/mindmap.js`

This rewrites `mountMindmap` to accept `{ store, recentEl }`, add a "Sumber" picker,
autosave on success, render the saved list, and support open/delete. Keep the
existing `renderMindmap(host, markdown)` function unchanged.

- [ ] **Step 1: Replace the whole `mindmap.js`** with:

```javascript
// Mindmap view: generate, autosave to a localStorage store, reopen + delete saved
// maps, and scope retrieval to selected papers via a /library doc picker.
import { escapeHtml, getJSON, postJSON } from "./api.js";

export function mountMindmap(viewEl, opts = {}) {
  const store = opts.store;            // makeMindmapStore(localStorage)
  const recentEl = opts.recentEl;      // sidebar list container (#mindmap-recent)

  viewEl.innerHTML = `
    <div class="scroll"><div class="inner">
      <form id="mm-form" class="df-form">
        <textarea id="mm-topic" rows="2" placeholder="Topik mindmap…"></textarea>
        <div class="df-row">
          <input id="mm-breadth" type="number" min="2" max="8" value="4" title="Jumlah subtopik" />
          <button class="df-btn ghost" id="mm-source" type="button">Sumber: semua korpus</button>
          <button class="df-btn" id="mm-submit" type="button">Buat mindmap</button>
        </div>
      </form>
      <pre id="mm-md" class="md"></pre>
      <div id="mm-svg" class="markmap-wrap"></div>
    </div></div>`;

  const topic = viewEl.querySelector("#mm-topic");
  const breadth = viewEl.querySelector("#mm-breadth");
  const md = viewEl.querySelector("#mm-md");
  const svg = viewEl.querySelector("#mm-svg");
  const sourceBtn = viewEl.querySelector("#mm-source");

  let selectedDocs = [];   // [] = whole corpus
  let libraryCache = null;  // cached /library items

  function sourceLabel() {
    return selectedDocs.length ? `${selectedDocs.length} paper` : "semua korpus";
  }
  function refreshSourceBtn() {
    sourceBtn.textContent = "Sumber: " + sourceLabel();
  }

  // ---- explicit markmap render (fills container; falls back to autoloader) ----
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

  // ---- saved-list (sidebar) ----
  function renderRecent() {
    if (!recentEl || !store) return;
    const items = store.list();
    if (!items.length) {
      recentEl.innerHTML = `<div class="side-empty">Belum ada mindmap.</div>`;
      return;
    }
    recentEl.innerHTML = items.map(m =>
      `<div class="recent-row"><button class="recent-open" data-mid="${m.id}" type="button">${escapeHtml(m.topic)}</button>` +
      `<button class="recent-del" data-del="${m.id}" title="Hapus" type="button">🗑</button></div>`).join("");
    recentEl.querySelectorAll("[data-mid]").forEach(b =>
      b.addEventListener("click", () => openSaved(b.dataset.mid)));
    recentEl.querySelectorAll("[data-del]").forEach(b =>
      b.addEventListener("click", () => { store.remove(b.dataset.del); renderRecent(); }));
  }

  function openSaved(id) {
    const m = store && store.get(id);
    if (!m) return;
    topic.value = m.topic || "";
    breadth.value = m.breadth || 4;
    selectedDocs = Array.isArray(m.docIds) ? m.docIds.slice() : [];
    refreshSourceBtn();
    md.textContent = m.markdown || "";
    if (m.markdown) renderMindmap(svg, m.markdown); else svg.innerHTML = "";
  }

  // ---- doc picker modal ----
  function openPicker() {
    const overlay = document.createElement("div");
    overlay.className = "mm-modal";
    overlay.innerHTML = `
      <div class="mm-modal-box">
        <div class="mm-modal-head">
          <strong>Pilih paper sumber</strong>
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
    const chosen = new Set(selectedDocs);

    function rowHtml(it) {
      const yr = it.year ? ` (${it.year})` : "";
      return `<label class="mm-pick-row"><input type="checkbox" data-id="${it.id}"${chosen.has(it.id) ? " checked" : ""}/>` +
        `<span>${escapeHtml(it.title || "(untitled)")}${escapeHtml(yr)}</span></label>`;
    }
    function paint(items) {
      listEl.innerHTML = items.map(rowHtml).join("") || `<div class="side-empty">Tidak ada paper.</div>`;
      listEl.querySelectorAll("input[data-id]").forEach(cb =>
        cb.addEventListener("change", () => {
          const id = Number(cb.dataset.id);
          if (cb.checked) chosen.add(id); else chosen.delete(id);
        }));
    }
    function close() { overlay.remove(); }

    async function load() {
      try {
        if (!libraryCache) libraryCache = (await getJSON("/library")).items || [];
        paint(libraryCache);
      } catch (err) {
        listEl.innerHTML = `<div class="side-empty">Gagal memuat daftar paper.</div>`;
      }
    }
    load();

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
    overlay.querySelector("#mm-pick-cancel").addEventListener("click", close);
    overlay.addEventListener("click", e => { if (e.target === overlay) close(); });
    overlay.querySelector("#mm-pick-ok").addEventListener("click", () => {
      selectedDocs = [...chosen];
      refreshSourceBtn();
      close();
    });
  }

  // ---- generate ----
  async function submit() {
    const t = topic.value.trim();
    if (!t) return;
    md.textContent = "Menyusun mindmap…";
    svg.innerHTML = "";
    try {
      const body = { topic: t, breadth: Number(breadth.value) || 4 };
      if (selectedDocs.length) body.doc_ids = selectedDocs;
      const res = await postJSON("/mindmap", body);
      md.textContent = res.markdown;
      renderMindmap(svg, res.markdown);
      if (store) {
        const now = Date.now();
        store.save({
          id: "m" + now,
          topic: t,
          breadth: Number(breadth.value) || 4,
          markdown: res.markdown,
          citations: res.citations || [],
          docIds: selectedDocs.slice(),
          docLabel: sourceLabel(),
          updatedAt: now,
        });
        renderRecent();
      }
    } catch (err) {
      md.textContent = "Error: " + err.message;
    }
  }

  viewEl.querySelector("#mm-submit").addEventListener("click", submit);
  sourceBtn.addEventListener("click", openPicker);
  refreshSourceBtn();
  renderRecent();
}
```

- [ ] **Step 2: Syntax check**

Run: `node --check app/web/static/new/mindmap.js`
Expected: no output.

- [ ] **Step 3: Confirm JS suite still green** (mindmap.js is DOM, not unit-tested, but ensure nothing else broke)

Run: `node --test tests/js/*.test.mjs`
Expected: all pass (27).

- [ ] **Step 4: Commit**

```bash
git add app/web/static/new/mindmap.js
git commit -m "feat(ui): mindmap autosave, saved-list open/delete, paper-scope picker"
```

---

### Task 7: Styles — doc-picker modal + saved-list

**Files:**
- Modify: `app/web/static/new/new.css`

- [ ] **Step 1: Append to `app/web/static/new/new.css`:**

```css
/* mindmap: source button, saved-list rows, doc-picker modal */
.df-btn.ghost{background:#fff;color:var(--text2);border:1px solid var(--border)}
.df-btn.ghost:hover{border-color:#7DD3FC;color:var(--brand);background:#F8FCFF}
.side-empty{color:var(--text3);font-size:12.5px;padding:6px 2px}
.recent-row{display:flex;align-items:center;gap:6px;padding:1px 0}
.recent-open{flex:1;text-align:left;background:none;border:none;cursor:pointer;color:var(--text2);font-size:13px;padding:6px 8px;border-radius:8px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.recent-open:hover{background:var(--brand-subtle);color:var(--brand)}
.recent-del{background:none;border:none;cursor:pointer;opacity:.5;font-size:12px;padding:4px}
.recent-del:hover{opacity:1}
.mm-modal{position:fixed;inset:0;background:rgba(15,23,42,.45);display:flex;align-items:center;justify-content:center;z-index:50}
.mm-modal-box{background:#fff;border-radius:16px;width:min(560px,92vw);max-height:80vh;display:flex;flex-direction:column;box-shadow:var(--shadow);overflow:hidden}
.mm-modal-head{display:flex;align-items:center;gap:12px;padding:16px 18px;border-bottom:1px solid var(--border)}
.mm-modal-head input{flex:1;border:1px solid var(--border);border-radius:9px;padding:7px 11px;font-size:13px}
.mm-pick-list{overflow:auto;padding:8px 10px;flex:1}
.mm-pick-row{display:flex;align-items:center;gap:9px;padding:7px 8px;border-radius:8px;cursor:pointer;font-size:13px;color:var(--text2)}
.mm-pick-row:hover{background:var(--brand-subtle)}
.mm-modal-foot{display:flex;align-items:center;gap:8px;padding:12px 16px;border-top:1px solid var(--border)}
.mm-modal-foot .grow{flex:1}
```

- [ ] **Step 2: Brace-balance check**

Run: `node -e "const c=require('fs').readFileSync('app/web/static/new/new.css','utf8');const o=(c.match(/{/g)||[]).length,x=(c.match(/}/g)||[]).length;if(o!==x)throw new Error('brace mismatch '+o+' vs '+x);console.log('braces ok',o)"`
Expected: `braces ok <n>`.

- [ ] **Step 3: Commit**

```bash
git add app/web/static/new/new.css
git commit -m "feat(ui): styles for mindmap source picker + saved-list"
```

---

### Task 8: Shell assertions + full verification

**Files:**
- Modify: `tests/test_new_ui.py`

- [ ] **Step 1: Append the shell test** to `tests/test_new_ui.py`:

```python
def test_mindmap_side_present():
    html = _html()
    for el in ('id="mindmap-side"', 'id="mindmap-recent"'):
        assert el in html, f"missing {el}"
```

- [ ] **Step 2: Run it**

Run: `venv/bin/python -m pytest tests/test_new_ui.py -v`
Expected: all pass (existing + the new test).

- [ ] **Step 3: Full automated suite**

Run: `node --test tests/js/*.test.mjs && venv/bin/python -m pytest tests/ -q`
Expected: all JS pass (27); all pytest pass.

- [ ] **Step 4: Manual verification** — `scripts/run.sh`, open `http://127.0.0.1:8765/` (needs Ollama + LLM key):
  1. Mindmap tab → sidebar shows "Mindmap tersimpan" (empty → "Belum ada mindmap.").
  2. Enter a topic → "Buat mindmap" → map renders AND a row appears in the sidebar.
  3. Click the saved row → topic/breadth/markdown/map restored (no new LLM call).
  4. 🗑 on a row → it disappears from the list.
  5. "Sumber: semua korpus" → pick 1 paper → "Sumber: 1 paper" → generate → citations only from that paper.
  6. Reload the page → saved mindmaps persist (localStorage).

- [ ] **Step 5: Commit**

```bash
git add tests/test_new_ui.py
git commit -m "test: assert mindmap-side sidebar present in /new"
```

---

## Self-review notes

- **Spec coverage:** autosave (T6 submit→store.save), riwayat list (T4 shell + T5 wiring + T6 renderRecent), delete (T6 recent-del), scope-paper (T2 backend + T3 route + T6 picker). Storage = localStorage pure store (T1). Sidebar-Recent location (T4/T5). Out-of-scope items omitted.
- **Type consistency:** `makeMindmapStore(storage)→{list,get,save,remove}` (T1) used in T5/T6; item shape `{id,topic,breadth,markdown,citations,docIds,docLabel,updatedAt}` identical in T1 tests, T6 save, T6 openSaved. `build_mindmap(...,doc_ids=None)` (T2) ↔ route call (T3) ↔ tests (T2/T3). `mountMindmap(viewEl,{store,recentEl})` (T6) ↔ main.js call (T5).
- **Back-compat:** `doc_ids` None/empty ⇒ `filters=None` ⇒ identical retrieval to today; `mountMindmap` works even if `opts` omitted (store/recentEl guarded with `if (store)` / `if (!recentEl)`).
- **No placeholders:** every step has exact code/commands. `renderMindmap` re-stated verbatim in the T6 full-file replace (engineer may read tasks out of order).
- **CSS reuse:** `.df-btn.ghost` variant added once (T7); `--brand-subtle`/`--shadow`/`--text2/3`/`--border` already defined in `:root`.
