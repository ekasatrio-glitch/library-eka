# library-eka

Personal local RAG for scientific corpus. Permanent + private library, precise citations (click-to-page PDF), cross-document synthesis, academic paragraphs, mindmap. Runs on MacBook M4 16 GB. Sync to VPS for remote access via Hermes (Telegram).

## Stack

- Backend: Python + FastAPI
- PDF extraction: PyMuPDF (fitz)
- Storage: SQLite + sqlite-vec (registry + metadata + vectors in one file)
- Embedding: Ollama `nomic-embed-text` (768-d)
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
