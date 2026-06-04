"""Re-embed the whole corpus with a different embedding model (e.g. bge-m3).

WARNING: changing the embedding model forces a full re-embed because the vector
dimension differs (nomic 768 -> bge-m3 1024). Document text (`documents`,
`chunks`) is preserved; only the `vec_chunks` index is rebuilt.

Idempotent: records the active model/dim in the `meta` table. Re-running with the
same target (and a complete index) is a no-op unless `--force` is given.

The query side must use the SAME model — after migrating, set in .env:
    EMBED_MODEL=bge-m3
    EMBED_DIM=1024
and ensure the VPS runs bge-m3 too (see README "Migrasi embedding bge-m3").

Usage:
    python -m app.ingest.reembed --model bge-m3 --dim 1024
    python -m app.ingest.reembed --model bge-m3 --dim 1024 --force
"""

import argparse
import sys
from typing import Callable, Optional

from app.core.db import (
    get_meta,
    init_db,
    serialize_vec,
    set_meta,
)
from app.ingest.embedder import embed_texts


def _recreate_vec_table(conn, dim: int) -> None:
    """vec0 dimension is fixed at creation, so a dim change means drop + recreate."""
    conn.execute("DROP TABLE IF EXISTS vec_chunks")
    conn.execute(
        f"CREATE VIRTUAL TABLE vec_chunks USING vec0("
        f"chunk_id INTEGER PRIMARY KEY, embedding FLOAT[{dim}])"
    )
    conn.commit()


def reembed(
    model: str,
    dim: int,
    batch: int = 32,
    db_path: Optional[str] = None,
    base_url: Optional[str] = None,
    force: bool = False,
    progress=None,
) -> int:
    conn = init_db(db_path)  # ensure schema (meta table, FTS) exists, even on legacy DBs
    try:
        n_chunks = conn.execute("SELECT COUNT(*) FROM chunks").fetchone()[0]
        n_vec = conn.execute("SELECT COUNT(*) FROM vec_chunks").fetchone()[0]
        cur_model = get_meta(conn, "embed_model")
        cur_dim = get_meta(conn, "embed_dim")

        if (
            not force
            and cur_model == model
            and str(cur_dim) == str(dim)
            and n_vec == n_chunks
        ):
            print(
                f"[reembed] already on {model} (dim {dim}), {n_vec}/{n_chunks} vectors — skip.",
                file=sys.stderr,
            )
            return 0

        if n_chunks == 0:
            print("[reembed] no chunks to embed.", file=sys.stderr)
            return 0

        print(
            f"[reembed] migrating {n_chunks} chunks -> {model} (dim {dim}), batch={batch}",
            file=sys.stderr,
        )
        _recreate_vec_table(conn, dim)

        rows = conn.execute("SELECT id, text FROM chunks ORDER BY id").fetchall()
        total = len(rows)
        done = 0
        for i in range(0, total, batch):
            part = rows[i : i + batch]
            embs = embed_texts([t for _, t in part], model=model, base_url=base_url)
            for (cid, _), emb in zip(part, embs):
                if len(emb) != dim:
                    raise ValueError(
                        f"model '{model}' returned dim {len(emb)}, expected {dim}; "
                        f"check --dim matches the model"
                    )
                conn.execute(
                    "INSERT INTO vec_chunks (chunk_id, embedding) VALUES (?, ?)",
                    (cid, serialize_vec(emb)),
                )
            conn.commit()
            done += len(part)
            print(f"[reembed] {done}/{total}", file=sys.stderr)
            if progress:
                progress(done, total)

        set_meta(conn, "embed_model", model)
        set_meta(conn, "embed_dim", str(dim))
        print(f"[reembed] done. {done} vectors written with {model}.", file=sys.stderr)
        return 0
    finally:
        conn.close()


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="Re-embed corpus with a new embedding model")
    p.add_argument("--model", default="bge-m3", help="Ollama embedding model (default: bge-m3)")
    p.add_argument("--dim", type=int, default=1024, help="Embedding dimension (default: 1024)")
    p.add_argument("--batch", type=int, default=32, help="Embed batch size")
    p.add_argument("--db", default=None, help="DB path override")
    p.add_argument("--base-url", default=None, help="Ollama base URL override")
    p.add_argument("--force", action="store_true", help="Re-embed even if already migrated")
    a = p.parse_args(argv)
    return reembed(a.model, a.dim, batch=a.batch, db_path=a.db, base_url=a.base_url, force=a.force)


if __name__ == "__main__":
    raise SystemExit(main())
