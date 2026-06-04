# Grid-Style UI for library-eka — Design

**Date:** 2026-06-04
**Status:** Approved (brainstorming complete)

## Goal

Rebuild the library-eka web UI in the visual style of `grid.jatevo.ai` ("Grid Analyst") — a clean, modern chat interface — covering the **Chat** and **Projects** features. Built as a parallel route (`/new`) alongside the existing UI, with no backend rewrite.

## Decisions (locked)

| # | Decision | Choice |
|---|----------|--------|
| 1 | Purpose | New front-end for library-eka (restyle existing app, not standalone clone) |
| 2 | Scope | **Chat + Projects** only. Draft / Mindmap / Library keep their current UI, linked from sidebar footer. |
| 3 | Conversation history | **Browser localStorage** — no backend change, not synced to VPS |
| 4 | Stack | **Vanilla + native ES modules**, no build step. FastAPI/Jinja unchanged. |
| 5 | Layout | **Two workspaces (Option B):** sidebar switches between a Chat view and a Projects view. Projects is a full page per project with tabs Papers / Matrix / Chat proyek / Export. |
| 6 | Citations | **Pills + collapsed sources (Option B):** `[n]` markers render as click-to-PDF cite-pills; the full source list lives behind a 📎 toggle. The cited / "Diambil, tidak dikutip" split (shipped earlier today) is preserved. |
| 7 | Cutover | **Parallel route `/new`.** Old UI stays at `/` untouched. Swap is a separate later decision. |
| 8 | Brand mark | **Open book + EKG pulse line** (medical), SVG stroke in brand color `#0369A1`. No lightning bolt. |
| 9 | Splash | First-visit welcome overlay with animated EKG, English tagline, close. Shown **once** (localStorage flag). |

## Splash screen (first visit only)

A welcome overlay covering `/new` on first load, dismissable, shown only once.

- **Trigger:** on `/new` load, if `localStorage['libeka.splashSeen']` is unset → show. Dismiss (✕, "Enter the library →", or "Don't show again") sets the flag so it never reappears. ("Don't show again" and the two dismiss buttons all set the same flag — there is no per-session reshow.)
- **Copy (English):**
  - Title (Merriweather): *"Welcome to **library-eka** — where all your books meet machine learning."* (brand word highlighted `--brand`)
  - Subtitle (Inter): *"Ask anything across your entire corpus. Precise answers with click-to-page citations."*
- **Visual:** same tokens/fonts as the app. Radial `--brand-subtle` glow + `backdrop-filter:blur` over a faint app silhouette. Book+EKG logo at top. Animated EKG line below the copy in `--accent` (Amber 600 `#D97706`): SVG path drawn via `stroke-dashoffset` keyframes (looping ~2.6s) with a soft blurred glow underlay (same color, low opacity); staggered `rise` fade-in for logo/title/subtitle/button. Respect `prefers-reduced-motion` → render the EKG static (no draw loop).
- **Controls:** `✕` top-right, primary "Enter the library →" button, subtle "Don't show again" text button. All dismiss + set the flag.
- **Implementation:** lives in `main.js` (or a small `splash.js` mounted by main.js); pure front-end, no backend route. CSS in `new.css`.

## Design tokens (from Grid Analyst)

```css
:root{
  --bg:#F9FAFB; --surface:#FFFFFF; --user-bubble:#F1F5F9;
  --text:#0F172A; --text2:#475569; --text3:#64748B;
  --brand:#0369A1; --brand-hover:#075985; --brand-subtle:#E0F2FE;
  --border:#E2E8F0; --border-strong:#CBD5E1;
  --radius:12px; --shadow:0 8px 30px rgba(15,23,42,.05);
  --accent:#D97706; /* Amber 600 — splash EKG line only */
}
```

`--accent` (Amber 600) is reserved for the splash EKG animation (line + blurred glow). It is **not** used elsewhere — brand UI stays blue (`--brand`).

Fonts (Google Fonts + fallback): **Inter** (UI), **Merriweather** serif (AI answer headings / page titles), **Fira Code** (cite-pills, ref numbers, monospace). Single responsive breakpoint at `768px` (sidebar hides on mobile).

## Architecture

Backend change is a single new route; everything else is static assets calling existing endpoints.

```
app/web/
  routes.py                 # + GET /new  → renders new.html  (only backend edit)
  templates/new.html        # shell: sidebar + main, <script type="module" src=".../main.js">
  static/new/
    new.css                 # tokens + layout (sidebar, chat, projects, matrix, input)
    main.js                 # entry: splash (first-visit), view switcher (Chat ⟷ Projects), sidebar render, routing-in-page
    api.js                  # postJSON / getJSON helpers, escapeHtml
    chat.js                 # chat thread, input (Enter=send, Shift+Enter=newline), empty-state cards, streaming-state
    citations.js            # parse [n] → cite-pill (→ /viewer?doc=&page=), 📎 toggle, cited/uncited split
    history.js              # localStorage conversations: list, save, load, delete; render "Recent"
    projects.js             # Projects view: list, tabs Papers/Matrix/Chat proyek/Export, scoped ask, nudge
```

### Units & responsibilities

- **main.js** — owns the sidebar and the active view (`chat` | `projects`). Mounts `chat.js` or `projects.js` into `.main`. No fetch logic of its own.
- **api.js** — the only module that calls `fetch`. Exports `postJSON(url, body)`, `getJSON(url)`, `escapeHtml(s)`. Everyone else depends on this; nothing depends on the DOM here.
- **chat.js** — renders a conversation thread + input. Calls `api.postJSON('/ask', …)`, renders answer via `citations.js`, persists via `history.js`. Used by both the global Chat view and the in-project "Chat proyek" tab (the latter posts to `/projects/{id}/ask` with `expand`).
- **citations.js** — pure-ish render: given an answer string + `citations[]`, returns HTML with cite-pills and the collapsed 📎 block (reusing the cited/uncited logic already in the old `citationBlock`). One consumer-facing function `renderAnswer(answer, citations)`.
- **history.js** — localStorage CRUD under one key (`libeka.conversations`). Each conversation `{id, title, scope: 'global'|projectId, messages:[{q,a,citations}], updatedAt}`. Renders the "Recent" list; emits select/delete callbacks to main.js.
- **projects.js** — Projects view. Lists projects (`GET /projects`), renders the active project header + tabs. Papers/Matrix/Export reuse existing endpoints (`/projects/{id}/papers`, `/matrix`, `/matrix/export.xlsx|csv`); "Chat proyek" tab mounts `chat.js` in scoped mode.

### Data flow

```
user types → chat.js → api.postJSON('/ask' | '/projects/{id}/ask')
   → citations.js renderAnswer()  → DOM
   → history.js save()            → localStorage
Projects view: projects.js → api.getJSON('/projects'), per-tab endpoints (matrix, papers, export)
cite-pill click → window.open('/viewer?doc={id}#page={n}')
```

No new backend state. History is browser-local by decision #3.

## Layout spec

**Sidebar (248px, hidden < 768px):** brand (book+pulse SVG + "library-eka") · nav items `💬 Chat` / `📁 Projects` (active = `--brand-subtle`) · context-dependent middle: in Chat view → "+ Percakapan baru" + **Recent** (localStorage); in Projects view → **Projects** list + "+ Proyek baru" · footer: `Draft ↗ · Mindmap ↗ · Library ↗` (links to existing routes) + "Powered by Jatevo · DeepSeek".

**Chat view main:** scroll area (max-width 760px) of message bubbles — user bubble right (`--user-bubble`, asymmetric radius), AI answer in bordered card (`--surface`) with Merriweather headings, cite-pills, 📎 collapsed sources, optional nudge box. Sticky input bar (textarea + circular send button). Empty state = Merriweather h1 + tagline + 2-col example-card grid.

**Projects view main:** project header (Merriweather title + meta line "N papers · skema matrix · codebook") + tab row. Tabs:
- **Papers** — grid/list of project papers; "+ Import dari library" + drop-PDF.
- **Matrix** — bordered table; codebook tag cells, explicit gaps (`tidak disebutkan` muted italic), views matrix/linimasa/tema.
- **Chat proyek** — embedded `chat.js` scoped to project, context chip with `expand` toggle + nudge.
- **Export** — `⬇ export.xlsx` (codebook colors) / `⬇ export.csv`.

## Preserved behaviors (must not regress)

- Enter sends, Shift+Enter newline (matches commit `c03508c`).
- Cited vs "Diambil, tidak dikutip" citation split (today's feature).
- Project scoped chat with `expand` to whole library + discovery `nudge` ("paper lain mungkin relevan" → + button adds to project).
- Click-to-page PDF citations via `/viewer?doc=<id>#page=<n>`.
- Indonesian UI strings.

## Out of scope

- No backend persistence of conversations (localStorage only).
- No build tooling (Vite/React/Tailwind).
- No restyle of Draft / Mindmap / Library (linked, not rebuilt).
- No change to `/` until a later explicit swap decision.
- No quota widget (local app).

## Testing

- Existing pytest suite must stay green (82 passing) — backend only gains a `GET /new` route returning 200 + the shell HTML; add one route test in `tests/test_web_ui.py`.
- JS has no unit harness in-repo; verify manually via `scripts/run.sh` → `http://127.0.0.1:8765/new`: splash shows on first visit + dismiss sets flag + does not reappear on reload, empty state, ask flow with cite-pills + cited/uncited toggle, history persists across reload, project switch, matrix render, export download, mobile width (<768px) hides sidebar.
- `node --check` each ES module before commit.
