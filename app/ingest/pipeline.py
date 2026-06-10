import argparse
import hashlib
import sys
from pathlib import Path
from typing import Iterable, List

from app.core.db import (
    init_db,
    document_exists,
    upsert_document,
    insert_chunk,
    delete_chunks,
    set_document_status,
)
from app.ingest.chunker import chunk_pages
from app.ingest.embedder import embed_texts, EmbeddingError
from app.ingest.extractor import extract_pages, first_page_text
from app.ingest.metadata import guess_metadata


def file_hash(path: Path, chunk_size: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for blk in iter(lambda: f.read(chunk_size), b""):
            h.update(blk)
    return h.hexdigest()


def find_pdfs(roots: Iterable[str | Path]) -> List[Path]:
    out: List[Path] = []
    for r in roots:
        rp = Path(r)
        if rp.is_file() and rp.suffix.lower() == ".pdf":
            out.append(rp)
        elif rp.is_dir():
            out.extend(sorted(rp.rglob("*.pdf")))
    return out


def ingest_pdf(pdf_path: str | Path, conn=None, progress=None) -> tuple[bool, str]:
    """Ingest single PDF. Returns (processed, reason).

    progress(stage, done, total) is called with stage "membaca" (extraction
    started) then "mengindeks" (per-batch embedding) — drives the upload UI bar.
    """
    def report(stage: str, done: int, total: int) -> None:
        if progress:
            progress(stage, done, total)

    path = Path(pdf_path).resolve()
    if not path.exists():
        return False, f"missing: {path}"

    own_conn = conn is None
    if own_conn:
        conn = init_db()

    try:
        h = file_hash(path)
        if document_exists(conn, h) is not None:
            return False, "skip (already ingested)"

        report("membaca", 0, 0)
        pages = extract_pages(path)
        if not pages:
            return False, "no pages"

        fp_text = pages[0][1] if pages else ""
        title, authors, year = guess_metadata(fp_text, path)

        doc_id = upsert_document(
            conn,
            path=str(path),
            content_hash=h,
            title=title,
            authors=authors,
            year=year,
            folder=str(path.parent),
            status="processing",
        )

        delete_chunks(conn, doc_id)  # clear stale chunks on re-ingest (hash changed)
        chunks = chunk_pages(pages)
        if not chunks:
            set_document_status(conn, doc_id, "empty")
            return False, "no chunks"

        texts = [c.text for c in chunks]
        report("mengindeks", 0, len(texts))
        embeddings: List[list] = []
        BATCH = 8
        for i in range(0, len(texts), BATCH):
            embeddings.extend(embed_texts(texts[i:i + BATCH]))
            report("mengindeks", min(i + BATCH, len(texts)), len(texts))
        for c, emb in zip(chunks, embeddings):
            insert_chunk(conn, doc_id, c.page_start, c.page_end, c.text, emb)

        set_document_status(conn, doc_id, "done")
        return True, f"ingested ({len(chunks)} chunks)"
    except EmbeddingError as e:
        return False, f"embed error: {e}"
    finally:
        if own_conn:
            conn.close()


def main(argv=None):
    p = argparse.ArgumentParser(description="Ingest PDFs into library-eka DB")
    p.add_argument("paths", nargs="+", help="Files or folders to scan")
    args = p.parse_args(argv)

    conn = init_db()
    pdfs = find_pdfs(args.paths)
    print(f"Found {len(pdfs)} PDFs", file=sys.stderr)
    ok = skip = err = 0
    for pdf in pdfs:
        processed, reason = ingest_pdf(pdf, conn=conn)
        if processed:
            ok += 1
            print(f"[OK]   {pdf}: {reason}")
        elif reason.startswith("skip"):
            skip += 1
            print(f"[SKIP] {pdf}: {reason}")
        else:
            err += 1
            print(f"[ERR]  {pdf}: {reason}", file=sys.stderr)
    conn.close()
    print(f"\nDone. ok={ok} skip={skip} err={err}", file=sys.stderr)
    return 0 if err == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
