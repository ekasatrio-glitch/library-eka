# Grid-Style UI (Chat + Projects) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a parallel `/new` web UI for library-eka in the Grid Analyst visual style, covering Chat and Projects, with a first-visit splash, leaving the existing `/` UI untouched.

**Architecture:** One new FastAPI route (`GET /new`) renders a static shell (`new.html`) that loads native ES modules from `app/web/static/new/`. All data comes from existing endpoints (`/ask`, `/projects/*`, `/library`, `/viewer`, export). Conversation history is browser localStorage. Pure-logic modules (api, citations, history, splash-flag) are DOM-free and unit-tested with Node's built-in `node:test`; DOM/wiring modules (chat, projects, main) are verified manually.

**Tech Stack:** Python/FastAPI + Jinja2 (backend, one route), vanilla JS ES modules (no build step), CSS custom properties, `node:test` (Node 24, zero deps) for JS unit tests, pytest + Starlette TestClient for the route.

**Spec:** `docs/superpowers/specs/2026-06-04-grid-style-ui-design.md`

## Backend contracts (already implemented — do NOT change)

- `POST /ask` `{question, top_k}` → `{answer, citations:[{n,doc_id,chunk_id,title,page_start,page_end,path,cited}], hits}`
- `POST /projects/{id}/ask` `{question, top_k, expand}` → same + `{nudge:[{doc_id,title}], scoped}`
- `GET /projects` → `{projects:[{id,name,description,folder_path,created_at,...}]}`
- `GET /projects/{id}` → project + `{papers:[{id,title,authors,year,...}]}`
- `POST /projects` `{name,description}` → `{id,...}`
- `DELETE /projects/{id}` ; `POST /projects/{id}/papers` `{doc_ids}` ; `DELETE /projects/{id}/papers/{doc_id}`
- `POST /projects/{id}/upload` (multipart `file`) ; `GET /library?q=` → `{items:[{id,title,authors,year,...}], folders, count}`
- `POST /projects/{id}/matrix` `{view, overrides}` and `GET /projects/{id}/matrix?view=` → `{view, columns:[fieldKey], rows:[{source,year,schema,fields:{key: string | {text,refs}}}]}`
- `GET /projects/{id}/matrix/export.xlsx?view=` and `.csv` (link hrefs)
- Citation → PDF page: `/viewer?doc=<doc_id>#page=<page_start>`

## File structure

```
app/web/
  routes.py                       # MODIFY: + GET /new
  templates/new.html              # CREATE: shell (sidebar, chat view, projects view, splash markup)
  static/new/
    api.js        # CREATE: postJSON/getJSON/escapeHtml (DOM-free)
    citations.js  # CREATE: pillHref(), renderAnswerHtml() — cited/uncited split (DOM-free, returns HTML string)
    history.js    # CREATE: makeHistory(storage) — conversations CRUD over injected storage (DOM-free)
    splash.js     # CREATE: shouldShowSplash(storage), markSplashSeen(storage) (DOM-free) + mountSplash(doc) (DOM)
    chat.js       # CREATE: mountChat() — thread, input, empty-state, /ask, citations+history (DOM)
    projects.js   # CREATE: mountProjects() — list, tabs, papers, matrix, scoped chat, export (DOM)
    main.js       # CREATE: entry — splash, sidebar, view switch, mounts chat/projects (DOM)
    new.css       # CREATE: tokens + layout
tests/
  test_new_ui.py                  # CREATE: pytest route + shell assertions
  js/
    api.test.mjs                  # CREATE
    citations.test.mjs            # CREATE
    history.test.mjs              # CREATE
    splash.test.mjs               # CREATE
```

Each JS module uses `export` so `node:test` can import it. Browser loads `main.js` via `<script type="module">`; main.js imports the others. No bundler.

---

### Task 1: Backend route `GET /new` + shell template

**Files:**
- Modify: `app/web/routes.py` (after the `/viewer` route, ~line 191)
- Create: `app/web/templates/new.html`
- Create: `tests/test_new_ui.py`

- [ ] **Step 1: Write the failing test** — create `tests/test_new_ui.py`:

```python
from fastapi.testclient import TestClient

from app.web.app import create_app


def _html():
    client = TestClient(create_app())
    r = client.get("/new")
    assert r.status_code == 200
    return r.text


def test_new_route_renders():
    html = _html()
    assert "library-eka" in html


def test_shell_core_elements_present():
    html = _html()
    for el in (
        'id="sidebar"', 'id="nav-chat"', 'id="nav-projects"',
        'id="view-chat"', 'id="view-projects"',
        'id="recent-list"', 'id="projects-list"',
        'id="splash"', 'id="splash-close"', 'id="splash-enter"',
    ):
        assert el in html, f"missing {el}"


def test_loads_main_module():
    html = _html()
    assert 'type="module"' in html
    assert '/static/new/main.js' in html


def test_old_index_untouched():
    client = TestClient(create_app())
    assert client.get("/").status_code == 200  # legacy UI still served
```

- [ ] **Step 2: Run to verify it fails**

Run: `venv/bin/python -m pytest tests/test_new_ui.py -v`
Expected: FAIL — `/new` returns 404.

- [ ] **Step 3: Add the route** — in `app/web/routes.py`, after the `viewer` function:

```python
@router.get("/new", response_class=HTMLResponse)
def new_ui(request: Request):
    return templates.TemplateResponse(request, "new.html", {})
```

- [ ] **Step 4: Create the shell** `app/web/templates/new.html`:

```html
<!DOCTYPE html>
<html lang="id">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0, viewport-fit=cover">
<title>library-eka</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=Merriweather:wght@400;700&family=Fira+Code:wght@400;500&display=swap" rel="stylesheet">
<link rel="stylesheet" href="/static/new/new.css">
</head>
<body>
<div class="app">
  <aside class="sidebar" id="sidebar">
    <div class="brand">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M4 4h7a2 2 0 0 1 2 2v14a2 2 0 0 0-2-2H4z"/><path d="M20 4h-7a2 2 0 0 0-2 2v14a2 2 0 0 1 2-2h7z"/><path d="M12.5 10h1.5l1 2 1.5-3 1 1H19"/></svg>
      <span>library-eka</span>
    </div>
    <nav class="nav">
      <button class="nav-item active" id="nav-chat" type="button">💬 Chat</button>
      <button class="nav-item" id="nav-projects" type="button">📁 Projects</button>
    </nav>
    <div class="side-body">
      <div id="chat-side">
        <button class="side-btn" id="new-conversation" type="button">+ Percakapan baru</button>
        <div class="side-label">Recent</div>
        <div id="recent-list"></div>
      </div>
      <div id="projects-side" hidden>
        <div class="side-label">Projects</div>
        <div id="projects-list"></div>
        <button class="side-btn" id="new-project" type="button">+ Proyek baru</button>
      </div>
    </div>
    <div class="side-foot">
      <a href="/#tab-draft">Draft ↗</a> · <a href="/#tab-mindmap">Mindmap ↗</a> · <a href="/#tab-library">Library ↗</a>
      <div>Powered by Jatevo · DeepSeek</div>
    </div>
  </aside>

  <main class="main">
    <section class="view" id="view-chat"></section>
    <section class="view" id="view-projects" hidden></section>
  </main>
</div>

<div class="splash" id="splash" hidden>
  <button class="splash-close" id="splash-close" type="button" aria-label="Tutup">✕</button>
  <div class="splash-logo">
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M4 4h7a2 2 0 0 1 2 2v14a2 2 0 0 0-2-2H4z"/><path d="M20 4h-7a2 2 0 0 0-2 2v14a2 2 0 0 1 2-2h7z"/><path d="M12.5 10h1.5l1 2 1.5-3 1 1H19"/></svg>
    <span>library-eka</span>
  </div>
  <h1 class="splash-title">Welcome to <span>library-eka</span> — where all your books meet machine learning.</h1>
  <p class="splash-sub">Ask anything across your entire corpus. Precise answers with click-to-page citations.</p>
  <div class="splash-ekg" aria-hidden="true">
    <svg viewBox="0 0 560 90" preserveAspectRatio="none">
      <path class="ekg-glow" d="M0,45 L120,45 L140,45 L150,30 L160,60 L172,12 L184,78 L196,45 L240,45 L420,45 L432,45 L442,32 L452,58 L464,16 L476,74 L488,45 L560,45"/>
      <path class="ekg-line" d="M0,45 L120,45 L140,45 L150,30 L160,60 L172,12 L184,78 L196,45 L240,45 L420,45 L432,45 L442,32 L452,58 L464,16 L476,74 L488,45 L560,45"/>
    </svg>
  </div>
  <button class="splash-enter" id="splash-enter" type="button">Enter the library →</button>
  <button class="splash-skip" id="splash-skip" type="button">Don't show again</button>
</div>

<script type="module" src="/static/new/main.js"></script>
</body>
</html>
```

- [ ] **Step 5: Run to verify it passes**

Run: `venv/bin/python -m pytest tests/test_new_ui.py -v`
Expected: 4 passed. (`main.js`/`new.css` 404 in the browser is fine for now — route + shell assertions pass.)

- [ ] **Step 6: Run full suite**

Run: `venv/bin/python -m pytest tests/ -q`
Expected: all PASS (82 existing + 4 new).

- [ ] **Step 7: Commit**

```bash
git add app/web/routes.py app/web/templates/new.html tests/test_new_ui.py
git commit -m "feat(ui): add /new route and Grid-style shell template"
```

---

### Task 2: `api.js` — fetch helpers (DOM-free, unit-tested)

**Files:**
- Create: `app/web/static/new/api.js`
- Create: `tests/js/api.test.mjs`

- [ ] **Step 1: Write the failing test** — create `tests/js/api.test.mjs`:

```javascript
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { escapeHtml, viewerHref } from '../../app/web/static/new/api.js';

test('escapeHtml neutralizes HTML metacharacters', () => {
  assert.equal(escapeHtml('<b>a&"\'</b>'), '&lt;b&gt;a&amp;&quot;&#39;&lt;/b&gt;');
});

test('escapeHtml tolerates null/undefined', () => {
  assert.equal(escapeHtml(null), '');
  assert.equal(escapeHtml(undefined), '');
});

test('viewerHref builds doc+page anchor', () => {
  assert.equal(viewerHref({ doc_id: 7, page_start: 3 }), '/viewer?doc=7#page=3');
});
```

- [ ] **Step 2: Run to verify it fails**

Run: `node --test tests/js/api.test.mjs`
Expected: FAIL — module not found / exports missing.

- [ ] **Step 3: Create** `app/web/static/new/api.js`:

```javascript
// Fetch + HTML helpers. DOM-free so it is unit-testable under node:test.

export function escapeHtml(s) {
  return (s || "").replace(/[&<>"']/g, c =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

export function viewerHref(citation) {
  return `/viewer?doc=${citation.doc_id}#page=${citation.page_start}`;
}

export async function postJSON(url, body) {
  const r = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!r.ok) throw new Error(`${r.status}: ${await r.text()}`);
  return r.json();
}

export async function getJSON(url) {
  const r = await fetch(url);
  if (!r.ok) throw new Error(`${r.status}: ${await r.text()}`);
  return r.json();
}
```

- [ ] **Step 4: Run to verify it passes**

Run: `node --test tests/js/api.test.mjs`
Expected: 3 passing.

- [ ] **Step 5: Syntax check + commit**

```bash
node --check app/web/static/new/api.js
git add app/web/static/new/api.js tests/js/api.test.mjs
git commit -m "feat(ui): api.js fetch + escape helpers with node tests"
```

---

### Task 3: `citations.js` — cite-pills + cited/uncited split (DOM-free, unit-tested)

**Files:**
- Create: `app/web/static/new/citations.js`
- Create: `tests/js/citations.test.mjs`

Citations array elements: `{n, doc_id, title, page_start, page_end, cited}`. The answer text contains markers like `[3]`. `renderAnswerHtml` returns an HTML string: the answer with each `[n]` turned into a clickable superscript pill (linking to that citation's PDF page), followed by a collapsed sources block split into cited vs "Diambil, tidak dikutip" (mirrors the shipped backend `cited` flag). If nothing is uncited, a single "Sumber" block is shown.

- [ ] **Step 1: Write the failing test** — create `tests/js/citations.test.mjs`:

```javascript
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { pillsForAnswer, sourcesBlock, renderAnswerHtml } from '../../app/web/static/new/citations.js';

const cits = [
  { n: 1, doc_id: 10, title: 'A', page_start: 1, page_end: 2, cited: false },
  { n: 2, doc_id: 11, title: 'B', page_start: 5, page_end: 5, cited: true },
  { n: 3, doc_id: 12, title: 'C', page_start: 7, page_end: 8, cited: true },
];

test('pillsForAnswer turns [n] into a pill anchor to the right page', () => {
  const html = pillsForAnswer('Klaim [2] dan [3].', cits);
  assert.match(html, /class="pill"[^>]*href="\/viewer\?doc=11#page=5"/);
  assert.match(html, /href="\/viewer\?doc=12#page=7"/);
  assert.ok(!html.includes('[2]'), 'marker should be replaced');
});

test('pillsForAnswer leaves out-of-range markers as text', () => {
  const html = pillsForAnswer('Lihat [9].', cits);
  assert.match(html, /\[9\]/);
});

test('pillsForAnswer escapes answer text', () => {
  const html = pillsForAnswer('a <b> [2]', cits);
  assert.match(html, /a &lt;b&gt;/);
});

test('sourcesBlock splits cited vs uncited', () => {
  const html = sourcesBlock(cits);
  assert.match(html, /Sumber dikutip \(2\)/);
  assert.match(html, /Diambil, tidak dikutip \(1\)/);
});

test('sourcesBlock single block when all cited', () => {
  const html = sourcesBlock([cits[1], cits[2]]);
  assert.match(html, /Sumber \(2\)/);
  assert.ok(!html.includes('tidak dikutip'));
});

test('renderAnswerHtml combines pills + sources', () => {
  const html = renderAnswerHtml('Klaim [2].', cits);
  assert.match(html, /class="pill"/);
  assert.match(html, /Sumber dikutip/);
});

test('renderAnswerHtml with no citations returns just escaped text', () => {
  assert.equal(renderAnswerHtml('halo', []), 'halo');
});
```

- [ ] **Step 2: Run to verify it fails**

Run: `node --test tests/js/citations.test.mjs`
Expected: FAIL — exports missing.

- [ ] **Step 3: Create** `app/web/static/new/citations.js`:

```javascript
// Render an answer with click-to-page cite-pills and a collapsed sources list
// split into cited vs retrieved-but-uncited. DOM-free: returns HTML strings.

import { escapeHtml, viewerHref } from "./api.js";

function citeLink(c) {
  const pg = c.page_start === c.page_end ? `p.${c.page_start}` : `p.${c.page_start}-${c.page_end}`;
  return `<li><a href="${viewerHref(c)}" target="_blank">[${c.n}] ${escapeHtml(c.title)} (${pg})</a></li>`;
}

// Replace [n] markers in the (escaped) answer with superscript pills.
export function pillsForAnswer(answer, citations) {
  const byN = new Map(citations.map(c => [c.n, c]));
  return escapeHtml(answer).replace(/\[(\d+)\]/g, (m, d) => {
    const c = byN.get(Number(d));
    if (!c) return m; // out-of-range marker: leave as text
    return `<a class="pill" href="${viewerHref(c)}" target="_blank" title="${escapeHtml(c.title)}">${c.n}</a>`;
  });
}

export function sourcesBlock(citations) {
  if (!citations || !citations.length) return "";
  const cited = citations.filter(c => c.cited !== false);
  const uncited = citations.filter(c => c.cited === false);
  if (!uncited.length) {
    return `<details class="cites"><summary>📎 Sumber (${citations.length})</summary>` +
      `<ul class="reflist">${cited.map(citeLink).join("")}</ul></details>`;
  }
  return `<details class="cites" open><summary>📎 Sumber dikutip (${cited.length})</summary>` +
    `<ul class="reflist">${cited.map(citeLink).join("")}</ul></details>` +
    `<details class="cites uncited"><summary>Diambil, tidak dikutip (${uncited.length})</summary>` +
    `<ul class="reflist">${uncited.map(citeLink).join("")}</ul></details>`;
}

export function renderAnswerHtml(answer, citations) {
  return pillsForAnswer(answer, citations) + sourcesBlock(citations);
}
```

- [ ] **Step 4: Run to verify it passes**

Run: `node --test tests/js/citations.test.mjs`
Expected: 7 passing.

- [ ] **Step 5: Syntax check + commit**

```bash
node --check app/web/static/new/citations.js
git add app/web/static/new/citations.js tests/js/citations.test.mjs
git commit -m "feat(ui): citations.js cite-pills + cited/uncited split with node tests"
```

---

### Task 4: `history.js` — localStorage conversations (DOM-free, unit-tested)

**Files:**
- Create: `app/web/static/new/history.js`
- Create: `tests/js/history.test.mjs`

`makeHistory(storage)` takes any object with `getItem(k)`/`setItem(k,v)` (browser `localStorage` in prod, a fake in tests). State is one JSON array under `libeka.conversations`. Conversation shape: `{id, title, scope, messages:[{q, a, citations}], updatedAt}`. IDs and timestamps are passed in by callers (so the module stays deterministic and testable — no `Date.now()` inside).

- [ ] **Step 1: Write the failing test** — create `tests/js/history.test.mjs`:

```javascript
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { makeHistory } from '../../app/web/static/new/history.js';

function fakeStorage() {
  const m = new Map();
  return { getItem: k => (m.has(k) ? m.get(k) : null), setItem: (k, v) => m.set(k, String(v)) };
}

test('starts empty', () => {
  const h = makeHistory(fakeStorage());
  assert.deepEqual(h.list(), []);
});

test('save then list returns newest-first', () => {
  const h = makeHistory(fakeStorage());
  h.save({ id: 'a', title: 'first', scope: 'global', messages: [], updatedAt: 1 });
  h.save({ id: 'b', title: 'second', scope: 'global', messages: [], updatedAt: 2 });
  assert.deepEqual(h.list().map(c => c.id), ['b', 'a']);
});

test('save with existing id updates in place', () => {
  const h = makeHistory(fakeStorage());
  h.save({ id: 'a', title: 't', scope: 'global', messages: [], updatedAt: 1 });
  h.save({ id: 'a', title: 't', scope: 'global', messages: [{ q: 'x', a: 'y', citations: [] }], updatedAt: 3 });
  assert.equal(h.list().length, 1);
  assert.equal(h.get('a').messages.length, 1);
});

test('remove deletes by id', () => {
  const h = makeHistory(fakeStorage());
  h.save({ id: 'a', title: 't', scope: 'global', messages: [], updatedAt: 1 });
  h.remove('a');
  assert.deepEqual(h.list(), []);
});

test('persists across instances sharing storage', () => {
  const s = fakeStorage();
  makeHistory(s).save({ id: 'a', title: 't', scope: 'global', messages: [], updatedAt: 1 });
  assert.equal(makeHistory(s).list().length, 1);
});

test('tolerates corrupt storage value', () => {
  const s = fakeStorage();
  s.setItem('libeka.conversations', 'not json');
  assert.deepEqual(makeHistory(s).list(), []);
});
```

- [ ] **Step 2: Run to verify it fails**

Run: `node --test tests/js/history.test.mjs`
Expected: FAIL — exports missing.

- [ ] **Step 3: Create** `app/web/static/new/history.js`:

```javascript
// Conversation history in localStorage. DOM-free; storage is injected so it is
// unit-testable. Callers pass id/updatedAt (no Date.now() inside => deterministic).

const KEY = "libeka.conversations";

export function makeHistory(storage) {
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
      return readAll().find(c => c.id === id) || null;
    },
    save(conv) {
      const arr = readAll().filter(c => c.id !== conv.id);
      arr.push(conv);
      writeAll(arr);
    },
    remove(id) {
      writeAll(readAll().filter(c => c.id !== id));
    },
  };
}
```

- [ ] **Step 4: Run to verify it passes**

Run: `node --test tests/js/history.test.mjs`
Expected: 6 passing.

- [ ] **Step 5: Syntax check + commit**

```bash
node --check app/web/static/new/history.js
git add app/web/static/new/history.js tests/js/history.test.mjs
git commit -m "feat(ui): history.js localStorage conversations with node tests"
```

---

### Task 5: `splash.js` — first-visit flag (DOM-free logic, unit-tested) + mount

**Files:**
- Create: `app/web/static/new/splash.js`
- Create: `tests/js/splash.test.mjs`

`shouldShowSplash(storage)` / `markSplashSeen(storage)` use flag `libeka.splashSeen`. `mountSplash(doc, storage)` wires the three dismiss controls (`#splash-close`, `#splash-enter`, `#splash-skip`) to hide `#splash` and set the flag; it shows `#splash` only when `shouldShowSplash` is true. The DOM-free flag functions are unit-tested; `mountSplash` is verified manually.

- [ ] **Step 1: Write the failing test** — create `tests/js/splash.test.mjs`:

```javascript
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { shouldShowSplash, markSplashSeen } from '../../app/web/static/new/splash.js';

function fakeStorage() {
  const m = new Map();
  return { getItem: k => (m.has(k) ? m.get(k) : null), setItem: (k, v) => m.set(k, String(v)) };
}

test('shows on first visit', () => {
  assert.equal(shouldShowSplash(fakeStorage()), true);
});

test('hidden after marked seen', () => {
  const s = fakeStorage();
  markSplashSeen(s);
  assert.equal(shouldShowSplash(s), false);
});
```

- [ ] **Step 2: Run to verify it fails**

Run: `node --test tests/js/splash.test.mjs`
Expected: FAIL — exports missing.

- [ ] **Step 3: Create** `app/web/static/new/splash.js`:

```javascript
// First-visit splash. Flag logic is DOM-free + tested; mountSplash wires the DOM.

const FLAG = "libeka.splashSeen";

export function shouldShowSplash(storage) {
  return storage.getItem(FLAG) !== "1";
}

export function markSplashSeen(storage) {
  storage.setItem(FLAG, "1");
}

export function mountSplash(doc, storage) {
  const el = doc.getElementById("splash");
  if (!el) return;
  if (!shouldShowSplash(storage)) {
    el.hidden = true;
    return;
  }
  el.hidden = false;
  const dismiss = () => {
    markSplashSeen(storage);
    el.hidden = true;
  };
  ["splash-close", "splash-enter", "splash-skip"].forEach(id => {
    const b = doc.getElementById(id);
    if (b) b.addEventListener("click", dismiss);
  });
}
```

- [ ] **Step 4: Run to verify it passes**

Run: `node --test tests/js/splash.test.mjs`
Expected: 2 passing.

- [ ] **Step 5: Syntax check + commit**

```bash
node --check app/web/static/new/splash.js
git add app/web/static/new/splash.js tests/js/splash.test.mjs
git commit -m "feat(ui): splash.js first-visit flag with node tests"
```

---

### Task 6: `new.css` — design tokens + layout + splash/EKG animation

**Files:**
- Create: `app/web/static/new/new.css`

No automated test (pure CSS). Verified visually in Task 9. Tokens and the EKG accent (`--accent:#D97706`) come straight from the spec.

- [ ] **Step 1: Create** `app/web/static/new/new.css`:

```css
*,*::before,*::after{box-sizing:border-box;margin:0;padding:0}
:root{
  --bg:#F9FAFB;--surface:#FFFFFF;--user-bubble:#F1F5F9;
  --text:#0F172A;--text2:#475569;--text3:#64748B;
  --brand:#0369A1;--brand-hover:#075985;--brand-subtle:#E0F2FE;
  --border:#E2E8F0;--border-strong:#CBD5E1;
  --accent:#D97706; /* Amber 600 — splash EKG only */
  --radius:12px;--shadow:0 8px 30px rgba(15,23,42,.05);
}
html,body{height:100%;font-family:'Inter',system-ui,sans-serif;background:var(--bg);color:var(--text);font-size:15px;line-height:1.6}
body{overflow:hidden}
a{color:var(--brand);text-decoration:none}
button,textarea{font:inherit}

.app{display:flex;height:100dvh;min-height:100vh;overflow:hidden;background:linear-gradient(180deg,#FCFDFE 0%,#F8FAFC 100%)}

/* sidebar */
.sidebar{width:248px;background:rgba(255,255,255,.9);backdrop-filter:blur(18px);border-right:1px solid var(--border);display:flex;flex-direction:column;padding:18px 14px;flex-shrink:0}
.brand{font-weight:700;font-size:17px;color:var(--brand);margin-bottom:18px;display:flex;align-items:center;gap:8px}
.brand svg{width:24px;height:24px}
.nav{display:flex;flex-direction:column;gap:2px;margin-bottom:8px}
.nav-item{display:flex;align-items:center;gap:9px;padding:9px 11px;border-radius:9px;cursor:pointer;font-size:14px;color:var(--text2);border:none;background:none;text-align:left;transition:.15s}
.nav-item.active{background:var(--brand-subtle);color:var(--brand);font-weight:600}
.nav-item:hover:not(.active){background:#F1F5F9}
.side-body{flex:1;overflow-y:auto;min-height:0;margin-top:8px}
.side-btn{display:flex;align-items:center;gap:8px;width:100%;padding:9px 11px;border-radius:9px;cursor:pointer;font-size:13px;color:var(--text2);border:1px solid var(--border);background:#fff;margin:6px 0;transition:.15s}
.side-btn:hover{background:var(--brand-subtle);color:var(--brand);border-color:#BAE6FD}
.side-label{font-size:10.5px;font-weight:600;text-transform:uppercase;letter-spacing:.05em;color:var(--text3);padding:0 11px;margin:12px 0 6px}
.hist{padding:7px 11px;border-radius:7px;cursor:pointer;font-size:13px;color:var(--text2);white-space:nowrap;overflow:hidden;text-overflow:ellipsis;display:flex;justify-content:space-between;gap:6px;align-items:center}
.hist:hover{background:var(--brand-subtle);color:var(--brand)}
.hist.active{background:var(--brand-subtle);color:var(--brand);font-weight:500}
.hist .del{opacity:0;border:none;background:none;cursor:pointer;color:var(--text3);font-size:14px}
.hist:hover .del{opacity:1}
.side-foot{margin-top:auto;font-size:11px;color:var(--text3);padding-top:14px;border-top:1px solid var(--border);line-height:1.9}
.side-foot a{color:var(--text2)}
.side-foot a:hover{color:var(--brand)}

/* main + views */
.main{flex:1;display:flex;flex-direction:column;min-width:0}
.view{flex:1;display:flex;flex-direction:column;min-height:0}
.view[hidden]{display:none}

/* chat */
.scroll{flex:1;overflow-y:auto;padding:24px 0 0}
.inner{max-width:760px;margin:0 auto;padding:0 24px 24px;width:100%}
.msg{margin-bottom:22px}
.msg-u{display:flex;justify-content:flex-end}
.msg-u .bub{background:var(--user-bubble);border:1px solid rgba(148,163,184,.12);border-radius:18px 18px 6px 18px;padding:11px 17px;max-width:75%;box-shadow:var(--shadow)}
.msg-a .ai{background:var(--surface);border:1px solid var(--border);border-radius:16px;padding:18px 22px;box-shadow:var(--shadow)}
.msg-a .ai h1,.msg-a .ai h2,.msg-a .ai h3{font-family:'Merriweather',serif;margin:14px 0 6px}
.pill{display:inline-flex;align-items:center;background:var(--brand-subtle);color:var(--brand);font-family:'Fira Code',monospace;font-size:10px;padding:1px 6px;border-radius:99px;font-weight:600;vertical-align:super;margin:0 1px;cursor:pointer;transition:.15s;text-decoration:none}
.pill:hover{background:var(--brand);color:#fff}
.cites{margin-top:12px}
.cites>summary{cursor:pointer;color:var(--text3);font-size:12.5px;list-style:none;font-weight:500}
.cites>summary::-webkit-details-marker{display:none}
.cites.uncited>summary{font-style:italic;opacity:.72}
.reflist{list-style:none;margin-top:8px;font-size:12.5px}
.reflist li{padding:4px 0;color:var(--text2)}
.nudge{margin-top:12px;font-size:12.5px;color:var(--text2);background:#F8FAFC;border:1px solid var(--border);border-radius:10px;padding:9px 12px}
.nudge button{font-size:12px;border:1px solid #BAE6FD;background:#fff;color:var(--brand);border-radius:99px;padding:2px 9px;cursor:pointer;margin:2px}

/* input */
.input{border-top:1px solid var(--border);background:rgba(255,255,255,.95);backdrop-filter:blur(18px);padding:14px 24px}
.input-in{max-width:760px;margin:0 auto;display:flex;gap:10px;align-items:flex-end}
.input-in textarea{flex:1;resize:none;border:1px solid var(--border);border-radius:16px;padding:11px 15px;font-size:14px;background:var(--bg);outline:none;min-height:46px;max-height:180px}
.input-in textarea:focus{border-color:var(--brand);box-shadow:0 0 0 4px rgba(14,165,233,.12)}
.send{width:46px;height:46px;border-radius:14px;background:var(--brand);color:#fff;border:none;cursor:pointer;display:flex;align-items:center;justify-content:center;flex-shrink:0}
.send:hover{background:var(--brand-hover)}
.send svg{width:19px;height:19px}

/* empty state */
.empty{display:flex;flex-direction:column;align-items:center;justify-content:center;height:100%;text-align:center;padding:30px 24px}
.empty h1{font-family:'Merriweather',serif;font-size:1.7em;margin-bottom:8px}
.empty p{color:var(--text2);max-width:480px;margin-bottom:26px}
.eg{display:grid;grid-template-columns:1fr 1fr;gap:10px;max-width:560px;width:100%}
.ecard{background:var(--surface);border:1px solid var(--border);border-radius:14px;padding:13px 15px;cursor:pointer;text-align:left;font-size:13px;color:var(--text2);box-shadow:var(--shadow);transition:.15s}
.ecard:hover{border-color:#7DD3FC;color:var(--brand);background:#F8FCFF}

/* projects */
.proj-head{padding:22px 24px 0;max-width:900px;margin:0 auto;width:100%}
.proj-title{font-family:'Merriweather',serif;font-size:1.5em;margin-bottom:3px}
.proj-sub{color:var(--text2);font-size:13.5px;margin-bottom:16px}
.tabs{display:flex;gap:4px;border-bottom:1px solid var(--border)}
.tab{padding:8px 15px;border-radius:8px 8px 0 0;cursor:pointer;font-size:13.5px;color:var(--text3);font-weight:500;border:none;background:none}
.tab.active{background:var(--brand-subtle);color:var(--brand);font-weight:600}
.panel{max-width:900px;margin:16px auto 0;padding:0 24px;width:100%}
.panel[hidden]{display:none}
table.matrix{width:100%;border-collapse:collapse;font-size:12.5px;background:#fff;border:1px solid var(--border);border-radius:10px;overflow:hidden}
table.matrix th,table.matrix td{border:1px solid var(--border);padding:8px 11px;text-align:left;vertical-align:top}
table.matrix th{background:var(--brand-subtle);font-weight:600}
.gap{color:var(--text3);font-style:italic}
.row-btn{font-size:12.5px;border:1px solid var(--border);background:#fff;color:var(--text2);padding:7px 13px;border-radius:8px;cursor:pointer;margin-right:8px}
.row-btn:hover{border-color:#7DD3FC;color:var(--brand)}
.paper-item{display:flex;justify-content:space-between;align-items:center;padding:9px 12px;border:1px solid var(--border);border-radius:10px;background:#fff;margin-bottom:7px;font-size:13.5px}

/* splash */
.splash{position:fixed;inset:0;z-index:1000;display:flex;flex-direction:column;align-items:center;justify-content:center;text-align:center;padding:40px;background:radial-gradient(1200px 600px at 50% 35%,rgba(224,242,254,.6),rgba(249,250,251,.96) 70%);backdrop-filter:blur(6px)}
.splash[hidden]{display:none}
.splash-close{position:absolute;top:18px;right:20px;width:34px;height:34px;border-radius:10px;border:1px solid var(--border);background:#fff;color:var(--text2);cursor:pointer;font-size:18px}
.splash-close:hover{background:var(--brand-subtle);color:var(--brand);border-color:#BAE6FD}
.splash-logo{display:flex;align-items:center;gap:12px;margin-bottom:22px;animation:rise .6s ease both}
.splash-logo svg{width:46px;height:46px;color:var(--brand)}
.splash-logo span{font-weight:700;font-size:30px;color:var(--brand);letter-spacing:-.5px}
.splash-title{font-family:'Merriweather',serif;font-size:34px;line-height:1.25;max-width:680px;margin-bottom:14px;animation:rise .6s .08s ease both}
.splash-title span{color:var(--brand)}
.splash-sub{color:var(--text2);font-size:16px;max-width:540px;margin-bottom:30px;animation:rise .6s .16s ease both}
.splash-ekg{width:min(560px,86%);height:90px;margin-bottom:34px;animation:rise .6s .24s ease both}
.splash-ekg svg{width:100%;height:100%;overflow:visible}
.ekg-line{fill:none;stroke:var(--accent);stroke-width:2.4;stroke-linecap:round;stroke-linejoin:round;stroke-dasharray:1600;stroke-dashoffset:1600;animation:draw 2.6s linear infinite}
.ekg-glow{fill:none;stroke:var(--accent);stroke-width:6;opacity:.18;filter:blur(3px);stroke-dasharray:1600;stroke-dashoffset:1600;animation:draw 2.6s linear infinite}
.splash-enter{font-weight:600;font-size:15px;background:var(--brand);color:#fff;border:none;border-radius:14px;padding:13px 30px;cursor:pointer;box-shadow:var(--shadow);transition:.15s;animation:rise .6s .32s ease both}
.splash-enter:hover{background:var(--brand-hover);transform:translateY(-1px)}
.splash-skip{display:block;margin-top:14px;font-size:12.5px;color:var(--text3);cursor:pointer;background:none;border:none;animation:rise .6s .4s ease both}
.splash-skip:hover{color:var(--brand)}
@keyframes draw{to{stroke-dashoffset:0}}
@keyframes rise{from{opacity:0;transform:translateY(14px)}to{opacity:1;transform:none}}
@media (prefers-reduced-motion: reduce){
  .ekg-line,.ekg-glow{stroke-dashoffset:0;animation:none}
  .splash-logo,.splash-title,.splash-sub,.splash-ekg,.splash-enter,.splash-skip{animation:none}
}

/* responsive */
@media (max-width:768px){
  body{overflow:auto}
  .sidebar{display:none}
  .inner,.input-in,.proj-head,.panel{padding-left:16px;padding-right:16px}
  .eg{grid-template-columns:1fr}
  .splash-title{font-size:26px}
}
```

- [ ] **Step 2: Syntax sanity** — confirm the file has balanced braces:

Run: `node -e "const c=require('fs').readFileSync('app/web/static/new/new.css','utf8');const o=(c.match(/{/g)||[]).length,x=(c.match(/}/g)||[]).length;if(o!==x)throw new Error('brace mismatch '+o+' vs '+x);console.log('braces ok',o)"`
Expected: `braces ok <n>`

- [ ] **Step 3: Commit**

```bash
git add app/web/static/new/new.css
git commit -m "feat(ui): new.css design tokens, layout, splash EKG animation"
```

---

### Task 7: `chat.js` — chat surface (DOM; manual verify)

**Files:**
- Create: `app/web/static/new/chat.js`

Renders a chat surface into a container. Used by both the global Chat view and (later, Task 8) the in-project "Chat proyek" tab. Configurable via an options object: where to POST, whether to render the nudge, and a hook to persist history. Enter sends, Shift+Enter inserts newline (preserve behavior from commit `c03508c`).

- [ ] **Step 1: Create** `app/web/static/new/chat.js`:

```javascript
// Chat surface. mountChat(container, opts) renders an empty state + thread + input.
// opts: { endpoint(question)->Promise(result), examples:[string], showNudge:bool,
//         initial:[{q,a,citations}], onExchange(messages), onAddPaper(docId) }
// Keeps an internal messages[] log; calls onExchange(messages) after each answer
// so the caller (main.js) can persist the whole conversation to history.
import { escapeHtml } from "./api.js";
import { renderAnswerHtml } from "./citations.js";

const DEFAULT_EXAMPLES = [
  "Apa temuan utama lintas paper tentang topik X?",
  "Bandingkan metode di dua studi terbaru.",
  "Ringkas bukti untuk klaim Y dengan sitasi.",
  "Apa keterbatasan yang disebut penulis?",
];

export function mountChat(container, opts) {
  const examples = opts.examples || DEFAULT_EXAMPLES;
  container.innerHTML = `
    <div class="scroll"><div class="inner" id="thread">
      <div class="empty" id="empty">
        <h1>library-eka</h1>
        <p>Tanya apa saja ke korpusmu. Jawaban presisi dengan sitasi klik-ke-halaman.</p>
        <div class="eg">${examples.map(e => `<button class="ecard" type="button">${escapeHtml(e)}</button>`).join("")}</div>
      </div>
    </div></div>
    <div class="input"><div class="input-in">
      <textarea id="q" rows="1" placeholder="Tanya korpus… (Enter kirim · Shift+Enter baris baru)"></textarea>
      <button class="send" id="send" type="button" aria-label="Kirim">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="22" y1="2" x2="11" y2="13"/><polygon points="22 2 15 22 11 13 2 9 22 2"/></svg>
      </button>
    </div></div>`;

  const thread = container.querySelector("#thread");
  let empty = container.querySelector("#empty");
  const ta = container.querySelector("#q");
  const send = container.querySelector("#send");
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
    return `<div class="nudge">${nudge.length} paper lain mungkin relevan: ` +
      nudge.map(n => `<button data-add="${n.doc_id}" type="button">+ ${escapeHtml(n.title || "(untitled)")}</button>`).join("") +
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
      const res = await opts.endpoint(q);
      pending.innerHTML = renderAnswerHtml(res.answer, res.citations) + nudgeHtml(res.nudge);
      pending.querySelectorAll("button[data-add]").forEach(b =>
        b.addEventListener("click", () => { opts.onAddPaper && opts.onAddPaper(Number(b.dataset.add)); b.remove(); }));
      messages.push({ q, a: res.answer, citations: res.citations || [] });
      if (opts.onExchange) opts.onExchange(messages);
    } catch (err) {
      pending.textContent = "Error: " + err.message;
    }
    const sc = container.querySelector(".scroll");
    sc.scrollTop = sc.scrollHeight;
  }

  // Replay a saved conversation, if provided.
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

- [ ] **Step 2: Syntax check**

Run: `node --check app/web/static/new/chat.js`
Expected: no output (valid).

- [ ] **Step 3: Commit**

```bash
git add app/web/static/new/chat.js
git commit -m "feat(ui): chat.js chat surface (Enter-send, cite-pills, nudge)"
```

---

### Task 8: `projects.js` — Projects view (DOM; manual verify)

**Files:**
- Create: `app/web/static/new/projects.js`

Renders the Projects sidebar list and the per-project workspace (header + tabs Papers / Matrix / Chat proyek / Export). Reuses `mountChat` for the scoped chat tab. Matrix cells render `{text}` objects as their text and plain strings directly; gap strings get a muted class.

- [ ] **Step 1: Create** `app/web/static/new/projects.js`:

```javascript
// Projects view. mountProjects(viewEl, sideListEl, deps) renders the project list
// into the sidebar and a workspace into the main view.
import { escapeHtml, getJSON, postJSON } from "./api.js";
import { mountChat } from "./chat.js";

function cell(v) {
  const text = (v && typeof v === "object") ? (v.text ?? "") : (v ?? "");
  const s = String(text);
  const gap = /tidak disebutkan|tidak dilaporkan|tidak ada paper/i.test(s);
  return `<td${gap ? ' class="gap"' : ""}>${escapeHtml(s)}</td>`;
}

function matrixTable(res) {
  const rows = res.rows || [];
  if (!rows.length) return `<p class="gap">Belum ada hasil. Klik "Bangun matrix".</p>`;
  const cols = res.columns || Object.keys(rows[0].fields || {});
  return `<table class="matrix"><thead><tr><th>Source</th><th>Tahun</th><th>Skema</th>` +
    cols.map(c => `<th>${escapeHtml(c)}</th>`).join("") + `</tr></thead><tbody>` +
    rows.map(r => `<tr><td>${escapeHtml(r.source || "")}</td><td>${r.year || ""}</td><td>${escapeHtml(r.schema || "")}</td>` +
      cols.map(c => cell((r.fields || {})[c])).join("") + `</tr>`).join("") +
    `</tbody></table>`;
}

export function mountProjects(viewEl, sideListEl, deps) {
  let current = null;

  async function loadList() {
    const { projects } = await getJSON("/projects");
    sideListEl.innerHTML = projects.map(p =>
      `<div class="hist${current === p.id ? " active" : ""}" data-pid="${p.id}">${escapeHtml(p.name)}</div>`).join("")
      || `<div class="gap" style="padding:6px 11px">Belum ada proyek.</div>`;
    sideListEl.querySelectorAll("[data-pid]").forEach(el =>
      el.addEventListener("click", () => open(Number(el.dataset.pid))));
  }

  async function open(pid) {
    current = pid;
    deps.activateProjectsView();
    const p = await getJSON(`/projects/${pid}`);
    const papers = p.papers || [];
    viewEl.innerHTML = `
      <div class="proj-head">
        <div class="proj-title">${escapeHtml(p.name)}</div>
        <div class="proj-sub">${papers.length} papers</div>
        <div class="tabs">
          <button class="tab active" data-tab="papers" type="button">Papers</button>
          <button class="tab" data-tab="matrix" type="button">Matrix</button>
          <button class="tab" data-tab="chat" type="button">Chat proyek</button>
          <button class="tab" data-tab="export" type="button">Export</button>
        </div>
      </div>
      <div class="panel" data-panel="papers">
        ${papers.map(d => `<div class="paper-item"><span>${escapeHtml(d.title || "(untitled)")} ${d.year ? "· " + d.year : ""}</span></div>`).join("") || `<p class="gap">Belum ada paper.</p>`}
      </div>
      <div class="panel" data-panel="matrix" hidden>
        <button class="row-btn" id="m-build" type="button">Bangun matrix</button>
        <select id="m-view"><option value="matrix">matrix</option><option value="linimasa">linimasa</option><option value="tema">tema</option></select>
        <div id="m-out" style="margin-top:12px"></div>
      </div>
      <div class="panel" data-panel="chat" hidden></div>
      <div class="panel" data-panel="export" hidden>
        <a class="row-btn" id="x-xlsx" target="_blank">⬇ export.xlsx</a>
        <a class="row-btn" id="x-csv" target="_blank">⬇ export.csv</a>
      </div>`;

    const panels = viewEl.querySelectorAll(".panel");
    viewEl.querySelectorAll(".tab").forEach(t =>
      t.addEventListener("click", () => {
        viewEl.querySelectorAll(".tab").forEach(x => x.classList.remove("active"));
        t.classList.add("active");
        panels.forEach(pn => { pn.hidden = pn.dataset.panel !== t.dataset.tab; });
      }));

    // chat tab (scoped)
    mountChat(viewEl.querySelector('[data-panel="chat"]'), {
      examples: [],
      showNudge: true,
      endpoint: q => postJSON(`/projects/${pid}/ask`, { question: q, expand: false }),
      onAddPaper: async docId => { await postJSON(`/projects/${pid}/papers`, { doc_ids: [docId] }); open(pid); },
    });

    // matrix tab
    const out = viewEl.querySelector("#m-out");
    const viewSel = viewEl.querySelector("#m-view");
    function exportLinks() {
      viewEl.querySelector("#x-xlsx").href = `/projects/${pid}/matrix/export.xlsx?view=${viewSel.value}`;
      viewEl.querySelector("#x-csv").href = `/projects/${pid}/matrix/export.csv?view=${viewSel.value}`;
    }
    viewEl.querySelector("#m-build").addEventListener("click", async () => {
      out.textContent = "Mengekstrak matriks (grounded)…";
      try { out.innerHTML = matrixTable(await postJSON(`/projects/${pid}/matrix`, { view: viewSel.value })); }
      catch (e) { out.textContent = "Error: " + e.message; }
      exportLinks();
    });
    viewSel.addEventListener("change", exportLinks);
    exportLinks();
  }

  async function createProject(name) {
    const p = await postJSON("/projects", { name });
    await loadList();
    open(p.id);
  }

  return { loadList, open, createProject };
}
```

- [ ] **Step 2: Syntax check**

Run: `node --check app/web/static/new/projects.js`
Expected: no output (valid).

- [ ] **Step 3: Commit**

```bash
git add app/web/static/new/projects.js
git commit -m "feat(ui): projects.js workspace (papers/matrix/scoped-chat/export)"
```

---

### Task 9: `main.js` — entry wiring + full manual verification

**Files:**
- Create: `app/web/static/new/main.js`

- [ ] **Step 1: Create** `app/web/static/new/main.js`:

```javascript
// Entry: splash, sidebar nav, view switching, mount chat + projects, history.
import { postJSON, escapeHtml } from "./api.js";
import { makeHistory } from "./history.js";
import { mountSplash } from "./splash.js";
import { mountChat } from "./chat.js";
import { mountProjects } from "./projects.js";

const history = makeHistory(window.localStorage);

mountSplash(document, window.localStorage);

const viewChat = document.getElementById("view-chat");
const viewProjects = document.getElementById("view-projects");
const chatSide = document.getElementById("chat-side");
const projectsSide = document.getElementById("projects-side");
const navChat = document.getElementById("nav-chat");
const navProjects = document.getElementById("nav-projects");
const recentList = document.getElementById("recent-list");

function showChat() {
  navChat.classList.add("active"); navProjects.classList.remove("active");
  viewChat.hidden = false; viewProjects.hidden = true;
  chatSide.hidden = false; projectsSide.hidden = true;
}
function showProjects() {
  navProjects.classList.add("active"); navChat.classList.remove("active");
  viewProjects.hidden = false; viewChat.hidden = true;
  projectsSide.hidden = false; chatSide.hidden = true;
}
navChat.addEventListener("click", showChat);
navProjects.addEventListener("click", showProjects);

// ----- global chat + localStorage history -----
let currentConvId = null;

function renderRecent() {
  const items = history.list();
  recentList.innerHTML = items.map(c =>
    `<div class="hist${c.id === currentConvId ? " active" : ""}" data-cid="${c.id}">` +
    `<span>${escapeHtml(c.title || "(tanpa judul)")}</span><button class="del" data-del="${c.id}" type="button" title="Hapus">✕</button></div>`
  ).join("") || `<div class="gap" style="padding:6px 11px">Belum ada percakapan.</div>`;
  recentList.querySelectorAll("[data-cid]").forEach(el =>
    el.addEventListener("click", e => {
      if (e.target.matches("[data-del]")) return;
      openConversation(el.dataset.cid);
    }));
  recentList.querySelectorAll("[data-del]").forEach(b =>
    b.addEventListener("click", () => {
      history.remove(b.dataset.del);
      if (currentConvId === b.dataset.del) newChat();
      else renderRecent();
    }));
}

function persist(messages) {
  if (!messages.length) return;
  history.save({
    id: currentConvId,
    title: messages[0].q.slice(0, 48),
    scope: "global",
    messages,
    updatedAt: Date.now(),
  });
  renderRecent();
}

function newChat() {
  currentConvId = "c" + Date.now();
  mountChat(viewChat, {
    showNudge: false,
    endpoint: q => postJSON("/ask", { question: q }),
    onExchange: persist,
  });
  renderRecent();
  showChat();
}

function openConversation(id) {
  const conv = history.get(id);
  if (!conv) return;
  currentConvId = id;
  mountChat(viewChat, {
    showNudge: false,
    initial: conv.messages,
    endpoint: q => postJSON("/ask", { question: q }),
    onExchange: persist,
  });
  renderRecent();
  showChat();
}

document.getElementById("new-conversation").addEventListener("click", newChat);

// ----- projects -----
const projects = mountProjects(viewProjects, document.getElementById("projects-list"), {
  activateProjectsView: showProjects,
});
projects.loadList();
document.getElementById("new-project").addEventListener("click", () => {
  const name = prompt("Nama proyek baru:");
  if (name && name.trim()) projects.createProject(name.trim());
});

// boot
newChat();
```

`Date.now()` lives only in `main.js` (browser) — never in the node-tested modules, which take `id`/`updatedAt` as arguments (Task 4). This keeps the unit tests deterministic while history still timestamps in the browser.

- [ ] **Step 2: Syntax check all modules**

Run: `for f in app/web/static/new/*.js; do node --check "$f" || echo "FAIL $f"; done`
Expected: no FAIL lines.

- [ ] **Step 3: Run all JS unit tests + full pytest**

Run: `node --test tests/js/ && venv/bin/python -m pytest tests/ -q`
Expected: all JS tests pass; pytest all PASS.

- [ ] **Step 4: Manual verification** — start the app and check the spec's acceptance list:

Run: `scripts/run.sh` then open `http://127.0.0.1:8765/new` (needs Ollama + an LLM key in `.env` for live answers).

Verify:
1. **Splash** shows on first load; the EKG line animates in Amber; clicking ✕ / "Enter the library →" / "Don't show again" closes it; reload → splash does NOT reappear. (To re-test: run `localStorage.removeItem('libeka.splashSeen')` in devtools.)
2. **Chat view** empty state shows example cards; clicking one sends. Typing + Enter sends; Shift+Enter adds a newline. Answer shows cite-pills; clicking a pill opens `/viewer?doc=…#page=…` in a new tab. 📎 sources block shows "Sumber dikutip (k)" + collapsed "Diambil, tidak dikutip (m)" when applicable.
   - **History:** after an answer, the conversation appears under "Recent" in the sidebar. Reload the page → click the Recent item → the conversation reloads its messages. "+ Percakapan baru" starts a fresh thread. The ✕ on a Recent item deletes it.
3. **Projects view** — nav switches sidebar to the Projects list. "+ Proyek baru" creates one and opens it. Tabs switch Papers / Matrix / Chat proyek / Export. Matrix "Bangun matrix" renders a table (gap cells muted). Export links carry the current view. Chat proyek answers and shows the nudge with "+ add" buttons.
4. **Mobile** — narrow the window < 768px: sidebar hides, layout stays usable.
5. **Legacy** — `http://127.0.0.1:8765/` still serves the old UI unchanged.

- [ ] **Step 5: Commit**

```bash
git add app/web/static/new/main.js
git commit -m "feat(ui): main.js entry wiring (splash, nav, chat, projects)"
```

---

## Self-review notes (for the implementer)

- **Spec coverage:** route `/new` (T1), tokens/fonts/layout (T6), two-workspace layout B (T1 shell + T9 nav + T8 workspace), citations pills + cited/uncited split (T3), localStorage history fully wired — module (T4) + Recent list render/open/delete (T9) + conversation replay (T7 `initial`), vanilla ES modules no build (all), splash first-visit + Amber EKG + reduced-motion (T1/T5/T6), parallel `/new` leaving `/` intact (T1 test `test_old_index_untouched`), book+EKG brand mark (T1 shell SVG). Draft/Mindmap/Library are linked from the sidebar footer (T1), not rebuilt — matches scope.
- **No backend state:** only `GET /new` added; everything else reuses existing endpoints. Confirmed against `routes.py` / `projects_routes.py`.
- **Testing reality:** pure modules (api, citations, history, splash-flag) have real `node:test` coverage; DOM modules (chat, projects, main) + CSS are manually verified — the repo has no browser test harness and the spec accepts manual verification for these.
```
