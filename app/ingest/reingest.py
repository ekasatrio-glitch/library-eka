"""One-time re-ingest migration (Phase D2): re-extract the whole corpus with the
current extractor (Docling), rebuild chunks + vectors + FTS5. Embeddings stay
nomic (dim 768). `documents` rows (path, hash, metadata) are preserved.

Idempotent: a `meta` flag records the migration so it isn't repeated by accident.
If the corpus was never ingested, this is a no-op (future ingests use Docling).
"""

import argparse
import sys
from pathlib import Path
from typing import Callable, Optional

from app.core.db import (
    delete_chunks,
    get_meta,
    init_db,
    insert_chunk,
    set_document_status,
    set_meta,
)
from app.ingest.chunker import chunk_pages
from app.ingest.embedder import embed_texts
from app.ingest.extractor import extract_pages

MIGRATION_KEY = "extractor_migration"
MIGRATION_TAG = "docling-v1"


def reingest_all(
    conn,
    force: bool = False,
    embed_fn: Callable = embed_texts,
    progress: Optional[Callable] = None,
) -> dict:
    """Re-extract + re-chunk + re-embed every document. Returns a summary dict."""
    if not force and get_meta(conn, MIGRATION_KEY) == MIGRATION_TAG:
        return {"status": "skip", "reason": "already migrated", "migrated": 0}

    rows = conn.execute("SELECT id, path FROM documents ORDER BY id").fetchall()
    migrated, missing, empty = 0, 0, 0
    for doc_id, path in rows:
        p = Path(path)
        if not p.exists():
            missing += 1
            set_document_status(conn, doc_id, "missing")
            continue
        try:
            pages = extract_pages(p)
            delete_chunks(conn, doc_id)  # triggers also clear FTS5 rows
            chunks = chunk_pages(pages)
            if not chunks:
                empty += 1
                set_document_status(conn, doc_id, "empty")
            else:
                embs = embed_fn([c.text for c in chunks])
                for c, emb in zip(chunks, embs):
                    insert_chunk(conn, doc_id, c.page_start, c.page_end, c.text, emb)
                set_document_status(conn, doc_id, "done")
                migrated += 1
        except Exception as e:  # keep going; one bad PDF shouldn't stop the batch
            set_document_status(conn, doc_id, "error")
            print(f"[reingest] error on doc {doc_id} ({p.name}): {e}", file=sys.stderr)
        if progress:
            progress(migrated + missing + empty, len(rows), doc_id)

    set_meta(conn, MIGRATION_KEY, MIGRATION_TAG)
    return {
        "status": "done",
        "total": len(rows),
        "migrated": migrated,
        "missing": missing,
        "empty": empty,
    }


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="Re-ingest corpus with the Docling extractor")
    p.add_argument("--all", action="store_true", help="re-extract all documents")
    p.add_argument("--force", action="store_true", help="run even if already migrated")
    p.add_argument("--db", default=None, help="DB path override")
    a = p.parse_args(argv)
    if not a.all:
        p.error("specify --all")

    conn = init_db(a.db)
    try:
        total = conn.execute("SELECT COUNT(*) FROM documents").fetchone()[0]
        print(f"[reingest] {total} documents to re-extract with Docling...", file=sys.stderr)

        def prog(done, n, doc_id):
            print(f"[reingest] {done}/{n} (doc {doc_id})", file=sys.stderr)

        res = reingest_all(conn, force=a.force, progress=prog)
        print(f"[reingest] {res}", file=sys.stderr)
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
