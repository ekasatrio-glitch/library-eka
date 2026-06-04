# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

Personal local RAG system for a scientific PDF corpus: ingest → hybrid retrieval → grounded answers with click-to-page citations, academic drafting, synthesis matrix, mindmap. Runs locally (MacBook), syncs DB to a VPS for a Telegram bot (Hermes).

## Commands

```bash
source venv/bin/activate                 # always work inside the venv

python -m pytest tests/ -v               # full Python suite
python -m pytest tests/test_rag.py -v    # single file
python -m pytest tests/test_rag.py::test_name -v   # single test

node --test tests/js/*.test.mjs          # JS unit tests (Node 24 built-in, zero deps)
# Use the GLOB form, not `tests/js/` — Node 24 treats a bare dir path as a module to run.

scripts/run.sh                           # web (http://127.0.0.1:8765) + watcher (logs/watcher.log)
scripts/start.command                    # double-click launcher: Ollama + watcher + web + browser

python -m app.ingest.pipeline /path/to/pdfs        # manual ingest (idempotent, hash-deduped)
python -m app.ingest.reingest --all                # re-extract corpus (e.g. after switching to docling); --force to redo
python -m app.ingest.reembed --model bge-m3 --dim 1024   # embedding migration (rebuilds vec_chunks only)
scripts/sync_to_vps.sh                   # snapshot DB (VACUUM INTO + flock) → rsync to VPS
```

Tests force `EXTRACTOR=pymupdf` via an autouse fixture in `tests/conftest.py` (avoids Docling model downloads). Docling has its own opt-in test.

## Architecture

Everything lives in **one SQLite file** (`data/library.db`): registry (`documents`), text (`chunks`), vectors (`vec_chunks`, sqlite-vec), full-text (FTS5, trigger-synced to `chunks`), projects, synthesis matrix, codebook, migration bookkeeping (`meta`). Config is env-driven via `app/core/config.py` (loads `.env`).

### Ingest (`app/ingest/`)

`pipeline.ingest_pdf()` is the single entry point: sha256 hash → dedupe → `extractor.extract_pages()` → `chunker` → `embedder` (Ollama) → insert. The extractor interface is `list[(page_no, text)]` — Docling (default, reading order + tables-as-markdown + optional OCR, falls back to pymupdf on error) and pymupdf both honor it, so everything downstream is extractor-agnostic. Page provenance flows into chunk `page_start/page_end`, which powers click-to-page citations.

`watcher.py` (watchdog) auto-ingests `WATCH_FOLDERS` and `PROJECTS_DIR` subfolders (`<id>-<slug>` → auto-link to that project), with debounce + queue + startup scan. Runs as a separate process (`run.sh` backgrounds it; LaunchAgent for login persistence).

### Retrieval (`app/rag/retriever.py`)

Hybrid: dense (sqlite-vec KNN) + sparse (FTS5/BM25) fused with RRF (k=60), then cross-encoder rerank over the fused pool (`RERANK_POOL`, default 40). Reranker selected by `RERANKER` env: `flashrank` (default) | `bge` | `none`; missing dependency degrades to RRF order, never hard-fails. Metadata filters (year/folder/author/doc) apply to both paths.

### Generation (`app/rag/`)

`ask.py` is end-to-end RAG (retrieve → generate → cite). LLM via OpenAI-compatible API: DeepSeek default, Jatevo fallback (`config.llm_config()`). `drafting.py` (Vancouver/APA paragraphs), `mindmap.py` (MarkMap markdown, multi-query retrieval), `matrix.py` (per-paper structured extraction, auto-schema `empiris|review|meta-analisis`, strictly grounded — gaps written explicitly as `tidak disebutkan`).

`citation.py` flags each `Citation.cited` by parsing the markers the LLM actually emitted (`extract_cited_ns` + `mark_cited`): `[n]` for chat answers (`ask.py`), `(n)` for Vancouver drafts. Out-of-range numbers (e.g. a year `(2020)`) are ignored; if no valid marker is found, everything stays `cited=True` so the UI falls back to a single source list. The UI then splits sources into "cited" vs "Diambil, tidak dikutip". APA drafts have no numeric markers and stay all-cited.

### Web (`app/web/`)

FastAPI app in `app.py`; routes split into `routes.py` (ask/draft/mindmap/library/pdf/viewer + `/new`), `projects_routes.py` (scoped chat with `expand` + discovery nudge), `rename_routes.py`, `export.py` (XLSX/CSV with codebook coloring).

Two front-ends:
- **Legacy** `/` (`templates/index.html` + `static/app.js`, `static/app.css`) — all five tabs (chat/draft/mindmap/library/projects), PDF.js viewer, MarkMap.
- **Grid-style** `/new` (`templates/new.html` + `static/new/*`) — a parallel, restyled UI covering Chat + Projects only, with a first-visit splash (animated EKG). Native ES modules, no build step: `api.js` (fetch/escape — the only `fetch` site), `citations.js` (cite-pills + cited/uncited split), `history.js` (conversations in `localStorage`, not synced to VPS), `splash.js` (first-visit flag `libeka.splashSeen`), `chat.js`/`projects.js` (DOM views), `main.js` (entry: splash, nav, mounts). The four pure modules are DOM-free and unit-tested with `node:test`; `chat/projects/main` + CSS are verified manually. `/new` adds no backend state — it reuses existing endpoints. The two UIs are independent; don't let a `/new` change touch `/`.

Design tokens for `/new` live in `static/new/new.css` (`:root` vars: sky-blue `--brand:#0369A1`, Inter/Merriweather/Fira Code, `--accent:#D97706` Amber 600 reserved for the splash EKG only). See spec `docs/superpowers/specs/2026-06-04-grid-style-ui-design.md`.

### Projects

Corpus stays global; a project only references documents (`project_documents`) — no duplication, no re-embed. Imported PDFs deduped by hash.

### Rename (`app/ingest/rename.py`, `title.py`)

Semantic title extraction (LLM + optional Crossref, no regex). Registry-safe: file move + `documents.path` update in one transaction; hash unchanged → no re-embed. Full undo log.

## Invariants

- Embed dimension must match between index and query — and between Mac and VPS (`EMBED_MODEL`/`EMBED_DIM` consistent on both; default nomic-embed-text/768). Mismatch breaks vector search.
- Never rsync the live DB; only via `sync_to_vps.sh` (consistent snapshot under flock), and only when the ingest queue is idle.
- Chunk page provenance (`page_start/page_end`) must stay accurate — citations depend on it.
- Migrations (`reembed`, `reingest`) are idempotent, tracked in the `meta` table.
- UI language is partly Indonesian (matrix labels like `tidak disebutkan`, views `matrix|linimasa|tema`) — keep user-facing strings consistent.

## Environment

Requires Ollama running locally for embeddings (`ollama pull nomic-embed-text`). LLM keys in `.env` (see `.env.example`). First Docling run downloads layout/table models (hundreds of MB).
