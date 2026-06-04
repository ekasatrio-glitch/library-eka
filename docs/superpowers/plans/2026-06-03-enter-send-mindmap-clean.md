# Enter-to-Send + Citation-Free Mindmap Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** (1) Pressing Enter in the chat and mindmap inputs sends/generates immediately (Shift+Enter inserts a newline); (2) the generated mindmap no longer contains `[n]` source markers, which distract the reader.

**Architecture:** (1) A tiny `app.js` helper attaches an Enter-to-submit keydown listener to a form's textarea (Enter → `form.requestSubmit()`, Shift+Enter → default newline), applied to the three input forms. (2) The mindmap outline prompt (`app/rag/mindmap.py`) is changed to NOT request `[n]` tags, and a defensive `_strip_citation_tags()` removes any `[digits]` the model still emits before returning the markdown. The `citations` list in the response is unaffected (mindmap keeps its citation data; only the rendered tree text is clean).

**Tech Stack:** Python (`app/rag/mindmap.py`, pytest), vanilla JS (`app/web/static/app.js`). No JS test runner — JS verified by `node --check` + manual.

---

## File Structure

- `app/rag/mindmap.py` — change `OUTLINE_SYS` (drop the `[n]` instruction), add `_strip_citation_tags(text)`, apply it in `build_mindmap` before returning `markdown`.
- `tests/test_mindmap.py` — add a test asserting the returned markdown has no `[n]` markers and that `OUTLINE_SYS` doesn't instruct them.
- `app/web/static/app.js` — add `enterToSend(form)` helper and call it for `#ask-form`, `#proj-ask-form`, `#mindmap-form`.

---

## Task 1: Mindmap without `[n]` source markers

**Files:**
- Modify: `app/rag/mindmap.py`
- Test: `tests/test_mindmap.py`

- [ ] **Step 1: Write the failing test** — append to `tests/test_mindmap.py`:

```python
def test_mindmap_strips_citation_markers():
    from app.rag import mindmap as mm

    # OUTLINE prompt must not instruct [n] tags anymore.
    assert "[n]" not in mm.OUTLINE_SYS

    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        db = str(root / "t.db")
        make_pdf(root / "a.pdf", "Insulin glucose pancreas regulation")
        conn = init_db(db)
        with patch("app.ingest.pipeline.embed_texts", side_effect=_embed_stub):
            ingest_pdf(root / "a.pdf", conn=conn)

        chat_outputs = iter([
            '["mekanisme insulin", "resistensi insulin"]',
            "# Diabetes\n## Mekanisme\n- Insulin atur glukosa [1]\n- Sekresi [2][3]\n",
        ])
        with patch("app.rag.retriever.embed_one", side_effect=lambda q: _embed_stub([q])[0]), \
             patch("app.rag.mindmap.chat", side_effect=lambda *a, **kw: next(chat_outputs)):
            res = build_mindmap("diabetes", breadth=2, top_k=3, conn=conn)

        # No [1]/[2][3]-style markers remain in the rendered tree.
        import re as _re
        assert not _re.search(r"\[\d+\]", res["markdown"]), res["markdown"]
        assert "Insulin atur glukosa" in res["markdown"]   # content kept, only tags removed
        assert len(res["citations"]) >= 1                  # citation data still returned
        conn.close()
```

- [ ] **Step 2: Run it to verify it fails**

Run: `./venv/bin/python -m pytest tests/test_mindmap.py::test_mindmap_strips_citation_markers -q`
Expected: FAIL — markdown still contains `[1]` (no stripping yet); and/or `OUTLINE_SYS` still contains `[n]`.

- [ ] **Step 3: Add the `re` import** at the top of `app/rag/mindmap.py`. The current first line is `import json`. Change it to:

```python
import json
import re
```

- [ ] **Step 4: Update `OUTLINE_SYS`** — replace the existing block:

```python
OUTLINE_SYS = (
    "Anda menyusun outline mindmap berbasis KONTEKS. Keluarkan markdown hierarki:\n"
    "- baris pertama: '# <topik>'\n"
    "- level 2 (##): tiap subtopik\n"
    "- level 3 (-): poin penting (3-6 per subtopik), tiap poin diakhiri tag sumber [n]\n"
    "Hanya gunakan informasi dari KONTEKS. Jangan karang. Bahasa Indonesia."
)
```

with:

```python
OUTLINE_SYS = (
    "Anda menyusun outline mindmap berbasis KONTEKS. Keluarkan markdown hierarki:\n"
    "- baris pertama: '# <topik>'\n"
    "- level 2 (##): tiap subtopik\n"
    "- level 3 (-): poin penting (3-6 per subtopik), ringkas dan mudah dibaca\n"
    "JANGAN tambahkan nomor/penanda sumber seperti [1] atau [n] di mindmap.\n"
    "Hanya gunakan informasi dari KONTEKS. Jangan karang. Bahasa Indonesia."
)
```

- [ ] **Step 5: Add the strip helper** right after the `OUTLINE_SYS` definition:

```python
def _strip_citation_tags(text: str) -> str:
    """Remove numeric source markers like [1] or [2][3] from mindmap text."""
    return re.sub(r"\s*\[\d+\]", "", text or "")
```

- [ ] **Step 6: Apply it in `build_mindmap`** — change the return's markdown line. Find:

```python
    return {
        "markdown": md.strip(),
        "citations": [c.to_dict() for c in citations],
        "subtopics": subs,
    }
```

and change the first value to:

```python
    return {
        "markdown": _strip_citation_tags(md).strip(),
        "citations": [c.to_dict() for c in citations],
        "subtopics": subs,
    }
```

- [ ] **Step 7: Run the test to verify it passes**

Run: `./venv/bin/python -m pytest tests/test_mindmap.py -q`
Expected: PASS (both the new test and the existing `test_mindmap_builds_markdown`).

- [ ] **Step 8: Commit**

```bash
git add app/rag/mindmap.py tests/test_mindmap.py
git commit -m "feat(mindmap): drop [n] source markers from the rendered tree"
```

---

## Task 2: Enter-to-send in chat + mindmap inputs

**Files:**
- Modify: `app/web/static/app.js`

- [ ] **Step 1: Add the helper** near the other small helpers (e.g. right after `formToBody`):

```javascript
function enterToSend(form) {
  const ta = form.querySelector("textarea");
  if (!ta) return;
  ta.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey && !e.isComposing) {
      e.preventDefault();
      form.requestSubmit();   // triggers the form's existing submit handler + validation
    }
  });
}
```

- [ ] **Step 2: Wire the three forms.** Add these three calls immediately after the helper definition (the form elements exist at script load — they are static markup):

```javascript
enterToSend(document.getElementById("ask-form"));
enterToSend(document.getElementById("proj-ask-form"));
enterToSend(document.getElementById("mindmap-form"));
```

- [ ] **Step 3: Verify syntax + presence**

Run:
```bash
cd "/Users/aininadhifa/Documents/project asal/library-eka"
node --check app/web/static/app.js && echo NODE_OK            # expect NODE_OK
grep -c "function enterToSend" app/web/static/app.js          # expect 1
grep -c "enterToSend(document.getElementById" app/web/static/app.js   # expect 3
```
Expected: `NODE_OK`, `1`, `3`.

- [ ] **Step 4: Manual click-through** (browser at http://127.0.0.1:8765, hard-refresh)

- Tanya tab: type a question, press **Enter** → it sends (no newline added); **Shift+Enter** → inserts a newline without sending.
- Project Chat: same.
- Mindmap: type a topic, press **Enter** → it generates.

- [ ] **Step 5: Commit**

```bash
git add app/web/static/app.js
git commit -m "feat(ui): Enter sends in chat + mindmap (Shift+Enter = newline)"
```

---

## Self-Review (completed by plan author)

**Spec coverage:** "enter langsung mengirim pesan" (chat + mindmap) → Task 2 wires `#ask-form`, `#proj-ask-form`, `#mindmap-form` with Enter→`requestSubmit`, Shift+Enter preserved as newline. "mindmap jangan ada nomor sitasi" → Task 1 removes the `[n]` prompt instruction AND strips any residual `[digits]` from the output. Both covered.

**Placeholder scan:** No TBD/TODO. The regex `\s*\[\d+\]` is concrete and matches `[1]`, `[12]`, and adjacent `[2][3]` (applied globally by `re.sub`). The `isComposing` guard avoids breaking IME input. No placeholders.

**Type/name consistency:** Helper `_strip_citation_tags` defined (Step 5) and used (Step 6) with matching name; `enterToSend` defined (Step 1) and called 3× (Step 2) with matching name. `OUTLINE_SYS` symbol unchanged (only its content), so existing imports/tests still resolve. The new test references `mm.OUTLINE_SYS` and `build_mindmap`, both real symbols.
