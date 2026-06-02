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
  rag/       # retrieval, generation, citation
  web/       # routes, static, templates
data/        # sqlite-vec db file
scripts/     # sync, run, launchd
tests/
```
