# Cited vs Uncited Sources Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Split the rendered source list into "Sumber dikutip" (numbers actually used in the answer text, original numbering kept) and a collapsed "Diambil, tidak dikutip" section, for both chat (`/ask`, `/projects/{id}/ask`) and Draft (Vancouver).

**Architecture:** Backend marks each `Citation` with a `cited` boolean by parsing the numeric markers the LLM emitted (`[n]` in chat answers, `(n)` in Vancouver drafts). Original numbers are never changed and nothing is removed from the payload — the frontend (`citationBlock`, draft refs renderer) splits the list into two sections. APA drafts have no numeric markers, so they keep a single undivided list (all `cited=True`, the fallback default).

**Tech Stack:** Python (FastAPI backend), vanilla JS frontend, pytest.

**Problem being fixed:** `ask()` returns *all* retrieved hits as citations; the LLM typically cites a subset (e.g. answer uses [3] and [6] but the UI shows "📎 Sumber (6)"). Readers can't tell why the list is longer than the cited numbers.

**Key design decisions (user-approved):**
- Option 2: keep original numbers, two sections — NOT renumbering, NOT dropping uncited.
- Applies to chat **and** Draft.
- Fallback: if no valid markers are parsed from the text (LLM forgot markers, or all out of range), treat **all** citations as cited → UI renders the single classic "📎 Sumber (n)" block. Never show an empty "dikutip" section.
- Out-of-range numbers in the text (e.g. `[9]` with 6 sources, or a year like `(2020)` matching the paren pattern) are ignored by validation — this is what makes the paren pattern safe for Vancouver despite years appearing in parentheses.

**Files:**
- Modify: `app/rag/citation.py` (add `cited` field, `extract_cited_ns()`, `mark_cited()`)
- Modify: `app/rag/ask.py` (mark after generation)
- Modify: `app/rag/drafting.py` (mark after generation, vancouver only)
- Modify: `app/web/static/app.js` (`citationBlock` split; draft refs split)
- Modify: `app/web/templates/index.html` (draft refs `<ol>` → `<div>` container)
- Modify: `app/web/static/app.css` (one rule for the uncited summary)
- Create: `tests/test_citation.py`
- Modify: `tests/test_rag.py`, `tests/test_drafting.py`

---

### Task 1: Marker parsing + cited flag in `app/rag/citation.py`

**Files:**
- Create: `tests/test_citation.py`
- Modify: `app/rag/citation.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_citation.py`:

```python
from app.rag.citation import Citation, build_citations, extract_cited_ns, mark_cited
from app.rag.retriever import Hit


def _hit(i: int) -> Hit:
    return Hit(
        chunk_id=i,
        doc_id=i,
        title=f"Paper {i}",
        path=f"/tmp/{i}.pdf",
        page_start=i,
        page_end=i,
        year=2020,
        authors="A",
        text="x",
        distance=0.1,
    )


def _citations(n: int):
    return build_citations([_hit(i) for i in range(1, n + 1)])


# --- extract_cited_ns ---

def test_extract_square_single_and_multiple():
    assert extract_cited_ns("klaim [3]. lain [6].", style="square") == {3, 6}


def test_extract_square_comma_list_and_range():
    assert extract_cited_ns("a [1, 2] b [4-6]", style="square") == {1, 2, 4, 5, 6}


def test_extract_square_ignores_paren():
    assert extract_cited_ns("hasil (3) tanpa kurung siku", style="square") == set()


def test_extract_paren_single_and_list():
    assert extract_cited_ns("klaim (1). lain (2,3).", style="paren") == {1, 2, 3}


def test_extract_no_markers():
    assert extract_cited_ns("tanpa sitasi sama sekali", style="square") == set()


# --- mark_cited ---

def test_mark_cited_flags_subset():
    cits = _citations(6)
    mark_cited(cits, {3, 6})
    assert [c.cited for c in cits] == [False, False, True, False, False, True]


def test_mark_cited_ignores_out_of_range():
    cits = _citations(3)
    mark_cited(cits, {2, 9, 2020})  # 9 and 2020 out of range
    assert [c.cited for c in cits] == [False, True, False]


def test_mark_cited_empty_set_keeps_all_cited():
    cits = _citations(3)
    mark_cited(cits, set())
    assert all(c.cited for c in cits)


def test_mark_cited_all_out_of_range_keeps_all_cited():
    cits = _citations(3)
    mark_cited(cits, {2020})
    assert all(c.cited for c in cits)


def test_citation_to_dict_has_cited():
    cits = _citations(1)
    assert cits[0].to_dict()["cited"] is True
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_citation.py -v`
Expected: FAIL / ERROR with `ImportError: cannot import name 'extract_cited_ns'`

- [ ] **Step 3: Implement in `app/rag/citation.py`**

Add `cited` field to the dataclass (after `path`):

```python
@dataclass
class Citation:
    n: int
    doc_id: int
    chunk_id: int
    title: str
    page_start: int
    page_end: int
    path: str
    cited: bool = True

    def to_dict(self) -> Dict:
        return asdict(self)
```

Add at the bottom of the file:

```python
import re

# [3], [1, 2], [4-6] — chat answers
_SQUARE = re.compile(r"\[(\d+(?:\s*[,\-–]\s*\d+)*)\]")
# (3), (1,2) — Vancouver drafts; years like (2020) parse but fail range validation
_PAREN = re.compile(r"\((\d+(?:\s*[,\-–]\s*\d+)*)\)")


def extract_cited_ns(text: str, style: str = "square") -> set:
    """Collect citation numbers the LLM actually used in `text`.
    style: 'square' for [n] (chat), 'paren' for (n) (Vancouver)."""
    pat = _SQUARE if style == "square" else _PAREN
    ns: set = set()
    for m in pat.finditer(text):
        for part in re.split(r"\s*,\s*", m.group(1)):
            rng = re.fullmatch(r"(\d+)\s*[\-–]\s*(\d+)", part.strip())
            if rng:
                ns.update(range(int(rng.group(1)), int(rng.group(2)) + 1))
            elif part.strip().isdigit():
                ns.add(int(part.strip()))
    return ns


def mark_cited(citations: List[Citation], ns: set) -> List[Citation]:
    """Flag citations whose number appears in `ns`. If no number is valid
    (LLM emitted no markers, or only out-of-range ones like years), keep
    everything cited=True so the UI falls back to the single classic list."""
    valid = {n for n in ns if 1 <= n <= len(citations)}
    if not valid:
        return citations
    for c in citations:
        c.cited = c.n in valid
    return citations
```

Move the `import re` to the top of the file with the other imports.

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_citation.py -v`
Expected: all PASS

- [ ] **Step 5: Run full suite (regression — `cited` key added to citation dicts)**

Run: `python -m pytest tests/ -v`
Expected: all PASS

- [ ] **Step 6: Commit**

```bash
git add app/rag/citation.py tests/test_citation.py
git commit -m "feat(rag): parse cited markers and flag citations as cited/uncited"
```

---

### Task 2: Mark citations in `ask()`

**Files:**
- Modify: `app/rag/ask.py`
- Modify: `tests/test_rag.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_rag.py`:

```python
def test_ask_marks_cited_subset():
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        db = str(root / "t.db")
        a = root / "quantum.pdf"
        make_pdf(a, "Quantum entanglement Bell test inequality measurement", pages=4)
        conn = init_db(db)
        with patch("app.ingest.pipeline.embed_texts", side_effect=_embed_stub):
            ingest_pdf(a, conn=conn)

        def fake_chat(system, user, **kw):
            return "Entanglement is correlation [2]."

        with patch("app.rag.retriever.embed_one", side_effect=lambda q: _embed_stub([q])[0]), \
             patch("app.rag.ask.chat", side_effect=fake_chat):
            res = ask("what is entanglement?", top_k=3, conn=conn)

        cits = res["citations"]
        assert len(cits) >= 2, "need >=2 retrieved chunks for this test"
        assert all("cited" in c for c in cits)
        assert [c["cited"] for c in cits] == [c["n"] == 2 for c in cits]
        conn.close()


def test_ask_no_markers_keeps_all_cited():
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        db = str(root / "t.db")
        a = root / "quantum.pdf"
        make_pdf(a, "Quantum entanglement Bell test inequality measurement", pages=2)
        conn = init_db(db)
        with patch("app.ingest.pipeline.embed_texts", side_effect=_embed_stub):
            ingest_pdf(a, conn=conn)

        def fake_chat(system, user, **kw):
            return "Answer without any markers."

        with patch("app.rag.retriever.embed_one", side_effect=lambda q: _embed_stub([q])[0]), \
             patch("app.rag.ask.chat", side_effect=fake_chat):
            res = ask("what is entanglement?", top_k=2, conn=conn)

        assert all(c["cited"] for c in res["citations"])
        conn.close()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_rag.py::test_ask_marks_cited_subset tests/test_rag.py::test_ask_no_markers_keeps_all_cited -v`
Expected: `test_ask_marks_cited_subset` FAILS (all `cited` True even though only [2] was used). `test_ask_no_markers_keeps_all_cited` may already pass (default is True) — that's fine.

- [ ] **Step 3: Implement in `app/rag/ask.py`**

Change the import line:

```python
from app.rag.citation import Citation, build_citations, extract_cited_ns, format_context, mark_cited
```

In `ask()`, after `answer = chat(...)` and before `return`:

```python
    answer = chat(SYSTEM, USER_TMPL.format(question=question, context=ctx))
    mark_cited(citations, extract_cited_ns(answer, style="square"))
    return {
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_rag.py -v`
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add app/rag/ask.py tests/test_rag.py
git commit -m "feat(rag): flag which citations the answer actually used"
```

---

### Task 3: Mark citations in Draft (Vancouver only)

**Files:**
- Modify: `app/rag/drafting.py`
- Modify: `tests/test_drafting.py`

- [ ] **Step 1: Write the failing tests** — append to `tests/test_drafting.py` (uses the file's existing `make_pdf` and `_embed_stub` helpers):

```python
def test_draft_vancouver_marks_cited():
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        db = str(root / "t.db")
        a = root / "a.pdf"
        make_pdf(a, "Vaccine efficacy mRNA clinical trial evidence", pages=4)
        conn = init_db(db)
        with patch("app.ingest.pipeline.embed_texts", side_effect=_embed_stub):
            ingest_pdf(a, conn=conn)

        with patch("app.rag.retriever.embed_one", side_effect=lambda q: _embed_stub([q])[0]), \
             patch("app.rag.drafting.chat", return_value="Sintesis bukti menunjukkan efek (2)."):
            res = draft_paragraph("mRNA vaksin", style="vancouver", top_k=3, conn=conn)

        cits = res["citations"]
        assert len(cits) >= 2, "need >=2 retrieved chunks for this test"
        assert all("cited" in c for c in cits)
        assert [c["cited"] for c in cits] == [c["n"] == 2 for c in cits]
        conn.close()


def test_draft_apa_keeps_all_cited():
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        db = str(root / "t.db")
        a = root / "a.pdf"
        make_pdf(a, "Cell biology 2022", pages=2)
        conn = init_db(db)
        with patch("app.ingest.pipeline.embed_texts", side_effect=_embed_stub):
            ingest_pdf(a, conn=conn)

        with patch("app.rag.retriever.embed_one", side_effect=lambda q: _embed_stub([q])[0]), \
             patch("app.rag.drafting.chat", return_value="Sel terdiri organel (Anon, 2022)."):
            res = draft_paragraph("biologi sel", style="apa", top_k=3, conn=conn)

        # APA has no numeric markers -> everything stays cited=True
        # (the literal "(2022)" is out of range and must be ignored).
        assert all(c["cited"] for c in res["citations"])
        conn.close()
```

If `make_pdf(..., pages=4)` still yields fewer than 2 chunks (chunker may merge short pages), lengthen the text per page instead of adding pages — the `len(cits) >= 2` guard assertion will tell you.

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_drafting.py -v`
Expected: `test_draft_vancouver_marks_cited` FAILS (all cited=True). `test_draft_apa_keeps_all_cited` passes already — fine, it pins the APA contract.

- [ ] **Step 3: Implement in `app/rag/drafting.py`**

Change the import line:

```python
from app.rag.citation import build_citations, extract_cited_ns, format_context, mark_cited
```

After `paragraph = chat(...)`:

```python
    paragraph = chat(sys, user, temperature=0.25, max_tokens=900)
    if style == "vancouver":
        mark_cited(citations, extract_cited_ns(paragraph, style="paren"))
    refs = [_format_reference(i + 1, h, style) for i, h in enumerate(hits)]
```

Years like `(2020)` inside the paragraph match the paren pattern but are discarded by `mark_cited`'s range check (2020 > len(citations)) — and if the LLM emitted *only* such tokens, the no-valid-marker fallback keeps everything cited. No special-casing needed.

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_drafting.py -v`
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add app/rag/drafting.py tests/test_drafting.py
git commit -m "feat(draft): flag cited sources in Vancouver paragraphs"
```

---

### Task 4: Frontend — split chat source list

**Files:**
- Modify: `app/web/static/app.js:19-23` (`citationBlock`)
- Modify: `app/web/static/app.css` (one rule)

- [ ] **Step 1: Replace `citationBlock` in `app/web/static/app.js`**

```js
function citationBlock(citations) {
  if (!citations || !citations.length) return "";
  const cited = citations.filter(c => c.cited !== false);
  const uncited = citations.filter(c => c.cited === false);
  // No split needed (old payloads, or LLM cited everything): classic single block.
  if (!uncited.length) {
    return `<details class="cites-toggle"><summary>📎 Sumber (${citations.length})</summary>` +
      `<ol class="cites">${citationLinks(citations)}</ol></details>`;
  }
  return `<details class="cites-toggle" open><summary>📎 Sumber dikutip (${cited.length})</summary>` +
    `<ol class="cites">${citationLinks(cited)}</ol></details>` +
    `<details class="cites-toggle cites-uncited"><summary>Diambil, tidak dikutip (${uncited.length})</summary>` +
    `<ol class="cites">${citationLinks(uncited)}</ol></details>`;
}
```

`c.cited !== false` (not `c.cited === true`) keeps backward compatibility with payloads lacking the field. Both `/ask` and `/projects/{id}/ask` render through this one function (`app.js:90` and `app.js:302`) — no other chat changes needed.

- [ ] **Step 2: Add CSS to `app/web/static/app.css`** (after the `.cites-toggle[open] > summary` rule, ~line 107):

```css
.cites-uncited > summary { font-style: italic; opacity: .75; }
```

- [ ] **Step 3: Manual verify**

Run: `scripts/run.sh`, open http://127.0.0.1:8765, ask a question on a corpus with several docs.
Expected: answer citing a subset shows "📎 Sumber dikutip (k)" expanded + collapsed italic "Diambil, tidak dikutip (m)". Numbers in the list match the numbers in the answer text (no renumbering). An answer citing everything shows the classic single "📎 Sumber (n)".

- [ ] **Step 4: Run full test suite (test_web_ui.py may assert on static content)**

Run: `python -m pytest tests/ -v`
Expected: all PASS. If a UI test asserts on the old `📎 Sumber (` literal, update that assertion to match the new conditional output.

- [ ] **Step 5: Commit**

```bash
git add app/web/static/app.js app/web/static/app.css
git commit -m "feat(ui): split chat sources into cited vs retrieved-but-uncited"
```

---

### Task 5: Frontend — split Draft references (Vancouver)

**Files:**
- Modify: `app/web/templates/index.html:47`
- Modify: `app/web/static/app.js:94-105` (draft submit handler)

- [ ] **Step 1: Change the refs container in `app/web/templates/index.html`**

Old (line 47):

```html
<ol id="draft-refs" class="citations"></ol>
```

New (a `<div>` so JS can render two `<ol>` sections inside):

```html
<div id="draft-refs"></div>
```

- [ ] **Step 2: Replace the draft submit handler in `app/web/static/app.js`**

```js
document.getElementById("draft-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const para = document.getElementById("draft-paragraph");
  const refsEl = document.getElementById("draft-refs");
  para.textContent = "Menulis draft...";
  refsEl.innerHTML = "";
  try {
    const res = await postJSON("/draft", formToBody(e.target));
    para.textContent = res.paragraph;
    const refs = res.references || [];
    const cits = res.citations || [];
    // references[i] pairs with citations[i] (same retrieval order).
    const cited = [], uncited = [];
    refs.forEach((r, i) => {
      ((cits[i] && cits[i].cited === false) ? uncited : cited).push(r);
    });
    let html = `<ol class="citations">${cited.map(r => `<li>${escapeHtml(r)}</li>`).join("")}</ol>`;
    if (uncited.length) {
      html += `<details class="cites-toggle cites-uncited"><summary>Diambil, tidak dikutip (${uncited.length})</summary>` +
        `<ol class="citations">${uncited.map(r => `<li>${escapeHtml(r)}</li>`).join("")}</ol></details>`;
    }
    refsEl.innerHTML = html;
  } catch (err) { para.textContent = "Error: " + err.message; }
});
```

Caveat (accepted): `.citations` uses `list-style: decimal inside`, so a split Vancouver list restarts visual numbering per section — but each Vancouver reference string already begins with its own `"{idx}. "` prefix from `_format_reference`, so the authoritative number is in the text. If the double numbering looks bad in manual verify, add `list-style: none` for these two lists via a `.citations.refs-split` class on both `<ol>`s.

- [ ] **Step 3: Manual verify**

Run: `scripts/run.sh`, open Draft tab, generate a Vancouver paragraph on a multi-doc corpus.
Expected: paragraph cites subset `(n)`; cited references listed first; uncited collapsed underneath. APA draft: single flat list, no split.

- [ ] **Step 4: Run full test suite**

Run: `python -m pytest tests/ -v`
Expected: all PASS (update any template-literal assertions in `tests/test_web_ui.py` if they reference the old `<ol id="draft-refs"`).

- [ ] **Step 5: Commit**

```bash
git add app/web/templates/index.html app/web/static/app.js
git commit -m "feat(ui): split draft references into cited vs uncited (Vancouver)"
```
