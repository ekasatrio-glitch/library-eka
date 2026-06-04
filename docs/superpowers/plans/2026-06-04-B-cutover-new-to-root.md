# Sub-project B — Cutover `/new` → `/` Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the Grid UI the default at `/`, move the legacy 5-tab UI to `/tools`, and redirect `/new` → `/` so existing links survive.

**Architecture:** Pure routing change in `app/web/routes.py` plus two small template edits (sidebar footer + noscript link in `new.html`) and test updates that re-point legacy-UI assertions from `/` to `/tools`.

**Tech Stack:** FastAPI, Jinja2, pytest + Starlette TestClient.

**Spec:** `docs/superpowers/specs/2026-06-04-grid-ui-expansion-design.md` (Sub-project B). **Run AFTER Sub-project A.**

## Routing contract after cutover

| Route | Serves |
|---|---|
| `GET /` | Grid UI (`new.html`) |
| `GET /tools` | Legacy UI (`index.html`) — all five tabs |
| `GET /new` | 307 redirect → `/` |
| `GET /viewer`, `/pdf/{id}`, all API routes | unchanged |

## Current state (verified)

- `app/web/routes.py`: `GET /` renders `index.html`; `GET /new` renders `new.html`; `GET /viewer` renders `viewer.html`. Imports `from fastapi.responses import FileResponse, HTMLResponse, JSONResponse`.
- `tests/test_web_ui.py` `_html()` does `client.get("/")` and asserts legacy ids (`proj-home`, `tab`-style markup, etc.).
- `tests/test_new_ui.py` `_html()` does `client.get("/new")`; `test_old_index_untouched` asserts `GET /` is 200.
- `new.html` sidebar footer: `<a href="/#tab-draft">Draft ↗</a> · <a href="/#tab-mindmap">Mindmap ↗</a> · <a href="/#tab-library">Library ↗</a>`. noscript: `…pakai antarmuka lama di <a href="/">/</a>.`
- Starlette `TestClient` follows redirects by default, so `client.get("/new")` returns the final `/` body with status 200 unless `follow_redirects=False`.

## Files

```
app/web/routes.py          # MODIFY: / → new.html; + /tools → index.html; /new → redirect /
app/web/templates/new.html # MODIFY: footer (Library→/tools), noscript link (→/tools)
tests/test_web_ui.py       # MODIFY: _html() targets /tools
tests/test_new_ui.py       # MODIFY: shell at /; legacy-at-/tools test; /new redirect test
```

---

### Task 1: Re-point routes (`/` Grid, `/tools` legacy, `/new` redirect)

**Files:**
- Modify: `app/web/routes.py`
- Modify: `tests/test_new_ui.py`

- [ ] **Step 1: Write the failing tests** — edit `tests/test_new_ui.py`. Replace the whole file with:

```python
from fastapi.testclient import TestClient

from app.web.app import create_app


def _html():
    client = TestClient(create_app())
    r = client.get("/")
    assert r.status_code == 200
    return r.text


def test_root_renders_grid_shell():
    html = _html()
    assert "library-eka" in html
    assert '/static/new/main.js' in html


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


def test_draft_mindmap_shell_present():
    html = _html()
    for el in (
        'id="nav-draft"', 'id="nav-mindmap"',
        'id="view-draft"', 'id="view-mindmap"',
        'markmap-autoloader',
    ):
        assert el in html, f"missing {el}"


def test_legacy_served_at_tools():
    client = TestClient(create_app())
    r = client.get("/tools")
    assert r.status_code == 200
    assert 'id="tab-mindmap"' in r.text  # legacy markup lives at /tools now


def test_new_redirects_to_root():
    client = TestClient(create_app())
    r = client.get("/new", follow_redirects=False)
    assert r.status_code in (302, 307, 308)
    assert r.headers["location"] == "/"
```

(This file already had `test_draft_mindmap_shell_present` added in Sub-project A Task 7; keep it — the full-file replacement above includes it so the file is consistent.)

- [ ] **Step 2: Run to verify it fails**

Run: `venv/bin/python -m pytest tests/test_new_ui.py -v`
Expected: FAIL — `/` still serves legacy (no `main.js`), `/tools` is 404, `/new` returns 200 not a redirect.

- [ ] **Step 3: Edit `app/web/routes.py`.** Update the imports line:

```python
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
```
to:
```python
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse
```

Then replace the existing `index` and `viewer` route block:

```python
@router.get("/", response_class=HTMLResponse)
def index(request: Request):
    return templates.TemplateResponse(request, "index.html", {})


@router.get("/viewer", response_class=HTMLResponse)
def viewer(request: Request):
    return templates.TemplateResponse(request, "viewer.html", {})
```

with:

```python
@router.get("/", response_class=HTMLResponse)
def index(request: Request):
    # Grid UI is the default; legacy 5-tab UI moved to /tools.
    return templates.TemplateResponse(request, "new.html", {})


@router.get("/tools", response_class=HTMLResponse)
def tools(request: Request):
    return templates.TemplateResponse(request, "index.html", {})


@router.get("/new")
def new_redirect():
    return RedirectResponse("/")


@router.get("/viewer", response_class=HTMLResponse)
def viewer(request: Request):
    return templates.TemplateResponse(request, "viewer.html", {})
```

(If the existing `GET /new` route lives elsewhere in the file — it was added earlier as `new_ui` rendering `new.html` — delete that old `new_ui` function so `/new` is defined only once, as the redirect above. Search the file for `new.html` to confirm `/` is now the only place it renders.)

- [ ] **Step 4: Run to verify it passes**

Run: `venv/bin/python -m pytest tests/test_new_ui.py -v`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add app/web/routes.py tests/test_new_ui.py
git commit -m "feat(web): cutover — / serves Grid UI, legacy at /tools, /new redirects"
```

---

### Task 2: Re-point legacy UI test to `/tools`

**Files:**
- Modify: `tests/test_web_ui.py`

`tests/test_web_ui.py` asserts legacy element ids (`proj-home`, subnav panels, chat threads, etc.) against `/`. Those now live at `/tools`.

- [ ] **Step 1: Run to confirm it now fails**

Run: `venv/bin/python -m pytest tests/test_web_ui.py -v`
Expected: FAIL — `/` returns the Grid shell, so the legacy-id assertions fail.

- [ ] **Step 2: Edit `tests/test_web_ui.py`** — change the `_html()` helper's request path from `/` to `/tools`:

```python
def _html():
    client = TestClient(create_app())
    r = client.get("/tools")
    assert r.status_code == 200
    return r.text
```

(Leave every other assertion unchanged — the legacy markup is identical, just served at `/tools`.)

- [ ] **Step 3: Run to verify it passes**

Run: `venv/bin/python -m pytest tests/test_web_ui.py -v`
Expected: all pass.

- [ ] **Step 4: Commit**

```bash
git add tests/test_web_ui.py
git commit -m "test: legacy UI assertions target /tools after cutover"
```

---

### Task 3: Fix `new.html` footer + noscript for the new routing

**Files:**
- Modify: `app/web/templates/new.html`

After A, Draft/Mindmap are internal nav items; the only external link is Library (legacy, at `/tools`). The noscript fallback must point to the legacy UI at `/tools` (not `/`, which is now the Grid UI).

- [ ] **Step 1: Replace the sidebar footer links** — change:

```html
    <div class="side-foot">
      <a href="/#tab-draft">Draft ↗</a> · <a href="/#tab-mindmap">Mindmap ↗</a> · <a href="/#tab-library">Library ↗</a>
      <div>Powered by Jatevo · DeepSeek</div>
    </div>
```

to:

```html
    <div class="side-foot">
      <a href="/tools#tab-library">Library ↗</a> · <a href="/tools">Tools lama ↗</a>
      <div>Powered by Jatevo · DeepSeek</div>
    </div>
```

- [ ] **Step 2: Fix the noscript link** — change:

```html
<noscript>
  <div style="padding:24px;text-align:center;color:#475569">
    UI ini perlu JavaScript. Aktifkan JS, atau pakai antarmuka lama di <a href="/">/</a>.
  </div>
</noscript>
```

to:

```html
<noscript>
  <div style="padding:24px;text-align:center;color:#475569">
    UI ini perlu JavaScript. Aktifkan JS, atau pakai antarmuka lama di <a href="/tools">/tools</a>.
  </div>
</noscript>
```

- [ ] **Step 3: Verify the shell test still passes** (footer/noscript text isn't asserted, but confirm nothing broke)

Run: `venv/bin/python -m pytest tests/test_new_ui.py -v`
Expected: all pass.

- [ ] **Step 4: Commit**

```bash
git add app/web/templates/new.html
git commit -m "feat(ui): /new footer + noscript point to /tools after cutover"
```

---

### Task 4: Full verification

- [ ] **Step 1: Full automated suite**

Run: `node --test tests/js/*.test.mjs && venv/bin/python -m pytest tests/ -q`
Expected: all JS tests pass; all pytest pass.

- [ ] **Step 2: Headless route check** — start the server on a spare port and curl the routes:

```bash
PORT=8799 venv/bin/python -m uvicorn app.web.app:app --host 127.0.0.1 --port 8799 >/tmp/cutover.log 2>&1 &
sleep 4
echo "/ (grid):";    curl -s http://127.0.0.1:8799/ | grep -c '/static/new/main.js'
echo "/tools (legacy):"; curl -s http://127.0.0.1:8799/tools | grep -c 'id="tab-mindmap"'
echo "/new redirect:"; curl -s -o /dev/null -w "%{http_code} -> %{redirect_url}\n" http://127.0.0.1:8799/new
pkill -f "uvicorn app.web.app:app --host 127.0.0.1 --port 8799"
```
Expected: `/` grep ≥1 (grid shell), `/tools` grep ≥1 (legacy), `/new` prints `307 -> http://127.0.0.1:8799/` (or 302/308).

- [ ] **Step 3: Manual verification** (`scripts/run.sh`, browser):
  1. `http://127.0.0.1:8765/` → Grid UI (splash first visit, Chat/Projects/Draft/Mindmap).
  2. `http://127.0.0.1:8765/tools` → legacy 5-tab UI (Tanya/Draft/Mindmap/Pustaka/Proyek).
  3. `http://127.0.0.1:8765/new` → redirects to `/`.
  4. Sidebar footer "Library ↗" → opens `/tools` at the library tab.

- [ ] **Step 4: (no commit — verification only)** If everything passes, Sub-project B is complete.

---

## Self-review notes

- **Spec coverage (B):** `/`→Grid, `/tools`→legacy, `/new`→redirect (T1); footer Library→/tools + noscript→/tools (T3); legacy tests re-pointed (T2), grid shell tests at `/` + redirect test (T1). `/viewer`/`/pdf`/API untouched.
- **Single `/new` definition:** T1 Step 3 explicitly removes the old `new_ui` route so `/new` is only the redirect.
- **Redirect status:** `RedirectResponse("/")` defaults to 307; the test accepts 302/307/308 and checks `location == "/"`.
- **Depends on A:** the footer drops Draft/Mindmap links because A made them internal nav — run A first.
```
