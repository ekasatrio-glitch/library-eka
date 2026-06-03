# Collapsible Citations Toggle Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the per-answer source list (`[1] … [n]`) collapsible — hidden by default with a small "Sumber (N)" toggle — so it stops distracting, in both the main "Tanya" chat thread and the project Chat thread.

**Architecture:** Wrap the citation `<ol>` in a native HTML `<details>` element (collapsed by default, no JS needed for toggling). Introduce ONE shared `citationBlock(citations)` helper in `app.js` and use it in all three places that currently render `<ol class="cites">…</ol>` (the `appendChat` helper, the `#ask-form` handler, the `#proj-ask-form` handler), so the behavior is DRY. The inline `[n]` markers inside the answer text are untouched — only the listed sources collapse.

**Tech Stack:** Vanilla JS (`app/web/static/app.js`), plain CSS (`app/web/static/app.css`). No backend changes. No JS test runner exists in this repo, so verification is `node --check` + grep invariants + manual click-through.

---

## File Structure

- `app/web/static/app.js` — add `citationBlock(citations)` (returns a `<details>` wrapper or `""`); replace the three existing inline `` `<ol class="cites">${citationLinks(...)}</ol>` `` usages with calls to it. The three sites: (1) `appendChat`, (2) `#ask-form` submit handler's `pending.innerHTML = …`, (3) `#proj-ask-form` submit handler's `pending.innerHTML = …`.
- `app/web/static/app.css` — style the toggle summary (`.cites-toggle`, `.cites-toggle summary`) to be small/subtle.

---

## Task 1: Shared `citationBlock` helper + use it everywhere

**Files:**
- Modify: `app/web/static/app.js`

- [ ] **Step 1: Add the helper** immediately AFTER the existing `citationLinks` function (it depends on `citationLinks`):

```javascript
function citationBlock(citations) {
  if (!citations || !citations.length) return "";
  return `<details class="cites-toggle"><summary>📎 Sumber (${citations.length})</summary>` +
    `<ol class="cites">${citationLinks(citations)}</ol></details>`;
}
```

- [ ] **Step 2: Use it inside `appendChat`.** In the `appendChat` function, find the line that builds `b.innerHTML` containing `(citations && citations.length ? \`<ol class="cites">${citationLinks(citations)}</ol>\` : "")` and replace that whole ternary with `citationBlock(citations)`. The result must read:

```javascript
  b.innerHTML = escapeHtml(answer).replace(/\n/g, "<br>") +
    citationBlock(citations) +
    (nudgeHtml ? `<div class="nudge">${nudgeHtml}</div>` : "");
```

- [ ] **Step 3: Use it in the `#ask-form` handler.** In the `#ask-form` submit handler, find the success line `pending.innerHTML = escapeHtml(res.answer).replace(/\n/g, "<br>") + ((res.citations || []).length ? \`<ol class="cites">${citationLinks(res.citations)}</ol>\` : "");` and replace it with:

```javascript
    pending.innerHTML = escapeHtml(res.answer).replace(/\n/g, "<br>") +
      citationBlock(res.citations);
```

- [ ] **Step 4: Use it in the `#proj-ask-form` handler.** In the `#proj-ask-form` submit handler, find the line `pending.innerHTML = escapeHtml(res.answer).replace(/\n/g, "<br>") + ((res.citations || []).length ? \`<ol class="cites">${citationLinks(res.citations)}</ol>\` : "") + (nudgeHtml ? \`<div class="nudge">${nudgeHtml}</div>\` : "");` and replace it with:

```javascript
    pending.innerHTML = escapeHtml(res.answer).replace(/\n/g, "<br>") +
      citationBlock(res.citations) +
      (nudgeHtml ? `<div class="nudge">${nudgeHtml}</div>` : "");
```

- [ ] **Step 5: Verify invariants**

Run:
```bash
cd "/Users/aininadhifa/Documents/project asal/library-eka"
grep -c "function citationBlock" app/web/static/app.js          # expect 1
grep -c "citationBlock(" app/web/static/app.js                  # expect 4 (def + 3 uses)
grep -c '<ol class="cites">' app/web/static/app.js              # expect 1 (only inside citationBlock)
node --check app/web/static/app.js && echo "NODE_OK"            # expect NODE_OK
```
Expected: `1`, `4`, `1`, `NODE_OK`.

- [ ] **Step 6: Commit**

```bash
git add app/web/static/app.js
git commit -m "feat(ui): collapsible per-answer citations (DRY citationBlock helper)"
```

---

## Task 2: Style the toggle

**Files:**
- Modify: `app/web/static/app.css` (append)

- [ ] **Step 1: Append styles**

```css
/* Collapsible citations */
.cites-toggle { margin-top:.4rem; }
.cites-toggle > summary { cursor:pointer; color:#8b93a7; font-size:.85em; list-style:none; user-select:none; }
.cites-toggle > summary::-webkit-details-marker { display:none; }
.cites-toggle[open] > summary { color:#b8c0d0; }
```

- [ ] **Step 2: Verify**

Run: `grep -c "cites-toggle" app/web/static/app.css`
Expected: a non-zero number (≥3).

- [ ] **Step 3: Commit**

```bash
git add app/web/static/app.css
git commit -m "feat(ui): subtle styling for citations toggle"
```

---

## Task 3: Runtime verification

**Files:** none (verification only)

- [ ] **Step 1: Run the full suite (no regressions)**

Run: `./venv/bin/python -m pytest -q`
Expected: all pass (same count as before; this change is client-side only).

- [ ] **Step 2: Start the app**

```bash
pkill -f "uvicorn app.web.app" 2>/dev/null; sleep 1
nohup ./venv/bin/python -m uvicorn app.web.app:app --host 127.0.0.1 --port 8765 > /tmp/eka_web.log 2>&1 &
sleep 4
curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1:8765/static/app.js   # expect 200
curl -s http://127.0.0.1:8765/static/app.js | grep -c "function citationBlock" # expect 1
```

- [ ] **Step 3: Manual click-through** (browser at http://127.0.0.1:8765)

- Tanya tab: ask a question with sources. The answer shows, and below it a small "📎 Sumber (N)" line — the list is HIDDEN by default. Click it → the `[1]…[n]` list expands; click again → it collapses.
- Project Chat: same behavior in the project thread.
- The inline `[n]` markers inside the answer paragraph are still visible (only the listed sources collapse).
- Citation links inside the expanded list still open the PDF viewer at the right page.

---

## Self-Review (completed by plan author)

**Spec coverage:** "toggle agar bisa muncul/hilang, tidak terdistraksi" → `<details>` collapsed-by-default with a "Sumber (N)" summary (Task 1 Step 1), applied to both chat threads via the shared helper used in all three render sites (Steps 2-4). Covered.

**Placeholder scan:** No TBD/TODO/"handle edge cases". Empty-citations case is handled explicitly (`citationBlock` returns `""`). No placeholders.

**Type/name consistency:** Helper named `citationBlock` consistently in definition (Step 1) and all three call sites (Steps 2-4) and the verification greps (Step 5). It reuses the existing `citationLinks` function (unchanged). CSS class `.cites-toggle` matches the class emitted by `citationBlock`. The grep in Step 5 expects exactly one remaining literal `<ol class="cites">` — which lives inside `citationBlock` — confirming the other sites were converted.
