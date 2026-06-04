# Switch Embedding Model to bge-m3 (768 → 1024) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `bge-m3` (1024-d) the configured embedding model for both ingestion and query, changing the code dimension constant from 768 to 1024 and updating `.env`, without breaking the test suite and without running ingestion.

**Architecture:** Embedding model/dim are env-driven in `app/core/config.py` (which `load_dotenv()`s `.env` at import). `init_db()` builds `vec_chunks` as `FLOAT[EMBED_DIM]`; `embedder.embed_texts`/`embed_one` use `EMBED_MODEL`; the query path (`retriever.embed_one`) already uses the same configured model, so it follows automatically. The only real hazard is the test suite: ~15 test files hard-code `768` in their fake embedding stubs, and because `.env` is loaded at import, raising `EMBED_DIM` to 1024 makes those 768-length vectors mismatch the `FLOAT[1024]` vec table. So stubs must be made dimension-agnostic **first** (while still at 768, proving no regression), then the dimension is flipped.

**Tech Stack:** Python, pytest, sqlite-vec, Ollama (bge-m3 already pulled).

## Critical ordering

1. **First** make every test stub derive its vector length from `config.EMBED_DIM` (suite stays green at 768 — pure refactor).
2. **Then** add a guard test that the query path embeds with the configured model.
3. **Then** flip the defaults + `.env` to bge-m3 / 1024 — the now-dim-agnostic suite re-proves the system at 1024.

Doing the flip first would red the whole suite at once with no useful signal. Don't.

## Operational notes (read before executing)

- **Do NOT run ingestion / reembed** (user instruction). This plan only changes config + tests.
- The existing on-disk DB (`DB_PATH=data/demo.db`) already has `vec_chunks` at `FLOAT[768]`; `init_db()` will NOT recreate an existing table. After this switch, live `/ask` against that old DB will fail on a 768-vs-1024 dimension mismatch until the user runs `python -m app.ingest.reembed --model bge-m3 --dim 1024` (rebuilds `vec_chunks` only). That is expected and deferred per the user's instruction.
- `.env` is gitignored — edit it locally; never commit it. `.env.example` IS committed — update its documented defaults.
- The query model is not a separate setting: `retriever.embed_one(question)` → `embedder.embed_one` → `embed_texts(model=None)` → falls back to `EMBED_MODEL`. Changing `EMBED_MODEL` covers both ingest and query. Task 2 adds a test that locks this in.

## File map

```
app/core/config.py        # MODIFY: EMBED_MODEL default + EMBED_DIM default
.env                      # MODIFY (local, gitignored): EMBED_MODEL, EMBED_DIM
.env.example              # MODIFY (committed): documented defaults
tests/test_db.py                 # MODIFY: 768 → config.EMBED_DIM (vector + query blob)
tests/test_retrieval.py          # MODIFY: seed stub 768 → config.EMBED_DIM  (leave the dim=8 reembed test)
tests/test_mindmap.py            # MODIFY
tests/test_project_folders.py    # MODIFY
tests/test_web.py                # MODIFY
tests/test_matrix.py             # MODIFY
tests/test_projects.py           # MODIFY
tests/test_drafting.py           # MODIFY
tests/test_rename.py             # MODIFY
tests/test_reingest.py           # MODIFY (two stubs)
tests/test_rag.py                # MODIFY
tests/test_pipeline.py           # MODIFY (two stubs)
tests/test_export.py             # MODIFY
tests/test_watcher.py            # MODIFY (embed stub only; leave the PDF `b"x"*1024`)
tests/test_embedder_model.py     # CREATE (Task 2 guard test)
```

---

### Task 1: Make test embedding stubs dimension-agnostic

Goal: replace every hard-coded `768` inside fake embedding stubs with `config.EMBED_DIM`, so the suite produces vectors matching whatever dimension the config is at. Done while config is still 768, so a green run proves the refactor changed nothing.

Each file gets a top-level `from app.core import config` added to its imports and its stub literal swapped to `config.EMBED_DIM`. Use attribute access (not `from ... import EMBED_DIM`) to match the existing conftest monkeypatch style and read the value live.

**Import status (checked):**
- `test_web.py` already imports it aliased at top: `from app.core import config as cfg` → in that file use **`cfg.EMBED_DIM`** and add no new import.
- `test_project_folders.py` imports `from app.core import config` but **inside a function** (line ~86); its stub is module-level, so add a **top-level** `from app.core import config`.
- All other listed files have no config import → add a top-level `from app.core import config`.

**Files & exact edits:**

- [ ] **Step 1: `tests/test_db.py`** — add `from app.core import config` to the imports, then:

Replace:
```python
        emb = [0.01] * 768
```
with:
```python
        emb = [0.01] * config.EMBED_DIM
```

Replace:
```python
            (b"".join(b"\x0a\xd7\x23\x3c" for _ in range(768)),),
```
with:
```python
            (b"".join(b"\x0a\xd7\x23\x3c" for _ in range(config.EMBED_DIM)),),
```

- [ ] **Step 2: `tests/test_retrieval.py`** — add `from app.core import config` if absent. Replace:
```python
        v = [0.0] * 768
```
with:
```python
        v = [0.0] * config.EMBED_DIM
```
**Leave** the `dim=8` reembed test untouched (`[[0.5] * 8 ...]`, `dim=8`, `FLOAT[8]` assertions): that test deliberately rebuilds the vec table at 8 dims via `reembed(..., dim=8)` and is independent of `EMBED_DIM`.

- [ ] **Step 3: `tests/test_mindmap.py`** — add `from app.core import config` if absent. Replace:
```python
    return [[1.0] + [0.0] * 767 for _ in texts]
```
with:
```python
    return [[1.0] + [0.0] * (config.EMBED_DIM - 1) for _ in texts]
```

- [ ] **Step 4: `tests/test_project_folders.py`** — add a **top-level** `from app.core import config` (the existing one is inside a function and won't be in scope for the module-level stub); replace:
```python
    return [[0.01] * 768 for _ in texts]
```
with:
```python
    return [[0.01] * config.EMBED_DIM for _ in texts]
```

- [ ] **Step 5: `tests/test_web.py`** — it already imports `from app.core import config as cfg` (no new import); replace:
```python
        v = [0.0] * 768
```
with:
```python
        v = [0.0] * cfg.EMBED_DIM
```

- [ ] **Step 6: `tests/test_matrix.py`** — add import; replace:
```python
    return [[0.01] * 768 for _ in texts]
```
with:
```python
    return [[0.01] * config.EMBED_DIM for _ in texts]
```

- [ ] **Step 7: `tests/test_projects.py`** — add import; replace:
```python
    return [[0.01] * 768 for _ in texts]
```
with:
```python
    return [[0.01] * config.EMBED_DIM for _ in texts]
```

- [ ] **Step 8: `tests/test_drafting.py`** — add a top-level `from app.core import config`; replace:
```python
    return [[1.0] + [0.0] * 767 for _ in texts]
```
with:
```python
    return [[1.0] + [0.0] * (config.EMBED_DIM - 1) for _ in texts]
```

- [ ] **Step 9: `tests/test_rename.py`** — add import; replace:
```python
    return [[0.01] * 768 for _ in texts]
```
with:
```python
    return [[0.01] * config.EMBED_DIM for _ in texts]
```

- [ ] **Step 10: `tests/test_reingest.py`** — add import; replace:
```python
    return [[0.02] * 768 for _ in texts]
```
with:
```python
    return [[0.02] * config.EMBED_DIM for _ in texts]
```
and replace:
```python
            return [[0.0] * 768]  # too few vectors (1 < n chunks)
```
with:
```python
            return [[0.0] * config.EMBED_DIM]  # too few vectors (1 < n chunks)
```

- [ ] **Step 11: `tests/test_rag.py`** — add import; replace:
```python
        v = [0.0] * 768
```
with:
```python
        v = [0.0] * config.EMBED_DIM
```
Also update the now-stale comment `# Map a few topic keywords to distinct unit-ish vectors in 768-d.` → `# Map a few topic keywords to distinct unit-ish vectors (config.EMBED_DIM-d).`

- [ ] **Step 12: `tests/test_pipeline.py`** — add import; replace BOTH occurrences (two separate stubs) of:
```python
            return [[0.001 * i] * 768 for i, _ in enumerate(texts, 1)]
```
with:
```python
            return [[0.001 * i] * config.EMBED_DIM for i, _ in enumerate(texts, 1)]
```

- [ ] **Step 13: `tests/test_export.py`** — add import; replace:
```python
        return [[0.01] * 768 for _ in texts]
```
with:
```python
        return [[0.01] * config.EMBED_DIM for _ in texts]
```

- [ ] **Step 14: `tests/test_watcher.py`** — add import; replace:
```python
            return [[0.01] * 768 for _ in texts]
```
with:
```python
            return [[0.01] * config.EMBED_DIM for _ in texts]
```
**Leave** `p.write_bytes(b"x" * 1024)` — that is fake PDF file content, not an embedding.

- [ ] **Step 15: Verify no embedding-stub `768` literals remain**

Run: `grep -rn "768\|\* 767\|767 " tests/ | grep -v "__pycache__"`
Expected: NO matches. (The `FLOAT[8]` / `dim=8` lines in test_retrieval.py are 8, not 768, and stay.)

- [ ] **Step 16: Run the full suite — proves the refactor is behavior-neutral at 768**

Run: `venv/bin/python -m pytest tests/ -q`
Expected: all PASS (same count as before — 86), because `config.EMBED_DIM` is still 768.

- [ ] **Step 17: Commit**

```bash
git add tests/
git commit -m "test: derive embedding stub dimension from config.EMBED_DIM"
```

---

### Task 2: Guard test — query path embeds with the configured model

Lock in "the query embedding also uses bge-m3" so a future regression (e.g. hard-coding a model) is caught. The test patches `httpx.Client` inside the embedder, calls `embed_one("q")` with no explicit model, and asserts the POSTed `model` equals `config.EMBED_MODEL`. Asserting against `config.EMBED_MODEL` (not a literal) keeps the test valid before and after the flip.

**Files:**
- Create: `tests/test_embedder_model.py`

- [ ] **Step 1: Write the failing test** — create `tests/test_embedder_model.py`:

```python
from unittest.mock import MagicMock, patch

from app.core import config
from app.ingest.embedder import embed_one


def test_embed_one_uses_configured_model():
    """Query embedding must go out with the configured EMBED_MODEL, so the
    query vector matches the index (e.g. both bge-m3)."""
    captured = {}

    class FakeResp:
        def raise_for_status(self): pass
        def json(self): return {"embedding": [0.0] * config.EMBED_DIM}

    class FakeClient:
        def __init__(self, *a, **k): pass
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def post(self, url, json=None):
            captured["model"] = json["model"]
            captured["url"] = url
            return FakeResp()

    with patch("app.ingest.embedder.httpx.Client", FakeClient):
        vec = embed_one("apa itu sedasi?")

    assert captured["model"] == config.EMBED_MODEL
    assert captured["url"].endswith("/api/embeddings")
    assert len(vec) == config.EMBED_DIM


def test_embed_one_respects_explicit_model_override():
    """An explicit model arg still wins (used by the reembed migration)."""
    captured = {}

    class FakeResp:
        def raise_for_status(self): pass
        def json(self): return {"embedding": [0.0] * 4}

    class FakeClient:
        def __init__(self, *a, **k): pass
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def post(self, url, json=None):
            captured["model"] = json["model"]
            return FakeResp()

    with patch("app.ingest.embedder.httpx.Client", FakeClient):
        embed_one("q", model="some-other-model")

    assert captured["model"] == "some-other-model"
```

- [ ] **Step 2: Run to verify behavior**

Run: `venv/bin/python -m pytest tests/test_embedder_model.py -v`
Expected: 2 PASS. (Both pass at the current config too — they assert against `config.EMBED_MODEL` dynamically, so this is a green guard, not a red-first. That's correct for a regression guard on existing behavior.)

- [ ] **Step 3: Commit**

```bash
git add tests/test_embedder_model.py
git commit -m "test: assert query embedding uses the configured EMBED_MODEL"
```

---

### Task 3: Flip defaults to bge-m3 / 1024 + update env files

Now the suite is dimension-agnostic, change the configured model and dimension. The same suite re-runs at 1024 and proves the system is consistent.

**Files:**
- Modify: `app/core/config.py`
- Modify: `.env` (local, gitignored)
- Modify: `.env.example` (committed)

- [ ] **Step 1: Change code defaults in `app/core/config.py`**

Replace:
```python
EMBED_MODEL = os.getenv("EMBED_MODEL", "nomic-embed-text")
```
with:
```python
EMBED_MODEL = os.getenv("EMBED_MODEL", "bge-m3")
```

Replace:
```python
EMBED_DIM = int(os.getenv("EMBED_DIM", "768"))
```
with:
```python
EMBED_DIM = int(os.getenv("EMBED_DIM", "1024"))
```

(Both defaults move together so the fallback pair stays internally consistent — nomic@1024 or bge-m3@768 would silently break vector search.)

- [ ] **Step 2: Update the local `.env`** (gitignored — do NOT commit it)

Set these two lines (leave every other line, including the API key, untouched):
```
EMBED_MODEL=bge-m3
EMBED_DIM=1024
```

Use the Edit tool on `.env`:
- `EMBED_MODEL=nomic-embed-text` → `EMBED_MODEL=bge-m3`
- `EMBED_DIM=768` → `EMBED_DIM=1024`

- [ ] **Step 3: Update `.env.example`** (committed) — change the documented embedding defaults so a fresh checkout matches the code. In `.env.example`, set:
```
EMBED_MODEL=bge-m3
EMBED_DIM=1024
```
Find the existing `EMBED_MODEL=nomic-embed-text` and `EMBED_DIM=768` lines and update them. If there is a comment like `# For bge-m3 migration (Phase 4.4): EMBED_MODEL=bge-m3 and EMBED_DIM=1024`, update it to reflect that bge-m3/1024 is now the default and nomic-embed-text/768 is the alternative.

- [ ] **Step 4: Confirm config now reports 1024 / bge-m3**

Run: `venv/bin/python -c "from app.core import config; print(config.EMBED_MODEL, config.EMBED_DIM)"`
Expected: `bge-m3 1024`

- [ ] **Step 5: Run the full suite at 1024**

Run: `venv/bin/python -m pytest tests/ -q`
Expected: all PASS (86). Fresh temp DBs now build `vec_chunks` as `FLOAT[1024]`; the dim-agnostic stubs feed 1024-length vectors; the guard test sees `model == "bge-m3"`.

- [ ] **Step 6: Confirm the vec table is created at 1024 (spot check)**

Run:
```bash
venv/bin/python -c "
import tempfile, os
from app.core.db import init_db
db = tempfile.mktemp(suffix='.db')
c = init_db(db)
print(c.execute(\"SELECT sql FROM sqlite_master WHERE name='vec_chunks'\").fetchone()[0])
c.close(); os.remove(db)
"
```
Expected: output contains `FLOAT[1024]`.

- [ ] **Step 7: Commit (code + .env.example only — NOT .env)**

```bash
git add app/core/config.py .env.example
git commit -m "feat(embed): default to bge-m3 (1024-d) for ingest and query"
```

Verify `.env` is not staged: `git status --porcelain .env` should print nothing (it is gitignored).

---

### Task 4: Update docs (CLAUDE.md + README)

Reflect the new default so future readers don't assume nomic/768.

**Files:**
- Modify: `CLAUDE.md`
- Modify: `README.md`

- [ ] **Step 1: `CLAUDE.md` invariant** — update the embed-dimension invariant line. Replace:
```
- Embed dimension must match between index and query — and between Mac and VPS (`EMBED_MODEL`/`EMBED_DIM` consistent on both; default nomic-embed-text/768). Mismatch breaks vector search.
```
with:
```
- Embed dimension must match between index and query — and between Mac and VPS (`EMBED_MODEL`/`EMBED_DIM` consistent on both; default **bge-m3 / 1024**, alt nomic-embed-text / 768). Mismatch breaks vector search. After changing the model, rebuild vectors with `python -m app.ingest.reembed --model <m> --dim <d>` (vec_chunks only) — an existing DB keeps its old `FLOAT[dim]` table until then.
```

- [ ] **Step 2: `README.md`** — update the Stack line. Replace:
```
- Embedding: Ollama `nomic-embed-text` (768-d)
```
with:
```
- Embedding: Ollama `bge-m3` (1024-d) by default; `nomic-embed-text` (768-d) supported
```

- [ ] **Step 3: Commit**

```bash
git add CLAUDE.md README.md
git commit -m "docs: bge-m3/1024 is the default embedding"
```

---

## Self-review notes

- **Spec coverage:** (a) `.env` EMBED_MODEL=bge-m3 → Task 3 Step 2; (b) code dimension constant 768→1024 → Task 3 Step 1; (c) query also uses bge-m3 → already true via shared `EMBED_MODEL`, locked by Task 2 guard test + verified Task 3 Step 4; (d) don't run ingestion → no ingest/reembed step anywhere, called out in Operational notes.
- **Why stubs first:** `.env` is `load_dotenv`-ed at import, so the dim flip takes effect inside the test process; hard-coded 768 stubs would break against `FLOAT[1024]`. Task 1 removes that coupling before the flip (Task 3), so each step's test run gives a clean signal.
- **Out of scope (deferred per user):** running `reembed`/`reingest`, migrating the existing `data/demo.db`, and the VPS-side bge-m3 pull (the README/CLAUDE VPS section already documents the Mac↔VPS consistency requirement).
- **Type consistency:** every edited stub uses the identical token `config.EMBED_DIM`; the `*767` cases become `*(config.EMBED_DIM - 1)` to preserve the "first element 1.0, rest 0.0" shape.
- **No placeholders:** every edit shows exact old→new text; the only non-literal edits (`.env`, `.env.example`) name the exact lines to change.
```
