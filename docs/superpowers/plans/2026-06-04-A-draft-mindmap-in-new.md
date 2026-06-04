# Sub-project A — Draft + Mindmap in `/new` Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add Draft (Vancouver/APA paragraph with citations) and Mindmap (MarkMap) as views in the Grid `/new` UI, reusing the existing `/draft` and `/mindmap` endpoints — no backend change.

**Architecture:** Two new DOM ES modules (`draft.js`, `mindmap.js`) mounted by `main.js`; the sidebar nav grows to Chat · Projects · Draft · Mindmap. Draft reuses `citations.js` for cite-pills + cited/uncited references (the one library change: `pillsForAnswer` gains an optional marker-style arg so it also handles Vancouver `(n)`). Mindmap renders markdown via the markmap-autoloader CDN script.

**Tech Stack:** Vanilla ES modules, `node:test` (pure logic), pytest+TestClient (shell assertions), markmap-autoloader CDN.

**Spec:** `docs/superpowers/specs/2026-06-04-grid-ui-expansion-design.md` (Sub-project A)

## Backend contracts (already implemented — do NOT change)

- `POST /draft` `{topic, style, top_k?, year_min?, year_max?}` → `{paragraph, citations:[{n,doc_id,title,page_start,page_end,cited,...}], references:[str], style}`. Vancouver paragraph cites `(n)`; references[i] pairs with citations[i] by index; APA stays all-cited.
- `POST /mindmap` `{topic, breadth?, top_k?}` → `{markdown, citations, subtopics}`.
- markmap render pattern (from legacy `app.js`): build `<div class="markmap"><script type="text/template">…markdown…</script></div>`, append, then `if (window.markmap?.autoLoader) window.markmap.autoLoader.renderAll();`.

## Files

```
app/web/static/new/citations.js   # MODIFY: pillsForAnswer/renderAnswerHtml gain style arg ("square"|"paren")
tests/js/citations.test.mjs        # MODIFY: paren-style cases
app/web/static/new/draft.js        # CREATE: mountDraft(viewEl)
app/web/static/new/mindmap.js      # CREATE: mountMindmap(viewEl)
app/web/static/new/new.css         # MODIFY: form + markmap container styles
app/web/templates/new.html         # MODIFY: nav buttons, view sections, markmap script
app/web/static/new/main.js         # MODIFY: register + mount draft/mindmap views
tests/test_new_ui.py               # MODIFY: assert new nav/view ids + markmap script
```

---

### Task 1: `pillsForAnswer` supports Vancouver `(n)` markers

**Files:**
- Modify: `app/web/static/new/citations.js`
- Modify: `tests/js/citations.test.mjs`

Current `pillsForAnswer(answer, citations)` only replaces `[n]`. Add an optional `style` arg: `"square"` (default, `[n]`) or `"paren"` (`(n)`). `renderAnswerHtml` forwards it. Out-of-range numbers stay as text (existing behavior).

- [ ] **Step 1: Add failing tests** — append to `tests/js/citations.test.mjs`:

```javascript
test('pillsForAnswer paren style turns (n) into a pill', () => {
  const html = pillsForAnswer('Bukti efek (2).', cits, 'paren');
  assert.match(html, /class="pill"[^>]*href="\/viewer\?doc=11#page=5"/);
  assert.ok(!html.includes('(2)'), 'paren marker should be replaced');
});

test('pillsForAnswer paren leaves out-of-range (year) as text', () => {
  const html = pillsForAnswer('Menurut studi (2020).', cits, 'paren');
  assert.match(html, /\(2020\)/);
});

test('pillsForAnswer square is still the default', () => {
  const html = pillsForAnswer('Klaim [2].', cits);
  assert.match(html, /class="pill"/);
  assert.ok(!html.includes('(2)'));
});
```

(The existing `cits` fixture at the top of the file has n=1..3 with doc_id 10/11/12 — reuse it.)

- [ ] **Step 2: Run to verify it fails**

Run: `node --test tests/js/citations.test.mjs`
Expected: FAIL — `pillsForAnswer` ignores the 3rd arg, so `(2)` is not replaced.

- [ ] **Step 3: Implement** — in `app/web/static/new/citations.js` replace the `pillsForAnswer` function and the `renderAnswerHtml` function:

```javascript
// Replace [n] (square) or (n) (paren) markers in the (escaped) answer with pills.
export function pillsForAnswer(answer, citations, style = "square") {
  const byN = new Map(citations.map(c => [c.n, c]));
  const re = style === "paren" ? /\((\d+)\)/g : /\[(\d+)\]/g;
  return escapeHtml(answer).replace(re, (m, d) => {
    const c = byN.get(Number(d));
    if (!c) return m; // out-of-range marker: leave as text
    return `<a class="pill" href="${viewerHref(c)}" target="_blank" title="${escapeHtml(c.title)}">${c.n}</a>`;
  });
}
```

```javascript
export function renderAnswerHtml(answer, citations, style = "square") {
  return pillsForAnswer(answer, citations, style) + sourcesBlock(citations);
}
```

(`escapeHtml` runs before the regex, so `(` / `[` are untouched by escaping — the markers still match. Verified: `escapeHtml` only maps `&<>"'`.)

- [ ] **Step 4: Run to verify it passes**

Run: `node --test tests/js/citations.test.mjs`
Expected: all pass (the 7 existing + 3 new = 10).

- [ ] **Step 5: Confirm no other module breaks** — `chat.js` calls `renderAnswerHtml(answer, citations || [])` with 2 args; the new 3rd arg defaults to `"square"`, so chat is unchanged.

Run: `node --test tests/js/*.test.mjs`
Expected: all JS tests pass.

- [ ] **Step 6: Commit**

```bash
git add app/web/static/new/citations.js tests/js/citations.test.mjs
git commit -m "feat(ui): pillsForAnswer supports Vancouver (n) marker style"
```

---

### Task 2: `draft.js` — Draft view

**Files:**
- Create: `app/web/static/new/draft.js`

`mountDraft(viewEl)` renders a topic textarea + style select + submit. On submit, POST `/draft`, render the paragraph with cite-pills (paren style for Vancouver, square for APA), then a references list split into cited vs collapsed "Diambil, tidak dikutip" — built from `references[i]` paired with `citations[i].cited` (same index, as the backend guarantees).

- [ ] **Step 1: Create** `app/web/static/new/draft.js`:

```javascript
// Draft view: academic paragraph (Vancouver/APA) with cite-pills + split references.
import { escapeHtml, postJSON } from "./api.js";
import { pillsForAnswer } from "./citations.js";

export function mountDraft(viewEl) {
  viewEl.innerHTML = `
    <div class="scroll"><div class="inner">
      <form id="df-form" class="df-form">
        <textarea id="df-topic" rows="3" placeholder="Topik paragraf akademik…"></textarea>
        <div class="df-row">
          <select id="df-style">
            <option value="vancouver">Vancouver</option>
            <option value="apa">APA</option>
          </select>
          <button class="df-btn" id="df-submit" type="button">Tulis draft</button>
        </div>
      </form>
      <div id="df-paragraph" class="msg-a"></div>
      <div id="df-refs"></div>
    </div></div>`;

  const topic = viewEl.querySelector("#df-topic");
  const styleSel = viewEl.querySelector("#df-style");
  const para = viewEl.querySelector("#df-paragraph");
  const refsEl = viewEl.querySelector("#df-refs");

  function refsHtml(references, citations) {
    const cited = [], uncited = [];
    references.forEach((r, i) => {
      ((citations[i] && citations[i].cited === false) ? uncited : cited).push(r);
    });
    let html = `<div class="ref-title">Referensi</div>` +
      `<ol class="reflist">${cited.map(r => `<li>${escapeHtml(r)}</li>`).join("")}</ol>`;
    if (uncited.length) {
      html += `<details class="cites uncited"><summary>Diambil, tidak dikutip (${uncited.length})</summary>` +
        `<ol class="reflist">${uncited.map(r => `<li>${escapeHtml(r)}</li>`).join("")}</ol></details>`;
    }
    return html;
  }

  async function submit() {
    const t = topic.value.trim();
    if (!t) return;
    const style = styleSel.value;
    para.innerHTML = `<div class="ai">Menulis draft…</div>`;
    refsEl.innerHTML = "";
    try {
      const res = await postJSON("/draft", { topic: t, style });
      const markerStyle = style === "vancouver" ? "paren" : "square";
      para.innerHTML = `<div class="ai">${pillsForAnswer(res.paragraph, res.citations || [], markerStyle)}</div>`;
      refsEl.innerHTML = refsHtml(res.references || [], res.citations || []);
    } catch (err) {
      para.innerHTML = `<div class="ai">Error: ${escapeHtml(err.message)}</div>`;
    }
  }

  viewEl.querySelector("#df-submit").addEventListener("click", submit);
}
```

- [ ] **Step 2: Syntax check**

Run: `node --check app/web/static/new/draft.js`
Expected: no output.

- [ ] **Step 3: Commit**

```bash
git add app/web/static/new/draft.js
git commit -m "feat(ui): draft.js view (Vancouver/APA, cite-pills, split refs)"
```

---

### Task 3: `mindmap.js` — Mindmap view

**Files:**
- Create: `app/web/static/new/mindmap.js`

`mountMindmap(viewEl)` renders a topic textarea + breadth input + submit. On submit, POST `/mindmap`, show the raw markdown and render a MarkMap via the autoloader.

- [ ] **Step 1: Create** `app/web/static/new/mindmap.js`:

```javascript
// Mindmap view: MarkMap rendered from /mindmap markdown via the autoloader CDN.
import { postJSON } from "./api.js";

export function mountMindmap(viewEl) {
  viewEl.innerHTML = `
    <div class="scroll"><div class="inner">
      <form id="mm-form" class="df-form">
        <textarea id="mm-topic" rows="2" placeholder="Topik mindmap…"></textarea>
        <div class="df-row">
          <input id="mm-breadth" type="number" min="2" max="8" value="4" title="Jumlah subtopik" />
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

  async function submit() {
    const t = topic.value.trim();
    if (!t) return;
    md.textContent = "Menyusun mindmap…";
    svg.innerHTML = "";
    try {
      const res = await postJSON("/mindmap", { topic: t, breadth: Number(breadth.value) || 4 });
      md.textContent = res.markdown;
      const div = document.createElement("div");
      div.className = "markmap";
      const tpl = document.createElement("script");
      tpl.type = "text/template";
      tpl.textContent = res.markdown;
      div.appendChild(tpl);
      svg.appendChild(div);
      if (window.markmap && window.markmap.autoLoader) window.markmap.autoLoader.renderAll();
    } catch (err) {
      md.textContent = "Error: " + err.message;
    }
  }

  viewEl.querySelector("#mm-submit").addEventListener("click", submit);
}
```

(Markdown is rendered via `textContent`, which is XSS-safe — no `escapeHtml` needed here, so it is not imported.)

- [ ] **Step 2: Syntax check**

Run: `node --check app/web/static/new/mindmap.js`
Expected: no output.

- [ ] **Step 3: Commit**

```bash
git add app/web/static/new/mindmap.js
git commit -m "feat(ui): mindmap.js view (MarkMap via autoloader)"
```

---

### Task 4: Shell — nav buttons, view sections, markmap script

**Files:**
- Modify: `app/web/templates/new.html`

- [ ] **Step 1: Add the two nav buttons** — replace the `<nav class="nav">` block:

```html
    <nav class="nav">
      <button class="nav-item active" id="nav-chat" type="button">💬 Chat</button>
      <button class="nav-item" id="nav-projects" type="button">📁 Projects</button>
    </nav>
```

with:

```html
    <nav class="nav">
      <button class="nav-item active" id="nav-chat" type="button">💬 Chat</button>
      <button class="nav-item" id="nav-projects" type="button">📁 Projects</button>
      <button class="nav-item" id="nav-draft" type="button">📝 Draft</button>
      <button class="nav-item" id="nav-mindmap" type="button">🗺️ Mindmap</button>
    </nav>
```

- [ ] **Step 2: Add the two view sections** — replace:

```html
  <main class="main">
    <section class="view" id="view-chat"></section>
    <section class="view" id="view-projects" hidden></section>
  </main>
```

with:

```html
  <main class="main">
    <section class="view" id="view-chat"></section>
    <section class="view" id="view-projects" hidden></section>
    <section class="view" id="view-draft" hidden></section>
    <section class="view" id="view-mindmap" hidden></section>
  </main>
```

- [ ] **Step 3: Add the markmap autoloader script** — replace:

```html
<script type="module" src="/static/new/main.js"></script>
```

with:

```html
<script src="https://cdn.jsdelivr.net/npm/markmap-autoloader@0.16"></script>
<script type="module" src="/static/new/main.js"></script>
```

- [ ] **Step 4: Commit**

```bash
git add app/web/templates/new.html
git commit -m "feat(ui): /new shell adds Draft + Mindmap nav, views, markmap script"
```

---

### Task 5: `main.js` — register and mount the two views

**Files:**
- Modify: `app/web/static/new/main.js`

Add Draft/Mindmap to the nav switcher. They reuse the Chat sidebar body (Recent stays visible — the sidebar never goes blank). Mount each module once at boot (stateless forms).

- [ ] **Step 1: Add imports** — replace the import block at the top:

```javascript
import { postJSON, escapeHtml } from "./api.js";
import { makeHistory } from "./history.js";
import { mountSplash } from "./splash.js";
import { mountChat } from "./chat.js";
import { mountProjects } from "./projects.js";
```

with:

```javascript
import { postJSON, escapeHtml } from "./api.js";
import { makeHistory } from "./history.js";
import { mountSplash } from "./splash.js";
import { mountChat } from "./chat.js";
import { mountProjects } from "./projects.js";
import { mountDraft } from "./draft.js";
import { mountMindmap } from "./mindmap.js";
```

- [ ] **Step 2: Add element refs** — after the line `const recentList = document.getElementById("recent-list");` add:

```javascript
const viewDraft = document.getElementById("view-draft");
const viewMindmap = document.getElementById("view-mindmap");
const navDraft = document.getElementById("nav-draft");
const navMindmap = document.getElementById("nav-mindmap");
```

- [ ] **Step 3: Rewrite the view-switch helpers** — replace the existing `showChat` and `showProjects` functions and their two `addEventListener` lines:

```javascript
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
```

with:

```javascript
const NAVS = [navChat, navProjects, navDraft, navMindmap];
const VIEWS = [viewChat, viewProjects, viewDraft, viewMindmap];

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

navChat.addEventListener("click", showChat);
navProjects.addEventListener("click", showProjects);
navDraft.addEventListener("click", showDraft);
navMindmap.addEventListener("click", showMindmap);
```

- [ ] **Step 4: Mount the two modules at boot** — replace the final boot section:

```javascript
// boot
newChat();
```

with:

```javascript
// draft + mindmap (stateless, mounted once)
mountDraft(viewDraft);
mountMindmap(viewMindmap);

// boot
newChat();
```

- [ ] **Step 5: Syntax check all modules**

Run: `for f in app/web/static/new/*.js; do node --check "$f" || echo "FAIL $f"; done`
Expected: no FAIL lines.

- [ ] **Step 6: Commit**

```bash
git add app/web/static/new/main.js
git commit -m "feat(ui): main.js mounts and switches Draft + Mindmap views"
```

---

### Task 6: Styles for draft/mindmap forms + markmap container

**Files:**
- Modify: `app/web/static/new/new.css`

- [ ] **Step 1: Append to `app/web/static/new/new.css`:**

```css
/* draft + mindmap views */
.df-form{max-width:760px;margin:0 auto 16px;width:100%}
.df-form textarea{width:100%;resize:vertical;border:1px solid var(--border);border-radius:14px;padding:11px 15px;font-size:14px;background:var(--bg);outline:none}
.df-form textarea:focus{border-color:var(--brand);box-shadow:0 0 0 4px rgba(14,165,233,.12)}
.df-row{display:flex;gap:10px;align-items:center;margin-top:10px}
.df-row select,.df-row input{border:1px solid var(--border);border-radius:10px;padding:8px 12px;font-size:14px;background:#fff}
.df-btn{background:var(--brand);color:#fff;border:none;border-radius:12px;padding:10px 20px;cursor:pointer;font-weight:600}
.df-btn:hover{background:var(--brand-hover)}
#df-paragraph .ai,#df-paragraph{margin-bottom:14px}
.ref-title{font-weight:600;font-size:11px;text-transform:uppercase;letter-spacing:.05em;color:var(--text3);margin:8px 0 6px}
.md{white-space:pre-wrap;font-family:'Fira Code',monospace;font-size:12px;color:var(--text2);background:#F8FAFC;border:1px solid var(--border);border-radius:10px;padding:12px;max-height:200px;overflow:auto;margin-bottom:12px}
.markmap-wrap{height:75vh;border:1px solid var(--border);border-radius:12px;background:#fff}
.markmap-wrap svg{width:100%;height:100%}
```

- [ ] **Step 2: Brace-balance check**

Run: `node -e "const c=require('fs').readFileSync('app/web/static/new/new.css','utf8');const o=(c.match(/{/g)||[]).length,x=(c.match(/}/g)||[]).length;if(o!==x)throw new Error('brace mismatch '+o+' vs '+x);console.log('braces ok',o)"`
Expected: `braces ok <n>`.

- [ ] **Step 3: Commit**

```bash
git add app/web/static/new/new.css
git commit -m "feat(ui): styles for draft/mindmap forms + markmap container"
```

---

### Task 7: Shell assertions + full verification

**Files:**
- Modify: `tests/test_new_ui.py`

- [ ] **Step 1: Add a failing test** — append to `tests/test_new_ui.py`:

```python
def test_draft_mindmap_shell_present():
    html = _html()
    for el in (
        'id="nav-draft"', 'id="nav-mindmap"',
        'id="view-draft"', 'id="view-mindmap"',
        'markmap-autoloader',
    ):
        assert el in html, f"missing {el}"
```

- [ ] **Step 2: Run it**

Run: `venv/bin/python -m pytest tests/test_new_ui.py -v`
Expected: all pass (the new test + the existing 4).

- [ ] **Step 3: Full automated suite**

Run: `node --test tests/js/*.test.mjs && venv/bin/python -m pytest tests/ -q`
Expected: all JS tests pass; all pytest pass.

- [ ] **Step 4: Manual verification** — `scripts/run.sh`, open `http://127.0.0.1:8765/new` (needs Ollama + LLM key):
  1. Nav shows Chat · Projects · Draft · Mindmap; clicking switches the main view; the sidebar keeps showing Recent for Draft/Mindmap.
  2. Draft: enter a topic, Vancouver → paragraph shows `(n)` cite-pills (click → PDF page) + a "Referensi" list with a collapsed "Diambil, tidak dikutip" section. APA → renders without numeric pills, references listed.
  3. Mindmap: enter a topic → markdown shows + a MarkMap renders below.

- [ ] **Step 5: Commit**

```bash
git add tests/test_new_ui.py
git commit -m "test: assert Draft + Mindmap shell present in /new"
```

---

## Self-review notes

- **Spec coverage (A):** nav grows to Chat/Projects/Draft/Mindmap (T4/T5); draft.js with cite-pills + cited/uncited refs (T2, reusing T1's paren support); mindmap.js via autoloader (T3/T4); the single `citations.js` change with a node:test (T1); Library NOT added (out of scope). Backend unchanged (only existing `/draft`,`/mindmap` called).
- **Type consistency:** `pillsForAnswer(answer, citations, style="square")` and `renderAnswerHtml(answer, citations, style="square")` — chat.js still calls with 2 args (defaults hold); draft.js passes `"paren"`/`"square"`; mindmap imports only `postJSON`.
- **No placeholders:** every step has exact code/commands. The mindmap import note resolves to the exact final import line in T3 Step 2.
- **Sidebar-never-blank** decision implemented in `activate(...)` (Draft/Mindmap keep `chatSide` visible).
```
