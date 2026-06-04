# library-eka

Personal local RAG for scientific corpus. Permanent + private library, precise citations (click-to-page PDF), cross-document synthesis, academic paragraphs, mindmap. Runs on MacBook M4 16 GB. Sync to VPS for remote access via Hermes (Telegram).

## Stack

- Backend: Python + FastAPI
- PDF extraction: PyMuPDF (fitz)
- Storage: SQLite + sqlite-vec (registry + metadata + vectors in one file)
- Embedding: Ollama `bge-m3` (1024-d) by default; `nomic-embed-text` (768-d) supported
- Generation: DeepSeek API (OpenAI-compatible); Jatevo fallback
- Auto-ingest: watchdog folder watcher (debounce + queue + startup scan)
- Web: FastAPI + PDF.js viewer + chat UI
- Mindmap: MarkMap
- macOS persistence: LaunchAgent
- Remote: rsync DB to VPS → Hermes Telegram handler

## Quickstart

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# edit .env: API keys + WATCH_FOLDERS
```

Start Ollama + pull embedder (once):

```bash
ollama pull nomic-embed-text
```

### Run the stack

```bash
scripts/run.sh
# Web: http://127.0.0.1:8765
# Watcher logs: logs/watcher.log
```

Manual ingest (one-off):

```bash
python -m app.ingest.pipeline /path/to/pdf_folder
```

### Persist watcher on login (macOS)

```bash
scripts/install_launchagent.sh
```

Stops/starts via `launchctl unload|load -w ~/Library/LaunchAgents/com.eka.library.watcher.plist`.

### Endpoints

| Method | Path             | Description                                  |
|--------|------------------|----------------------------------------------|
| GET    | `/`              | Chat / Draft / Mindmap / Library UI          |
| GET    | `/viewer`        | PDF.js viewer (`?doc=<id>#page=<n>`)         |
| POST   | `/ask`           | RAG question → answer + grounded citations   |
| POST   | `/draft`         | Academic paragraph (Vancouver / APA)         |
| POST   | `/mindmap`       | MarkMap markdown (multi-query retrieval)     |
| GET    | `/library`       | Indexed docs + folder/year/author filters    |
| GET    | `/pdf/{id}`      | Stream the source PDF                        |

### Extraction (Docling)

PDF text extraction uses **Docling** by default (`EXTRACTOR=docling`): correct
multi-column reading order, tables exported as inline **markdown** (so quantitative
data is indexed and can feed matrix fields), and optional **OCR** for scanned PDFs
(`OCR=true`, slower). Per-page provenance is preserved so chunk `page_start/page_end`
— and click-to-page citations — stay accurate. The extractor output interface is
unchanged (`list[(page_no, text)]`), so chunker/embedder/registry/FTS5 are untouched.
First Docling run downloads layout/table models (hundreds of MB). On any Docling
error it falls back to `pymupdf`. Embeddings remain **nomic** (dim 768).

Migrate an existing corpus to Docling extraction (one-time, embeddings retained):

```bash
python -m app.ingest.reingest --all        # idempotent; --force to re-run
```

### Retrieval (hybrid + rerank)

`app.rag.retriever.search()` runs **hybrid retrieval**: dense (sqlite-vec KNN) and
sparse (SQLite **FTS5 / BM25**) candidates fused with **Reciprocal Rank Fusion**
(RRF, k=60), then sharpened by a cross-encoder **reranker** over the small fused
pool. Metadata filters (year/folder/author/doc) apply to both paths.

Reranker is selected via `.env`:

| `RERANKER` | Backend                | Notes                                  |
|------------|------------------------|----------------------------------------|
| `flashrank`| tiny ONNX cross-encoder| default, ms-level on CPU               |
| `bge`      | `bge-reranker-v2-m3`   | multilingual ID/EN, higher accuracy; needs `pip install sentence-transformers` |
| `none`     | passthrough            | keep RRF order                         |

If the configured reranker's dependency is missing, retrieval falls back to RRF
order (logged) — it never hard-fails. `RERANK_POOL` (default 40) sizes the
candidate set fed to the reranker.

FTS5 stays in sync with `chunks` via triggers; `init_db()` backfills the index
for pre-existing rows (drift detected via the `_docsize` shadow table).

### Projects, synthesis matrix, rename (Phase 10–14)

- **Projects/workspaces** (`/projects`): the corpus stays global; a project references
  a subset of documents (no duplication, no re-embed). Import from the library or drop
  a new PDF (ingested once, deduped by hash).
- **Scoped chat** (`POST /projects/{id}/ask`): retrieval defaults to project papers;
  `expand` widens to the whole library. A discovery `nudge` surfaces relevant library
  papers not yet in the project.
- **Synthesis matrix** (`POST /projects/{id}/matrix`): per-paper structured extraction
  with auto-detected schema (`empiris` | `review` | `meta-analisis`), strictly grounded —
  gaps are written explicitly (`tidak disebutkan` / `tidak dilaporkan`), weaknesses split
  into author-stated vs. `saran — perlu verifikasi`, supporting papers from the corpus only,
  notes are `(draft)`. Views: `matrix` | `linimasa` | `tema`.
- **Export** (`/projects/{id}/matrix/export.xlsx|csv`): XLSX colors tag cells by the
  project **codebook**; bootstrap the codebook from an old sheet/CSV (`closed coding`).
- **Rename by title** (`/rename/preview` → `/rename/apply` → `/rename/undo`): semantic
  title extraction (LLM + optional Crossref, **no regex**), registry-safe (file move +
  `documents.path` update in one transaction, hash unchanged → no re-embed), collision
  suffixes, full undo log.

### Tests

```bash
python -m pytest tests/ -v
```

## Layout

```
app/
  core/      # db, config
  ingest/    # extractor, chunker, embedder, watcher
  rag/       # retrieval, generation, citation, drafting, mindmap
  web/       # routes, static, templates
data/        # sqlite-vec db file
scripts/     # sync, run, launchd
tests/
```

## VPS (sync + Hermes)

### Sync DB to VPS

Set in `.env`:

```
VPS_USER=...
VPS_HOST=...
VPS_PATH=/srv/library-eka/library.db.snapshot
VPS_SSH_PORT=22
```

Run after a batch:

```bash
scripts/sync_to_vps.sh
```

The script makes a consistent snapshot (`VACUUM INTO`) under a file lock, then `rsync` it over SSH. Trigger automatically from the ingestion worker once a batch is idle.

### VPS setup

1. Install **sqlite-vec** extension on the VPS Python venv:

   ```bash
   pip install sqlite-vec
   ```

2. Run **`nomic-embed-text` via Ollama** on the VPS — embed dimension MUST match the laptop (768) or vector search fails:

   ```bash
   curl -fsSL https://ollama.com/install.sh | sh
   ollama pull nomic-embed-text
   ollama serve  # systemd unit recommended
   ```

3. **Hermes handler** (Telegram bot):
   - Receive question → call `app.ingest.embedder.embed_one(q)` (Ollama on VPS) → `app.rag.retriever.search(...)` against the synced DB → generate via **Jatevo** (`LLM_PROVIDER=jatevo`) → reply.
   - Short answer inline; long answer attach `.md` file with citations.
   - Use `app.rag.ask.ask()` directly for end-to-end RAG.

4. Never rsync while the DB is being written. The provided script uses `VACUUM INTO` + flock; the worker should call `sync_to_vps.sh` only when its queue is idle.

### Migrasi embedding bge-m3 (Phase 4.4, opsional)

`bge-m3` lebih akurat + multilingual (ID/EN), tapi **memaksa re-embed seluruh
korpus** (dimensi 768 → 1024). Teks (`documents`, `chunks`) tetap; hanya
`vec_chunks` dibangun ulang. Skrip migrasi idempotent (mencatat model/dim di
tabel `meta`):

```bash
ollama pull bge-m3
python -m app.ingest.reembed --model bge-m3 --dim 1024   # tambah --force utk paksa
```

Lalu set di `.env` (Mac **dan** VPS):

```
EMBED_MODEL=bge-m3
EMBED_DIM=1024
```

⚠️ **Konsisten Mac ↔ VPS wajib.** Query di-embed dengan model yang sama dengan
indeks. Setelah migrasi, DB hasil sync berisi vektor 1024-d, jadi **VPS harus
menjalankan `ollama pull bge-m3`** dan memakai `EMBED_MODEL=bge-m3`/`EMBED_DIM=1024`.
Jika VPS terlalu kecil untuk bge-m3, **jangan** migrasi — tetap di `nomic-embed-text`
(768) agar dimensi cocok. Re-sync DB setelah re-embed selesai.
