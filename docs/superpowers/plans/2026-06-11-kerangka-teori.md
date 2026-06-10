# Kerangka Teori Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Generate a grounded theoretical-framework diagram (kerangka teori) per naskah — user pastes a research title, the system builds a cited causal graph (typed nodes + arrows) as an editable text DSL, renders it to SVG in the browser, and exports PNG.

**Architecture:** A deterministic Python generator (`framework.py`) parses the title (LLM), retrieves corpus context (`search`), builds a grounded graph (corpus nodes cited to `doc_id`+page, external nodes verified via Crossref), and persists a DSL + citations map to a new `project_framework` table (one row per project). The browser holds the DSL as source-of-truth: a pure JS compiler (`dsl.js`) turns DSL → DOT, viz.js (Graphviz WASM) renders DOT → SVG, and `framework.js` overlays citation badges and exports PNG. Mirrors the existing matrix feature's injectable-dependency + grounding discipline.

**Tech Stack:** Python 3 / FastAPI / SQLite (sqlite-vec); pytest; vanilla ES modules + `node:test` for JS; viz.js (Graphviz WASM, CDN) for rendering.

---

## File Structure

| File | Action | Responsibility |
|---|---|---|
| `app/core/db.py` | Modify | Add `project_framework` table to `SCHEMA`. |
| `app/ingest/title.py` | Modify | `crossref_lookup()` returns `doi` + `url` (additive). |
| `app/rag/framework.py` | Create | Generator: `parse_title`, `build_framework`, `load_framework`. Injectable `chat_fn`/`search_fn`/`crossref_fn`. |
| `app/web/projects_routes.py` | Modify | 3 endpoints: parse-title, build, get. |
| `app/web/static/new/dsl.js` | Create | Pure compiler: `parseDSL()`, `dslToDot()`, `slug()`. Unit-tested. |
| `app/web/static/new/framework.js` | Create | Tab view DOM: title input → confirm vars → render SVG → edit DSL → source panel → PNG export. |
| `app/web/static/new/workspace.js` | Modify | Add 5th tab "Kerangka", mount `framework.js`. |
| `app/web/templates/new.html` | Modify | Add viz.js `<script>` (Graphviz WASM CDN). |
| `app/web/static/new/new.css` | Modify | Badge + tab styles. |
| `tests/test_framework.py` | Create | Generator + endpoint tests. |
| `tests/js/dsl.test.mjs` | Create | `parseDSL` / `dslToDot` / `slug` unit tests. |
| `CLAUDE.md` | Modify | Document the feature (Web + Projects sections). |

**Do not touch:** legacy `/tools` UI, retriever, generator core, ingest pipeline.

Tasks map 1:1 to the spec's commit plan (§10). Run `source venv/bin/activate` before any pytest command.

---

### Task 1: Database table `project_framework`

**Files:**
- Modify: `app/core/db.py` (append to `SCHEMA` string, ends at `db.py:121`)
- Test: `tests/test_db.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_db.py`:

```python
def test_project_framework_table_and_cascade():
    import tempfile
    from pathlib import Path
    from app.core import projects as proj
    from app.core.db import init_db

    with tempfile.TemporaryDirectory() as td:
        conn = init_db(str(Path(td) / "t.db"))
        pid = proj.create_project(conn, "P")
        conn.execute(
            "INSERT INTO project_framework (project_id, title, dsl, citations, variables) "
            "VALUES (?, ?, ?, ?, ?)",
            (pid, "Judul", "[diteliti] A", "{}", "{}"),
        )
        conn.commit()
        row = conn.execute(
            "SELECT title, dsl FROM project_framework WHERE project_id=?", (pid,)
        ).fetchone()
        assert row == ("Judul", "[diteliti] A")

        # Upsert: second write to same project_id updates, not duplicates.
        conn.execute(
            "INSERT INTO project_framework (project_id, dsl) VALUES (?, ?) "
            "ON CONFLICT(project_id) DO UPDATE SET dsl=excluded.dsl",
            (pid, "[diteliti] B"),
        )
        conn.commit()
        assert conn.execute(
            "SELECT COUNT(*) FROM project_framework WHERE project_id=?", (pid,)
        ).fetchone()[0] == 1

        # CASCADE: deleting the project removes its framework row.
        proj.delete_project(conn, pid)
        assert conn.execute(
            "SELECT COUNT(*) FROM project_framework WHERE project_id=?", (pid,)
        ).fetchone()[0] == 0
        conn.close()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_db.py::test_project_framework_table_and_cascade -v`
Expected: FAIL with `sqlite3.OperationalError: no such table: project_framework`

- [ ] **Step 3: Add the table to `SCHEMA`**

In `app/core/db.py`, insert this block into the `SCHEMA` string, right after the `project_matrix` table definition (after `db.py:89`, before the `rename_log` comment):

```sql
-- Persisted theoretical-framework diagram: one row per project. `dsl` is the
-- editable source-of-truth; `citations` maps node label -> source (corpus or
-- external/Crossref); `variables` holds the confirmed {bebas,terikat,populasi}.
CREATE TABLE IF NOT EXISTS project_framework (
  project_id INTEGER PRIMARY KEY REFERENCES projects(id) ON DELETE CASCADE,
  title      TEXT NOT NULL DEFAULT '',
  dsl        TEXT NOT NULL DEFAULT '',
  citations  TEXT NOT NULL DEFAULT '{}',
  variables  TEXT NOT NULL DEFAULT '{}',
  updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_db.py::test_project_framework_table_and_cascade -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/core/db.py tests/test_db.py
git commit -m "feat(db): project_framework table (one row per project, CASCADE)"
```

---

### Task 2: `crossref_lookup` returns `doi` + `url`

**Files:**
- Modify: `app/ingest/title.py:85-119` (`crossref_lookup`)
- Test: `tests/test_rename.py`

This is additive — existing callers (`extract_meta`) read only `title`/`authors`/`year`, so adding keys is safe.

- [ ] **Step 1: Write the failing test**

Add to `tests/test_rename.py`:

```python
def test_crossref_lookup_includes_doi_and_url():
    from unittest.mock import patch, MagicMock
    from app.ingest.title import crossref_lookup

    fake_json = {
        "message": {
            "items": [{
                "title": ["Glycocalyx degradation in sepsis"],
                "author": [{"given": "D", "family": "Chappell"}],
                "issued": {"date-parts": [[2008]]},
                "DOI": "10.1234/abcd",
            }]
        }
    }
    resp = MagicMock()
    resp.json.return_value = fake_json
    resp.raise_for_status.return_value = None
    with patch("httpx.get", return_value=resp):
        out = crossref_lookup("glycocalyx sepsis")
    assert out["title"] == "Glycocalyx degradation in sepsis"
    assert out["year"] == 2008
    assert out["doi"] == "10.1234/abcd"
    assert out["url"] == "https://doi.org/10.1234/abcd"


def test_crossref_lookup_missing_doi_yields_none_doi_url():
    from unittest.mock import patch, MagicMock
    from app.ingest.title import crossref_lookup

    fake_json = {"message": {"items": [{"title": ["No DOI paper"]}]}}
    resp = MagicMock()
    resp.json.return_value = fake_json
    resp.raise_for_status.return_value = None
    with patch("httpx.get", return_value=resp):
        out = crossref_lookup("no doi")
    assert out["doi"] is None
    assert out["url"] is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_rename.py::test_crossref_lookup_includes_doi_and_url -v`
Expected: FAIL with `KeyError: 'doi'`

- [ ] **Step 3: Add `doi`/`url` to the return dict**

In `app/ingest/title.py`, replace the final return inside `crossref_lookup` (currently `return {"title": title, "authors": authors, "year": year}` at `title.py:117`). First, just before that return, derive the DOI/URL:

```python
        doi = it.get("DOI") or None
        url = (f"https://doi.org/{doi}" if doi else None)
        return {"title": title, "authors": authors, "year": year, "doi": doi, "url": url}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_rename.py::test_crossref_lookup_includes_doi_and_url tests/test_rename.py::test_crossref_lookup_missing_doi_yields_none_doi_url -v`
Expected: PASS (both)

- [ ] **Step 5: Run the full rename suite to confirm no regression**

Run: `python -m pytest tests/test_rename.py -v`
Expected: PASS (all)

- [ ] **Step 6: Commit**

```bash
git add app/ingest/title.py tests/test_rename.py
git commit -m "feat(title): crossref_lookup returns doi + url (additive)"
```

---

### Task 3: Generator `framework.py` — `parse_title`

**Files:**
- Create: `app/rag/framework.py`
- Test: `tests/test_framework.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_framework.py`:

```python
import json
import tempfile
from pathlib import Path

from app.rag import framework


def test_parse_title_extracts_variables():
    def fake_chat(system, user):
        return json.dumps({
            "bebas": ["Dosis norepinefrin", "Gula darah sewaktu"],
            "terikat": "Syndecan-1",
            "populasi": "pasien sepsis",
        })

    out = framework.parse_title(
        "Pengaruh dosis norepinefrin dan gula darah terhadap syndecan-1 pada pasien sepsis",
        chat_fn=fake_chat,
    )
    assert out["bebas"] == ["Dosis norepinefrin", "Gula darah sewaktu"]
    assert out["terikat"] == "Syndecan-1"
    assert out["populasi"] == "pasien sepsis"


def test_parse_title_malformed_json_is_fail_safe():
    def fake_chat(system, user):
        return "maaf saya tidak bisa"

    out = framework.parse_title("judul apa pun", chat_fn=fake_chat)
    assert out == {"bebas": [], "terikat": "", "populasi": ""}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_framework.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.rag.framework'`

- [ ] **Step 3: Create the module with `parse_title` + shared helpers**

Create `app/rag/framework.py`:

```python
"""Kerangka teori (theoretical framework) generator.

Builds a grounded causal graph from a research title, obeying the project's
Core Principles: NOT LLM-driven. Every corpus node is cited to a real
doc_id + page; a node claimed `src:korpus` without a supporting doc_id is
REJECTED at assembly. External citations never come from LLM memory — always
through Crossref.

All dependencies are injectable so the generator is testable without a live
model or network: `chat_fn`, `search_fn`, `crossref_fn`.
"""

import json
from typing import Any, Callable, Dict, List, Optional

from app.rag.generator import chat
from app.rag.retriever import search
from app.ingest.title import crossref_lookup

# ---- Prompts (Bahasa Indonesia, module constants) ----

PARSE_TITLE_SYS = (
    "Ekstrak variabel bebas (daftar), terikat (satu), dan populasi dari judul "
    "penelitian. Kembalikan HANYA JSON {\"bebas\":[],\"terikat\":\"\",\"populasi\":\"\"}. "
    "Jangan mengarang variabel yang tidak ada di judul."
)

BACKBONE_SYS = (
    "Susun rantai mekanistik antar variabel HANYA dari KONTEKS yang diberikan. "
    "Tiap node sertakan: label (ringkas), relasi (memicu|menghambat), dari (label "
    "asal), ke (label tujuan), src_idx (indeks sumber konteks yang mendukung). "
    "Kembalikan HANYA JSON array. Jangan pakai pengetahuan di luar KONTEKS. "
    "Jika konteks tak cukup, kembalikan []."
)

EXTERNAL_SYS = (
    "Usulkan faktor latar relevan yang TIDAK ada di konteks korpus (pengetahuan "
    "domain). Tiap usulan: label, relasi (memicu|menghambat), target (label tujuan). "
    "Kembalikan HANYA JSON array. Usulan ini akan diverifikasi ke Crossref — "
    "jangan mengarang referensi atau sitasi."
)


def _parse_json(raw: str) -> Any:
    """Strip code-fence then load JSON; fail-safe to None on error (matrix.py pattern)."""
    raw = (raw or "").strip()
    if raw.startswith("```"):
        raw = raw.strip("`")
        if raw[:4].lower() == "json":
            raw = raw[4:]
    # Try object first, then array.
    for open_c, close_c in (("{", "}"), ("[", "]")):
        start, end = raw.find(open_c), raw.rfind(close_c)
        if start != -1 and end != -1 and end > start:
            try:
                return json.loads(raw[start : end + 1])
            except Exception:
                continue
    return None


def parse_title(title: str, chat_fn: Optional[Callable] = None) -> Dict[str, Any]:
    """Title -> {"bebas":[str], "terikat":str, "populasi":str}. Fail-safe to empties.

    `chat_fn` is resolved at CALL time (default `chat`) so endpoint tests can
    patch `app.rag.framework.chat`. Passing it explicitly bypasses the module
    global (used by the generator unit tests)."""
    chat_fn = chat_fn or chat
    obj = _parse_json(chat_fn(PARSE_TITLE_SYS, f"JUDUL: {title}\n\nKeluarkan JSON."))
    if not isinstance(obj, dict):
        return {"bebas": [], "terikat": "", "populasi": ""}
    bebas = obj.get("bebas") or []
    if isinstance(bebas, str):
        bebas = [bebas]
    return {
        "bebas": [str(b).strip() for b in bebas if str(b).strip()],
        "terikat": str(obj.get("terikat") or "").strip(),
        "populasi": str(obj.get("populasi") or "").strip(),
    }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_framework.py -v`
Expected: PASS (both `parse_title` tests)

- [ ] **Step 5: Commit**

```bash
git add app/rag/framework.py tests/test_framework.py
git commit -m "feat(framework): parse_title + prompts + json helper"
```

---

### Task 4: Generator `framework.py` — `build_framework` + `load_framework`

**Files:**
- Modify: `app/rag/framework.py`
- Test: `tests/test_framework.py`

The algorithm (spec §4.2): resolve `doc_ids` → emit `[diteliti]` nodes for vars → ask LLM for a corpus-grounded backbone (`[latar*]` mediators cited to a Hit) → ask LLM for external `[latar]` factors verified via Crossref → reject any corpus node whose `src_idx` is out of range → assemble DSL + citations → upsert.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_framework.py`:

```python
import fitz
from unittest.mock import patch
from app.core import config
from app.core import projects as proj
from app.core.db import init_db
from app.ingest.pipeline import ingest_pdf


def _mk(path: Path, text: str, pages: int = 2):
    doc = fitz.open()
    for i in range(pages):
        page = doc.new_page()
        page.insert_text((72, 72), f"{text} Page {i + 1}", fontsize=10)
    doc.save(str(path))
    doc.close()


def _embed_stub(texts, model=None, base_url=None):
    return [[0.01] * config.EMBED_DIM for _ in texts]


class _FakeHit:
    def __init__(self, doc_id, title, ps, pe):
        self.doc_id, self.title, self.page_start, self.page_end = doc_id, title, ps, pe


def _seed_project(td: Path):
    conn = init_db(str(td / "t.db"))
    a = td / "p.pdf"
    _mk(a, "glycocalyx degradation in sepsis norepinephrine")
    with patch("app.ingest.pipeline.embed_texts", side_effect=_embed_stub):
        ingest_pdf(a, conn=conn)
    doc_id = conn.execute("SELECT id FROM documents").fetchone()[0]
    pid = proj.create_project(conn, "P")
    proj.add_papers(conn, pid, [doc_id])
    return conn, pid, doc_id


def _vars():
    return {"bebas": ["Dosis norepinefrin"], "terikat": "Syndecan-1", "populasi": "sepsis"}


def test_build_framework_grounds_corpus_node_and_verifies_external():
    with tempfile.TemporaryDirectory() as td:
        conn, pid, doc_id = _seed_project(Path(td))

        def fake_search(q, top_k=6, filters=None, conn=None):
            return [_FakeHit(doc_id, "Sepsis paper", 7, 7)]

        calls = {"n": 0}
        def fake_chat(system, user):
            calls["n"] += 1
            if system == framework.BACKBONE_SYS:
                return json.dumps([{
                    "label": "Kerusakan glikokaliks", "relasi": "memicu",
                    "dari": "Dosis norepinefrin", "ke": "Syndecan-1", "src_idx": 0,
                }])
            if system == framework.EXTERNAL_SYS:
                return json.dumps([{
                    "label": "ROS", "relasi": "memicu", "target": "Kerusakan glikokaliks",
                }])
            return "[]"

        def fake_crossref(query, timeout=6.0):
            return {"title": "The endothelial glycocalyx", "authors": ["Chappell D"],
                    "year": 2008, "doi": "10.1/x", "url": "https://doi.org/10.1/x"}

        out = framework.build_framework(
            conn, pid, _vars(),
            chat_fn=fake_chat, search_fn=fake_search, crossref_fn=fake_crossref,
        )
        # Diteliti nodes present in DSL.
        assert "[diteliti] Dosis norepinefrin" in out["dsl"]
        assert "[diteliti] Syndecan-1" in out["dsl"]
        # Corpus mediator node is [latar*] and cited to doc_id+page.
        assert "[latar*] Kerusakan glikokaliks" in out["dsl"]
        cit = out["citations"]["Kerusakan glikokaliks"]
        assert cit["src"] == "korpus" and cit["doc_id"] == doc_id and cit["page"] == 7
        # External node verified via Crossref -> perlu_verifikasi + ref.
        ros = out["citations"]["ROS"]
        assert ros["src"] == "eksternal" and ros["status"] == "perlu_verifikasi"
        assert ros["ref"]["doi"] == "10.1/x"
        # Edges present.
        assert "Dosis norepinefrin -> Kerusakan glikokaliks : memicu" in out["dsl"]
        conn.close()


def test_build_framework_external_miss_is_unverified_not_dropped():
    with tempfile.TemporaryDirectory() as td:
        conn, pid, doc_id = _seed_project(Path(td))

        def fake_search(q, top_k=6, filters=None, conn=None):
            return []

        def fake_chat(system, user):
            if system == framework.EXTERNAL_SYS:
                return json.dumps([{"label": "Albumin", "relasi": "menghambat",
                                    "target": "Syndecan-1"}])
            return "[]"

        def fake_crossref(query, timeout=6.0):
            return None  # no hit

        out = framework.build_framework(
            conn, pid, _vars(),
            chat_fn=fake_chat, search_fn=fake_search, crossref_fn=fake_crossref,
        )
        alb = out["citations"]["Albumin"]
        assert alb["src"] == "eksternal" and alb["status"] == "tak_terverifikasi"
        assert alb["ref"] is None
        assert "[latar] Albumin" in out["dsl"]  # still created, not silently dropped
        conn.close()


def test_build_framework_rejects_out_of_range_src_idx():
    with tempfile.TemporaryDirectory() as td:
        conn, pid, doc_id = _seed_project(Path(td))

        def fake_search(q, top_k=6, filters=None, conn=None):
            return [_FakeHit(doc_id, "Sepsis paper", 7, 7)]  # only index 0 valid

        def fake_chat(system, user):
            if system == framework.BACKBONE_SYS:
                return json.dumps([{
                    "label": "Node hantu", "relasi": "memicu",
                    "dari": "Dosis norepinefrin", "ke": "Syndecan-1", "src_idx": 5,
                }])
            return "[]"

        out = framework.build_framework(
            conn, pid, _vars(),
            chat_fn=fake_chat, search_fn=fake_search, crossref_fn=lambda q, timeout=6.0: None,
        )
        # Out-of-range src_idx node rejected: not in DSL, no citation, no edge.
        assert "Node hantu" not in out["dsl"]
        assert "Node hantu" not in out["citations"]
        conn.close()


def test_build_framework_no_papers_raises():
    with tempfile.TemporaryDirectory() as td:
        conn = init_db(str(Path(td) / "t.db"))
        pid = proj.create_project(conn, "Empty")
        try:
            framework.build_framework(
                conn, pid, _vars(),
                chat_fn=lambda s, u: "[]", search_fn=lambda *a, **k: [],
                crossref_fn=lambda q, timeout=6.0: None,
            )
            assert False, "expected ValueError"
        except ValueError as e:
            assert "naskah tanpa paper" in str(e)
        conn.close()


def test_build_framework_persist_load_roundtrip_and_upsert():
    with tempfile.TemporaryDirectory() as td:
        conn, pid, doc_id = _seed_project(Path(td))
        deps = dict(chat_fn=lambda s, u: "[]",
                    search_fn=lambda *a, **k: [],
                    crossref_fn=lambda q, timeout=6.0: None)
        framework.build_framework(conn, pid, _vars(), **deps)
        loaded = framework.load_framework(conn, pid)
        assert loaded is not None
        assert "[diteliti] Dosis norepinefrin" in loaded["dsl"]
        assert loaded["variables"]["terikat"] == "Syndecan-1"
        # Upsert: build twice -> still one row.
        framework.build_framework(conn, pid, _vars(), **deps)
        assert conn.execute(
            "SELECT COUNT(*) FROM project_framework WHERE project_id=?", (pid,)
        ).fetchone()[0] == 1
        conn.close()


def test_load_framework_none_after_project_delete():
    with tempfile.TemporaryDirectory() as td:
        conn, pid, doc_id = _seed_project(Path(td))
        framework.build_framework(
            conn, pid, _vars(),
            chat_fn=lambda s, u: "[]", search_fn=lambda *a, **k: [],
            crossref_fn=lambda q, timeout=6.0: None)
        proj.delete_project(conn, pid)
        assert framework.load_framework(conn, pid) is None
        conn.close()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_framework.py -v`
Expected: FAIL with `AttributeError: module 'app.rag.framework' has no attribute 'build_framework'`

- [ ] **Step 3: Implement `build_framework` + `load_framework`**

Append to `app/rag/framework.py`:

```python
# ---- DSL assembly helpers ----

def _node_line(kind: str, label: str) -> str:
    return f"[{kind}] {label}"


def _edge_line(frm: str, to: str, reltype: str) -> str:
    arrow = "-|" if reltype == "menghambat" else "->"
    return f"{frm} {arrow} {to} : {reltype}"


def _reltype(raw: Optional[str]) -> str:
    return "menghambat" if str(raw or "").strip().lower() == "menghambat" else "memicu"


def build_framework(
    conn,
    project_id: int,
    variables: Dict[str, Any],
    chat_fn: Optional[Callable] = None,
    search_fn: Optional[Callable] = None,
    crossref_fn: Optional[Callable] = None,
) -> Dict[str, Any]:
    """Build a grounded framework, persist it, and return {dsl, citations, variables}.

    Deps resolve at CALL time (defaults `chat`/`search`/`crossref_lookup`) so the
    endpoint route — which calls this with no deps — picks up patched module
    globals in tests; generator unit tests pass stubs explicitly."""
    from app.core.projects import project_doc_ids

    chat_fn = chat_fn or chat
    search_fn = search_fn or search
    crossref_fn = crossref_fn or crossref_lookup

    doc_ids = project_doc_ids(conn, project_id)
    if not doc_ids:
        raise ValueError("naskah tanpa paper")

    bebas = [str(b).strip() for b in (variables.get("bebas") or []) if str(b).strip()]
    terikat = str(variables.get("terikat") or "").strip()
    diteliti = bebas + ([terikat] if terikat else [])

    # Ordered node declarations + per-label kind, plus citations + edges.
    nodes: Dict[str, str] = {}  # label -> kind (last write wins; diteliti is set first)
    order: List[str] = []       # preserve first-seen order
    citations: Dict[str, Any] = {}
    edges: List[tuple] = []     # (from, to, reltype)

    def add_node(label: str, kind: str) -> None:
        label = label.strip()
        if not label:
            return
        if label not in nodes:
            order.append(label)
        nodes[label] = kind

    for v in diteliti:
        add_node(v, "diteliti")

    # --- Backbone: corpus-grounded mediators between each bebas and terikat ---
    for src_var in bebas:
        if not terikat:
            break
        query = f"{src_var} {terikat}"
        try:
            hits = search_fn(query, top_k=6, filters={"doc_ids": doc_ids}, conn=conn)
        except Exception:
            hits = []
        chain = _parse_json(chat_fn(
            BACKBONE_SYS,
            _backbone_prompt(src_var, terikat, hits),
        )) or []
        if not isinstance(chain, list):
            chain = []
        for item in chain:
            if not isinstance(item, dict):
                continue
            label = str(item.get("label") or "").strip()
            src_idx = item.get("src_idx")
            # Guard: corpus node must cite a real Hit (in-range index).
            if not label or not isinstance(src_idx, int) or not (0 <= src_idx < len(hits)):
                continue  # rejected (anti-hallucination); skip node + its edges
            hit = hits[src_idx]
            page = hit.page_start
            if page is None:
                continue
            add_node(label, "latar*")
            citations[label] = {
                "src": "korpus", "doc_id": hit.doc_id, "page": page,
                "title": getattr(hit, "title", None) or "",
                "quote": "",
            }
            frm = str(item.get("dari") or src_var).strip()
            to = str(item.get("ke") or terikat).strip()
            rel = _reltype(item.get("relasi"))
            edges.append((frm, to, rel))

    # --- External latar factors, verified via Crossref ---
    proposals = _parse_json(chat_fn(EXTERNAL_SYS, _external_prompt(diteliti))) or []
    if not isinstance(proposals, list):
        proposals = []
    for item in proposals:
        if not isinstance(item, dict):
            continue
        label = str(item.get("label") or "").strip()
        target = str(item.get("target") or "").strip()
        if not label or not target:
            continue
        ref = None
        try:
            ref = crossref_fn(label)
        except Exception:
            ref = None
        if ref and ref.get("title"):
            citations[label] = {
                "src": "eksternal", "status": "perlu_verifikasi",
                "ref": {"title": ref.get("title"), "authors": ref.get("authors") or [],
                        "year": ref.get("year"), "doi": ref.get("doi"),
                        "url": ref.get("url")},
            }
        else:
            citations[label] = {"src": "eksternal", "status": "tak_terverifikasi", "ref": None}
        add_node(label, "latar")
        edges.append((label, target, _reltype(item.get("relasi"))))

    # --- Drop edges whose endpoints were never created as nodes (rejected) ---
    valid = set(nodes)
    edges = [(f, t, r) for (f, t, r) in edges if f in valid and t in valid]

    dsl = _assemble_dsl(order, nodes, edges)

    payload_vars = {"bebas": bebas, "terikat": terikat,
                    "populasi": str(variables.get("populasi") or "").strip()}
    conn.execute(
        "INSERT INTO project_framework (project_id, title, dsl, citations, variables, updated_at) "
        "VALUES (?, ?, ?, ?, ?, datetime('now')) "
        "ON CONFLICT(project_id) DO UPDATE SET title=excluded.title, dsl=excluded.dsl, "
        "citations=excluded.citations, variables=excluded.variables, updated_at=excluded.updated_at",
        (project_id, str(variables.get("title") or ""), dsl,
         json.dumps(citations, ensure_ascii=False),
         json.dumps(payload_vars, ensure_ascii=False)),
    )
    conn.commit()
    return {"dsl": dsl, "citations": citations, "variables": payload_vars}


def _backbone_prompt(src_var: str, terikat: str, hits: List[Any]) -> str:
    ctx = "\n\n".join(
        f"[{i}] (hlm {getattr(h, 'page_start', '?')}) {getattr(h, 'title', '') or ''}"
        for i, h in enumerate(hits)
    ) or "(konteks kosong)"
    return (
        f"VARIABEL ASAL: {src_var}\nVARIABEL TUJUAN: {terikat}\n\n"
        f"KONTEKS (tiap entri diawali indeks sumber):\n{ctx}\n\n"
        f"Keluarkan JSON array node rantai mekanistik."
    )


def _external_prompt(diteliti: List[str]) -> str:
    return (
        f"VARIABEL DITELITI: {', '.join(diteliti)}\n\n"
        f"Usulkan faktor latar yang relevan namun TIDAK ada di korpus. "
        f"Keluarkan JSON array."
    )


def _assemble_dsl(order: List[str], nodes: Dict[str, str], edges: List[tuple]) -> str:
    """Emit node declarations (diteliti -> latar* -> latar) then edges."""
    lines: List[str] = []
    for kind in ("diteliti", "latar*", "latar"):
        for label in order:
            if nodes.get(label) == kind:
                lines.append(_node_line(kind, label))
    if edges:
        lines.append("")
        for frm, to, rel in edges:
            lines.append(_edge_line(frm, to, rel))
    return "\n".join(lines)


def load_framework(conn, project_id: int) -> Optional[Dict[str, Any]]:
    """Return the persisted framework or None if the project has none."""
    row = conn.execute(
        "SELECT dsl, citations, variables, title, updated_at "
        "FROM project_framework WHERE project_id = ?",
        (project_id,),
    ).fetchone()
    if not row:
        return None
    return {
        "dsl": row[0],
        "citations": json.loads(row[1] or "{}"),
        "variables": json.loads(row[2] or "{}"),
        "title": row[3] or "",
        "updated_at": row[4],
    }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_framework.py -v`
Expected: PASS (all generator tests)

- [ ] **Step 5: Commit**

```bash
git add app/rag/framework.py tests/test_framework.py
git commit -m "feat(framework): grounded build_framework + load_framework"
```

---

### Task 5: Endpoints — parse-title, build, get

**Files:**
- Modify: `app/web/projects_routes.py` (add 3 routes, follow the `/matrix` pattern at `projects_routes.py:195-227`)
- Test: `tests/test_framework.py`

- [ ] **Step 1: Write the failing endpoint tests**

Add to `tests/test_framework.py`. These build a FastAPI `TestClient` over a temp DB (mirrors `tests/test_web.py`) and patch the generator's injected functions so no model/network is hit:

```python
def _client(monkeypatch, td):
    db = str(Path(td) / "web.db")
    from app.core import config as cfg
    monkeypatch.setattr(cfg, "DB_PATH", db)
    import app.core.db as dbmod
    monkeypatch.setattr(dbmod, "DB_PATH", db)
    from fastapi.testclient import TestClient
    from app.web.app import create_app
    return TestClient(create_app()), db


def test_endpoint_parse_title_422_on_empty(monkeypatch):
    with tempfile.TemporaryDirectory() as td:
        client, _ = _client(monkeypatch, td)
        from app.core.db import connect
        conn = connect(); pid = proj.create_project(conn, "P"); conn.close()
        r = client.post(f"/projects/{pid}/framework/parse-title", json={"title": ""})
        assert r.status_code == 422


def test_endpoint_parse_title_ok(monkeypatch):
    with tempfile.TemporaryDirectory() as td:
        client, _ = _client(monkeypatch, td)
        from app.core.db import connect
        conn = connect(); pid = proj.create_project(conn, "P"); conn.close()
        with patch("app.rag.framework.chat", lambda s, u: json.dumps(
                {"bebas": ["A"], "terikat": "B", "populasi": "P"})):
            r = client.post(f"/projects/{pid}/framework/parse-title", json={"title": "judul"})
        assert r.status_code == 200
        assert r.json()["variables"]["terikat"] == "B"


def test_endpoint_build_400_without_papers(monkeypatch):
    with tempfile.TemporaryDirectory() as td:
        client, _ = _client(monkeypatch, td)
        from app.core.db import connect
        conn = connect(); pid = proj.create_project(conn, "P"); conn.close()
        r = client.post(f"/projects/{pid}/framework",
                        json={"variables": _vars(), "title": "judul"})
        assert r.status_code == 400
        assert "naskah tanpa paper" in r.json()["detail"]


def test_endpoint_get_empty_is_not_404(monkeypatch):
    with tempfile.TemporaryDirectory() as td:
        client, _ = _client(monkeypatch, td)
        from app.core.db import connect
        conn = connect(); pid = proj.create_project(conn, "P"); conn.close()
        r = client.get(f"/projects/{pid}/framework")
        assert r.status_code == 200
        body = r.json()
        assert body == {"dsl": "", "citations": {}, "variables": {},
                        "title": "", "updated_at": None}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_framework.py -k endpoint -v`
Expected: FAIL with `404` (routes not registered)

- [ ] **Step 3: Add the three routes**

In `app/web/projects_routes.py`, add request models near the other `BaseModel` declarations (after `MatrixRequest` at `projects_routes.py:190-192`):

```python
class ParseTitleRequest(BaseModel):
    title: str = Field("", min_length=0)


class FrameworkRequest(BaseModel):
    variables: Dict[str, Any] = Field(default_factory=dict)
    title: str = ""
```

Then add the routes (place them after the matrix routes, before the codebook section at `projects_routes.py:272`):

```python
@router.post("/{project_id}/framework/parse-title")
def framework_parse_title(project_id: int, req: ParseTitleRequest) -> JSONResponse:
    from app.rag.framework import parse_title

    if not (req.title or "").strip():
        raise HTTPException(422, "title kosong")
    conn = connect()
    try:
        if not proj.get_project(conn, project_id):
            raise HTTPException(404, "project not found")
        try:
            variables = parse_title(req.title)
        except RuntimeError as e:  # missing LLM key etc.
            raise HTTPException(503, str(e))
        return JSONResponse({"variables": variables})
    finally:
        conn.close()


@router.post("/{project_id}/framework")
def framework_build(project_id: int, req: FrameworkRequest) -> JSONResponse:
    from app.rag.framework import build_framework

    conn = connect()
    try:
        if not proj.get_project(conn, project_id):
            raise HTTPException(404, "project not found")
        variables = dict(req.variables)
        variables["title"] = req.title
        try:
            out = build_framework(conn, project_id, variables)
        except ValueError as e:  # naskah tanpa paper
            raise HTTPException(400, str(e))
        except RuntimeError as e:
            raise HTTPException(503, str(e))
        return JSONResponse(out)
    finally:
        conn.close()


@router.get("/{project_id}/framework")
def framework_get(project_id: int) -> JSONResponse:
    from app.rag.framework import load_framework

    conn = connect()
    try:
        if not proj.get_project(conn, project_id):
            raise HTTPException(404, "project not found")
        out = load_framework(conn, project_id)
        if out is None:
            out = {"dsl": "", "citations": {}, "variables": {}, "title": "", "updated_at": None}
        return JSONResponse(out)
    finally:
        conn.close()
```

Note: `Dict` and `Any` are already imported at `projects_routes.py:6`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_framework.py -k endpoint -v`
Expected: PASS (all 4 endpoint tests)

- [ ] **Step 5: Run the full framework + projects suites**

Run: `python -m pytest tests/test_framework.py tests/test_projects.py -v`
Expected: PASS (all)

- [ ] **Step 6: Commit**

```bash
git add app/web/projects_routes.py tests/test_framework.py
git commit -m "feat(web): framework parse-title/build/get endpoints"
```

---

### Task 6: `dsl.js` compiler + unit tests

**Files:**
- Create: `app/web/static/new/dsl.js`
- Test: `tests/js/dsl.test.mjs`

`parseDSL(text)` → `{ nodes:[{label,kind,implicit}], edges:[{from,to,type}], errors:[{line,col,msg}] }`.
`dslToDot(parsed, citations)` → DOT string. `slug(label)` → deterministic id, shared by DOT emission and badge overlay.

- [ ] **Step 1: Write the failing tests**

Create `tests/js/dsl.test.mjs`:

```javascript
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { parseDSL, dslToDot, slug } from '../../app/web/static/new/dsl.js';

test('parseDSL reads the three node kinds', () => {
  const p = parseDSL('[diteliti] A\n[latar] B\n[latar*] C');
  assert.equal(p.errors.length, 0);
  const byLabel = Object.fromEntries(p.nodes.map(n => [n.label, n.kind]));
  assert.equal(byLabel['A'], 'diteliti');
  assert.equal(byLabel['B'], 'latar');
  assert.equal(byLabel['C'], 'latar*');
});

test('parseDSL: -> defaults to memicu, -| is menghambat', () => {
  const p = parseDSL('[diteliti] A\n[diteliti] B\nA -> B\nB -| A');
  const types = p.edges.map(e => e.type);
  assert.deepEqual(types, ['memicu', 'menghambat']);
});

test('parseDSL: -> with : menghambat resolves to menghambat', () => {
  const p = parseDSL('[diteliti] A\n[diteliti] B\nA -> B : menghambat');
  assert.equal(p.edges[0].type, 'menghambat');
});

test('parseDSL: -| with : memicu is a parse error (contradiction)', () => {
  const p = parseDSL('[diteliti] A\n[diteliti] B\nA -| B : memicu');
  assert.equal(p.edges.length, 0);
  assert.equal(p.errors.length, 1);
  assert.equal(p.errors[0].line, 3);
  assert.match(p.errors[0].msg, /kontradiksi/i);
});

test('parseDSL ignores comments and blank lines', () => {
  const p = parseDSL('# judul\n\n[diteliti] A\n   \n# komentar');
  assert.equal(p.nodes.length, 1);
  assert.equal(p.errors.length, 0);
});

test('parseDSL makes an implicit [latar] node for an edge-only label', () => {
  const p = parseDSL('[diteliti] A\nA -> Z');
  const z = p.nodes.find(n => n.label === 'Z');
  assert.ok(z, 'Z node created');
  assert.equal(z.kind, 'latar');
  assert.equal(z.implicit, true);
});

test('parseDSL merges duplicate labels (label is identity)', () => {
  const p = parseDSL('[diteliti] A\n[latar] A');
  assert.equal(p.nodes.filter(n => n.label === 'A').length, 1);
});

test('parseDSL reports line+col for a malformed node decl', () => {
  const p = parseDSL('[salah] A');
  assert.equal(p.errors.length, 1);
  assert.equal(p.errors[0].line, 1);
  assert.ok(typeof p.errors[0].col === 'number');
});

test('dslToDot styles diteliti bold, latar dashed', () => {
  const dot = dslToDot(parseDSL('[diteliti] A\n[latar] B'), {});
  assert.match(dot, /penwidth=2\.5/);
  assert.match(dot, /style=dashed/);
});

test('dslToDot colors memicu red and menghambat blue with diamond', () => {
  const dot = dslToDot(parseDSL('[diteliti] A\n[diteliti] B\nA -> B\nB -| A'), {});
  assert.match(dot, /color="#c0392b"/);          // memicu red
  assert.match(dot, /color="#2c5fa8"/);          // menghambat blue
  assert.match(dot, /arrowhead=diamond/);
});

test('dslToDot escapes double quotes in labels (DOT injection guard)', () => {
  const dot = dslToDot(parseDSL('[diteliti] He said "hi"'), {});
  assert.ok(!/[^\\]"hi"/.test(dot), 'inner quotes must be escaped');
  assert.match(dot, /\\"hi\\"/);
});

test('dslToDot emits a stable id per node, matching slug()', () => {
  const dot = dslToDot(parseDSL('[diteliti] ↑ ROS'), {});
  assert.match(dot, new RegExp(`id="node-${slug('↑ ROS')}"`));
});

test('slug is deterministic and reversible-enough for distinct labels', () => {
  assert.equal(slug('↑ ROS'), slug('↑ ROS'));
  assert.notEqual(slug('A'), slug('B'));
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `node --test tests/js/dsl.test.mjs`
Expected: FAIL with `Cannot find module '.../dsl.js'`

- [ ] **Step 3: Implement `dsl.js`**

Create `app/web/static/new/dsl.js`:

```javascript
// DSL compiler for kerangka teori. Pure (DOM-free) so it is unit-testable under
// node:test. parseDSL is the source-of-truth reader; dslToDot emits Graphviz DOT.

const KINDS = new Set(["diteliti", "latar", "latar*"]);

// Deterministic id from a label: keep [A-Za-z0-9], map everything else to its
// code point in hex. Shared by DOT emission AND badge overlay so ids round-trip.
export function slug(label) {
  let out = "";
  for (const ch of String(label)) {
    out += /[A-Za-z0-9]/.test(ch) ? ch : "_" + ch.codePointAt(0).toString(16);
  }
  return out || "_empty";
}

function dotEscape(label) {
  return String(label).replace(/\\/g, "\\\\").replace(/"/g, '\\"').replace(/[\r\n]+/g, " ");
}

// Resolve edge type from arrow + optional ": reltype". Returns {type} or {error}.
function resolveEdge(arrow, suffix) {
  const rel = (suffix || "").trim().toLowerCase();
  if (arrow === "-|") {
    if (rel === "memicu") return { error: "kontradiksi: -| tidak boleh : memicu" };
    return { type: "menghambat" };
  }
  // arrow === "->"
  if (rel === "menghambat") return { type: "menghambat" };
  return { type: "memicu" };
}

export function parseDSL(text) {
  const nodes = new Map();   // label -> {label, kind, implicit}
  const edges = [];
  const errors = [];

  const ensure = (label, kind, implicit) => {
    label = label.trim();
    if (!label) return;
    const existing = nodes.get(label);
    if (existing) {
      // Explicit decl upgrades an implicit node's kind.
      if (!implicit) { existing.kind = kind; existing.implicit = false; }
      return;
    }
    nodes.set(label, { label, kind, implicit: !!implicit });
  };

  const lines = String(text || "").split(/\r?\n/);
  lines.forEach((raw, i) => {
    const lineNo = i + 1;
    const line = raw.trim();
    if (!line || line.startsWith("#")) return;

    // Node decl: starts with "[kind]".
    if (line.startsWith("[")) {
      const close = line.indexOf("]");
      if (close === -1) {
        errors.push({ line: lineNo, col: 1, msg: "kurung ']' tidak ditemukan" });
        return;
      }
      const kind = line.slice(1, close).trim();
      const label = line.slice(close + 1).trim();
      if (!KINDS.has(kind)) {
        errors.push({ line: lineNo, col: 2, msg: `jenis node tidak dikenal: ${kind}` });
        return;
      }
      if (!label) {
        errors.push({ line: lineNo, col: close + 2, msg: "label node kosong" });
        return;
      }
      ensure(label, kind, false);
      return;
    }

    // Edge decl: "<label> <arrow> <label> [: reltype]".
    const arrowIdx = line.search(/->|-\|/);
    if (arrowIdx === -1) {
      errors.push({ line: lineNo, col: 1, msg: "baris bukan node maupun panah" });
      return;
    }
    const arrow = line.substr(arrowIdx, 2);
    const from = line.slice(0, arrowIdx).trim();
    let rest = line.slice(arrowIdx + 2).trim();
    let suffix = "";
    const colon = rest.lastIndexOf(":");
    if (colon !== -1) {
      suffix = rest.slice(colon + 1);
      rest = rest.slice(0, colon).trim();
    }
    const to = rest.trim();
    if (!from || !to) {
      errors.push({ line: lineNo, col: 1, msg: "panah perlu label asal dan tujuan" });
      return;
    }
    const resolved = resolveEdge(arrow, suffix);
    if (resolved.error) {
      errors.push({ line: lineNo, col: arrowIdx + 1, msg: resolved.error });
      return;
    }
    ensure(from, "latar", true);
    ensure(to, "latar", true);
    edges.push({ from, to, type: resolved.type });
  });

  return { nodes: [...nodes.values()], edges, errors };
}

export function dslToDot(parsed, citations = {}) {
  const lines = [
    "digraph G {",
    '  rankdir=TB;',
    '  node [shape=box, fontname="Inter"];',
  ];
  for (const n of parsed.nodes) {
    const id = `id="node-${slug(n.label)}"`;
    let style;
    if (n.kind === "diteliti") {
      style = `penwidth=2.5, style=solid`;
    } else {
      style = `style=dashed, color="#999", fontcolor="#555"`;
    }
    lines.push(`  "${dotEscape(n.label)}" [${style}, ${id}];`);
  }
  for (const e of parsed.edges) {
    const attrs = e.type === "menghambat"
      ? 'color="#2c5fa8", arrowhead=diamond'
      : 'color="#c0392b"';
    lines.push(`  "${dotEscape(e.from)}" -> "${dotEscape(e.to)}" [${attrs}];`);
  }
  lines.push("}");
  return lines.join("\n");
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `node --test tests/js/dsl.test.mjs`
Expected: PASS (all)

- [ ] **Step 5: Commit**

```bash
git add app/web/static/new/dsl.js tests/js/dsl.test.mjs
git commit -m "feat(ui): dsl.js compiler (parseDSL/dslToDot/slug) + tests"
```

---

### Task 7: `framework.js` view + viz.js loader + 5th tab + CSS

**Files:**
- Modify: `app/web/templates/new.html` (add viz.js script after `new.html:50`)
- Create: `app/web/static/new/framework.js`
- Modify: `app/web/static/new/workspace.js` (add tab button + panel + mount)
- Modify: `app/web/static/new/new.css` (badge/error styles)

This task is DOM/manual-verify (per spec §9 "Manual"). No automated JS test for `framework.js`; the compiler it depends on is already covered by Task 6.

- [ ] **Step 1: Add viz.js (Graphviz WASM) to `new.html`**

In `app/web/templates/new.html`, add after the markmap autoloader line (`new.html:50`):

```html
<script src="https://cdn.jsdelivr.net/npm/@viz-js/viz@3.2.4/lib/viz-standalone.js"></script>
```

- [ ] **Step 2: Create `framework.js`**

Create `app/web/static/new/framework.js`:

```javascript
// Kerangka teori tab: title input -> confirm variables -> build grounded graph
// -> render SVG (viz.js) -> edit DSL -> source-badge overlay -> export PNG.
// DOM view, verified manually. Pure compiler lives in dsl.js (unit-tested).
import { escapeHtml, getJSON, postJSON, friendlyError } from "./api.js";
import { parseDSL, dslToDot, slug } from "./dsl.js";

let _vizPromise = null;
function getViz() {
  // viz.js (window.Viz) is loaded async from CDN; retry once if not ready.
  if (_vizPromise) return _vizPromise;
  _vizPromise = new Promise((resolve, reject) => {
    const tryLoad = (attempt) => {
      if (window.Viz && window.Viz.instance) {
        window.Viz.instance().then(resolve).catch(reject);
      } else if (attempt < 20) {
        setTimeout(() => tryLoad(attempt + 1), 250);
      } else {
        reject(new Error("mesin diagram belum siap"));
      }
    };
    tryLoad(0);
  });
  return _vizPromise;
}

export function mountFramework(panel, pid, deps = {}) {
  let citations = {};
  let lastSvg = "";

  panel.innerHTML = `
    <div class="kt">
      <div class="kt-setup">
        <input id="kt-title" type="text" placeholder="Tempel judul penelitian…" />
        <button class="df-btn" id="kt-parse" type="button" disabled>Parse judul</button>
        <div id="kt-vars"></div>
        <button class="df-btn" id="kt-build" type="button" hidden>Bangun kerangka</button>
      </div>
      <div class="kt-main" hidden>
        <div class="kt-diagram" id="kt-diagram"></div>
        <div class="kt-side">
          <textarea id="kt-dsl" spellcheck="false" placeholder="DSL kerangka…"></textarea>
          <div class="kt-actions">
            <button class="df-btn" id="kt-render" type="button">Render ulang</button>
            <button class="df-btn ghost" id="kt-png" type="button" disabled>⬇ PNG</button>
            <button class="df-btn ghost" id="kt-copy" type="button">Salin DSL</button>
          </div>
          <div class="kt-errors" id="kt-errors"></div>
          <div class="kt-sources" id="kt-sources"></div>
        </div>
      </div>
    </div>`;

  const titleEl = panel.querySelector("#kt-title");
  const parseBtn = panel.querySelector("#kt-parse");
  const varsEl = panel.querySelector("#kt-vars");
  const buildBtn = panel.querySelector("#kt-build");
  const mainEl = panel.querySelector(".kt-main");
  const diagramEl = panel.querySelector("#kt-diagram");
  const dslEl = panel.querySelector("#kt-dsl");
  const errEl = panel.querySelector("#kt-errors");
  const srcEl = panel.querySelector("#kt-sources");
  const pngBtn = panel.querySelector("#kt-png");

  titleEl.addEventListener("input", () => { parseBtn.disabled = !titleEl.value.trim(); });

  // ----- Parse title -> variable confirmation checklist -----
  parseBtn.addEventListener("click", async () => {
    parseBtn.disabled = true;
    varsEl.textContent = "Mengurai judul…";
    try {
      const res = await postJSON(`/projects/${pid}/framework/parse-title`,
        { title: titleEl.value.trim() });
      renderVarConfirm(res.variables || { bebas: [], terikat: "", populasi: "" });
    } catch (e) {
      varsEl.textContent = friendlyError(e);
    } finally {
      parseBtn.disabled = !titleEl.value.trim();
    }
  });

  function renderVarConfirm(v) {
    const bebas = v.bebas || [];
    varsEl.innerHTML =
      `<div class="kt-vargroup"><div class="side-label">Variabel bebas</div>` +
      bebas.map((b, i) =>
        `<label><input type="checkbox" data-bebas="${i}" checked> ${escapeHtml(b)}</label>`).join("") +
      `</div>` +
      `<label class="kt-field">Terikat <input id="kt-terikat" value="${escapeHtml(v.terikat || "")}"></label>` +
      `<label class="kt-field">Populasi <input id="kt-populasi" value="${escapeHtml(v.populasi || "")}"></label>`;
    varsEl._bebas = bebas;
    buildBtn.hidden = false;
  }

  // ----- Build framework -----
  buildBtn.addEventListener("click", async () => {
    const bebas = (varsEl._bebas || []).filter((_, i) =>
      varsEl.querySelector(`[data-bebas="${i}"]`)?.checked);
    const terikat = panel.querySelector("#kt-terikat")?.value.trim() || "";
    const populasi = panel.querySelector("#kt-populasi")?.value.trim() || "";
    buildBtn.disabled = true;
    buildBtn.textContent = "Menyusun kerangka…";
    try {
      const res = await postJSON(`/projects/${pid}/framework`, {
        variables: { bebas, terikat, populasi },
        title: titleEl.value.trim(),
      });
      citations = res.citations || {};
      dslEl.value = res.dsl || "";
      mainEl.hidden = false;
      await renderDsl();
    } catch (e) {
      errEl.textContent = friendlyError(e);
    } finally {
      buildBtn.disabled = false;
      buildBtn.textContent = "Bangun kerangka";
    }
  });

  // ----- Render DSL -> SVG (debounced on edit) -----
  let renderTimer = null;
  dslEl.addEventListener("input", () => {
    clearTimeout(renderTimer);
    renderTimer = setTimeout(renderDsl, 400);
  });
  panel.querySelector("#kt-render").addEventListener("click", renderDsl);

  async function renderDsl() {
    const parsed = parseDSL(dslEl.value);
    if (parsed.errors.length) {
      errEl.innerHTML = `<div class="side-label">Kesalahan DSL</div>` +
        parsed.errors.map(e =>
          `<div class="kt-err">baris ${e.line}, kol ${e.col}: ${escapeHtml(e.msg)}</div>`).join("");
      return; // keep the last good SVG
    }
    errEl.textContent = "";
    const dot = dslToDot(parsed, citations);
    let viz;
    try {
      viz = await getViz();
    } catch (e) {
      diagramEl.innerHTML = `<p class="gap">Render diagram perlu koneksi pertama kali.</p>`;
      return;
    }
    const svg = viz.renderSVGElement(dot);
    diagramEl.innerHTML = "";
    diagramEl.appendChild(svg);
    lastSvg = diagramEl.innerHTML;
    pngBtn.disabled = false;
    overlayBadges(parsed);
    renderSources(parsed);
  }

  // ----- Source badges over rendered nodes -----
  function overlayBadges(parsed) {
    for (const n of parsed.nodes) {
      const cit = citations[n.label];
      if (!cit) continue;
      const g = diagramEl.querySelector(`#node-${cssEscape(slug(n.label))}`);
      if (!g) continue;
      const badge = document.createElement("span");
      badge.className = "kt-badge " +
        (cit.src === "korpus" ? "korpus"
          : cit.status === "tak_terverifikasi" ? "tak" : "perlu");
      badge.textContent = cit.src === "korpus" ? "📄" : "🌐";
      badge.title = badgeTitle(cit);
      if (cit.src === "korpus" && cit.doc_id) {
        badge.style.cursor = "pointer";
        badge.addEventListener("click", () =>
          window.open(`/viewer?doc=${cit.doc_id}#page=${cit.page}`, "_blank"));
      }
      g.appendChild(badge);
    }
  }

  function badgeTitle(cit) {
    if (cit.src === "korpus") return `${cit.title || ""} (hlm ${cit.page})`;
    if (cit.ref) {
      const r = cit.ref;
      return `${r.title || ""} — ${(r.authors || []).join(", ")} (${r.year || "?"})` +
        (r.doi ? `\n${r.url || r.doi}` : "");
    }
    return "sumber tak ditemukan — perlu verifikasi";
  }

  function renderSources(parsed) {
    const items = parsed.nodes.map(n => [n.label, citations[n.label]]).filter(x => x[1]);
    if (!items.length) { srcEl.innerHTML = ""; return; }
    srcEl.innerHTML = `<div class="side-label">Sumber</div>` + items.map(([label, cit]) => {
      if (cit.src === "korpus") {
        return `<div class="kt-src korpus">📄 <b>${escapeHtml(label)}</b> — ${escapeHtml(cit.title || "")} (hlm ${cit.page})</div>`;
      }
      const tag = cit.status === "tak_terverifikasi"
        ? `<span class="kt-tag tak">sumber tak ditemukan</span>`
        : `<span class="kt-tag perlu">perlu verifikasi</span>`;
      const ref = cit.ref ? ` — ${escapeHtml(cit.ref.title || "")} (${cit.ref.year || "?"})` : "";
      return `<div class="kt-src eksternal">🌐 <b>${escapeHtml(label)}</b>${ref} ${tag}</div>`;
    }).join("");
  }

  // ----- Export PNG -----
  pngBtn.addEventListener("click", async () => {
    const svg = diagramEl.querySelector("svg");
    if (!svg) return;
    try { await document.fonts.ready; } catch (_) {}
    const xml = new XMLSerializer().serializeToString(svg);
    const img = new Image();
    const blobUrl = URL.createObjectURL(new Blob([xml], { type: "image/svg+xml" }));
    img.onload = () => {
      const canvas = document.createElement("canvas");
      canvas.width = img.width || svg.clientWidth || 800;
      canvas.height = img.height || svg.clientHeight || 600;
      const ctx = canvas.getContext("2d");
      ctx.fillStyle = "#fff";
      ctx.fillRect(0, 0, canvas.width, canvas.height);
      ctx.drawImage(img, 0, 0);
      URL.revokeObjectURL(blobUrl);
      canvas.toBlob(b => {
        const a = document.createElement("a");
        a.href = URL.createObjectURL(b);
        a.download = `kerangka-${pid}.png`;
        a.click();
        URL.revokeObjectURL(a.href);
      }, "image/png");
    };
    img.src = blobUrl;
  });

  panel.querySelector("#kt-copy").addEventListener("click", () => {
    navigator.clipboard?.writeText(dslEl.value);
  });

  // CSS.escape fallback for older engines.
  function cssEscape(s) {
    return window.CSS && CSS.escape ? CSS.escape(s) : String(s).replace(/[^A-Za-z0-9_-]/g, "\\$&");
  }

  // ----- On mount: load persisted framework, render if present -----
  getJSON(`/projects/${pid}/framework`).then(res => {
    if (res.title) titleEl.value = res.title;
    parseBtn.disabled = !titleEl.value.trim();
    if (res.dsl) {
      citations = res.citations || {};
      dslEl.value = res.dsl;
      mainEl.hidden = false;
      renderDsl();
    }
  }).catch(() => {});

  return { refresh: () => getJSON(`/projects/${pid}/framework`) };
}
```

- [ ] **Step 3: Wire the 5th tab into `workspace.js`**

In `app/web/static/new/workspace.js`, add the import (after `workspace.js:5`):

```javascript
import { mountFramework } from "./framework.js";
```

Add the tab button in the `.ws-tabs` block (after the Matriks tab at `workspace.js:44`):

```javascript
          <button class="tab" data-tab="kerangka" type="button">🧭 Kerangka</button>
```

Add the panel `<div>` after the matriks panel (`workspace.js:50`):

```javascript
      <div class="ws-panel" data-panel="kerangka" hidden></div>
```

Mount it after the Matriks block (after `workspace.js:174`, before `newConv();`):

```javascript
  // ----- Kerangka (theoretical framework diagram) -----
  mountFramework(screen.querySelector('[data-panel="kerangka"]'), pid);
```

- [ ] **Step 4: Add CSS for badges, errors, layout**

Append to `app/web/static/new/new.css`:

```css
/* ---- Kerangka teori tab ---- */
.kt-setup { padding: 16px 20px; display: flex; flex-wrap: wrap; gap: 10px; align-items: center; }
.kt-setup #kt-title { flex: 1 1 360px; padding: 8px 12px; border: 1px solid var(--line, #e2e8f0); border-radius: 8px; font: inherit; }
.kt-vargroup { width: 100%; margin: 8px 0; }
.kt-vargroup label, .kt-field { display: block; margin: 4px 0; }
.kt-field input { margin-left: 6px; padding: 4px 8px; border: 1px solid var(--line, #e2e8f0); border-radius: 6px; }
.kt-main { display: grid; grid-template-columns: 1fr 360px; gap: 12px; padding: 0 20px 20px; }
.kt-diagram { overflow: auto; border: 1px solid var(--line, #e2e8f0); border-radius: 8px; min-height: 320px; position: relative; background: #fff; }
.kt-diagram svg { max-width: none; }
.kt-side { display: flex; flex-direction: column; gap: 8px; }
.kt-side #kt-dsl { width: 100%; min-height: 240px; font-family: "Fira Code", monospace; font-size: 13px; border: 1px solid var(--line, #e2e8f0); border-radius: 8px; padding: 10px; resize: vertical; }
.kt-actions { display: flex; gap: 8px; flex-wrap: wrap; }
.kt-err { color: #c0392b; font-size: 13px; padding: 2px 0; }
.kt-src { font-size: 13px; padding: 4px 0; border-bottom: 1px solid var(--line, #f1f5f9); }
.kt-tag { font-size: 11px; padding: 1px 6px; border-radius: 10px; }
.kt-tag.perlu { background: #fef3c7; color: #92400e; }       /* yellow: needs verify */
.kt-tag.tak { background: #fee2e2; color: #991b1b; }         /* red: not found */
.kt-badge { display: inline-block; margin-left: 2px; font-size: 13px; }
.kt-badge.tak { filter: grayscale(0); }
```

- [ ] **Step 5: Verify the existing JS suite still passes**

Run: `node --test tests/js/*.test.mjs`
Expected: PASS (all, including the new `dsl.test.mjs`)

- [ ] **Step 6: Manual smoke (per spec §9)**

Run: `scripts/run.sh`, open `http://127.0.0.1:8765`, open a naskah with ≥1 paper, click the **🧭 Kerangka** tab. Confirm:
- Paste a title → "Parse judul" → variable checklist appears.
- "Bangun kerangka" → diagram renders; bold `[diteliti]` boxes, dashed `[latar]`, red/blue arrows.
- 📄 badge click opens the PDF page; 🌐 badge hover shows the Crossref ref.
- Edit the DSL textarea → debounced re-render; introduce a bad line → error list shows, last SVG stays.
- "⬇ PNG" downloads `kerangka-<pid>.png`.

- [ ] **Step 7: Commit**

```bash
git add app/web/templates/new.html app/web/static/new/framework.js app/web/static/new/workspace.js app/web/static/new/new.css
git commit -m "feat(ui): kerangka tab — viz.js render, badges, PNG export"
```

---

### Task 8: Documentation + full-suite gate

**Files:**
- Modify: `CLAUDE.md`

- [ ] **Step 1: Document the feature in `CLAUDE.md`**

In the **Web** section's grid-style bullet (the one listing tabs `Tanya, Paper, Draft, Matriks`), add `Kerangka` and a one-line description. In the **Projects** section, add a sentence:

```markdown
A project may also hold one **kerangka teori** (theoretical-framework diagram):
`app/rag/framework.py` builds a grounded causal graph from a research title —
corpus nodes cited to doc_id+page, external nodes verified via Crossref — stored
as an editable DSL in `project_framework` (one row per project). The browser
compiles DSL → DOT (`dsl.js`) → SVG (viz.js) and exports PNG (`framework.js`).
```

- [ ] **Step 2: Run the full Python suite**

Run: `python -m pytest tests/ -v`
Expected: PASS (all green, including `test_framework.py`)

- [ ] **Step 3: Run the full JS suite**

Run: `node --test tests/js/*.test.mjs`
Expected: PASS (all green, including `dsl.test.mjs`)

- [ ] **Step 4: Commit**

```bash
git add CLAUDE.md
git commit -m "docs: kerangka teori (Web + Projects sections)"
```

---

## Acceptance (spec §11)

- Paste a sepsis title → confirm 4 variables → "Bangun kerangka" → layered diagram: `[diteliti]` bold boxes on the backbone, dashed `[latar]` at the margins, red/blue arrows, 📄 badge (click → PDF page) and 🌐 yellow badge (hover → Crossref ref).
- Edit DSL (add node/edge) → "Render ulang" → diagram updates; DSL errors show without breaking the view.
- PNG export produces a thesis-ready image.
- A node with no corpus support and no Crossref hit shows a red "sumber tak ditemukan" tag — not silently dropped.
- `/tools` and other features unchanged; full suite green.
