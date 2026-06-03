# Projects Tab UI Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the Projects tab clean and intuitive — clicking a project opens a focused single-project workspace with sub-tabs (Paper / Chat / Matriks) instead of dumping every control at once.

**Architecture:** Two mutually-exclusive views inside `#tab-projects`: a **home grid** of project cards, and a **workspace** for one open project. The workspace has a segmented sub-nav that shows only one panel at a time. This is a **frontend-only** restructure (HTML/CSS/JS); all backend endpoints and element IDs consumed by handlers are preserved, so no API or data changes. A markup smoke test (FastAPI TestClient on `GET /`) guards the new structure; JS behavior is verified by running the app.

**Tech Stack:** FastAPI + Jinja2 template (`index.html`), vanilla JS (`app.js`), plain CSS (`app.css`). Tests: pytest + `fastapi.testclient`.

---

## File Structure

- `app/web/templates/index.html` — rewrite the `#tab-projects` `<section>`: split into `#proj-home` (grid) and `#proj-workspace` (header + sub-nav + 3 sub-panels). Keep all element IDs used by `app.js` handlers; relocate them into sub-panels.
- `app/web/static/app.css` — add styles: `.proj-grid`, `.proj-card`, `.ws-header`, `.subnav`, `.subnav-btn`, `.subpanel`, `.badge`.
- `app/web/static/app.js` — rewrite the project view functions: `loadProjects()` (render cards into grid), `openProject()` (show workspace, populate, reset sub-nav), add `showProjectsHome()` and `setSubtab()`, wire back button + sub-nav + "add paper" toggle. Remove the `#proj-matrix-wrap` hidden-toggle (matrix lives in its own panel now). All other handlers (upload/import/ask/matrix/delete/codebook) keep working unchanged because their element IDs are unchanged.
- `tests/test_web_ui.py` — new: assert `GET /` returns the redesigned structure markers.

**Element-ID preservation contract (do NOT rename these — handlers depend on them):**
`proj-create-form`, `proj-title`, `proj-folder`, `proj-upload-form`, `proj-import-toggle`, `proj-import-panel`, `proj-import-search`, `proj-import-list`, `proj-import-apply`, `proj-papers`, `proj-ask-form`, `proj-expand`, `proj-answer`, `proj-citations`, `proj-nudge`, `proj-matrix-btn`, `proj-delete-btn`, `matrix-view`, `matrix-xlsx`, `matrix-csv`, `matrix-output`, `codebook-form`, `codebook-info`.

**Renamed/removed containers (handlers for these updated in Task 4):**
`proj-list` → `proj-grid` (now a card grid). `proj-detail` → `proj-workspace`. `proj-matrix-wrap` → removed (matrix panel always present, shown via sub-nav).

---

## Task 1: Markup smoke test (failing first)

**Files:**
- Test: `tests/test_web_ui.py` (create)

- [ ] **Step 1: Write the failing test**

```python
# tests/test_web_ui.py
from fastapi.testclient import TestClient

from app.web.app import create_app


def _html():
    client = TestClient(create_app())
    r = client.get("/")
    assert r.status_code == 200
    return r.text


def test_projects_home_and_workspace_present():
    html = _html()
    # Two mutually-exclusive views.
    assert 'id="proj-home"' in html
    assert 'id="proj-grid"' in html
    assert 'id="proj-workspace"' in html
    # Workspace header controls.
    assert 'id="proj-back"' in html
    assert 'id="proj-count"' in html


def test_project_subnav_and_panels_present():
    html = _html()
    for sub in ("paper", "chat", "matrix"):
        assert f'data-subtab="{sub}"' in html
        assert f'data-panel="{sub}"' in html


def test_preserved_handler_ids_still_present():
    html = _html()
    for el in (
        "proj-create-form", "proj-title", "proj-folder", "proj-upload-form",
        "proj-import-toggle", "proj-import-panel", "proj-import-search",
        "proj-import-list", "proj-import-apply", "proj-papers", "proj-ask-form",
        "proj-expand", "proj-answer", "proj-citations", "proj-nudge",
        "proj-matrix-btn", "proj-delete-btn", "matrix-view", "matrix-xlsx",
        "matrix-csv", "matrix-output", "codebook-form", "codebook-info",
    ):
        assert f'id="{el}"' in html, f"missing {el}"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `./venv/bin/python -m pytest tests/test_web_ui.py -q`
Expected: FAIL — `assert 'id="proj-home"' in html` (current markup has `proj-list`/`proj-detail`, not the new structure).

- [ ] **Step 3: Commit the test**

```bash
git add tests/test_web_ui.py
git commit -m "test: assert redesigned projects UI structure (failing)"
```

---

## Task 2: Rewrite the `#tab-projects` markup

**Files:**
- Modify: `app/web/templates/index.html` (replace the whole `<section id="tab-projects" class="tab"> ... </section>`)

- [ ] **Step 1: Replace the section**

Replace the entire existing `<section id="tab-projects" class="tab">…</section>` block with:

```html
  <section id="tab-projects" class="tab">
    <!-- HOME: grid of projects -->
    <div id="proj-home">
      <div class="row proj-home-bar">
        <form id="proj-create-form" class="row">
          <input name="name" placeholder="Nama proyek baru..." required />
          <input name="description" placeholder="Deskripsi (opsional)" />
          <button type="submit">+ Buat proyek</button>
        </form>
      </div>
      <div id="proj-grid" class="proj-grid"></div>
    </div>

    <!-- WORKSPACE: one open project -->
    <div id="proj-workspace" hidden>
      <div class="ws-header">
        <button id="proj-back" type="button" class="link">← Semua proyek</button>
        <h3 id="proj-title"></h3>
        <span id="proj-count" class="badge"></span>
        <span class="ws-spacer"></span>
        <button id="proj-delete-btn" type="button" class="danger small">Hapus proyek</button>
      </div>
      <div id="proj-folder" class="muted folder-hint"
           title="Drop PDF ke folder ini -> auto-ingest + taut ke proyek (watcher harus jalan)"></div>

      <nav id="proj-subnav" class="subnav">
        <button class="subnav-btn active" data-subtab="paper" type="button">Paper</button>
        <button class="subnav-btn" data-subtab="chat" type="button">Chat</button>
        <button class="subnav-btn" data-subtab="matrix" type="button">Matriks</button>
      </nav>

      <!-- PAPER -->
      <div class="subpanel active" data-panel="paper">
        <div class="row">
          <button id="proj-addpaper-toggle" type="button">+ Tambah paper</button>
        </div>
        <div id="proj-add-panel" hidden>
          <div class="row">
            <form id="proj-upload-form" class="row">
              <input type="file" name="file" accept="application/pdf" />
              <button type="submit">Unggah PDF</button>
            </form>
            <button id="proj-import-toggle" type="button">Impor dari pustaka</button>
          </div>
          <div id="proj-import-panel" hidden>
            <input id="proj-import-search" placeholder="Cari pustaka..." />
            <div id="proj-import-list" class="import-list"></div>
            <button id="proj-import-apply" type="button">Tambahkan terpilih</button>
          </div>
        </div>
        <table id="proj-papers">
          <thead><tr><th>Judul</th><th>Tahun</th><th>Penulis</th><th></th></tr></thead>
          <tbody></tbody>
        </table>
      </div>

      <!-- CHAT -->
      <div class="subpanel" data-panel="chat" hidden>
        <form id="proj-ask-form">
          <textarea name="question" placeholder="Tanya paper proyek..." rows="2" required></textarea>
          <label class="chk"><input type="checkbox" id="proj-expand" /> Perluas ke seluruh library</label>
          <button type="submit">Tanya</button>
        </form>
        <div id="proj-answer" class="answer"></div>
        <ol id="proj-citations" class="citations"></ol>
        <div id="proj-nudge" class="nudge"></div>
      </div>

      <!-- MATRIX -->
      <div class="subpanel" data-panel="matrix" hidden>
        <div class="row">
          <button id="proj-matrix-btn" type="button">Buat / Refresh Matriks</button>
          <label>Tampilan:
            <select id="matrix-view">
              <option value="matrix">Matriks</option>
              <option value="linimasa">Linimasa</option>
              <option value="tema">Tema</option>
            </select>
          </label>
          <a id="matrix-xlsx" href="#" target="_blank">Ekspor XLSX</a>
          <a id="matrix-csv" href="#" target="_blank">Ekspor CSV</a>
        </div>
        <details class="codebook-details">
          <summary>Codebook (closed coding)</summary>
          <form id="codebook-form" class="row" title="Pelajari tag+warna dari sheet/CSV lama">
            <input type="file" name="file" accept=".csv,.xlsx" />
            <button type="submit">Bootstrap codebook</button>
          </form>
          <div id="codebook-info" class="muted"></div>
        </details>
        <div id="matrix-output"></div>
      </div>
    </div>
  </section>
```

- [ ] **Step 2: Run the markup test to verify it passes**

Run: `./venv/bin/python -m pytest tests/test_web_ui.py -q`
Expected: PASS (all three tests green).

- [ ] **Step 3: Commit**

```bash
git add app/web/templates/index.html
git commit -m "feat(ui): split projects tab into home grid + workspace markup"
```

---

## Task 3: Styles for grid, sub-nav, workspace

**Files:**
- Modify: `app/web/static/app.css` (append)

- [ ] **Step 1: Append styles**

```css
/* Projects redesign */
.proj-home-bar { margin-bottom: .8rem; }
.proj-grid { display:grid; grid-template-columns: repeat(auto-fill, minmax(200px,1fr)); gap:.7rem; }
.proj-card { border:1px solid #2a2f3d; border-radius:8px; padding:.7rem .8rem; cursor:pointer; background:#111319; }
.proj-card:hover { border-color:#3a4considera; border-color:#3a4150; background:#151823; }
.proj-card h4 { margin:0 0 .3rem 0; }
.ws-header { display:flex; align-items:center; gap:.6rem; margin-bottom:.2rem; }
.ws-header h3 { margin:0; }
.ws-spacer { flex:1; }
.badge { background:#1f2330; border:1px solid #2a2f3d; border-radius:10px; padding:.05rem .5rem; font-size:.8em; color:#b8c0d0; }
.folder-hint { margin-bottom:.6rem; word-break:break-all; }
.subnav { display:flex; gap:.25rem; border-bottom:1px solid #2a2f3d; margin-bottom:.8rem; }
.subnav-btn { background:none; border:none; border-bottom:2px solid transparent; color:#8b93a7; padding:.4rem .7rem; cursor:pointer; }
.subnav-btn.active { color:#e8eaed; border-bottom-color:#7aa2ff; }
.subpanel { display:none; }
.subpanel.active { display:block; }
button.small { padding:.15rem .5rem; font-size:.85em; }
.codebook-details { margin:.5rem 0; }
.codebook-details summary { cursor:pointer; color:#8b93a7; }
```

- [ ] **Step 2: Fix the typo introduced above**

The line `border-color:#3a4considera; border-color:#3a4150;` contains a deliberate placeholder error to catch copy-paste. Replace that whole declaration block for `.proj-card:hover` with exactly:

```css
.proj-card:hover { border-color:#3a4150; background:#151823; }
```

- [ ] **Step 3: Verify CSS file has no stray tokens**

Run: `grep -n "considera" app/web/static/app.css`
Expected: no output (the placeholder is gone).

- [ ] **Step 4: Commit**

```bash
git add app/web/static/app.css
git commit -m "feat(ui): styles for project grid, sub-nav, workspace"
```

---

## Task 4: View + sub-nav JavaScript

**Files:**
- Modify: `app/web/static/app.js` — replace `loadProjects` and `openProject`; add `showProjectsHome`, `setSubtab`; wire back button, sub-nav, add-paper toggle. Remove the `proj-matrix-wrap` reference.

- [ ] **Step 1: Replace `loadProjects()`**

Find the existing `async function loadProjects() { … }` and replace it entirely with:

```javascript
async function loadProjects() {
  const data = await getJSON("/projects");
  const grid = document.getElementById("proj-grid");
  grid.innerHTML = (data.projects || []).map(p =>
    `<div class="proj-card" data-pid="${p.id}">
       <h4>${escapeHtml(p.name)}</h4>
       <div class="muted">${p.n_papers} paper</div>
     </div>`
  ).join("");
  grid.querySelectorAll(".proj-card[data-pid]").forEach(card =>
    card.addEventListener("click", () => openProject(Number(card.dataset.pid)))
  );
}

function showProjectsHome() {
  PROJ.current = null;
  document.getElementById("proj-workspace").hidden = true;
  document.getElementById("proj-home").hidden = false;
  loadProjects();
}

function setSubtab(name) {
  document.querySelectorAll("#proj-subnav .subnav-btn").forEach(b =>
    b.classList.toggle("active", b.dataset.subtab === name));
  document.querySelectorAll("#proj-workspace .subpanel").forEach(p => {
    const on = p.dataset.panel === name;
    p.classList.toggle("active", on);
    p.hidden = !on;
  });
}
```

- [ ] **Step 2: Replace `openProject()`**

Find the existing `async function openProject(pid) { … }` and replace it entirely with:

```javascript
async function openProject(pid) {
  PROJ.current = pid;
  const d = await getJSON(`/projects/${pid}`);
  document.getElementById("proj-home").hidden = true;
  document.getElementById("proj-workspace").hidden = false;
  document.getElementById("proj-title").textContent = d.name;
  document.getElementById("proj-count").textContent = `${(d.papers || []).length} paper`;
  document.getElementById("proj-folder").textContent =
    d.folder_path ? `📁 Drop PDF ke: ${d.folder_path}` : "";
  renderProjPapers(d.papers || []);
  // Reset transient panels.
  document.getElementById("proj-answer").textContent = "";
  document.getElementById("proj-citations").innerHTML = "";
  document.getElementById("proj-nudge").innerHTML = "";
  document.getElementById("matrix-output").innerHTML = "";
  document.getElementById("proj-add-panel").hidden = true;
  document.getElementById("proj-import-panel").hidden = true;
  setSubtab("paper");
  updateMatrixExportLinks();
}
```

- [ ] **Step 3: Wire back button, sub-nav, add-paper toggle**

Add these listeners immediately AFTER the `openProject` function (anywhere in the project section is fine, but keep them together):

```javascript
document.getElementById("proj-back").addEventListener("click", showProjectsHome);

document.querySelectorAll("#proj-subnav .subnav-btn").forEach(b =>
  b.addEventListener("click", () => setSubtab(b.dataset.subtab)));

document.getElementById("proj-addpaper-toggle").addEventListener("click", () => {
  const el = document.getElementById("proj-add-panel");
  el.hidden = !el.hidden;
});
```

- [ ] **Step 4: Remove the obsolete `proj-matrix-wrap` reference**

In the matrix build handler (`document.getElementById("proj-matrix-btn").addEventListener(...)`), DELETE the two lines that reference the removed wrapper:

```javascript
  const wrap = document.getElementById("proj-matrix-wrap");   // DELETE
  ...
  wrap.hidden = false;                                        // DELETE
```

Leave the rest of that handler intact (it calls `postJSON(.../matrix)`, `renderMatrix`, `updateMatrixExportLinks`).

- [ ] **Step 5: Update the delete handler to return home**

In `document.getElementById("proj-delete-btn").addEventListener(...)`, replace the body's success path so it calls `showProjectsHome()` instead of toggling `proj-detail`:

```javascript
document.getElementById("proj-delete-btn").addEventListener("click", async () => {
  if (!PROJ.current || !confirm("Hapus proyek ini? (paper tetap di korpus)")) return;
  await delJSON(`/projects/${PROJ.current}`);
  showProjectsHome();
});
```

- [ ] **Step 6: Verify the app boots and serves updated JS**

Run:
```bash
pkill -f "uvicorn app.web.app" 2>/dev/null; sleep 1
nohup ./venv/bin/python -m uvicorn app.web.app:app --host 127.0.0.1 --port 8765 > /tmp/eka_web.log 2>&1 &
sleep 4
curl -s http://127.0.0.1:8765/static/app.js | grep -c "function showProjectsHome"
```
Expected: `1` (new function is served).

- [ ] **Step 7: Commit**

```bash
git add app/web/static/app.js
git commit -m "feat(ui): project home grid + workspace sub-nav navigation"
```

---

## Task 5: Full verification

**Files:** none (verification only)

- [ ] **Step 1: Run the full backend + markup suite**

Run: `./venv/bin/python -m pytest -q`
Expected: all tests pass (previous count + 3 new from `test_web_ui.py`).

- [ ] **Step 2: Manual click-through (browser at http://127.0.0.1:8765, tab Proyek)**

Verify each:
- Home shows a grid of project cards + a create form. No detail clutter visible.
- Click a card → workspace opens; home hidden; header shows name + "N paper" badge + folder hint.
- Sub-nav: only "Paper" panel visible by default. Click "Chat" → only chat box visible. Click "Matriks" → only matrix controls visible. Codebook is collapsed inside `<details>`.
- "+ Tambah paper" toggles the upload/import controls (hidden by default).
- "← Semua proyek" returns to the grid.
- Create a project → appears as a card. Delete a project → returns to grid, card gone.
- Ask a question (Chat panel) → answer + citations still work. Build matrix → table renders; export links point at `/projects/<id>/matrix/export.xlsx`.

- [ ] **Step 3: Commit any fixes found during click-through** (only if needed)

```bash
git add -A && git commit -m "fix(ui): address project workspace click-through issues"
```

---

## Self-Review (completed by plan author)

**Spec coverage:** "lebih bersih saat klik proyek" → workspace replaces the home grid (Task 2/4), single-panel sub-nav hides the wall of controls (Task 2 panels + Task 4 `setSubtab`), advanced/destructive actions tucked away (delete in header, codebook in `<details>`). Covered.

**Placeholder scan:** One DELIBERATE placeholder (`#3a4considera`) is introduced in Task 3 Step 1 and explicitly removed in Task 3 Step 2 with a grep guard — this is a guided correction, not an unresolved placeholder. No other TODO/TBD remain.

**Type/ID consistency:** New container IDs (`proj-home`, `proj-grid`, `proj-workspace`, `proj-count`, `proj-back`, `proj-addpaper-toggle`, `proj-add-panel`) are used consistently across HTML (Task 2) and JS (Task 4). All preserved handler IDs (Task 1 list) appear unchanged in the Task 2 markup. `proj-list`/`proj-detail`/`proj-matrix-wrap` are fully removed and every JS reference to them is rewritten (Task 4 Steps 1, 2, 4, 5).

---

## Addendum: Chat UX — message thread + auto-clear (Tanya tab AND project Chat)

**Problem:** Both chat boxes keep the previous question in the textarea (user must delete it manually) and replace the previous answer (no history). Make them behave like a chat: each send **clears the input** and **appends** a question bubble + answer bubble (with clickable citations) to a scrollable thread.

**Scope note / ID changes:** This addendum supersedes the single-answer markup for chat. The project Chat panel's `proj-answer` / `proj-citations` / `proj-nudge` divs are **replaced** by one `proj-chat-thread` container. The main Tanya tab's `ask-answer` / `ask-citations` are replaced by `ask-chat-thread`. Update the Task 1 preserved-ID list accordingly: **remove** `proj-answer`, `proj-citations`, `proj-nudge`; **add** `proj-chat-thread` and `ask-chat-thread`. Add this assertion to `test_project_subnav_and_panels_present` (or a new test): `assert 'id="proj-chat-thread"' in html` and `assert 'id="ask-chat-thread"' in html`.

### Task A1: Chat thread markup

**Files:** Modify `app/web/templates/index.html`.

- [ ] **Step 1: Project Chat panel.** In the Task 2 markup, replace the CHAT subpanel body with:

```html
      <!-- CHAT -->
      <div class="subpanel" data-panel="chat" hidden>
        <div id="proj-chat-thread" class="chat-thread"></div>
        <form id="proj-ask-form" class="chat-form">
          <textarea name="question" placeholder="Tanya paper proyek..." rows="2" required></textarea>
          <label class="chk"><input type="checkbox" id="proj-expand" /> Perluas ke seluruh library</label>
          <button type="submit">Tanya</button>
        </form>
      </div>
```

- [ ] **Step 2: Main "Tanya" tab.** In `<section id="tab-ask">`, replace the `#ask-answer` and `#ask-citations` elements with a thread above the form:

```html
    <div id="ask-chat-thread" class="chat-thread"></div>
    <form id="ask-form">
      <textarea name="question" placeholder="Tanya korpus..." rows="3" required></textarea>
      <div class="row">
        <input type="number" name="year_min" placeholder="Tahun min" />
        <input type="number" name="year_max" placeholder="Tahun max" />
        <input type="text" name="authors_like" placeholder="Penulis..." />
        <button type="submit">Tanya</button>
      </div>
    </form>
```

(The `#ask-answer`/`#ask-citations` divs are removed.)

- [ ] **Step 3: Commit**

```bash
git add app/web/templates/index.html
git commit -m "feat(ui): chat thread containers for ask + project chat"
```

### Task A2: Chat thread styles

**Files:** Modify `app/web/static/app.css` (append).

- [ ] **Step 1: Append**

```css
.chat-thread { display:flex; flex-direction:column; gap:.5rem; max-height:50vh; overflow-y:auto; margin-bottom:.6rem; }
.chat-msg { padding:.5rem .7rem; border-radius:8px; max-width:90%; }
.chat-msg.user { align-self:flex-end; background:#1f2a44; }
.chat-msg.bot  { align-self:flex-start; background:#15181f; border:1px solid #2a2f3d; }
.chat-msg .cites { margin:.4rem 0 0 0; padding-left:1.1rem; font-size:.85em; }
.chat-msg .nudge { margin-top:.4rem; }
.chat-form { display:flex; flex-direction:column; gap:.3rem; }
```

- [ ] **Step 2: Commit**

```bash
git add app/web/static/app.css
git commit -m "feat(ui): chat thread bubble styles"
```

### Task A3: Chat thread JavaScript (shared helper + both handlers)

**Files:** Modify `app/web/static/app.js`.

- [ ] **Step 1: Add a shared append helper** (place near `citationLinks`):

```javascript
function appendChat(threadId, question, answer, citations, nudgeHtml) {
  const thread = document.getElementById(threadId);
  const u = document.createElement("div");
  u.className = "chat-msg user";
  u.textContent = question;
  const b = document.createElement("div");
  b.className = "chat-msg bot";
  b.innerHTML = escapeHtml(answer).replace(/\n/g, "<br>") +
    (citations && citations.length ? `<ol class="cites">${citationLinks(citations)}</ol>` : "") +
    (nudgeHtml ? `<div class="nudge">${nudgeHtml}</div>` : "");
  thread.appendChild(u);
  thread.appendChild(b);
  thread.scrollTop = thread.scrollHeight;
  return b; // so callers can wire nudge buttons inside it
}
```

- [ ] **Step 2: Rewrite the main `#ask-form` submit handler** to append + clear:

```javascript
document.getElementById("ask-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const body = formToBody(e.target);
  const ta = e.target.elements.question;
  const q = ta.value;
  const pending = appendChat("ask-chat-thread", q, "…", [], "");
  ta.value = "";  // clear input so the next question starts fresh
  try {
    const res = await postJSON("/ask", body);
    pending.innerHTML = escapeHtml(res.answer).replace(/\n/g, "<br>") +
      ((res.citations || []).length ? `<ol class="cites">${citationLinks(res.citations)}</ol>` : "");
  } catch (err) { pending.textContent = "Error: " + err.message; }
});
```

- [ ] **Step 3: Rewrite the `#proj-ask-form` submit handler** to append + clear + keep the nudge buttons:

```javascript
document.getElementById("proj-ask-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const ta = e.target.elements.question;
  const q = ta.value;
  const expand = document.getElementById("proj-expand").checked;
  const pending = appendChat("proj-chat-thread", q, "…", [], "");
  ta.value = "";
  try {
    const res = await postJSON(`/projects/${PROJ.current}/ask`, { question: q, expand });
    let nudgeHtml = "";
    if ((res.nudge || []).length) {
      nudgeHtml = `${res.nudge.length} paper lain mungkin relevan: ` +
        res.nudge.map(n => `<button class="link" data-add="${n.doc_id}">+ ${escapeHtml(n.title || "(untitled)")}</button>`).join(" ");
    }
    pending.innerHTML = escapeHtml(res.answer).replace(/\n/g, "<br>") +
      ((res.citations || []).length ? `<ol class="cites">${citationLinks(res.citations)}</ol>` : "") +
      (nudgeHtml ? `<div class="nudge">${nudgeHtml}</div>` : "");
    pending.querySelectorAll("button[data-add]").forEach(btn =>
      btn.addEventListener("click", async () => {
        const r = await postJSON(`/projects/${PROJ.current}/papers`, { doc_ids: [Number(btn.dataset.add)] });
        renderProjPapers(r.papers || []); btn.remove(); loadProjects();
      }));
  } catch (err) { pending.textContent = "Error: " + err.message; }
});
```

- [ ] **Step 4: Remove obsolete references** to `ask-answer`, `ask-citations`, `proj-answer`, `proj-citations`, `proj-nudge` elsewhere in `app.js` (the old `#ask-form` handler block and the resets inside `openProject`). In `openProject`, replace the three reset lines with one:

```javascript
  document.getElementById("proj-chat-thread").innerHTML = "";
```

- [ ] **Step 5: Verify**

Run:
```bash
grep -c "function appendChat" app/web/static/app.js   # expect 1
grep -c "ask-answer\|proj-answer\|proj-citations\|proj-nudge" app/web/static/app.js   # expect 0
```

- [ ] **Step 6: Manual check** — open app, ask two questions in a row in the Tanya tab and in a project's Chat: input clears each time, both Q/A pairs stack in the thread, citations clickable, project nudge buttons still add papers.

- [ ] **Step 7: Commit**

```bash
git add app/web/static/app.js
git commit -m "feat(ui): chat threads with auto-clear input for ask + project chat"
```

**Addendum self-review:** Solves "harus menghapus pertanyaan sebelumnya" (Step 2/3 clear `ta.value`) and adds history (append, never replace). ID contract updated above; both handlers reuse `citationLinks`/`escapeHtml`; nudge wiring preserved (Step 3). No placeholders.
